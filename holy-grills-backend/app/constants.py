"""
Central application constants.
Single source of truth for role definitions and system-wide enumerations.
"""

ADMIN_ROLES = {"admin", "super_admin"}

# Brand tagline and the fallback value for the optional APP_TAGLINE env var
# (email template data, notification payloads). The fixed email sign-off line
# itself lives in app.utils.email.EMAIL_SIGNOFF.
APP_TAGLINE_DEFAULT = "Made with more than flame ❤️‍🔥"

# Campus Ambassador Programme staff. A community_manager may open the
# ambassador programme sections (tag list, promo distribution, activity
# tracking, monthly reviews) but can never issue financial rewards — every
# grant endpoint additionally checks ADMIN_ROLES server-side.
COMMUNITY_MANAGER_ROLE = "community_manager"
AMBASSADOR_STAFF_ROLES = ADMIN_ROLES | {COMMUNITY_MANAGER_ROLE}

VALID_ROLES = {"student", "admin", "kitchen", "rider", "super_admin", COMMUNITY_MANAGER_ROLE}
