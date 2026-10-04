"""
app/routes/messages.py

Serves the user-facing copy catalog (``app/messages.py``) to the frontend.

Why: every user-facing string in this codebase already lives in ONE place —
``MSG`` — and the API responses use it. The frontend's own copy (toast titles,
validation errors, empty states) used to live only in the TypeScript source, so
a wording revamp meant two edits in two repos. This route closes that gap: the
client fetches the catalog once and renders ``MSG.*`` values for its own copy
too, so a revamp is a single-file change.

Contract:
    GET /api/messages → 200 {"messages": {"<KEY>": "<text>", ...}, "count": N}

The catalog is public: it is copy shown to users by definition, carries no
secrets, and is cacheable. The frontend falls back to its own bundled default
when a key is missing (or the request fails), so a client older than the
registry, or an offline load, still renders real text — never a raw key.

Frontend-owned copy lives under the ``FE_`` prefix in the registry; keys without
the prefix are API/notification messages that the client mostly receives in
response bodies. ``npm run messages:check`` (frontend) fails the build when a
``t('FE_*', '…')`` call site and the registry disagree.
"""

from flask import Blueprint, jsonify

from app.messages import MSG, resolve_env_only

messages_bp = Blueprint("messages", __name__)


@messages_bp.route("", methods=["GET"])
def list_messages():
    """
    The user-facing copy catalog.
    ---
    tags: [Meta]
    security: []
    responses:
      200:
        description: Every MSG constant as a key → text map
    """
    catalog = {
        key: resolve_env_only(value)     # {currency}/{platform} come from the environment
        for key, value in vars(MSG).items()
        if not key.startswith("_") and isinstance(value, str)
    }
    response = jsonify({"messages": catalog, "count": len(catalog)})
    # Copy changes at deploy time, not per request — let browsers and the CDN hold it.
    response.headers["Cache-Control"] = "public, max-age=300"
    return response, 200
