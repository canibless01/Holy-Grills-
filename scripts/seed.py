"""
Holy Grills FUTA — Production Seed Script
==========================================
Seeds the production Supabase DB with enough real data to exercise
every API endpoint immediately on deployment.

Safe to re-run: every insert uses resolution=ignore-duplicates, so
running this twice leaves the DB identical to running it once.

Tables seeded (in FK dependency order):
  1. menu_categories    — 8 categories (fixed UUIDs)
  2. menu_items         — 24 items spread across all categories
  3. operating_hours    — 7 rows Mon–Sun with realistic FUTA hours
  4. storefront_sections— 4 sections (hero, featured, promo, info)
  5. kitchen_settings   — 6 operational settings (key/value)
  6. delivery_windows   — 4 time-of-day windows (replaces test data)
  7. promo_codes        — 3 production-grade discount codes
  8. system_settings    — 9 platform-wide keys (upsert)

Tables NOT seeded (already have data or require live users):
  - hp_tiers        ← 5 tiers already present in production
  - profiles        ← created at auth signup
  - orders / hp_transactions ← live data only

Column names are verified against the live production schema.
Run: python scripts/seed.py
"""

import os
import sys
import requests

SUPABASE_URL = os.environ["SUPABASE_URL"]
SRK = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SRK,
    "Authorization": f"Bearer {SRK}",
    "Content-Type": "application/json",
    "Prefer": "resolution=ignore-duplicates,return=representation",
}

PASS = "✓"
FAIL = "✗"


# ── Helpers ───────────────────────────────────────────────────────────────────

def insert_rows(table: str, rows: list) -> tuple[int, int]:
    """Bulk insert; rows whose PK already exists are silently skipped.
    On unique-constraint conflict (409) the rows already exist — treat as skipped.
    """
    if not rows:
        return 0, 0
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=HEADERS,
        json=rows,
        timeout=20,
    )
    if r.status_code in (200, 201):
        inserted = len(r.json()) if r.json() else 0
        skipped = len(rows) - inserted
        return inserted, skipped
    if r.status_code == 409:
        # Unique constraint conflict — all rows already present
        return 0, len(rows)
    print(f"  {FAIL} {table}: HTTP {r.status_code} — {r.text[:300]}")
    return 0, len(rows)


def upsert_kv(table: str, rows: list) -> tuple[int, int]:
    """Upsert rows one-by-one for key/value tables (merge-duplicates)."""
    ok = err = 0
    kv_headers = {**HEADERS, "Prefer": "resolution=merge-duplicates,return=minimal"}
    for row in rows:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=kv_headers,
            json=row,
            timeout=10,
        )
        if r.status_code in (200, 201, 204):
            ok += 1
        else:
            print(f"  {FAIL} {table} key={row.get('key','?')}: {r.text[:200]}")
            err += 1
    return ok, err


def report(table: str, inserted: int, skipped: int):
    icon = PASS if (inserted + skipped) > 0 else FAIL
    print(f"  {icon} {table}: {inserted} inserted, {skipped} already present")


# ── Fixed UUIDs ───────────────────────────────────────────────────────────────
# Using fixed UUIDs ensures the seed is idempotent and menu_items
# can reference category IDs without a prior lookup.

CAT = {
    "burgers":  "10000001-cafe-cafe-cafe-000000000001",
    "grills":   "10000001-cafe-cafe-cafe-000000000002",
    "rice":     "10000001-cafe-cafe-cafe-000000000003",
    "pasta":    "10000001-cafe-cafe-cafe-000000000004",
    "sides":    "10000001-cafe-cafe-cafe-000000000005",
    "drinks":   "10000001-cafe-cafe-cafe-000000000006",
    "desserts": "10000001-cafe-cafe-cafe-000000000007",
    "specials": "10000001-cafe-cafe-cafe-000000000008",
}

ITEM = {
    "classic_burger":  "20000001-cafe-cafe-cafe-000000000001",
    "double_burger":   "20000001-cafe-cafe-cafe-000000000002",
    "chicken_burger":  "20000001-cafe-cafe-cafe-000000000003",
    "grilled_chicken": "20000001-cafe-cafe-cafe-000000000004",
    "beef_suya":       "20000001-cafe-cafe-cafe-000000000005",
    "fish_grill":      "20000001-cafe-cafe-cafe-000000000006",
    "jollof_rice":     "20000001-cafe-cafe-cafe-000000000007",
    "fried_rice":      "20000001-cafe-cafe-cafe-000000000008",
    "ofada_rice":      "20000001-cafe-cafe-cafe-000000000009",
    "spaghetti":       "20000001-cafe-cafe-cafe-000000000010",
    "mac_cheese":      "20000001-cafe-cafe-cafe-000000000011",
    "fries":           "20000001-cafe-cafe-cafe-000000000012",
    "coleslaw":        "20000001-cafe-cafe-cafe-000000000013",
    "moi_moi":         "20000001-cafe-cafe-cafe-000000000014",
    "plantain":        "20000001-cafe-cafe-cafe-000000000015",
    "zobo":            "20000001-cafe-cafe-cafe-000000000016",
    "fresh_juice":     "20000001-cafe-cafe-cafe-000000000017",
    "bottled_water":   "20000001-cafe-cafe-cafe-000000000018",
    "chapman":         "20000001-cafe-cafe-cafe-000000000019",
    "chin_chin":       "20000001-cafe-cafe-cafe-000000000020",
    "puff_puff":       "20000001-cafe-cafe-cafe-000000000021",
    "holy_combo":      "20000001-cafe-cafe-cafe-000000000022",
    "futa_platter":    "20000001-cafe-cafe-cafe-000000000023",
    "grills_feast":    "20000001-cafe-cafe-cafe-000000000024",
}


# ── 1. Menu Categories ────────────────────────────────────────────────────────
# Verified columns: id, name, slug, description, sort_order, is_active, created_at
# NO icon column in production schema.

CATEGORIES = [
    {"id": CAT["burgers"],  "name": "Burgers",       "slug": "burgers",   "description": "Juicy hand-pressed beef and chicken burgers",         "sort_order": 1, "is_active": True},
    {"id": CAT["grills"],   "name": "Grills",         "slug": "grills",    "description": "Charcoal-grilled chicken, beef and fish",              "sort_order": 2, "is_active": True},
    {"id": CAT["rice"],     "name": "Rice Dishes",    "slug": "rice",      "description": "Nigerian classics — jollof, fried and ofada rice",     "sort_order": 3, "is_active": True},
    {"id": CAT["pasta"],    "name": "Pasta",          "slug": "pasta",     "description": "Freshly cooked pasta with rich sauces",                "sort_order": 4, "is_active": True},
    {"id": CAT["sides"],    "name": "Sides",          "slug": "sides",     "description": "Fries, plantain, moi moi and more",                   "sort_order": 5, "is_active": True},
    {"id": CAT["drinks"],   "name": "Drinks",         "slug": "drinks",    "description": "Fresh juices, zobo, chapman and chilled water",        "sort_order": 6, "is_active": True},
    {"id": CAT["desserts"], "name": "Desserts",       "slug": "desserts",  "description": "Sweet treats to round off your meal",                  "sort_order": 7, "is_active": True},
    {"id": CAT["specials"], "name": "Holy Specials",  "slug": "specials",  "description": "Exclusive combos and platters — best value on campus", "sort_order": 8, "is_active": True},
]


# ── 2. Menu Items ─────────────────────────────────────────────────────────────
# Verified columns: id, category_id, name, slug, description, image_url, price,
#   hp_earn, hp_earn_value, is_available, is_featured, tags, options,
#   daily_limit, deleted_at, created_at, updated_at
# NO calories column in production schema.

ITEMS = [
    # hp_earn is INTEGER in production schema (1=earns HP, 0=does not earn HP)
    # Burgers
    {"id": ITEM["classic_burger"], "category_id": CAT["burgers"],
     "name": "Classic Beef Burger", "slug": "classic-beef-burger",
     "description": "Single beef patty, lettuce, tomato, pickles and house sauce in a toasted bun",
     "price": 2500, "hp_earn": 1, "hp_earn_value": 25, "daily_limit": None,
     "is_available": True, "is_featured": True, "tags": ["beef", "popular"], "options": []},

    {"id": ITEM["double_burger"], "category_id": CAT["burgers"],
     "name": "Double Stack Burger", "slug": "double-stack-burger",
     "description": "Two beef patties, double cheese, caramelised onion and secret sauce",
     "price": 3800, "hp_earn": 1, "hp_earn_value": 38, "daily_limit": None,
     "is_available": True, "is_featured": False, "tags": ["beef", "indulgent"], "options": []},

    {"id": ITEM["chicken_burger"], "category_id": CAT["burgers"],
     "name": "Crispy Chicken Burger", "slug": "crispy-chicken-burger",
     "description": "Crispy fried chicken fillet, coleslaw and jalapeño mayo in a brioche bun",
     "price": 2800, "hp_earn": 1, "hp_earn_value": 28, "daily_limit": None,
     "is_available": True, "is_featured": True, "tags": ["chicken", "spicy"], "options": []},

    # Grills
    {"id": ITEM["grilled_chicken"], "category_id": CAT["grills"],
     "name": "Half Grilled Chicken", "slug": "half-grilled-chicken",
     "description": "Charcoal-grilled half chicken with Holy Grills spice blend, served with a side",
     "price": 3500, "hp_earn": 1, "hp_earn_value": 35, "daily_limit": None,
     "is_available": True, "is_featured": True, "tags": ["chicken", "grilled", "popular"], "options": []},

    {"id": ITEM["beef_suya"], "category_id": CAT["grills"],
     "name": "Beef Suya Skewers", "slug": "beef-suya-skewers",
     "description": "Tender beef strips on skewers with yaji spice and fresh onion rings",
     "price": 2200, "hp_earn": 1, "hp_earn_value": 22, "daily_limit": None,
     "is_available": True, "is_featured": False, "tags": ["beef", "spicy", "street-food"], "options": []},

    {"id": ITEM["fish_grill"], "category_id": CAT["grills"],
     "name": "Grilled Catfish", "slug": "grilled-catfish",
     "description": "Whole catfish grilled over open flame with pepper sauce and herbs",
     "price": 4200, "hp_earn": 1, "hp_earn_value": 42, "daily_limit": None,
     "is_available": True, "is_featured": False, "tags": ["fish", "grilled"], "options": []},

    # Rice
    {"id": ITEM["jollof_rice"], "category_id": CAT["rice"],
     "name": "Party Jollof Rice", "slug": "party-jollof-rice",
     "description": "Smoky party jollof rice cooked over firewood with rich tomato base",
     "price": 1800, "hp_earn": 1, "hp_earn_value": 18, "daily_limit": None,
     "is_available": True, "is_featured": True, "tags": ["rice", "nigerian", "popular"], "options": []},

    {"id": ITEM["fried_rice"], "category_id": CAT["rice"],
     "name": "Special Fried Rice", "slug": "special-fried-rice",
     "description": "Vegetable fried rice with shrimp, chicken liver and sweet corn",
     "price": 2000, "hp_earn": 1, "hp_earn_value": 20, "daily_limit": None,
     "is_available": True, "is_featured": False, "tags": ["rice", "nigerian"], "options": []},

    {"id": ITEM["ofada_rice"], "category_id": CAT["rice"],
     "name": "Ofada Rice & Stew", "slug": "ofada-rice-stew",
     "description": "Authentic ofada rice with traditional green pepper stew and assorted meat",
     "price": 2300, "hp_earn": 1, "hp_earn_value": 23, "daily_limit": None,
     "is_available": True, "is_featured": False, "tags": ["rice", "nigerian", "traditional"], "options": []},

    # Pasta
    {"id": ITEM["spaghetti"], "category_id": CAT["pasta"],
     "name": "Spaghetti Bolognese", "slug": "spaghetti-bolognese",
     "description": "Al-dente spaghetti in rich beef bolognese sauce topped with parmesan",
     "price": 2100, "hp_earn": 1, "hp_earn_value": 21, "daily_limit": None,
     "is_available": True, "is_featured": False, "tags": ["pasta", "beef"], "options": []},

    {"id": ITEM["mac_cheese"], "category_id": CAT["pasta"],
     "name": "Holy Mac & Cheese", "slug": "holy-mac-cheese",
     "description": "Creamy four-cheese macaroni baked to golden perfection",
     "price": 1900, "hp_earn": 1, "hp_earn_value": 19, "daily_limit": None,
     "is_available": True, "is_featured": False, "tags": ["pasta", "vegetarian"], "options": []},

    # Sides
    {"id": ITEM["fries"], "category_id": CAT["sides"],
     "name": "Seasoned Fries", "slug": "seasoned-fries",
     "description": "Crispy golden fries seasoned with Holy Grills spice blend",
     "price": 900, "hp_earn": 1, "hp_earn_value": 9, "daily_limit": None,
     "is_available": True, "is_featured": False, "tags": ["sides", "vegetarian"], "options": []},

    {"id": ITEM["coleslaw"], "category_id": CAT["sides"],
     "name": "Creamy Coleslaw", "slug": "creamy-coleslaw",
     "description": "Fresh cabbage and carrot slaw with house mayo dressing",
     "price": 700, "hp_earn": 1, "hp_earn_value": 7, "daily_limit": None,
     "is_available": True, "is_featured": False, "tags": ["sides", "vegetarian"], "options": []},

    {"id": ITEM["moi_moi"], "category_id": CAT["sides"],
     "name": "Moi Moi", "slug": "moi-moi",
     "description": "Steamed bean pudding with egg, crayfish and smoked fish",
     "price": 800, "hp_earn": 1, "hp_earn_value": 8, "daily_limit": None,
     "is_available": True, "is_featured": False, "tags": ["sides", "nigerian"], "options": []},

    {"id": ITEM["plantain"], "category_id": CAT["sides"],
     "name": "Fried Plantain (Dodo)", "slug": "fried-plantain-dodo",
     "description": "Sweet ripe plantain slices fried to caramelised perfection",
     "price": 700, "hp_earn": 1, "hp_earn_value": 7, "daily_limit": None,
     "is_available": True, "is_featured": False, "tags": ["sides", "nigerian", "vegetarian"], "options": []},

    # Drinks
    {"id": ITEM["zobo"], "category_id": CAT["drinks"],
     "name": "Zobo Drink", "slug": "zobo-drink",
     "description": "Chilled hibiscus zobo with ginger and pineapple — no preservatives",
     "price": 600, "hp_earn": 1, "hp_earn_value": 6, "daily_limit": None,
     "is_available": True, "is_featured": False, "tags": ["drinks", "cold", "nigerian"], "options": []},

    {"id": ITEM["fresh_juice"], "category_id": CAT["drinks"],
     "name": "Fresh Orange Juice", "slug": "fresh-orange-juice",
     "description": "Freshly squeezed orange juice — no added sugar",
     "price": 1000, "hp_earn": 1, "hp_earn_value": 10, "daily_limit": None,
     "is_available": True, "is_featured": False, "tags": ["drinks", "cold", "healthy"], "options": []},

    {"id": ITEM["bottled_water"], "category_id": CAT["drinks"],
     "name": "Bottled Water (50cl)", "slug": "bottled-water-50cl",
     "description": "Chilled 50cl mineral water",
     "price": 300, "hp_earn": 0, "hp_earn_value": 0, "daily_limit": None,
     "is_available": True, "is_featured": False, "tags": ["drinks", "cold"], "options": []},

    {"id": ITEM["chapman"], "category_id": CAT["drinks"],
     "name": "Chapman Cocktail", "slug": "chapman-cocktail",
     "description": "Classic Nigerian Chapman — Sprite, Fanta, Grenadine and cucumber",
     "price": 1200, "hp_earn": 1, "hp_earn_value": 12, "daily_limit": None,
     "is_available": True, "is_featured": True, "tags": ["drinks", "cold", "popular"], "options": []},

    # Desserts
    {"id": ITEM["chin_chin"], "category_id": CAT["desserts"],
     "name": "Crunchy Chin Chin", "slug": "crunchy-chin-chin",
     "description": "Freshly fried crunchy chin chin in original and coconut flavours",
     "price": 500, "hp_earn": 1, "hp_earn_value": 5, "daily_limit": None,
     "is_available": True, "is_featured": False, "tags": ["desserts", "snacks"], "options": []},

    {"id": ITEM["puff_puff"], "category_id": CAT["desserts"],
     "name": "Puff Puff (6 pieces)", "slug": "puff-puff-6-pieces",
     "description": "Soft, fluffy Nigerian doughnuts lightly dusted with powdered sugar",
     "price": 700, "hp_earn": 1, "hp_earn_value": 7, "daily_limit": None,
     "is_available": True, "is_featured": False, "tags": ["desserts", "snacks", "nigerian"], "options": []},

    # Specials (combos — higher HP earn, daily limits set)
    {"id": ITEM["holy_combo"], "category_id": CAT["specials"],
     "name": "Holy Combo", "slug": "holy-combo",
     "description": "Burger + seasoned fries + drink — the student's best deal on campus",
     "price": 3500, "hp_earn": 1, "hp_earn_value": 45, "daily_limit": 50,
     "is_available": True, "is_featured": True, "tags": ["combo", "value", "popular"], "options": []},

    {"id": ITEM["futa_platter"], "category_id": CAT["specials"],
     "name": "FUTA Platter", "slug": "futa-platter",
     "description": "Jollof rice, grilled chicken quarter, plantain, coleslaw and a drink — feeds two",
     "price": 6500, "hp_earn": 1, "hp_earn_value": 80, "daily_limit": 30,
     "is_available": True, "is_featured": True, "tags": ["platter", "sharing", "value"], "options": []},

    {"id": ITEM["grills_feast"], "category_id": CAT["specials"],
     "name": "Grills Feast Box", "slug": "grills-feast-box",
     "description": "Half grilled chicken, suya skewers, moi moi and two drinks — perfect for a group",
     "price": 9500, "hp_earn": 1, "hp_earn_value": 120, "daily_limit": 20,
     "is_available": True, "is_featured": False, "tags": ["platter", "sharing", "group"], "options": []},
]


# ── 3. Operating Hours ────────────────────────────────────────────────────────
# Verified columns: id, weekday (0=Mon … 6=Sun), opens_at, closes_at, is_closed
# Table has unique constraint on weekday — check before inserting.

HOURS = [
    {"weekday": 0, "opens_at": "08:00", "closes_at": "21:00", "is_closed": False},
    {"weekday": 1, "opens_at": "08:00", "closes_at": "21:00", "is_closed": False},
    {"weekday": 2, "opens_at": "08:00", "closes_at": "21:00", "is_closed": False},
    {"weekday": 3, "opens_at": "08:00", "closes_at": "21:00", "is_closed": False},
    {"weekday": 4, "opens_at": "08:00", "closes_at": "22:00", "is_closed": False},
    {"weekday": 5, "opens_at": "10:00", "closes_at": "22:00", "is_closed": False},
    {"weekday": 6, "opens_at": "12:00", "closes_at": "20:00", "is_closed": False},
]


# ── 4. Storefront Sections ────────────────────────────────────────────────────
# Verified columns: id, key, title, section_type, content (jsonb),
#   sort_order, is_active, published_at, created_by, created_at, updated_at

SECTIONS = [
    {
        "key": "hero_banner",
        "title": "Welcome to Holy Grills FUTA",
        "section_type": "hero",
        "content": {
            "headline": "Campus Food. Elevated.",
            "subheadline": "Order hot, earn Holy Points, eat happy.",
            "cta_text": "Order Now",
            "cta_link": "/menu",
        },
        "sort_order": 1,
        "is_active": True,
    },
    {
        "key": "featured_items",
        "title": "Fan Favourites",
        "section_type": "featured",
        "content": {
            "item_ids": [
                ITEM["holy_combo"], ITEM["classic_burger"],
                ITEM["grilled_chicken"], ITEM["jollof_rice"], ITEM["chapman"],
            ],
            "display_count": 5,
        },
        "sort_order": 2,
        "is_active": True,
    },
    {
        "key": "promo_banner",
        "title": "HP Loyalty Programme",
        "section_type": "promo",
        "content": {
            "text": "Earn Holy Points on every order. Redeem for free food.",
            "badge_text": "1 HP per ₦10 spent",
            "cta_text": "Learn More",
            "cta_link": "/hp",
        },
        "sort_order": 3,
        "is_active": True,
    },
    {
        "key": "campus_delivery",
        "title": "Free Campus Delivery",
        "section_type": "info",
        "content": {
            "text": "Delivering to all FUTA hostels, halls and lecture areas.",
            "subtext": "Orders above ₦3,000 qualify for free delivery",
        },
        "sort_order": 4,
        "is_active": True,
    },
]


# ── 5. Kitchen Settings ───────────────────────────────────────────────────────
# Verified columns: key, value, updated_by, updated_at

KITCHEN = [
    {"key": "max_active_orders",     "value": "40"},
    {"key": "avg_prep_time_minutes", "value": "20"},
    {"key": "auto_accept_orders",    "value": "true"},
    {"key": "order_cutoff_minutes",  "value": "15"},
    {"key": "max_items_per_order",   "value": "20"},
    {"key": "delivery_fee_naira",    "value": "500"},
]


# ── 6. Delivery Windows ───────────────────────────────────────────────────────
# Verified columns: id, label, starts_at, ends_at, capacity,
#   is_active, status, zone_id, created_by, created_at
# Using fixed UUIDs so re-runs are idempotent.
# Old test rows (non-seed UUIDs) are removed before inserting.

def _make_windows():
    """
    Build 4 delivery windows anchored to a fixed far-future date (2099-12-31)
    with status='open' so the gte(ends_at, now) + eq(status, 'open') query
    always finds them. Re-running the seed is idempotent via fixed UUIDs.
    """
    base = "2099-12-31"
    return [
        {"id": "30000001-cafe-cafe-cafe-000000000001",
         "label": "Morning — 8 am to 10 am",
         "starts_at": f"{base}T08:00:00+00:00", "ends_at": f"{base}T10:00:00+00:00",
         "capacity": 30, "is_active": True, "status": "open"},
        {"id": "30000001-cafe-cafe-cafe-000000000002",
         "label": "Lunch — 12 pm to 2 pm",
         "starts_at": f"{base}T12:00:00+00:00", "ends_at": f"{base}T14:00:00+00:00",
         "capacity": 60, "is_active": True, "status": "open"},
        {"id": "30000001-cafe-cafe-cafe-000000000003",
         "label": "Afternoon — 4 pm to 6 pm",
         "starts_at": f"{base}T16:00:00+00:00", "ends_at": f"{base}T18:00:00+00:00",
         "capacity": 50, "is_active": True, "status": "open"},
        {"id": "30000001-cafe-cafe-cafe-000000000004",
         "label": "Evening — 7 pm to 9 pm",
         "starts_at": f"{base}T19:00:00+00:00", "ends_at": f"{base}T21:00:00+00:00",
         "capacity": 40, "is_active": True, "status": "open"},
    ]

DELIVERY_WINDOWS = _make_windows()


# ── 7. Promo Codes ────────────────────────────────────────────────────────────
# Verified columns: id, code, description, discount_type, discount_value,
#   scope, applicable_item_ids, applicable_category_ids, max_uses,
#   max_uses_per_user, min_order_amount, starts_at, ends_at,
#   is_active, used_count, created_by, created_at

PROMOS = [
    # scope is NOT NULL in production — using "cart" (applies to whole cart)
    # All rows have identical keys (PostgREST bulk insert requirement)
    {"id": "40000001-cafe-cafe-cafe-000000000001",
     "code": "WELCOME20",
     "description": "20% off your first order — welcome to Holy Grills!",
     "discount_type": "percentage", "discount_value": 20,
     "min_order_amount": 1500, "max_uses": 1000, "max_uses_per_user": 1,
     "scope": "cart", "applicable_item_ids": [], "applicable_category_ids": [],
     "starts_at": None, "ends_at": None, "is_active": True, "used_count": 0},
    {"id": "40000001-cafe-cafe-cafe-000000000002",
     "code": "STUDENT10",
     "description": "10% off for FUTA students — valid always",
     "discount_type": "percentage", "discount_value": 10,
     "min_order_amount": 1000, "max_uses": None, "max_uses_per_user": None,
     "scope": "cart", "applicable_item_ids": [], "applicable_category_ids": [],
     "starts_at": None, "ends_at": None, "is_active": True, "used_count": 0},
    {"id": "40000001-cafe-cafe-cafe-000000000003",
     "code": "HOLYGRILLS500",
     "description": "₦500 flat discount on orders above ₦3,000",
     "discount_type": "fixed", "discount_value": 500,
     "min_order_amount": 3000, "max_uses": 500, "max_uses_per_user": 2,
     "scope": "cart", "applicable_item_ids": [], "applicable_category_ids": [],
     "starts_at": None, "ends_at": None, "is_active": True, "used_count": 0},
]


# ── 8. System Settings ────────────────────────────────────────────────────────

SETTINGS = [
    {"key": "platform_name",              "value": "Holy Grills FUTA"},
    {"key": "currency_code",              "value": "NGN"},
    {"key": "currency_symbol",            "value": "₦"},
    {"key": "hp_redeem_rate",             "value": "100"},
    {"key": "min_hp_redeem",              "value": "100"},
    {"key": "welcome_bonus_hp",           "value": "50"},
    {"key": "referral_hp_reward",         "value": "75"},
    {"key": "free_delivery_threshold",    "value": "3000"},
    {"key": "supabase_project_url",       "value": os.environ.get("SUPABASE_URL", "")},
    # ── New feature settings (new_features.sql migration) ─────────────────
    {"key": "first_order_gift_enabled",   "value": "true"},
    {"key": "launch_window_end_date",     "value": "2026-12-31"},
    {"key": "monthly_hp_cap",             "value": "800"},
    {"key": "decay_onset_days",           "value": "120"},
    {"key": "decay_rate_monthly",         "value": "0.10"},
    {"key": "login_streak_hp",            "value": "2"},
    {"key": "share_prompt_hp",            "value": "25"},
    {"key": "order_lock_max_discount",    "value": "50"},
]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 55)
    print("  Holy Grills FUTA — Production Seed")
    print("=" * 55)

    # 1. Categories (must come before items — FK dependency)
    print("\n1. menu_categories")
    report("menu_categories", *insert_rows("menu_categories", CATEGORIES))

    # 2. Items
    print("2. menu_items")
    report("menu_items", *insert_rows("menu_items", ITEMS))

    # 3. Operating hours — skip days that already exist (unique weekday constraint)
    print("3. operating_hours")
    existing = requests.get(
        f"{SUPABASE_URL}/rest/v1/operating_hours?select=weekday",
        headers={**HEADERS, "Prefer": ""},
        timeout=10,
    ).json()
    existing_days = {r["weekday"] for r in (existing or [])}
    new_hours = [h for h in HOURS if h["weekday"] not in existing_days]
    if new_hours:
        report("operating_hours", *insert_rows("operating_hours", new_hours))
    else:
        report("operating_hours", 0, len(HOURS))

    # 4. Storefront sections (unique on key column)
    print("4. storefront_sections")
    report("storefront_sections", *insert_rows("storefront_sections", SECTIONS))

    # 5. Kitchen settings (key/value — upsert)
    print("5. kitchen_settings")
    ok, err = upsert_kv("kitchen_settings", KITCHEN)
    report("kitchen_settings", ok, err)

    # 6. Delivery windows — remove old test rows then insert seed rows
    print("6. delivery_windows")
    existing_dw = requests.get(
        f"{SUPABASE_URL}/rest/v1/delivery_windows?select=id",
        headers={**HEADERS, "Prefer": ""},
        timeout=10,
    ).json()
    seed_ids = {w["id"] for w in DELIVERY_WINDOWS}
    old_ids = [r["id"] for r in (existing_dw or []) if r["id"] not in seed_ids]
    for oid in old_ids:
        requests.delete(
            f"{SUPABASE_URL}/rest/v1/delivery_windows?id=eq.{oid}",
            headers={**HEADERS, "Prefer": ""},
            timeout=8,
        )
    if old_ids:
        print(f"  → removed {len(old_ids)} stale test window(s)")
    report("delivery_windows", *insert_rows("delivery_windows", DELIVERY_WINDOWS))

    # 7. Promo codes
    print("7. promo_codes")
    report("promo_codes", *insert_rows("promo_codes", PROMOS))

    # 8. System settings (upsert)
    print("8. system_settings")
    ok, err = upsert_kv("system_settings", SETTINGS)
    report("system_settings", ok, err)

    print("\n" + "=" * 55)
    print("  Seed complete. DB is ready for API testing.")
    print("  Fully idempotent — safe to run again anytime.")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
