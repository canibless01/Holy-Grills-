"""Campus scoping for reference data that is either global (campus_id IS NULL, super_admin only)
or belongs to one campus (that campus's admin)."""
from flask import g, abort

from app.messages import MSG
from app.middleware.auth import assert_owns_campus, header_campus_id
from app.utils.validators import validate_uuid


def as_campus_id(value):
    """None or '' -> None. A valid UUID string -> lowercase. Anything else raises ValueError."""
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not validate_uuid(value):
        raise ValueError("invalid campus_id")
    return value.lower()


def campus_or_global(q, campus_id, none_means_all=False):
    """Restrict a query to global rows plus one campus's rows.
    campus_id must already be validated (it goes into a raw or_ filter).
    No campus: global rows only, or every row when none_means_all=True."""
    if campus_id:
        return q.or_(f"campus_id.eq.{campus_id},campus_id.is.null")
    if none_means_all:
        return q
    return q.is_("campus_id", "null")


def prefer_campus_rows(rows, key):
    """When a campus row and a global row share the same key, keep the campus row. Keeps first-seen order."""
    chosen = {}
    for row in rows:
        k = key(row)
        if k not in chosen or (row.get("campus_id") and not chosen[k].get("campus_id")):
            chosen[k] = row
    return list(chosen.values())


def public_campus(requested):
    """Guests choose a campus; users default to their own; super_admin is scoped only by the request."""
    if getattr(g, "user_role", None) == "super_admin":
        return requested
    return requested or getattr(g, "campus_id", None)


def resolve_write_campus(requested):
    """Campus a NEW row belongs to. super_admin: the requested campus, or None (global row).
    Anyone else: their own campus; naming a different campus is 403."""
    assert_owns_campus(requested)
    if getattr(g, "user_role", None) == "super_admin":
        # Fall back to the campus selected in the admin header switcher
        # (X-Campus-ID) so admin writes land on the campus being viewed.
        return requested or header_campus_id() or None
    return getattr(g, "campus_id", None)


def assert_can_modify(record_campus_id):
    """super_admin: any row. Campus admin: only rows of their own campus (global rows are super_admin-only)."""
    if getattr(g, "user_role", None) == "super_admin":
        return
    if not record_campus_id or record_campus_id != getattr(g, "campus_id", None):
        abort(403, description=MSG.RESOURCE_ACCESS_DENIED)


# Note: assert_owns_campus lets a NULL record campus through for non-super_admin, so it is not used
# to guard edits here; assert_can_modify is (confirmed at ADM-10).
