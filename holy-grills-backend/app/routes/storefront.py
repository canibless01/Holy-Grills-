"""
Storefront / CMS routes (D17) — corrected version produced by the audit.
Every change is tagged with its finding id (D17-Bxx / D17-Sxx) so it can be traced back to the audit log.
"""
import math
import os
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit

from flask import Blueprint, request, jsonify, g

from app.middleware.auth import (  # D17-B04 (validate_promo now requires login)
    require_auth, require_role, optional_auth,
    resolve_admin_write_campus, GLOBAL_SCOPE_MARKERS,
)
from app.middleware.rate_limit import rate_limit                                 # D17-B16: newsletter abuse guard
from app.constants import ADMIN_ROLES
from app.db import get_db, get_user_client, SupabaseError
from app.messages import MSG
from app.routes.events import _get_campus_id
from app.services import newsletter_service


from app.utils.logger import get_logger
from app.utils.tz import today_wat
from app.utils.schedule import override_window, resolve_date_override
from app.utils.validators import validate_email
from app.utils.upload_urls import is_cms_image_url

logger = get_logger(__name__)                                                    # D17-B09: module had no logging at all

storefront_bp = Blueprint("storefront", __name__)


def _active_gift_campaign(campus_id):
    if not campus_id or (getattr(g, 'user_id', None) and getattr(g, 'user_role', None) != 'student'):
        return None
    from app.services.gift_campaigns import read_config, features_ready
    config, _, _ = read_config(get_db(), campus_id)
    if not config.get('enabled') or not features_ready(get_db(), config): return None
    now = datetime.now(timezone.utc)
    if not datetime.fromisoformat(config['starts_at']) <= now < datetime.fromisoformat(config['ends_at']): return None
    # First-order/signup eligibility is confirmed privately when claiming. The
    # guest teaser advertises that audience; existing signed-in customers use
    # their earned Rewards receipts instead of an unconditional welcome banner.
    if getattr(g, 'user_id', None) and config['eligibility'] != 'everyone': return None
    return config


@storefront_bp.route('/gift-campaign', methods=['GET'])
@optional_auth
def public_gift_campaign():
    try: return jsonify({'campaign': _active_gift_campaign(_get_campus_id())}), 200
    except Exception: return jsonify({'error': MSG.GIFT_CAMPAIGN_UNAVAILABLE}), 503

try:
    from zoneinfo import ZoneInfo
    _WAT = ZoneInfo("Africa/Lagos")
except Exception:                                                                # tzdata missing -> fixed UTC+1 (WAT has no DST)
    _WAT = timezone(timedelta(hours=1))

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?$")
_SECTION_CONTENT_FIELDS = ("subtitle", "body", "image_url", "cta_text", "cta_url", "config")   # D17-B01
_SECTION_CONTENT_ALIASES = {"subtitle": "subheadline", "cta_url": "cta_link"}                        # D17-B01: the live hero content stores these under other names
_WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
_SECTION_FLAT_KEYS = _SECTION_CONTENT_FIELDS + ("placement",)    # D17-B02: flat body keys folded into `content`


# ───────────────────────────── helpers ─────────────────────────────
def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _storefront_read_query(table, campus_id, columns="*"):
    """Guest reads use only a validated campus scope, never an unbounded service read."""
    if getattr(g, "user_id", None):
        return get_user_client().table(table).select(columns)
    q = get_db().table(table).select(columns)
    return q.or_(f"campus_id.is.null,campus_id.eq.{campus_id}") if campus_id else q.eq("campus_id", None)


def _section_content(data, base=None):
    """Fold the flat section fields the admin editors post into the single JSONB `content` column.

    `storefront_sections` stores everything visual in `content`, but the editors submit
    `subtitle`, `image_url`, `cta_text`, `cta_url` (and `placement`) as flat body keys.
    Both shapes are merged so a create/edit never silently drops the image or CTA.
    Returns None when `content` is present but not an object (caller answers 400).
    """
    content = dict(base) if isinstance(base, dict) else {}
    if "content" in data:
        if not isinstance(data["content"], dict):
            return None
        content.update(data["content"])
    for k in _SECTION_CONTENT_FIELDS:
        if k in data:
            content[k] = data[k]
            alias = _SECTION_CONTENT_ALIASES.get(k)
            if alias:
                content[alias] = data[k]                                            # live hero reads the legacy names
    if "placement" in data:
        content["placement"] = data["placement"]                                    # sections have no placement column — lives in content
    return content


def _section_content_touched(data):
    """True when the body carries anything that belongs in `content`."""
    return "content" in data or any(k in data for k in _SECTION_FLAT_KEYS)


def _json_body():
    """Parsed JSON *object* body, or None when the body is missing / not an object (D17-B13)."""
    data = request.get_json(force=True, silent=True)
    return data if isinstance(data, dict) else None


def _bad_request():
    return jsonify({"error": MSG.ERR_BAD_REQUEST}), 400


def _field_required(field):
    return jsonify({"error": MSG.AUTH_FIELD_REQUIRED.format(field=field)}), 400


def _row(result):
    """First row of a write result; None when RLS / the filter matched nothing (D17-B03)."""
    if isinstance(result, list):
        return result[0] if result else None
    return result or None


def _insert_cms(db, table, payload, data):
    """Use the existing row UUID for response-loss recovery; no new intent table."""
    if "request_id" not in data:
        try:
            return jsonify(_row(db.table(table).insert(payload))), 201
        except SupabaseError as exc:
            if exc.details.get("code") == "23505":
                return _key_conflict_response(db, table, payload.get("key"))
            raise
    try:
        if not isinstance(data["request_id"], str):
            return _bad_request()
        intent = str(uuid.UUID(data["request_id"]))
    except (ValueError, TypeError, AttributeError):
        return _bad_request()
    payload = dict(payload, id=intent, created_by=g.user_id)
    payload.setdefault("campus_id", None)
    try:
        return jsonify(_row(db.table(table).insert(payload))), 201
    except SupabaseError as exc:
        if exc.details.get("code") != "23505":
            raise
    existing = db.table(table).select("*").eq("id", intent).single().execute()
    if not existing:
        # A different row owns the section key: this is not a changed replay.
        return _key_conflict_response(db, table, payload.get("key"))
    def same(key, value):
        saved = existing.get(key)
        if key in ("starts_at", "ends_at") and saved and value:
            return datetime.fromisoformat(saved.replace("Z", "+00:00")) == datetime.fromisoformat(value.replace("Z", "+00:00"))
        return saved == value
    if existing and all(same(key, value) for key, value in payload.items()):
        return jsonify(existing), 200
    return jsonify({"error": MSG.STOREFRONT_CREATE_CONFLICT}), 409


def _same_timestamp(left, right):
    """The editor may serialize UTC as Z rather than +00:00; compare instants."""
    if left == right:
        return True
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    try:
        a = datetime.fromisoformat(left.replace("Z", "+00:00"))
        b = datetime.fromisoformat(right.replace("Z", "+00:00"))
        return a.tzinfo is not None and b.tzinfo is not None and a == b
    except ValueError:
        return False


def _write_denied():
    return jsonify({"error": MSG.UPDATE_NOT_PERMITTED}), 403


def _parse_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, int) and v in (0, 1):
        return bool(v)
    if isinstance(v, str) and v.strip().lower() in ("true", "1", "yes"):
        return True
    if isinstance(v, str) and v.strip().lower() in ("false", "0", "no"):
        return False
    raise ValueError("not a boolean")


def _parse_int(v):
    if isinstance(v, bool) or v is None:
        raise ValueError("not an int")
    if isinstance(v, float) and (not math.isfinite(v) or not v.is_integer()):
        raise ValueError("not an int")
    return int(v)


def _cms_destination_valid(dest):
    if not isinstance(dest, str):
        return False
    if not dest:
        return True
    if any(c.isspace() or ord(c) < 32 for c in dest) or "\\" in dest:
        return False
    if dest.startswith("/") and not dest.startswith("//"):
        return True
    try:
        parsed = urlsplit(dest)
        if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
            return False
        parsed.port
        return True
    except ValueError:
        return False


def _supporter_links_valid(links):
    if not isinstance(links, dict):
        return False
    for key in ('url', 'link'):
        value = links.get(key)
        if value in (None, ''):
            continue
        if not isinstance(value, str) or not value.startswith(('https://', 'http://')) or not _cms_destination_valid(value):
            return False
    return True


def _section_validation(content, section_type):
    """Validate fields consumed by the storefront; unrelated JSON metadata survives."""
    text_fields = ("subtitle", "subheadline", "body", "image_url", "base_image_url",
                   "photo_url", "cta_text", "cta_url", "cta_link", "eyebrow", "badge",
                   "name", "review", "caption_template", "tier_slug", "slug", "key",
                   "title", "line", "description", "destination")
    for field in text_fields:
        if field in content and not isinstance(content[field], str):
            return _bad_request()
    if "config" in content and not isinstance(content["config"], dict):
        return _bad_request()
    if "display_mode" in content and content["display_mode"] not in ("text", "image"):
        return _bad_request()
    if "placement" in content:
        allowed = {"home", "menu", "dashboard", "orders", "rewards"} if section_type == "popup" else {"home", "menu", "checkout"}
        if not isinstance(content["placement"], str) or content["placement"] not in allowed | {""}:
            return _bad_request()
    for field in ("image_url", "base_image_url", "photo_url"):
        if content.get(field) and not is_cms_image_url(content[field]):
            return jsonify({"error": MSG.STOREFRONT_IMAGE_PROVIDER_INVALID}), 400
    for field in ("cta_url", "cta_link", "destination"):
        if not _cms_destination_valid(content.get(field, "")):
            return _bad_request()
    if section_type == "testimonial" and "rating" in content:
        try:
            rating = _parse_int(content["rating"])
            if not 1 <= rating <= 5:
                raise ValueError("out of range")
        except (TypeError, ValueError, OverflowError):
            return jsonify({"error": MSG.STOREFRONT_RATING_INVALID}), 400
        content["rating"] = rating
    if section_type == "tier_icon" and content.get("tier_slug") and content["tier_slug"] not in ("ember", "flame", "blaze", "holy"):
        return _bad_request()
    return None


def _section_insert_requirements(section_type, title, content, key):
    """Only require information the selected consumer needs to render content."""
    image_only = section_type == "popup" or content.get("display_mode") == "image"
    if section_type == "testimonial":
        if not (content.get("name") or title).strip():
            return _field_required("name")
        if not content.get("review", "").strip():
            return _field_required("review")
    elif section_type == "share_template":
        if not content.get("base_image_url", "").strip():
            return _field_required("base_image_url")
    elif section_type == "tier_icon":
        if not content.get("image_url", "").strip():
            return _field_required("image_url")
        slug = content.get("tier_slug") or content.get("slug") or re.sub(r"^tier[_-]icon[_-]", "", key)
        if slug not in ("ember", "flame", "blaze", "holy"):
            return _field_required("tier_slug")
    elif image_only:
        if not content.get("image_url", "").strip():
            return _field_required("image_url")
    elif section_type in ("our_story", "catering", "promo"):
        visible_fields = ("image_url", "subtitle", "line") if section_type != "catering" else ("image_url", "subtitle", "body", "description")
        if not any(str(value or "").strip() for value in (title, *(content.get(field) for field in visible_fields))):
            return _field_required("title")
    elif not title.strip():
        return _field_required("title")
    if section_type == "how_its_made" and not content.get("image_url", "").strip():
        return _field_required("image_url")
    return None


def _valid_time(v):
    return isinstance(v, str) and bool(_TIME_RE.match(v.strip()))


def _to_minutes(v):
    parts = str(v).strip().split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _body_global_scope():
    """True when the JSON body explicitly asks for the global ("All Campuses")
    scope via `scope`/`campus_scope`. The primary channel is the X-Campus-Scope
    header (set by apiClient on every admin write); the body field is accepted
    for API clients that cannot set headers."""
    if not request.is_json:
        return False
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return False
    marker = str(body.get("scope") or body.get("campus_scope") or "").strip().lower()
    return marker in GLOBAL_SCOPE_MARKERS


def _write_campus_id(explicit=None):
    """
    Campus a write is aimed at (D17-B05, A12).
      non-super_admin : always their own campus (g.campus_id) — every supplied
                        value, header and scope marker are ignored.
      super_admin     : explicit body/query campus_id wins; otherwise the admin
                        header switcher is honoured exactly: X-Campus-ID selects
                        that campus, X-Campus-Scope: global (or a body
                        scope="global") means a global row (campus_id NULL).
                        Only with no selector signal at all does the profile
                        campus remain the fallback (legacy/API callers).
    """
    return resolve_admin_write_campus(
        explicit or request.args.get("campus_id"),
        global_scope=_body_global_scope(),
    )


def _campus_scope_label(db, campus_id):
    """Human label for a row's scope in an error message: 'Global' or the campus name."""
    if not campus_id:
        return "Global"
    try:
        row = db.table("campuses").select("name").eq("id", campus_id).single().execute()
        if row and row.get("name"):
            return row["name"]
    except SupabaseError:
        logger.warning("scope label: campus name lookup failed for %s", campus_id, exc_info=True)
    return "another campus"


def _key_conflict_response(db, table, key):
    """409 for a duplicate key that names the scope already owning it, so an admin
    never has to guess whether 'key already exists' means the global row or a
    campus row. Falls back to the generic message when the owner can't be read."""
    generic = jsonify({"error": MSG.STOREFRONT_KEY_EXISTS}), 409
    if not key:
        return generic
    try:
        # The unique constraint is on (key, campus_id) — key alone locates the
        # owning row regardless of its section_type.
        owners = db.table(table).select("campus_id").eq("key", key).limit(1).execute() or []
    except SupabaseError:
        logger.warning("key-conflict scope lookup failed for %s/%s", table, key, exc_info=True)
        return generic
    if not owners:
        return generic
    owner_campus = owners[0].get("campus_id")
    label = _campus_scope_label(db, owner_campus)
    return jsonify({
        "error": MSG.STOREFRONT_KEY_EXISTS_SCOPE.format(scope=label),
        "campus_id": owner_campus,
        "scope": "global" if not owner_campus else "campus",
    }), 409


def _scoped(rows, campus_id, key_fn=None):
    """
    Public-read campus filter: rows of the caller's campus + global (NULL campus) rows.
    With key_fn, a campus-specific row wins over a global row with the same key (D17-B08).
    No campus chosen yet -> only the global (NULL campus) rows: a guest sees the global storefront until they pick a campus.
    """
    if not isinstance(rows, list):
        return []
    if not campus_id:
        return [r for r in rows if r.get("campus_id") is None]
    kept = [r for r in rows if r.get("campus_id") in (campus_id, None)]
    if key_fn is None:
        return kept
    best = {}
    for r in kept:
        k = key_fn(r)
        cur = best.get(k)
        if cur is None or (cur.get("campus_id") is None and r.get("campus_id") is not None):
            best[k] = r
    return list(best.values())


def _images_error(images):
    """None when valid. Carousel `images` must be a list of non-empty strings."""
    if images is None:
        return None
    if not isinstance(images, list) or not all(isinstance(u, str) and u for u in images):
        return jsonify({"error": MSG.STOREFRONT_IMAGES_INVALID}), 400
    return None


def _banner_window_error(data):
    if data.get("starts_at") and data.get("ends_at"):
        start = datetime.fromisoformat(data["starts_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(data["ends_at"].replace("Z", "+00:00"))
        if end <= start:
            return jsonify({"error": MSG.STOREFRONT_BANNER_WINDOW_INVALID}), 400
    return None


def _banner_fields(data, placement=None):
    """
    Whitelisted, schema-valid banner columns from a request body (D17-B02).
    Accepts the legacy names cta_text/cta_url and stores them in action_label/action_url.
    Returns (dict, error_response|None).
    """
    out = {}
    if "metadata" in data:
        if not isinstance(data["metadata"], dict):
            return None, _bad_request()
        out["metadata"] = dict(data["metadata"])
    if "slides" in out.get("metadata", {}):
        slides = out["metadata"]["slides"]
        if not isinstance(slides, list) or len(slides) > 50:
            return None, _bad_request()
        clean = []
        fields = ("image_url", "mobile_image_url", "eyebrow", "title", "subtitle", "cta_text", "cta_url")
        compact = data.get("placement", placement) in ("menu", "checkout")
        for slide in slides:
            if not isinstance(slide, dict):
                return None, _bad_request()
            if any(not isinstance(slide.get(k, ""), str) for k in fields):
                return None, _bad_request()
            row = {k: slide.get(k, "").strip() for k in fields}
            mode = slide.get("display_mode", "image")
            if mode not in ("image", "text") or (mode == "text" and not compact):
                return None, _bad_request()
            row["display_mode"] = mode
            if len(row["eyebrow"]) > 240 or (compact and mode == "text" and not row["title"]) or (not (compact and mode == "text") and not row["image_url"]) or (not compact and not row["title"]):
                return None, _bad_request()
            if any(row[k] and not is_cms_image_url(row[k]) for k in ("image_url", "mobile_image_url")):
                return None, (jsonify({"error": MSG.STOREFRONT_IMAGE_PROVIDER_INVALID}), 400)
            if (row["cta_text"] and not row["cta_url"]) or (not (compact and mode == "image") and bool(row["cta_text"]) != bool(row["cta_url"])):
                return None, (jsonify({"error": MSG.FE_CMS_CTA_PAIR}), 400)
            # A destination must be an app path or an explicit web URL.
            dest = row["cta_url"]
            if not _cms_destination_valid(dest):
                return None, _bad_request()
            clean.append(row)
        out["metadata"]["slides"] = clean
    if "eyebrow" in data:
        if not isinstance(data["eyebrow"], str) or len(data["eyebrow"]) > 240:
            return None, _bad_request()
        out.setdefault("metadata", {})["eyebrow"] = data["eyebrow"].strip()
    for k in ("title", "subtitle", "image_url", "mobile_image_url", "action_url", "action_label", "placement"):
        if k in data:
            if not isinstance(data[k], str):
                return None, _bad_request()
            out[k] = data[k]
    for field in ("cta_text", "cta_url"):
        if field in data and not isinstance(data[field], str):
            return None, _bad_request()
    if "placement" in out and out["placement"] not in ("hero", "home", "menu", "checkout"):
        return None, _bad_request()
    if "cta_text" in data and "action_label" not in data:
        out["action_label"] = data["cta_text"]
    if "cta_url" in data and "action_url" not in data:
        out["action_url"] = data["cta_url"]
    if not _cms_destination_valid(out.get("action_url", "")):
        return None, _bad_request()
    try:
        if "is_active" in data:
            out["is_active"] = _parse_bool(data["is_active"])
        if "sort_order" in data:
            out["sort_order"] = _parse_int(data["sort_order"])
        for k in ("starts_at", "ends_at"):
            if data.get(k) is not None:
                when = datetime.fromisoformat(str(data[k]).replace("Z", "+00:00"))
                if when.tzinfo is None:
                    return None, _bad_request()
                out[k] = when.astimezone(timezone.utc).isoformat()
            elif k in data:
                out[k] = None
    except (TypeError, ValueError):
        return None, _bad_request()
    if data.get("images") is not None:
        err = _images_error(data["images"])
        if err:
            return None, err
        out["images"] = data["images"]
    for field in ("image_url", "mobile_image_url"):
        if out.get(field) and not is_cms_image_url(out[field]):
            return None, (jsonify({"error": MSG.STOREFRONT_IMAGE_PROVIDER_INVALID}), 400)
    if any(not is_cms_image_url(url) for url in out.get("images", [])):
        return None, (jsonify({"error": MSG.STOREFRONT_IMAGE_PROVIDER_INVALID}), 400)
    if "slides" in out.get("metadata", {}):
        slides = out["metadata"]["slides"]
        first = slides[0] if slides else {}
        # One authoritative slide set, mirrored to existing legacy columns.
        out.update(images=[row["image_url"] for row in slides if row["image_url"]],
                   image_url=first.get("image_url", ""), mobile_image_url=first.get("mobile_image_url", ""),
                   title=first.get("title", ""), subtitle=first.get("subtitle", ""),
                   action_label=first.get("cta_text", ""), action_url=first.get("cta_url", ""))
        out["metadata"]["eyebrow"] = first.get("eyebrow", "")
    return out, None


# ───────────────────────────── public config ─────────────────────────────
@storefront_bp.route("/feature-flags", methods=["GET"])
@optional_auth
def public_feature_flags():
    campus_id = _get_campus_id()
    rows = get_db().table("feature_flags").select("feature_name,is_active,campus_id").execute() or []
    flags = {}
    for row in sorted(rows, key=lambda r: r.get("campus_id") is not None):
        if row.get("campus_id") is None or (campus_id and row.get("campus_id") == campus_id):
            flags[row["feature_name"]] = bool(row["is_active"])
    return jsonify([{"feature_name": name, "is_active": active} for name, active in sorted(flags.items())]), 200


@storefront_bp.route("/config/public", methods=["GET"])
@optional_auth
def get_public_config():
    """
    Get public system settings and configs.
    ---
    tags: [Storefront]
    security: []
    responses:
      200:
        description: Public system configuration
      503:
        description: Configuration temporarily unavailable
    """
    db = get_user_client()
    campus_id = _get_campus_id()
    try:
        settings = db.table("system_settings").select("key,value,campus_id").eq("is_public", True).execute() or []
        if campus_id:
            settings = [s for s in settings if s.get("campus_id") in (campus_id, None)]
        else:                                                                        # no campus chosen: global settings only, never an arbitrary campus's
            settings = [s for s in settings if s.get("campus_id") is None]
        config_dict = {}
        global_email = next((r.get("value") for r in settings if r.get("key") == "support_email" and r.get("campus_id") is None), "")
        # global rows first, campus rows last -> campus value wins for the same key (D17-B08)
        for row in sorted(settings, key=lambda r: r.get("campus_id") is not None):
            if row.get("key"):
                config_dict[row["key"]] = row["value"]
    except Exception:
        logger.exception("get_public_config: system_settings read failed")           # D17-B09 (was swallowed -> 200 {})
        return jsonify({"error": MSG.STOREFRONT_CONFIG_UNAVAILABLE}), 503

    max_radius = 15.0
    c_lat, c_lon = None, None
    if campus_id:                                                                    # D17-B09: never guess a campus
        try:
            # SF-RLS-01: kitchen_settings is RLS-restricted to campus staff, so the anon/customer client always read 0 rows here
            # and every guest silently got the 15 km default. The radius is public delivery config -> read just this key
            # with the service client (same approach as the campus-location endpoint in admin.py).
            ks_res = (get_db().table("kitchen_settings").select("value")
                      .eq("key", "max_delivery_radius_km").eq("campus_id", campus_id).limit(1).execute()) or []
            if ks_res and ks_res[0].get("value"):
                max_radius = float(ks_res[0]["value"])
        except Exception:
            logger.warning("get_public_config: max_delivery_radius_km unreadable for campus %s — using default", campus_id, exc_info=True)
        try:                                                                         # D17-B09: separate try — a bad radius no longer hides lat/lon
            c_row = db.table("campuses").select("lat,lon").eq("id", campus_id).single().execute()
            if c_row:
                c_lat = c_row.get("lat")
                c_lon = c_row.get("lon")
        except Exception:
            logger.warning("get_public_config: campus coordinates unreadable for %s", campus_id, exc_info=True)

    from app.utils.social_links import public_social_links
    config_dict['global_social_links'] = public_social_links(settings)
    config_dict["global_support_email"] = global_email
    config_dict["max_delivery_radius_km"] = max_radius
    config_dict["campus_lat"] = c_lat
    config_dict["campus_lon"] = c_lon
    # Guests may use global contact details before choosing a campus. Once a
    # campus is resolved, WhatsApp must come from that campus's public row.
    if campus_id:
        config_dict["whatsapp_support_number"] = next((r.get("value") for r in settings if r.get("key") == "whatsapp_support_number" and r.get("campus_id") == campus_id), "")
    elif not config_dict.get("whatsapp_support_number"):
        config_dict["whatsapp_support_number"] = (os.environ.get("WHATSAPP_SUPPORT_NUMBER") or "").strip() or None
    if not config_dict.get("whatsapp_support_message"):
        config_dict["whatsapp_support_message"] = (os.environ.get("WHATSAPP_SUPPORT_MESSAGE") or "").strip() or None
    return jsonify(config_dict), 200


# ───────────────────────────── sections ─────────────────────────────
@storefront_bp.route("/sections", methods=["GET"])
@optional_auth
def list_sections():
    """
    Get active storefront CMS sections (homepage, banners, etc).
    ---
    tags: [Storefront]
    security: []
    responses:
      200:
        description: Storefront sections
    """
    campus_id = _get_campus_id()
    q = _storefront_read_query("storefront_sections", campus_id)
    # Public callers get the active rows only. An admin needs to see the rows
    # they switched off too — otherwise flipping is_active off makes a section
    # vanish from the CMS list with no way to turn it back on.
    include_inactive = str(request.args.get("include_inactive") or "").lower() in ("1", "true", "yes")
    management_read = include_inactive and getattr(g, "user_role", None) in ADMIN_ROLES
    if not management_read:
        q = q.eq("is_active", "true")
    section_type = request.args.get("section_type")
    if section_type:
        q = q.eq("section_type", section_type)
    sections = q.order("sort_order").execute() or []
    if include_inactive and getattr(g, "user_role", None) == "super_admin" and not campus_id:
        return jsonify(sections), 200
    return jsonify(_scoped(sections, campus_id, key_fn=None if management_read else lambda row: (row.get("section_type"), row.get("key")))), 200


@storefront_bp.route("/sections/<section_id>", methods=["PATCH"])
@require_role("admin")
def update_section(section_id):
    """
    Update a storefront section (admin only).
    Real columns: title, is_active, sort_order, content. The legacy flat fields
    (subtitle, body, image_url, cta_text, cta_url, config) are merged into `content`.
    ---
    tags: [Storefront]
    parameters:
      - in: path
        name: section_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            title: {type: string}
            content: {type: object, description: "Merged into the existing content object"}
            subtitle: {type: string}
            body: {type: string}
            image_url: {type: string}
            cta_text: {type: string}
            cta_url: {type: string}
            config: {type: object}
            is_active: {type: boolean}
            sort_order: {type: integer}
    responses:
      200:
        description: Section updated
      404:
        description: Section not found
    """
    db = get_user_client()
    data = _json_body()
    if data is None:
        return _bad_request()
    existing = db.table("storefront_sections").select("id,content,section_type").eq("id", section_id).single().execute()
    if not existing:
        return jsonify({"error": MSG.SECTION_NOT_FOUND}), 404

    update = {}
    if "key" in data:
        if not isinstance(data["key"], str) or not data["key"].strip():
            return _field_required("key")
        update["key"] = data["key"].strip()
    try:
        if "title" in data:
            if not isinstance(data["title"], str):
                return _bad_request()
            update["title"] = data["title"]
        if "is_active" in data:
            update["is_active"] = _parse_bool(data["is_active"])
        if "sort_order" in data:
            update["sort_order"] = _parse_int(data["sort_order"])
    except (TypeError, ValueError):
        return _bad_request()

    content = _section_content(data, existing.get("content"))
    if content is None:
        return _bad_request()                                                       # D17-B13 (content: null -> NOT NULL 500)
    if _section_content_touched(data):
        err = _section_validation(content, existing.get("section_type"))
        if err:
            return err
        update["content"] = content
    if not update:
        return jsonify({"error": MSG.STOREFRONT_NOTHING_TO_UPDATE}), 400

    update["updated_at"] = _now_iso()
    try:
        updated = _row(db.table("storefront_sections").eq("id", section_id).update(update))
    except SupabaseError as exc:
        if exc.details.get("code") == "23505":
            return _key_conflict_response(db, "storefront_sections", update.get("key"))
        raise
    if updated is None:
        return _write_denied()
    return jsonify(updated), 200


@storefront_bp.route("/sections", methods=["POST"])
@require_role("admin")
def create_section():
    """
    Create a new CMS homepage section (admin only).
    ---
    tags: [Storefront]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [key, section_type]
          properties:
            key: {type: string, description: "Unique identifier slug (unique per campus)"}
            title: {type: string, description: "Required except for popup or image-only sections"}
            section_type: {type: string, description: "e.g. hero, banner, promo, faq"}
            content: {type: object}
            subtitle: {type: string, description: "folded into content.subtitle / content.subheadline"}
            image_url: {type: string, description: "folded into content.image_url"}
            body: {type: string, description: "folded into content.body"}
            cta_text: {type: string, description: "folded into content.cta_text"}
            cta_url: {type: string, description: "folded into content.cta_url / content.cta_link"}
            placement: {type: string, description: "folded into content.placement (sections have no placement column)"}
            is_active: {type: boolean}
            sort_order: {type: integer}
            campus_id: {type: string, description: "super_admin only — target campus"}
    responses:
      201:
        description: Section created
      409:
        description: Key already exists for this campus
    """
    db = get_user_client()
    data = _json_body()
    if data is None:
        return _bad_request()
    for f in ("key", "section_type"):
        if not isinstance(data.get(f), str) or not data[f].strip():
            return _field_required(f)
    content = _section_content(data)
    if content is None:
        return _bad_request()                                                       # D17-B13 (content: null -> NOT NULL 500)
    # Artwork-only sections have no overlay copy; title remains a string column.
    title = data.get("title", "")
    if not isinstance(title, str):
        return _bad_request()
    err = _section_validation(content, data["section_type"].strip())
    if err:
        return err
    err = _section_insert_requirements(data["section_type"].strip(), title, content, data["key"].strip())
    if err:
        return err
    try:
        safe = {
            "key": data["key"].strip(),
            "title": title,
            "section_type": data["section_type"].strip(),
            "content": content,
            "is_active": _parse_bool(data["is_active"]) if "is_active" in data else True,
            "sort_order": _parse_int(data["sort_order"]) if "sort_order" in data else 0,
        }
    except (TypeError, ValueError):
        return _bad_request()
    campus_id = _write_campus_id(data.get("campus_id"))
    if campus_id:
        safe["campus_id"] = campus_id
    return _insert_cms(db, "storefront_sections", safe, data)


@storefront_bp.route("/sections/<section_id>", methods=["DELETE"])
@require_role("admin")
def delete_section(section_id):
    """
    Deactivate (soft-delete) a CMS homepage section (admin only).
    ---
    tags: [Storefront]
    parameters:
      - in: path
        name: section_id
        type: string
        required: true
    responses:
      200:
        description: Section deactivated
      404:
        description: Not found
    """
    db = get_user_client()
    existing = db.table("storefront_sections").select("id").eq("id", section_id).limit(1).execute()
    if not existing:
        return jsonify({"error": MSG.SECTION_NOT_FOUND}), 404
    updated = _row(db.table("storefront_sections").eq("id", section_id).update({"is_active": False, "updated_at": _now_iso()}))
    if updated is None:
        return _write_denied()                                                      # D17-B03 (was: 200 "deactivated" with nothing changed)
    return jsonify({"message": MSG.SECTION_DEACTIVATED, "section_id": section_id}), 200


@storefront_bp.route("/sections/<section_id>/image", methods=["POST"])
@require_role("admin")
def update_section_image(section_id):
    """Update storefront section image with Cloudinary URL (stored in content.image_url)."""
    db = get_user_client()
    section = db.table("storefront_sections").select("content").eq("id", section_id).single().execute()
    if not section:
        return jsonify({"error": MSG.SECTION_NOT_FOUND}), 404
    data = _json_body() or {}
    image_url = data.get("image_url")
    if not isinstance(image_url, str) or not image_url.strip():
        return jsonify({"error": MSG.STOREFRONT_IMAGE_URL_REQUIRED}), 400
    if not is_cms_image_url(image_url):
        return jsonify({"error": MSG.STOREFRONT_IMAGE_PROVIDER_INVALID}), 400
    content = dict(section.get("content") or {})
    content["image_url"] = image_url
    updated = _row(db.table("storefront_sections").eq("id", section_id).update({"content": content, "updated_at": _now_iso()}))
    if updated is None:
        return _write_denied()
    return jsonify({"image_url": image_url}), 200


# ───────────────────────────── operating hours ─────────────────────────────
def _parse_time(t_str):
    try:
        parts = str(t_str).split(":")
        return datetime(2000, 1, 1, int(parts[0]), int(parts[1])).time()
    except Exception:
        return datetime(2000, 1, 1, 0, 0).time()


def _is_currently_open(schedule, override, now=None) -> bool:
    now = now or datetime.now(_WAT)
    today_weekday = now.weekday()                                                    # 0=Monday … 6=Sunday

    if override:
        if override.get("is_closed"):
            return False
        # override_window() is the shared reading of an open override: NULL times
        # mean the whole day (00:00-23:59), not "fall back to the weekly schedule".
        open_val, close_val = override_window(override)
        return _parse_time(open_val) <= now.time() <= _parse_time(close_val)

    for row in schedule:
        if row.get("weekday") == today_weekday:
            if row.get("is_closed"):
                return False
            open_val = row.get("open_time") or row.get("opens_at") or "00:00"       # D17-B10: NULL time no longer means "closed all day"
            close_val = row.get("close_time") or row.get("closes_at") or "23:59"
            return _parse_time(open_val) <= now.time() <= _parse_time(close_val)
    return False


@storefront_bp.route("/operating-hours", methods=["GET"])
@optional_auth
def get_hours():
    """
    Get current operating hours schedule and any today-specific override.
    ---
    tags: [Storefront]
    security: []
    responses:
      200:
        description: Operating hours including today's status (is_open is null when no campus was supplied)
    """
    db = get_user_client()
    campus_id = _get_campus_id()

    hours = db.table("operating_hours").select("*").order("weekday").execute() or []
    hours = _scoped(hours, campus_id, key_fn=lambda r: r.get("weekday"))

    today_iso = today_wat().isoformat()
    # Same helper the ordering gate uses (app/utils/schedule.py), so a holiday means
    # the same thing on this endpoint and at checkout. Before a campus is chosen this
    # returns the global row, exactly as the scoped read above does.
    override = resolve_date_override(db, campus_id, today_iso)

    from app.utils.schedule import effective_windows_with_config
    effective, source = effective_windows_with_config(db, campus_id, today_iso, today_wat().weekday(), operating_hours=hours) if campus_id else ([], None)
    current = datetime.now(_WAT).time()
    is_open = any(not row.get('is_closed') and _parse_time(row.get('opens_at')) <= current <= _parse_time(row.get('closes_at')) for row in effective)
    return jsonify({
        "schedule": hours,
        "today_override": override,
        "effective_source": source,
        # D17-B08: without a campus the rows of several campuses are mixed, so "open?" has no single answer
        "is_open": is_open if campus_id else None,
    }), 200


@storefront_bp.route("/operating-hours", methods=["PATCH"])
@require_role("admin")
def update_hours():
    """
    Update (or create) operating hours for one weekday of one campus (admin only).
    ---
    tags: [Storefront]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          properties:
            day: {type: string, enum: [monday, tuesday, wednesday, thursday, friday, saturday, sunday]}
            open_time: {type: string, example: "10:00"}
            close_time: {type: string, example: "21:00"}
            is_closed: {type: boolean}
            campus_id: {type: string, description: "super_admin only — required when the super_admin has no campus"}
    responses:
      200:
        description: Hours updated
      201:
        description: Hours created for a campus that had no row for this weekday
    """
    db = get_user_client()
    data = _json_body()
    if data is None:
        return _bad_request()
    day_name = str(data.get("day") or "").strip().lower()
    if not day_name:
        return jsonify({"error": MSG.STOREFRONT_DAY_REQUIRED}), 400
    if day_name not in _WEEKDAYS:
        return jsonify({"error": MSG.STOREFRONT_INVALID_DAY.format(day=day_name)}), 400
    weekday_int = _WEEKDAYS[day_name]

    campus_id = _write_campus_id(data.get("campus_id"))
    if not campus_id:                                                                # D17-B05: never fan out to every campus
        return jsonify({"error": MSG.STOREFRONT_CAMPUS_REQUIRED}), 400

    update = {}
    for src, dst in (("open_time", "opens_at"), ("close_time", "closes_at")):
        if src in data:
            if data[src] is not None and not _valid_time(data[src]):
                return jsonify({"error": MSG.STOREFRONT_TIME_INVALID.format(field=src)}), 400
            update[dst] = data[src]
    if "is_closed" in data:
        try:
            update["is_closed"] = _parse_bool(data["is_closed"])
        except ValueError:
            return _bad_request()
    if not update:
        return jsonify({"error": MSG.STOREFRONT_HOURS_FIELDS_REQUIRED}), 400

    existing = (db.table("operating_hours").select("*").eq("weekday", weekday_int).eq("campus_id", campus_id).limit(1).execute()) or []
    cur = existing[0] if existing else {}
    eff_open = update.get("opens_at", cur.get("opens_at"))
    eff_close = update.get("closes_at", cur.get("closes_at"))
    eff_closed = update.get("is_closed", cur.get("is_closed", False))
    if not eff_closed and eff_open and eff_close and _to_minutes(eff_close) <= _to_minutes(eff_open):
        return jsonify({"error": MSG.STOREFRONT_HOURS_ORDER_INVALID}), 400           # D17-B10: overnight windows can never read as "open"

    if existing:
        updated = _row(db.table("operating_hours").eq("weekday", weekday_int).eq("campus_id", campus_id).update(update))
        if updated is None:
            return _write_denied()
        return jsonify(updated), 200

    # D17-B06: campuses other than the seeded one had no way to get hours (needs Part A02: unique(weekday, campus_id))
    if not update.get("is_closed") and not (update.get("opens_at") and update.get("closes_at")):
        return jsonify({"error": MSG.STOREFRONT_HOURS_CREATE_REQUIRES_TIMES}), 400
    created = _row(db.table("operating_hours").insert({"weekday": weekday_int, "campus_id": campus_id, **update}))
    return jsonify(created), 201


@storefront_bp.route("/operating-hours/override", methods=["POST"])
@require_role("admin")
def set_override():
    """
    Set a date-specific operating hours override (e.g., public holiday closure).
    ---
    tags: [Storefront]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [override_date]
          properties:
            override_date: {type: string, format: date}
            is_closed: {type: boolean}
            open_time: {type: string}
            close_time: {type: string}
            reason: {type: string}
            campus_id: {type: string, description: "super_admin only; omit for a global override"}
    responses:
      201:
        description: Override set
    """
    db = get_user_client()
    data = _json_body()
    if data is None:
        return _bad_request()
    raw_date = data.get("override_date") or data.get("date")
    if not raw_date:
        return jsonify({"error": MSG.STOREFRONT_DATE_REQUIRED}), 400
    try:
        day = date.fromisoformat(str(raw_date)).isoformat()
    except ValueError:
        return jsonify({"error": MSG.STOREFRONT_DATE_INVALID.format(field="date")}), 400

    payload = {"date": day}
    campus_id = _write_campus_id(data.get("campus_id"))
    if campus_id:
        payload["campus_id"] = campus_id
    try:
        if "is_closed" in data:
            payload["is_closed"] = _parse_bool(data["is_closed"])
    except ValueError:
        return _bad_request()
    for src, dst in (("open_time", "opens_at"), ("close_time", "closes_at")):
        if src in data:
            if data[src] is not None and not _valid_time(data[src]):
                return jsonify({"error": MSG.STOREFRONT_TIME_INVALID.format(field=src)}), 400
            payload[dst] = data[src]
    if "reason" in data:
        payload["reason"] = data["reason"]
    if payload.get("is_closed"):
        payload["opens_at"] = None                                                   # D17-B11: a closure must not keep stale hours
        payload["closes_at"] = None
    elif payload.get("opens_at") and payload.get("closes_at") and _to_minutes(payload["closes_at"]) <= _to_minutes(payload["opens_at"]):
        return jsonify({"error": MSG.STOREFRONT_HOURS_ORDER_INVALID}), 400

    row = _row(db.table("operating_hour_overrides").upsert(payload, on_conflict="date,campus_id"))
    return jsonify(row), 201


# ───────────────────────────── promo (deprecated) ─────────────────────────────
@storefront_bp.route("/promo-codes/validate", methods=["POST"])
@require_auth                                                                        # D17-B04: anon can't read promo_codes (RLS) -> the public version could never succeed
def validate_promo():
    """
    [DEPRECATED] Validate a promo code — use POST /orders/validate-promo instead.
    Requires login (promo_codes are only readable by authenticated users).
    ---
    tags: [Storefront]
    deprecated: true
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [code, order_subtotal]
          properties:
            code: {type: string}
            order_subtotal: {type: number}
    responses:
      200:
        description: Promo code valid with discount info (deprecated — use /orders/validate-promo)
      400:
        description: Invalid or expired code
    """
    db = get_user_client()

    def _dep(body, status=200):
        r = jsonify({**body, "_deprecated": True, "_use_instead": "POST /api/orders/validate-promo"})
        r.headers["Deprecation"] = "true"
        r.headers["Sunset"] = "Thu, 01 Oct 2026 00:00:00 GMT"                       # D17-B04: RFC 8594 wants an HTTP-date
        r.headers["Link"] = '</api/orders/validate-promo>; rel="successor-version"'
        return r, status

    data = _json_body()
    if data is None:
        return _dep({"error": MSG.ERR_BAD_REQUEST}, 400)
    code = data.get("code")
    if not isinstance(code, str) or not code.strip():                                # D17-B13 (code: null -> AttributeError 500)
        return _dep({"error": MSG.AUTH_FIELD_REQUIRED.format(field="code")}, 400)
    code = code.strip().upper()
    try:
        subtotal = float(data.get("order_subtotal", 0))
        if not math.isfinite(subtotal) or subtotal < 0:                              # D17-B13 (negative subtotal -> negative discount)
            raise ValueError
    except (TypeError, ValueError):
        return _dep({"error": MSG.STOREFRONT_PROMO_AMOUNT_INVALID}, 400)

    rows = db.table("promo_codes").select("*").eq("code", code).eq("is_active", "true").limit(1).execute()
    promo = rows[0] if rows else None
    if not promo:
        return _dep({"error": MSG.STOREFRONT_PROMO_INVALID}, 400)

    campus_id = getattr(g, "campus_id", None)                                        # D17-B04: same campus rule as orders._apply_promo
    if campus_id and promo.get("campus_id") and promo["campus_id"] != campus_id:
        return _dep({"error": MSG.STOREFRONT_PROMO_INVALID}, 400)

    now = _now_iso()
    if promo.get("ends_at") and promo["ends_at"] < now:
        return _dep({"error": MSG.STOREFRONT_PROMO_EXPIRED}, 400)
    if promo.get("starts_at") and promo["starts_at"] > now:
        return _dep({"error": MSG.STOREFRONT_PROMO_NOT_ACTIVE}, 400)
    if promo.get("max_uses") and int(promo.get("used_count") or 0) >= promo["max_uses"]:
        return _dep({"error": MSG.STOREFRONT_PROMO_LIMIT}, 400)
    if subtotal < float(promo.get("min_order_amount") or 0):
        return _dep({"error": MSG.STOREFRONT_PROMO_MIN_ORDER.format(min_amount=float(promo.get("min_order_amount") or 0))}, 400)

    if promo["discount_type"] == "percentage":
        discount = subtotal * float(promo["discount_value"]) / 100
    else:
        discount = float(promo["discount_value"])

    return _dep({
        "valid": True,
        "discount_type": promo["discount_type"],
        "discount_value": promo["discount_value"],
        "calculated_discount": round(discount, 2),
        "code": code,
    })


# ───────────────────────────── early supporters ─────────────────────────────
@storefront_bp.route("/early-supporters", methods=["GET"])
@optional_auth
def list_early_supporters():
    """
    Get the public-facing Early Supporters list (storefront_sections with section_type='early_supporter').
    ---
    tags: [Storefront]
    security: []
    responses:
      200:
        description: List of early supporters (ordered by sort_order)
    """
    campus_id = _get_campus_id()
    q = (
        _storefront_read_query("storefront_sections", campus_id, "id,title,content,sort_order,created_at,campus_id,is_active")
        .eq("section_type", "early_supporter")
    )
    management_read = str(request.args.get("include_inactive") or "").lower() in ("1", "true", "yes") and getattr(g, "user_role", None) in ADMIN_ROLES
    if not management_read:
        q = q.eq("is_active", "true")
    rows = q.order("sort_order", ascending=True).execute() or []
    if not (management_read and getattr(g, "user_role", None) == "super_admin" and not campus_id):
        rows = _scoped(rows, campus_id)
    supporters = []
    for row in rows:
        content = row.get("content") if isinstance(row.get("content"), dict) else {}
        supporters.append({
            "id": row.get("id"),
            "name": content.get("name") or row.get("title"),
            "photo_url": content.get("photo_url"),
            "social_links": content.get("social_links") or {},
            "note": content.get("note"),
            "sort_order": row.get("sort_order", 0),
            "is_active": row.get("is_active", True),
            "campus_id": row.get("campus_id"),
        })
    return jsonify(supporters), 200


@storefront_bp.route("/early-supporters", methods=["POST"])
@require_role("admin")
def create_early_supporter():
    """
    Add a new Early Supporter entry (admin only).
    ---
    tags: [Storefront]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [name]
          properties:
            name: {type: string}
            photo_url: {type: string}
            social_links: {type: object}
            note: {type: string}
            sort_order: {type: integer}
            campus_id: {type: string, description: "super_admin only"}
    responses:
      201:
        description: Early supporter created
    """
    db = get_user_client()
    data = _json_body()
    if data is None:
        return _bad_request()
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        return _field_required("name")
    name = name.strip()
    social_links = data.get("social_links") or {}
    if not _supporter_links_valid(social_links):
        return _bad_request()
    if data.get("photo_url") and not is_cms_image_url(data["photo_url"]):
        return jsonify({"error": MSG.STOREFRONT_IMAGE_PROVIDER_INVALID}), 400
    try:
        sort_order = _parse_int(data.get("sort_order", 0))
    except (TypeError, ValueError):
        return _bad_request()

    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or uuid.uuid4().hex[:8]
    payload = {
        "key": f"early_supporter_{slug}",
        "title": name,
        "section_type": "early_supporter",
        "content": {"name": name, "photo_url": data.get("photo_url"), "social_links": social_links, "note": data.get("note")},
        "is_active": True,
        "sort_order": sort_order,
    }
    campus_id = _write_campus_id(data.get("campus_id"))
    if campus_id:
        payload["campus_id"] = campus_id

    if "request_id" in data:
        response, status = _insert_cms(db, "storefront_sections", payload, data)
        if status in (200, 201):
            return jsonify({"message": MSG.STOREFRONT_SUPPORTER_ADDED, "supporter": response.get_json()}), status
        return response, status
    try:
        result = db.table("storefront_sections").insert(payload)
    except SupabaseError as e:
        if str((e.details or {}).get("code")) != "23505":                            # D17-B12: match the SQLSTATE, not message text
            raise
        payload["key"] = f"{payload['key']}_{uuid.uuid4().hex[:8]}"                  # D17-B12: 1-second timestamp suffix could collide
        result = db.table("storefront_sections").insert(payload)
    return jsonify({"message": MSG.STOREFRONT_SUPPORTER_ADDED, "supporter": _row(result)}), 201


@storefront_bp.route("/early-supporters/<section_id>", methods=["PATCH"])
@require_role("admin")
def update_early_supporter(section_id):
    """
    Update an Early Supporter entry (admin only).
    ---
    tags: [Storefront]
    """
    db = get_user_client()
    data = _json_body()
    if data is None:
        return _bad_request()
    existing = (
        db.table("storefront_sections").select("id,content,section_type")
        .eq("id", section_id).eq("section_type", "early_supporter").limit(1).execute()
    )
    if not existing:
        return jsonify({"error": MSG.STOREFRONT_SUPPORTER_NOT_FOUND}), 404

    content = dict(existing[0].get("content") or {})
    update_payload = {}
    try:
        if "name" in data:
            if not isinstance(data["name"], str) or not data["name"].strip():
                return _field_required("name")
            content["name"] = data["name"].strip()
            update_payload["title"] = content["name"]
        for field in ("photo_url", "note"):
            if field in data:
                content[field] = data[field]
        if "social_links" in data:
            if data["social_links"] is not None and not _supporter_links_valid(data["social_links"]):
                return _bad_request()
            content["social_links"] = data["social_links"] or {}
        if "sort_order" in data:
            update_payload["sort_order"] = _parse_int(data["sort_order"])
        if "is_active" in data:
            update_payload["is_active"] = _parse_bool(data["is_active"])             # D17-B12: bool("false") was True
    except (TypeError, ValueError):
        return _bad_request()
    if not any(k in data for k in ("name", "photo_url", "note", "social_links", "sort_order", "is_active")):
        return jsonify({"error": MSG.STOREFRONT_NOTHING_TO_UPDATE}), 400

    if "photo_url" in data and content.get("photo_url") and not is_cms_image_url(content["photo_url"]):
        return jsonify({"error": MSG.STOREFRONT_IMAGE_PROVIDER_INVALID}), 400
    update_payload["content"] = content
    update_payload["updated_at"] = _now_iso()
    updated = _row(db.table("storefront_sections").eq("id", section_id).update(update_payload))
    if updated is None:
        return _write_denied()
    return jsonify(updated), 200


@storefront_bp.route("/early-supporters/<section_id>", methods=["DELETE"])
@require_role("admin")
def delete_early_supporter(section_id):
    """
    Deactivate an Early Supporter entry (admin only — soft delete).
    ---
    tags: [Storefront]
    """
    db = get_user_client()
    existing = (
        db.table("storefront_sections").select("id")
        .eq("id", section_id).eq("section_type", "early_supporter").limit(1).execute()
    )
    if not existing:
        return jsonify({"error": MSG.STOREFRONT_SUPPORTER_NOT_FOUND}), 404
    updated = _row(db.table("storefront_sections").eq("id", section_id).update({"is_active": False, "updated_at": _now_iso()}))
    if updated is None:
        return _write_denied()
    return jsonify({"message": MSG.STOREFRONT_SUPPORTER_REMOVED, "id": section_id}), 200


@storefront_bp.route("/early-supporters/<section_id>/photo", methods=["POST"])
@require_role("admin")
def update_early_supporter_photo(section_id):
    """Update early supporter photo with Cloudinary URL."""
    data = _json_body() or {}
    photo_url = data.get("photo_url")
    if not isinstance(photo_url, str) or not photo_url.strip():
        return jsonify({"error": MSG.STOREFRONT_PHOTO_URL_REQUIRED}), 400
    if not is_cms_image_url(photo_url):
        return jsonify({"error": MSG.STOREFRONT_IMAGE_PROVIDER_INVALID}), 400
    db = get_user_client()
    section = (
        db.table("storefront_sections").select("content")
        .eq("id", section_id).eq("section_type", "early_supporter").single().execute()
    )
    if not section:
        return jsonify({"error": MSG.STOREFRONT_SUPPORTER_NOT_FOUND}), 404
    content = dict(section.get("content") or {})
    content["photo_url"] = photo_url
    updated = _row(db.table("storefront_sections").eq("id", section_id).update({"content": content, "updated_at": _now_iso()}))
    if updated is None:
        return _write_denied()
    return jsonify({"photo_url": photo_url}), 200


# ───────────────────────────── banners ─────────────────────────────
@storefront_bp.route("/banners", methods=["GET"])
@optional_auth
def list_banners():
    """
    Get active promotional banners for the storefront homepage.
    ---
    tags: [Storefront]
    security: []
    parameters:
      - in: query
        name: placement
        type: string
    responses:
      200:
        description: Active banners ordered by sort_order
    """
    campus_id = _get_campus_id()
    q = _storefront_read_query("banners", campus_id)
    # The public list only ever served is_active rows, so an admin could not
    # see — let alone repair or re-enable — a banner that had been switched
    # off; it simply vanished from the panel. `include_inactive=1` is honoured
    # for admin callers only (a public caller asking for it gets the active
    # set, never the hidden rows).
    include_inactive = str(request.args.get("include_inactive") or "").lower() in ("1", "true", "yes")
    management_read = include_inactive and getattr(g, "user_role", None) in ADMIN_ROLES
    if not management_read:
        q = q.eq("is_active", "true")
    placement = request.args.get("placement")
    if placement:
        q = q.eq("placement", placement)
    banners = q.order("sort_order").execute() or []
    if not management_read:
        now = datetime.now(timezone.utc)
        def visible(banner):
            try:
                for field, is_start in (("starts_at", True), ("ends_at", False)):
                    value = banner.get(field)
                    if not value:
                        continue
                    when = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    if when.tzinfo is None:
                        when = when.replace(tzinfo=timezone.utc)
                    if (is_start and when > now) or (not is_start and when < now):
                        return False
                return True
            except (TypeError, ValueError):
                return False
        banners = [banner for banner in banners if visible(banner)]
    if management_read and getattr(g, "user_role", None) == "super_admin" and not campus_id:
        return jsonify(banners), 200
    return jsonify(_scoped(banners, campus_id)), 200


@storefront_bp.route("/banners", methods=["POST"])
@require_role("admin")
def create_banner():
    """
    Create a new promotional banner (admin only).
    Columns: title, subtitle, image_url, mobile_image_url, action_url, action_label (legacy aliases cta_url / cta_text),
    placement, is_active, sort_order, starts_at, ends_at, images (carousel — needs Part A04).
    ---
    tags: [Storefront]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [title, image_url]
          properties:
            title: {type: string}
            subtitle: {type: string}
            image_url: {type: string}
            mobile_image_url: {type: string}
            images: {type: array, items: {type: string}}
            action_url: {type: string}
            action_label: {type: string}
            placement: {type: string}
            is_active: {type: boolean}
            sort_order: {type: integer}
            starts_at: {type: string, format: date-time}
            ends_at: {type: string, format: date-time}
            campus_id: {type: string, description: "super_admin only"}
    responses:
      201:
        description: Banner created
      400:
        description: Missing required field or invalid value
    """
    db = get_user_client()
    data = _json_body()
    if data is None:
        return _bad_request()
    safe, err = _banner_fields(data)
    if err:
        return err
    slides = (safe.get("metadata") or {}).get("slides")
    if slides is not None:
        if not slides:
            return _bad_request()
    else:
        required = ("image_url",) if data.get("placement") in ("menu", "checkout") else ("title", "image_url")
        for field in required:
            if not isinstance(safe.get(field), str) or not safe[field].strip():
                return _field_required(field)
    err = _banner_window_error(safe)
    if err:
        return err
    safe.setdefault("title", "")
    safe.setdefault("is_active", True)
    safe.setdefault("sort_order", 0)
    campus_id = _write_campus_id(data.get("campus_id"))
    if campus_id:
        safe["campus_id"] = campus_id
    return _insert_cms(db, "banners", safe, data)


@storefront_bp.route("/banners/<banner_id>", methods=["DELETE"])
@require_role("admin")
def delete_banner(banner_id):
    """
    Delete a banner (admin only).
    ---
    tags: [Storefront]
    parameters:
      - in: path
        name: banner_id
        type: string
        required: true
    responses:
      200:
        description: Banner deleted
      404:
        description: Not found
    """
    db = get_user_client()
    banner = db.table("banners").select("id,title").eq("id", banner_id).single().execute()
    if not banner:
        return jsonify({"error": MSG.STOREFRONT_BANNER_NOT_FOUND}), 404
    deleted = _row(db.table("banners").eq("id", banner_id).delete())
    if deleted is None:
        return _write_denied()                                                       # D17-B03 (was: 200 "deleted" with nothing deleted)
    return jsonify({"message": MSG.STOREFRONT_BANNER_DELETED.format(title=banner.get("title") or banner_id)}), 200


@storefront_bp.route("/banners/<banner_id>", methods=["PATCH"])
@require_role("admin")
def update_banner(banner_id):
    """
    Update a banner (admin only). Pass `images` to set carousel slides (needs Part A04).
    ---
    tags: [Storefront]
    parameters:
      - in: path
        name: banner_id
        type: string
        required: true
    responses:
      200:
        description: Banner updated
      400:
        description: Invalid value
      404:
        description: Banner not found
    """
    db = get_user_client()
    data = _json_body()
    if data is None:
        return _bad_request()
    # Validate media and action safety before touching the row; title requirements
    # are then resolved from the saved placement (menu artwork has no copy).
    _, err = _banner_fields(data, "menu")
    if err:
        return err
    existing = db.table("banners").select("id,image_url,images,metadata,updated_at,starts_at,ends_at,placement").eq("id", banner_id).single().execute()
    if not existing:
        return jsonify({"error": MSG.STOREFRONT_BANNER_NOT_FOUND}), 404
    update, err = _banner_fields(data, existing.get("placement"))
    if err:
        return err
    if "expected_updated_at" in data and not _same_timestamp(data["expected_updated_at"], existing.get("updated_at")):
        return jsonify({"error": MSG.STOREFRONT_CONCURRENT_EDIT}), 409
    if "starts_at" in update or "ends_at" in update:
        err = _banner_window_error(dict(existing, **update))
        if err:
            return err
    if not update:
        return jsonify({"error": MSG.STOREFRONT_NOTHING_TO_UPDATE}), 400            # D17-B02 (all keys dropped silently before)
    # The renderer prefers the carousel array. Replacing its main image must
    # replace that same image in the array, or the old picture stays visible.
    if "image_url" in update and "images" not in update and existing.get("images"):
        update["images"] = list(dict.fromkeys(
            update["image_url"] if url == existing.get("image_url") else url
            for url in existing["images"]
            if url != existing.get("image_url") or update["image_url"]
        ))
    if "slides" not in update.get("metadata", {}) and isinstance((existing.get("metadata") or {}).get("slides"), list):
        slides = [dict(row) for row in existing["metadata"]["slides"]]
        if "image_url" in update:
            for row in slides:
                if row.get("image_url") == existing.get("image_url"):
                    row["image_url"] = update["image_url"]
        if "images" in update:
            slides = [row for row in slides if row.get("image_url") in update["images"]]
        if "mobile_image_url" in update and slides:
            slides[0]["mobile_image_url"] = update["mobile_image_url"] or ""
        copy_fields = {"title": "title", "subtitle": "subtitle", "action_label": "cta_text", "action_url": "cta_url"}
        if slides:
            for column, field in copy_fields.items():
                if column in update:
                    slides[0][field] = update[column] or ""
            if "eyebrow" in data:
                slides[0]["eyebrow"] = data["eyebrow"].strip()
        if any(field in update for field in ("images", "mobile_image_url", "metadata", *copy_fields)):
            update["metadata"] = dict(existing.get("metadata") or {}, **update.get("metadata", {}), slides=slides)
    if "images" in data and not update.get("images"):
        update["image_url"] = ""
    update["updated_at"] = _now_iso()
    # Do not overwrite slides added after the editor's read.
    q = db.table("banners").eq("id", banner_id)
    if "images" in update or "metadata" in update or "expected_updated_at" in data:
        q = q.eq("updated_at", existing.get("updated_at"))
    updated = _row(q.update(update))
    if updated is None:
        if "images" in update or "metadata" in update or "expected_updated_at" in data:
            return jsonify({"error": MSG.STOREFRONT_CONCURRENT_EDIT}), 409
        return _write_denied()
    return jsonify(updated), 200


@storefront_bp.route("/banners/<banner_id>/image", methods=["POST"])
@require_role("admin")
def update_banner_image(banner_id):
    """Append a Cloudinary carousel slide; retries never duplicate the image."""
    db = get_user_client()
    data = _json_body() or {}
    image_url = data.get("image_url")
    if not isinstance(image_url, str) or not image_url.strip():
        return jsonify({"error": MSG.STOREFRONT_IMAGE_URL_REQUIRED}), 400
    if not is_cms_image_url(image_url):
        return jsonify({"error": MSG.STOREFRONT_IMAGE_PROVIDER_INVALID}), 400
    for attempt in range(6):
        existing = db.table("banners").select("id,image_url,images,metadata,title,subtitle,action_label,action_url,updated_at,campus_id").eq("id", banner_id).single().execute()
        if not existing:
            return jsonify({"error": MSG.STOREFRONT_BANNER_NOT_FOUND}), 404
        if getattr(g, "user_role", None) != "super_admin" and existing.get("campus_id") != getattr(g, "campus_id", None):
            return _write_denied()
        images = existing.get("images") or [existing.get("image_url")]
        images = list(dict.fromkeys(url for url in images if url))
        if image_url in images:
            return jsonify({"image_url": image_url, "images": images}), 200
        images.append(image_url)
        update = {"images": images, "updated_at": _now_iso()}
        metadata = existing.get("metadata") or {}
        if isinstance(metadata.get("slides"), list):
            # Compatibility for old clients: preserve the configured slides.
            update["metadata"] = dict(metadata, slides=metadata["slides"] + [{
                "image_url": image_url, "mobile_image_url": "", "eyebrow": "",
                "title": existing.get("title") or "", "subtitle": existing.get("subtitle") or "",
                "cta_text": existing.get("action_label") or "", "cta_url": existing.get("action_url") or ""}])
        updated = _row(db.table("banners").eq("id", banner_id).eq("updated_at", existing.get("updated_at")).update(update))
        if updated:
            return jsonify({"image_url": image_url, "images": images}), 200
    return jsonify({"error": MSG.STOREFRONT_CONCURRENT_EDIT}), 409


# ───────────────────────────── newsletter ─────────────────────────────
def _clean_email(data):
    email = data.get("email")
    if not isinstance(email, str) or not email.strip():
        return None, (jsonify({"error": MSG.STOREFRONT_EMAIL_REQUIRED}), 400)
    email = email.strip().lower()
    if len(email) > 254 or not validate_email(email):                                # shared validator (app.utils.validators)
        return None, (jsonify({"error": MSG.STOREFRONT_EMAIL_INVALID}), 400)
    return email, None


@storefront_bp.route("/newsletter", methods=["POST"])
@rate_limit(max_requests=20, window_seconds=60)                                      # D17-B16 (per IP; campus Wi-Fi shares IPs, so not tighter)
def newsletter_subscribe():
    """
    Subscribe an email address to the Holy Grills newsletter.
    ---
    tags: [Storefront]
    security: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [email]
          properties:
            email: {type: string, format: email}
            full_name: {type: string}
            source: {type: string, example: "footer"}
    responses:
      201:
        description: Subscribed successfully
      200:
        description: Already subscribed / resubscribed
    """
    db = get_db()
    data = _json_body()
    if data is None:
        return _bad_request()
    email, err = _clean_email(data)
    if err:
        return err

    existing_rows = db.table("newsletter_subscriptions").select("id,unsubscribed_at").eq("email", email).limit(1).execute()
    existing = existing_rows[0] if existing_rows else None
    if existing:
        if not existing.get("unsubscribed_at"):
            return jsonify({"message": MSG.STOREFRONT_ALREADY_SUBSCRIBED}), 200
        db.table("newsletter_subscriptions").eq("email", email).update({"unsubscribed_at": None})
        return jsonify({"message": MSG.STOREFRONT_RESUBSCRIBED}), 200

    full_name = data.get("full_name")
    source = data.get("source")
    payload = {
        "email": email,
        "full_name": full_name.strip()[:120] if isinstance(full_name, str) and full_name.strip() else None,
        "source": source.strip()[:50] if isinstance(source, str) and source.strip() else "direct",   # D17-B15 (source:null hit the NOT NULL column)
        "is_confirmed": True,
    }
    campus_id = _get_campus_id()                                                     # D17-B14: rows were never campus-stamped
    if campus_id:
        try:
            ok = db.table("campuses").select("id").eq("id", campus_id).eq("is_active", "true").limit(1).execute()
        except SupabaseError:
            ok = None
        if ok:
            payload["campus_id"] = campus_id

    try:
        row = _row(db.table("newsletter_subscriptions").insert(payload)) or {}
    except SupabaseError as e:
        if str((e.details or {}).get("code")) == "23505":                            # D17-B15: concurrent duplicate -> already subscribed
            return jsonify({"message": MSG.STOREFRONT_ALREADY_SUBSCRIBED}), 200
        raise
    return jsonify({**row, "message": MSG.STOREFRONT_SUBSCRIBED}), 201


@storefront_bp.route("/newsletter/unsubscribe", methods=["POST"])
@rate_limit(max_requests=60, window_seconds=60)                                      # mail providers' one-click POSTs share IPs
def newsletter_unsubscribe():
    """
    Unsubscribe using the signed token from the unsubscribe link in a newsletter email.
    Accepts the token as ?token=… (RFC 8058 one-click) or as JSON {"token": "…"}.
    ---
    tags: [Storefront]
    security: []
    parameters:
      - in: query
        name: token
        type: string
      - in: body
        name: body
        schema:
          properties:
            token: {type: string}
    responses:
      200:
        description: Unsubscribed successfully
      400:
        description: Missing or invalid token
    """
    data = request.get_json(force=True, silent=True)
    token = request.args.get("token") or (data.get("token") if isinstance(data, dict) else None)
    if not isinstance(token, str) or not token.strip():
        return jsonify({"error": MSG.STOREFRONT_UNSUB_TOKEN_REQUIRED}), 400
    email = newsletter_service.read_unsubscribe_token(token.strip())
    if not email:
        return jsonify({"error": MSG.STOREFRONT_UNSUB_TOKEN_INVALID}), 400
    db = get_db()
    (db.table("newsletter_subscriptions").eq("email", email).is_("unsubscribed_at", "null")
       .update({"unsubscribed_at": _now_iso()}))                                     # D17-B17: only stamps rows that are still subscribed
    return jsonify({"message": MSG.STOREFRONT_UNSUBSCRIBED}), 200


@storefront_bp.route("/newsletter", methods=["GET"])
@require_role("admin")
def newsletter_list():
    """
    List newsletter subscribers (admin only). Campus admins see their campus; super_admin sees all (or ?campus_id=X).
    ---
    tags: [Storefront]
    parameters:
      - in: query
        name: active_only
        type: boolean
        default: true
      - in: query
        name: limit
        type: integer
        default: 100
      - in: query
        name: offset
        type: integer
        default: 0
      - in: query
        name: campus_id
        type: string
        description: super_admin only
    responses:
      200:
        description: Subscriber list
    """
    db = get_user_client()
    try:
        limit = max(1, min(int(request.args.get("limit", 100)), 500))               # D17-B18: 'abc' / negative values were 500s
        offset = max(0, int(request.args.get("offset", 0)))
    except (TypeError, ValueError):
        return _bad_request()
    q = db.table("newsletter_subscriptions").select("*")
    if request.args.get("active_only", "true").lower() != "false":
        q = q.is_("unsubscribed_at", "null")
    if getattr(g, "user_role", None) == "super_admin" and request.args.get("campus_id"):
        q = q.eq("campus_id", request.args["campus_id"].strip())
    rows = q.order("created_at", ascending=False).limit(limit).offset(offset).execute()
    return jsonify(rows), 200


@storefront_bp.route("/newsletter/admin-unsubscribe", methods=["POST"])
@require_role("admin")
def admin_newsletter_unsubscribe():
    """The admin button uses staff authorization; public links require signed tokens."""
    data = _json_body()
    if data is None:
        return _bad_request()
    email, err = _clean_email(data)
    if err:
        return err
    db = get_user_client()
    campus_id = _get_campus_id()
    q = db.table("newsletter_subscriptions").select("id,unsubscribed_at").eq("email", email)
    if campus_id:
        q = q.eq("campus_id", campus_id)
    row = _row(q.limit(1).execute())
    if not row:
        return jsonify({"error": MSG.STOREFRONT_SUBSCRIBER_NOT_FOUND}), 404
    if not row.get("unsubscribed_at"):
        db.table("newsletter_subscriptions").eq("id", row["id"]).is_("unsubscribed_at", "null").update({"unsubscribed_at": _now_iso()})
    return jsonify({"message": MSG.STOREFRONT_UNSUBSCRIBED}), 200


# ───────────────────────────── newsletter campaigns (admin sends to their campus) ─────────────────────────────
_CAMPAIGN_LIST_COLS = "id,campus_id,subject,status,total_recipients,sent_count,failed_count,created_at,started_at,completed_at,last_error"


def _campaign_text(data):
    """(subject, body, error_response|None) — plain text only; it is HTML-escaped when the email is built."""
    subject, body = data.get("subject"), data.get("body")
    for name, v in (("subject", subject), ("body", body)):
        if not isinstance(v, str) or not v.strip():
            return None, None, _field_required(name)
    subject, body = " ".join(subject.split()), body.strip()                       # no truncation here: too long is a 400
    if len(subject) > 200 or len(body) > 20000:
        return None, None, (jsonify({"error": MSG.STOREFRONT_CAMPAIGN_TEXT_LIMITS}), 400)
    return subject, body, None


def _campaign_target(data):
    """
    (campus_id|None, error_response|None). Campus admins always send to their own campus.
    super_admin must be explicit: `campus_id`, or `all_campuses: true` (campus_id None = every campus).
    """
    if getattr(g, "user_role", None) == "super_admin":
        if data.get("all_campuses") is True:
            return None, None
        cid = str(data.get("campus_id") or request.args.get("campus_id") or "").strip()
        if not cid:
            return None, (jsonify({"error": MSG.STOREFRONT_CAMPAIGN_TARGET_REQUIRED}), 400)
        return cid, None
    return getattr(g, "campus_id", None), None


@storefront_bp.route("/newsletter/campaigns", methods=["POST"])
@require_role("admin")
def create_newsletter_campaign():
    """
    Queue a newsletter to the subscribers of the admin's campus (admin) or of a chosen / all campuses (super_admin).
    Delivery runs in the background (every 5 minutes, in batches). Plain text body; an unsubscribe link is added to every email.
    ---
    tags: [Storefront]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [subject, body]
          properties:
            subject: {type: string, maxLength: 200}
            body: {type: string, maxLength: 20000}
            campus_id: {type: string, description: "super_admin only"}
            all_campuses: {type: boolean, description: "super_admin only — send to every campus"}
    responses:
      201:
        description: Campaign queued
      409:
        description: An identical campaign was queued in the last 10 minutes
    """
    db = get_user_client()
    data = _json_body()
    if data is None:
        return _bad_request()
    subject, body, err = _campaign_text(data)
    if err:
        return err
    campus_id, err = _campaign_target(data)
    if err:
        return err

    since = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()         # double-click / retry guard
    recent = db.table("newsletter_campaigns").select("id,campus_id,body").eq("subject", subject).gte("created_at", since).execute() or []
    if any(r.get("campus_id") == campus_id and r.get("body") == body for r in recent):
        return jsonify({"error": MSG.STOREFRONT_CAMPAIGN_DUPLICATE}), 409

    payload = {"subject": subject, "body": body, "status": "queued", "created_by": g.user_id}
    if campus_id:
        payload["campus_id"] = campus_id
    row = _row(db.table("newsletter_campaigns").insert(payload))
    return jsonify({"message": MSG.STOREFRONT_CAMPAIGN_QUEUED, "campaign": row}), 201


@storefront_bp.route("/newsletter/campaigns", methods=["GET"])
@require_role("admin")
def list_newsletter_campaigns():
    """List newsletter campaigns (campus admins: their campus; super_admin: all). Newest first."""
    db = get_user_client()
    try:
        limit = max(1, min(int(request.args.get("limit", 50)), 200))
        offset = max(0, int(request.args.get("offset", 0)))
    except (TypeError, ValueError):
        return _bad_request()
    rows = (db.table("newsletter_campaigns").select(_CAMPAIGN_LIST_COLS)
            .order("created_at", ascending=False).limit(limit).offset(offset).execute()) or []
    return jsonify(rows), 200


@storefront_bp.route("/newsletter/campaigns/<campaign_id>", methods=["GET"])
@require_role("admin")
def get_newsletter_campaign(campaign_id):
    """Campaign detail incl. body and delivery counts."""
    db = get_user_client()
    row = db.table("newsletter_campaigns").select("*").eq("id", campaign_id).single().execute()
    if not row:
        return jsonify({"error": MSG.STOREFRONT_CAMPAIGN_NOT_FOUND}), 404
    return jsonify(row), 200


@storefront_bp.route("/newsletter/campaigns/<campaign_id>/cancel", methods=["POST"])
@require_role("admin")
def cancel_newsletter_campaign(campaign_id):
    """Stop a queued / sending campaign. Emails already delivered stay delivered."""
    db = get_user_client()
    row = db.table("newsletter_campaigns").select("id,status").eq("id", campaign_id).single().execute()
    if not row:
        return jsonify({"error": MSG.STOREFRONT_CAMPAIGN_NOT_FOUND}), 404
    if row["status"] not in ("queued", "sending"):
        return jsonify({"error": MSG.STOREFRONT_CAMPAIGN_NOT_CANCELLABLE}), 409
    updated = _row(db.table("newsletter_campaigns").eq("id", campaign_id).in_("status", ["queued", "sending"])
                   .update({"status": "cancelled", "completed_at": _now_iso()}))
    if updated is None:                                                              # finished between the read and the update
        return jsonify({"error": MSG.STOREFRONT_CAMPAIGN_NOT_CANCELLABLE}), 409
    return jsonify({"message": MSG.STOREFRONT_CAMPAIGN_CANCELLED, "campaign": updated}), 200


@storefront_bp.route("/newsletter/campaigns/test", methods=["POST"])
@require_role("admin")
@rate_limit(max_requests=10, window_seconds=60)
def send_newsletter_test():
    """Send the newsletter to the calling admin's own email address only (preview). Nothing is stored."""
    data = _json_body()
    if data is None:
        return _bad_request()
    subject, body, err = _campaign_text(data)
    if err:
        return err
    from app.utils.email import get_user_email_and_name
    email, name = get_user_email_and_name(g.user_id)
    if not email:
        return jsonify({"error": MSG.STOREFRONT_TEST_NO_EMAIL}), 409
    if not newsletter_service.frontend_base_ok():
        return jsonify({"error": MSG.STOREFRONT_CONFIG_UNAVAILABLE}), 503
    if not newsletter_service.send_test(email, name, subject, body):
        return jsonify({"error": MSG.SERVICE_UNAVAILABLE}), 503
    return jsonify({"message": MSG.STOREFRONT_CAMPAIGN_TEST_SENT, "sent_to": email}), 200
