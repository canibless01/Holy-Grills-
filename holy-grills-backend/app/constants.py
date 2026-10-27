"""
Central application constants.
Single source of truth for role definitions and system-wide enumerations.
"""

ADMIN_ROLES = {"admin", "super_admin"}

# Campus Ambassador Programme staff. A community_manager may open the
# ambassador programme sections (tag list, promo distribution, activity
# tracking, monthly reviews) but can never issue financial rewards — every
# grant endpoint additionally checks ADMIN_ROLES server-side.
COMMUNITY_MANAGER_ROLE = "community_manager"
AMBASSADOR_STAFF_ROLES = ADMIN_ROLES | {COMMUNITY_MANAGER_ROLE}

VALID_ROLES = {"student", "admin", "kitchen", "rider", "super_admin", COMMUNITY_MANAGER_ROLE}
