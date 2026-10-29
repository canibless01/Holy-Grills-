"""
Delivery Location routes — hostels, gates, fee calculation, admin CRUD.
"""

import math
import requests
from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_role, optional_auth, resolve_scoped_campus_id
from app.db import get_db, get_user_client, SupabaseError
from app.messages import MSG
from app.utils.logger import get_logger
from datetime import datetime, timezone
from app.utils.admin_helpers import as_number, as_text, as_bool, as_uuid, db_error_response
from app.utils.campus_scope import resolve_write_campus, assert_can_modify

logger = get_logger(__name__)

delivery_bp = Blueprint("delivery", __name__)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _location_fields(data, money_fields):
    if not isinstance(data, dict):
        raise ValueError
    result = dict(data)
    if "name" in result:
        result["name"] = as_text(result["name"], 200)
    if "is_active" in result:
        if not isinstance(result["is_active"], bool):
            raise ValueError
    for field in money_fields:
        if field in result:
            result[field] = as_number(result[field], minimum=0)
    if "gate_id" in result:
        result["gate_id"] = as_uuid(result["gate_id"])
    if "campus_id" in result:
        result["campus_id"] = as_uuid(result["campus_id"])
    return result


def _valid_hostel_gate(db, gate_id, campus_id):
    return not gate_id or bool(db.table("gates").select("id").eq("id", gate_id).eq("campus_id", campus_id).eq("is_active", True).single().execute())

def _admin_location(db, table, location_id):
    try:
        valid_id = as_uuid(location_id)
        if not valid_id:
            raise ValueError
    except ValueError:
        return None, (jsonify({"error": MSG.INVALID_INPUT}), 400)
    try:
        row = db.table(table).select("*").eq("id", valid_id).single().execute()
    except (SupabaseError, requests.RequestException) as exc:
        return None, db_error_response(exc, "delivery_location_lookup")
    if not row:
        return None, (jsonify({"error": MSG.RESOURCE_NOT_FOUND}), 404)
    assert_can_modify(row.get("campus_id"))
    return row, None


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Return the great-circle distance in kilometres between two lat/lon points."""
    R = 6371.0
    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlam = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def validate_coordinates(lat, lon):
    """
    Validate that coordinates are floats, are within standard spherical bounds,
    and fall inside the Nigerian geographic bounding box.
    """
    if lat is None or lon is None:
        return None, None
    try:
        f_lat = float(lat)
        f_lon = float(lon)
    except (ValueError, TypeError):
        raise ValueError(MSG.COORDINATES_INVALID)

    if not (-90.0 <= f_lat <= 90.0) or not (-180.0 <= f_lon <= 180.0):
        raise ValueError(MSG.COORDINATES_OUT_OF_BOUNDS)

    # Nigerian geographical bounding box (generous bounds)
    if not (4.0 <= f_lat <= 14.0) or not (2.5 <= f_lon <= 15.0):
        raise ValueError(MSG.COORDINATES_UNSUPPORTED_REGION)
    return f_lat, f_lon


def calculate_off_campus_fee(gate: dict, user_lat=None, user_lon=None) -> tuple[float, float | None]:
    """
    Calculate off-campus delivery fee for a given gate.
    Returns (fee_in_naira, distance_km_or_None).
    If user coordinates are absent, falls back to gate.min_fee.
    """
    base_fee = float(gate.get("base_fee") or 0)
    rate_per_km = float(gate.get("rate_per_km") or 0)
    min_fee = float(gate.get("min_fee") or 0)
    gate_lat = gate.get("lat")
    gate_lon = gate.get("lon")

    if (user_lat is not None and user_lon is not None
            and gate_lat is not None and gate_lon is not None):
        try:
            user_lat, user_lon = validate_coordinates(user_lat, user_lon)
            dist = haversine_km(gate_lat, gate_lon, user_lat, user_lon)
            fee = base_fee + (dist * rate_per_km)
            return round(max(fee, min_fee), 2), round(dist, 3)
        except Exception as e:
            raise ValueError(f"Coordinate validation failed: {str(e)}")
    return round(max(base_fee, min_fee), 2), None


def is_within_delivery_area(db, lat: float, lon: float, campus_id: str | None) -> bool:
    """
    Whether (lat, lon) is within the campus's configured delivery radius of
    the campus's own center point — this is the ONLY thing that should ever
    reject an order for being too far away. Fails open (returns True) if the
    campus has no center point configured yet, so a missing one-time admin
    setup step never blocks every off-campus order.
    """
    if not campus_id:
        return True
    campus = db.table("campuses").select("lat,lon").eq("id", campus_id).single().execute()
    if not campus or campus.get("lat") is None or campus.get("lon") is None:
        return True  # not configured yet — don't block orders because of it

    max_radius_km = 15.0
    try:
        # kitchen_settings is readable only by that campus's admin/kitchen staff (RLS), so a student's or
        # guest's client never sees the configured radius and would always fall back to 15 km. The
        # radius is a non-sensitive admin setting, so it is read with the service client.
        row = (
            get_db().table("kitchen_settings")
            .select("value")
            .eq("key", "max_delivery_radius_km")
            .eq("campus_id", campus_id)
            .single()
            .execute()
        )
        if row and row.get("value"):
            max_radius_km = float(row["value"])
    except Exception as e:
        logger.warning("is_within_delivery_area: radius lookup failed for campus %s, using %s km: %s",
                       campus_id, max_radius_km, e)

    return haversine_km(campus["lat"], campus["lon"], lat, lon) <= max_radius_km


def find_nearest_gate(db, lat: float, lon: float, campus_id: str | None) -> dict | None:
    """
    Return the active gate with lat/lon set that's closest to (lat, lon) —
    used purely for fee calculation and batch grouping, once the pin has
    already passed is_within_delivery_area separately. This never rejects an
    order for being "too far" — that's not its job. Returns None only if no
    gate anywhere has coordinates set at all; the order still proceeds without
    an auto-resolved gate in that case.
    """
    q = db.table("gates").select("*").eq("is_active", "true")
    if campus_id:
        q = q.eq("campus_id", campus_id)
    gates = q.execute() or []
    candidates = [g for g in gates if g.get("lat") is not None and g.get("lon") is not None]
    if not candidates:
        return None
    return min(candidates, key=lambda g: haversine_km(g["lat"], g["lon"], lat, lon))


# ─────────────────────────────────────────────────────────────────────────────
# Public user endpoints
# ─────────────────────────────────────────────────────────────────────────────

from app.routes.events import _require_campus_selection

@delivery_bp.route("/hostels", methods=["GET"])
@optional_auth
def list_hostels():
    """
    List all active on-campus hostels with their delivery fees for the selected campus.
    ---
    tags: [Delivery]
    security: []
    responses:
      200:
        description: |
          { hostels: [{ id, name, gate_id, delivery_fee, is_active, gates: {...} }] }
    """
    campus_id, err = _require_campus_selection()
    if err:
        return err
    db = get_user_client()
    try:
        q = db.table("hostels").select("*,gates(name,lat,lon)").eq("is_active", "true")
        hostels = q.order("name").execute() or []
        if isinstance(hostels, list):
            hostels = [h for h in hostels if h.get("campus_id") == campus_id or h.get("campus_id") is None]
    except Exception as e:
        logger.warning("list_hostels unavailable: %s", type(e).__name__)
        return jsonify({"error": MSG.SERVICE_UNAVAILABLE}), 503
    return jsonify({"hostels": hostels}), 200


@delivery_bp.route("/gates", methods=["GET"])
@optional_auth
def list_gates():
    """
    List all active delivery gates (used for off-campus fee calculation) for the selected campus.
    ---
    tags: [Delivery]
    security: []
    responses:
      200:
        description: |
          { gates: [{ id, name, lat, lon, base_fee, rate_per_km, min_fee }] }
    """
    campus_id, err = _require_campus_selection()
    if err:
        return err
    db = get_user_client()
    try:
        q = db.table("gates").select("*").eq("is_active", "true")
        gates = q.order("name").execute() or []
        if isinstance(gates, list):
            gates = [g_row for g_row in gates if g_row.get("campus_id") == campus_id or g_row.get("campus_id") is None]
    except Exception as e:
        logger.warning("list_gates unavailable: %s", type(e).__name__)
        return jsonify({"error": MSG.SERVICE_UNAVAILABLE}), 503
    return jsonify({"gates": gates}), 200


@delivery_bp.route("/calculate-fee", methods=["POST"])
@optional_auth
def calculate_fee():
    """
    Preview the delivery fee before placing an order.

    For on_campus: pass delivery_location_id = hostel_id → returns hostel.delivery_fee.
    For off_campus: pass delivery_location_id = gate_id and optional lat/lon
    → returns base_fee + distance × rate_per_km, floored at gate.min_fee.
    ---
    tags: [Delivery]
    security: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [delivery_type, delivery_location_id]
          properties:
            delivery_type:
              type: string
              enum: [on_campus, off_campus]
            delivery_location_id:
              type: string
              description: "hostel_id for on_campus, gate_id for off_campus"
            lat:
              type: number
              description: "User latitude for distance-based off_campus fee (optional)"
            lon:
              type: number
              description: "User longitude for distance-based off_campus fee (optional)"
    responses:
      200:
        description: Calculated fee
      400:
        description: Validation error
      404:
        description: Hostel or gate not found
    """
    db = get_user_client()
    data = request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": MSG.REQUEST_BODY_INVALID}), 400
    delivery_type = data.get("delivery_type")

    if delivery_type not in ("on_campus", "off_campus"):
        return jsonify({"error": MSG.DELIVERY_TYPE_INVALID}), 400

    location_id = data.get("delivery_location_id")
    user_lat = data.get("lat")
    user_lon = data.get("lon")

    if user_lat is not None or user_lon is not None:
        try:
            user_lat, user_lon = validate_coordinates(user_lat, user_lon)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    if not location_id:
        if data.get("delivery_type") == "off_campus" and user_lat is not None and user_lon is not None:
            # The reference resolver (events._get_campus_id): ?campus_id=, then the
            # X-Campus-ID header the campus gate sends, then the signed-in session.
            # Reading only the body and g.campus_id meant a guest -- who has no
            # g.campus_id, and whose fee request carries no campus_id in the body --
            # resolved to None. is_within_delivery_area() fails open on None (no
            # radius check at all) and find_nearest_gate() drops its campus filter,
            # so the nearest gate was picked from EVERY campus and the fee priced
            # against a gate the guest does not belong to.
            from app.routes.events import _get_campus_id
            campus_id = _get_campus_id()
            if not campus_id:
                # Same refusal /delivery/hostels and /delivery/gates already give.
                # Without a campus there is no radius to check and no gate pool to
                # pick from, and create_order refuses such an order anyway — so a
                # quote priced off some other campus's gate would only mislead.
                return jsonify({
                    "error": "Please select a campus to continue",
                    "code": "CAMPUS_SELECTION_REQUIRED",
                }), 400
            if not is_within_delivery_area(db, user_lat, user_lon, campus_id):
                return jsonify({"error": MSG.DELIVERY_OUTSIDE_AREA}), 400
            nearest = find_nearest_gate(db, user_lat, user_lon, campus_id)
            if nearest:
                location_id = nearest["id"]
            else:
                return jsonify({"error": "'delivery_location_id' is required"}), 400
        else:
            return jsonify({"error": "'delivery_location_id' is required"}), 400

    try:
        tier_free_avail = False
        if getattr(g, "user_id", None):
            try:
                from app.services.tier_service import resolve_perk
                if resolve_perk(g.user_id, "monthly_free_delivery"):
                    curr_m = datetime.now(timezone.utc).strftime("%Y-%m")
                    used = db.table("tier_monthly_perk_usage").select("id").eq("user_id", g.user_id).eq("month", curr_m).eq("perk_key", "monthly_free_delivery").execute() or []
                    tier_free_avail = not bool(used)
            except Exception as e:
                logger.warning("calculate_fee: tier free-delivery lookup failed for %s: %s", g.user_id, e)

        if delivery_type == "on_campus":
            hostel = (
                db.table("hostels")
                .select("*")
                .eq("id", location_id)
                .eq("is_active", "true")
                .single()
                .execute()
            )
            if not hostel:
                return jsonify({"error": MSG.DELIVERY_HOSTEL_NOT_FOUND}), 404
            hostel_fee = float(hostel.get("delivery_fee") or 0)
            return jsonify({
                "delivery_type": "on_campus",
                "delivery_fee": 0.0 if tier_free_avail else hostel_fee,
                "original_delivery_fee": hostel_fee,
                "hostel": hostel,
                "distance_km": None,
                "tier_free_delivery_available": tier_free_avail,
                "message": MSG.DELIVERY_FEE_CALCULATED,
            }), 200

        # off_campus
        gate = (
            db.table("gates")
            .select("*")
            .eq("id", location_id)
            .eq("is_active", "true")
            .single()
            .execute()
        )
        if not gate:
            return jsonify({"error": MSG.DELIVERY_GATE_NOT_FOUND}), 404
        fee, distance_km = calculate_off_campus_fee(gate, user_lat, user_lon)
        return jsonify({
            "delivery_type": "off_campus",
            "delivery_fee": 0.0 if tier_free_avail else fee,
            "original_delivery_fee": fee,
            "gate": gate,
            "distance_km": distance_km,
            "tier_free_delivery_available": tier_free_avail,
            "message": MSG.DELIVERY_FEE_CALCULATED,
        }), 200

    except Exception:
        logger.exception("calculate_fee: calculation failed")
        return jsonify({"error": MSG.ERR_UNEXPECTED}), 500


# ─────────────────────────────────────────────────────────────────────────────
# Admin — Hostels
# ─────────────────────────────────────────────────────────────────────────────

@delivery_bp.route("/admin/hostels", methods=["GET"])
@require_role("admin")
def admin_list_hostels():
    """
    List all hostels including inactive ones (admin only).
    ---
    tags: [Delivery Admin]
    responses:
      200:
        description: All hostels
    """
    db = get_user_client()
    try:
        campus_id = resolve_scoped_campus_id(as_uuid(request.args.get("campus_id")))
        q = db.table("hostels").select("*,gates(name)").order("name")
        if campus_id:
            q = q.eq("campus_id", campus_id)
        hostels = q.execute() or []
    except ValueError:
        return jsonify({"error": MSG.INVALID_CAMPUS_ID}), 400
    except (SupabaseError, requests.RequestException) as exc:
        return db_error_response(exc, "admin_list_hostels")
    return jsonify({"hostels": hostels}), 200


@delivery_bp.route("/admin/hostels", methods=["POST"])
@require_role("admin")
def admin_create_hostel():
    """
    Create a new on-campus hostel (admin only).
    ---
    tags: [Delivery Admin]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [name, delivery_fee]
          properties:
            name: {type: string, example: "Python Hall"}
            gate_id: {type: string, description: "The nearest campus gate"}
            delivery_fee: {type: number, example: 200}
            is_active: {type: boolean, default: true}
    responses:
      201:
        description: Hostel created
      400:
        description: Missing required field
    """
    db = get_user_client()
    try:
        data = _location_fields(request.get_json(force=True, silent=True), ("delivery_fee",))
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    for f in ["name", "delivery_fee"]:
        if data.get(f) is None:
            return jsonify({"error": MSG.FIELD_REQUIRED.format(field=f)}), 400

    campus_id = resolve_write_campus(data.get("campus_id"))
    if not campus_id:
        return jsonify({"error": MSG.CAMPUS_ID_REQUIRED}), 400
    try:
        if not _valid_hostel_gate(db, data.get("gate_id"), campus_id):
            return jsonify({"error": MSG.INVALID_INPUT}), 400
    except (SupabaseError, requests.RequestException) as exc:
        return db_error_response(exc, "hostel_gate_lookup")
    record = {
        "name": data["name"],
        "delivery_fee": float(data["delivery_fee"]),
        "is_active": bool(data.get("is_active", True)),
        "campus_id": campus_id,
    }
    if data.get("gate_id"):
        record["gate_id"] = data["gate_id"]

    try:
        result = db.table("hostels").insert(record)
        return jsonify(result[0] if isinstance(result, list) else result), 201
    except (SupabaseError, requests.RequestException) as exc:
        return db_error_response(exc, "delivery_location_write", MSG.DELIVERY_LOCATION_EXISTS)


@delivery_bp.route("/admin/hostels/<hostel_id>", methods=["PATCH"])
@require_role("admin")
def admin_update_hostel(hostel_id):
    """
    Update an on-campus hostel (admin only).
    ---
    tags: [Delivery Admin]
    parameters:
      - in: path
        name: hostel_id
        type: string
        required: true
    responses:
      200:
        description: Hostel updated
      404:
        description: Hostel not found
    """
    db = get_user_client()
    try:
        data = _location_fields(request.get_json(force=True, silent=True), ("delivery_fee",))
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    existing, error = _admin_location(db, "hostels", hostel_id)
    if error:
        return error
    try:
        if not _valid_hostel_gate(db, data.get("gate_id"), existing.get("campus_id")):
            return jsonify({"error": MSG.INVALID_INPUT}), 400
    except (SupabaseError, requests.RequestException) as exc:
        return db_error_response(exc, "hostel_gate_lookup")
    allowed = {"name", "gate_id", "delivery_fee", "is_active"}
    update = {k: v for k, v in data.items() if k in allowed}
    if not update:
        return jsonify({"error": MSG.NO_VALID_FIELDS}), 400
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        result = db.table("hostels").eq("id", hostel_id).update(update)
        if not result:
            return jsonify({"error": MSG.DELIVERY_HOSTEL_NOT_FOUND}), 404
        return jsonify(result[0] if isinstance(result, list) else result), 200
    except (SupabaseError, requests.RequestException) as exc:
        return db_error_response(exc, "delivery_location_write", MSG.DELIVERY_LOCATION_EXISTS)


@delivery_bp.route("/admin/hostels/<hostel_id>", methods=["DELETE"])
@require_role("admin")
def admin_delete_hostel(hostel_id):
    """
    Deactivate a hostel (admin only). Does not permanently delete.
    ---
    tags: [Delivery Admin]
    parameters:
      - in: path
        name: hostel_id
        type: string
        required: true
    responses:
      200:
        description: Hostel deactivated
      404:
        description: Hostel not found
    """
    db = get_user_client()
    existing, error = _admin_location(db, "hostels", hostel_id)
    if error:
        return error
    try:
        result = db.table("hostels").eq("id", hostel_id).update({
            "is_active": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        if not result:
            return jsonify({"error": MSG.DELIVERY_HOSTEL_NOT_FOUND}), 404
        return jsonify({"message": MSG.DELIVERY_HOSTEL_HIDDEN, "hostel_id": hostel_id}), 200
    except (SupabaseError, requests.RequestException) as exc:
        return db_error_response(exc, "delivery_location_write", MSG.DELIVERY_LOCATION_EXISTS)


def _gate_coordinates(lat, lon):
    """Gate coordinates come as a pair: both or neither. Off-campus gates carry them and both must be inside
    the supported region, because fees and nearest-gate selection are measured from them. On-campus gates
    have none (just a name and a price) and stay valid."""
    # a form that leaves the coordinate boxes empty (on-campus gates have none) sends "" - treat it as absent
    lat = None if isinstance(lat, str) and not lat.strip() else lat
    lon = None if isinstance(lon, str) and not lon.strip() else lon
    if lat is None and lon is None:
        return None, None
    if lat is None or lon is None:
        raise ValueError(MSG.COORDINATES_INVALID)
    return validate_coordinates(lat, lon)


# ─────────────────────────────────────────────────────────────────────────────
# Admin — Gates
# ─────────────────────────────────────────────────────────────────────────────

@delivery_bp.route("/admin/gates", methods=["GET"])
@require_role("admin")
def admin_list_gates():
    """
    List all gates including inactive (admin only).
    ---
    tags: [Delivery Admin]
    responses:
      200:
        description: All gates
    """
    db = get_user_client()
    try:
        campus_id = resolve_scoped_campus_id(as_uuid(request.args.get("campus_id")))
        q = db.table("gates").select("*").order("name")
        if campus_id:
            q = q.eq("campus_id", campus_id)
        gates = q.execute() or []
    except ValueError:
        return jsonify({"error": MSG.INVALID_CAMPUS_ID}), 400
    except (SupabaseError, requests.RequestException) as exc:
        return db_error_response(exc, "admin_list_gates")
    return jsonify({"gates": gates}), 200


@delivery_bp.route("/admin/gates", methods=["POST"])
@require_role("admin")
def admin_create_gate():
    """
    Create a delivery gate (admin only).
    ---
    tags: [Delivery Admin]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [name]
          properties:
            name: {type: string, example: "Main Gate"}
            lat: {type: number, example: 7.2985}
            lon: {type: number, example: 5.1421}
            base_fee: {type: number, default: 0, description: "Base fee in ₦"}
            rate_per_km: {type: number, default: 0, description: "₦ per km beyond base"}
            min_fee: {type: number, default: 0, description: "Minimum fee when no coordinates"}
            is_active: {type: boolean, default: true}
    responses:
      201:
        description: Gate created
      400:
        description: Missing required field
    """
    db = get_user_client()
    try:
        data = _location_fields(request.get_json(force=True, silent=True), ("base_fee", "rate_per_km", "min_fee"))
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    if not data.get("name"):
        return jsonify({"error": MSG.FIELD_REQUIRED.format(field="name")}), 400

    campus_id = resolve_write_campus(data.get('campus_id'))
    if not campus_id:
        return jsonify({'error': MSG.CAMPUS_ID_REQUIRED}), 400
    try:
        lat, lon = _gate_coordinates(data.get("lat"), data.get("lon"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    record = {
        "name": data["name"],
        "base_fee": float(data.get("base_fee") or 0),
        "rate_per_km": float(data.get("rate_per_km") or 0),
        "min_fee": float(data.get("min_fee") or 0),
        "is_active": bool(data.get("is_active", True)),
        "campus_id": campus_id,
    }
    if lat is not None:
        record["lat"] = lat
        record["lon"] = lon

    try:
        result = db.table("gates").insert(record)
        return jsonify(result[0] if isinstance(result, list) else result), 201
    except (SupabaseError, requests.RequestException) as exc:
        return db_error_response(exc, "delivery_location_write", MSG.DELIVERY_LOCATION_EXISTS)


@delivery_bp.route("/admin/gates/<gate_id>", methods=["PATCH"])
@require_role("admin")
def admin_update_gate(gate_id):
    """
    Update a delivery gate (admin only).
    ---
    tags: [Delivery Admin]
    parameters:
      - in: path
        name: gate_id
        type: string
        required: true
    responses:
      200:
        description: Gate updated
      404:
        description: Gate not found
    """
    db = get_user_client()
    try:
        data = _location_fields(request.get_json(force=True, silent=True), ("base_fee", "rate_per_km", "min_fee"))
    except ValueError:
        return jsonify({"error": MSG.INVALID_INPUT}), 400
    existing, error = _admin_location(db, "gates", gate_id)
    if error:
        return error
    allowed = {"name", "lat", "lon", "base_fee", "rate_per_km", "min_fee", "is_active"}
    update = {k: v for k, v in data.items() if k in allowed}
    if not update:
        return jsonify({"error": MSG.NO_VALID_FIELDS}), 400
    if "lat" in update or "lon" in update:
        try:
            update["lat"], update["lon"] = _gate_coordinates(update.get("lat", existing.get("lat")), update.get("lon", existing.get("lon")))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        result = db.table("gates").eq("id", gate_id).update(update)
        if not result:
            return jsonify({"error": MSG.DELIVERY_GATE_NOT_FOUND}), 404
        return jsonify(result[0] if isinstance(result, list) else result), 200
    except (SupabaseError, requests.RequestException) as exc:
        return db_error_response(exc, "delivery_location_write", MSG.DELIVERY_LOCATION_EXISTS)


@delivery_bp.route("/admin/gates/<gate_id>", methods=["DELETE"])
@require_role("admin")
def admin_delete_gate(gate_id):
    """
    Deactivate a gate (admin only). Does not permanently delete.
    ---
    tags: [Delivery Admin]
    parameters:
      - in: path
        name: gate_id
        type: string
        required: true
    responses:
      200:
        description: Gate deactivated
      404:
        description: Gate not found
    """
    db = get_user_client()
    existing, error = _admin_location(db, "gates", gate_id)
    if error:
        return error
    try:
        result = db.table("gates").eq("id", gate_id).update({
            "is_active": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        if not result:
            return jsonify({"error": MSG.DELIVERY_GATE_NOT_FOUND}), 404
        return jsonify({"message": MSG.DELIVERY_GATE_HIDDEN, "gate_id": gate_id}), 200
    except (SupabaseError, requests.RequestException) as exc:
        return db_error_response(exc, "delivery_location_write", MSG.DELIVERY_LOCATION_EXISTS)
