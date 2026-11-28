"""Feature flag lookup — is a named feature switched on for a campus?"""

from app.db import get_db
from app.utils.logger import get_logger

logger = get_logger(__name__)


def is_feature_enabled(feature_name: str, campus_id: str = None) -> bool:
    """
    True if the named feature is active. Checks the campus-specific row first,
    falls back to a global (campus_id IS NULL) row, defaults to False (fail closed)
    if no row exists at all for this feature, or if the lookup itself fails — a DB
    error here must not turn into a 500 on every gated route; it should behave the
    same as "flag not configured".

    Uses get_db() deliberately: this is an internal, system-triggered check (not a
    personal read), so it behaves the same from a request handler or a cron job.
    """
    if campus_id is None:
        from flask import has_request_context, g
        if has_request_context():
            from app.middleware.auth import resolve_scoped_campus_id, header_campus_id
            campus_id = resolve_scoped_campus_id()
            if not getattr(g, 'user_id', None) and getattr(g, 'user_role', None) != 'super_admin':
                campus_id = campus_id or header_campus_id()
    try:
        db = get_db()
        if campus_id:
            row = (
                db.table("feature_flags")
                .select("is_active")
                .eq("feature_name", feature_name)
                .eq("campus_id", campus_id)
                .single()
                .execute()
            )
            if row is not None:
                return bool(row.get("is_active"))
        row = (
            db.table("feature_flags")
            .select("is_active")
            .eq("feature_name", feature_name)
            .is_("campus_id", "null")
            .single()
            .execute()
        )
        return bool(row.get("is_active")) if row else False
    except Exception:
        logger.warning("is_feature_enabled(%r, campus_id=%r) lookup failed — failing closed",
                       feature_name, campus_id, exc_info=True)
        return False
