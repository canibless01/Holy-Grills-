"""Shared eligibility for the existing one-time push milestone, across clients."""


def has_registered_push(db, user_id):
    # Device ownership always comes from the authenticated/current milestone
    # user, never a supplied recipient or another account's browser session.
    return bool(db.table("device_tokens").select("id").eq("user_id", user_id)
                .in_("platform", ["web", "android"]).limit(1).execute() or [])
