"""
Economics Dashboard Service — aggregation queries for admin economics reporting.
"""
from app.services.economics_service import _get_econ_setting


def get_economics_overview(db, start_date: str = None, end_date: str = None, campus_id: str = None) -> dict:
    orders_q = db.table("orders").select("subtotal").eq("status", "delivered")
    if start_date:
        orders_q = orders_q.gte("created_at", start_date)
    if end_date:
        orders_q = orders_q.lte("created_at", end_date)
    if campus_id:
        orders_q = orders_q.eq("campus_id", campus_id)
    orders = orders_q.execute() or []
    food_revenue = sum(float(o["subtotal"] or 0) for o in orders)

    hp_tx_q = db.table("hp_transactions").select("amount,type,source")
    if start_date:
        hp_tx_q = hp_tx_q.gte("created_at", start_date)
    if end_date:
        hp_tx_q = hp_tx_q.lte("created_at", end_date)
    if campus_id:
        hp_tx_q = hp_tx_q.eq("campus_id", campus_id)
    hp_tx = hp_tx_q.execute() or []
    hp_issued = sum(t["amount"] for t in hp_tx if t.get("type") == "earn" and t.get("source") == "food_order")
    hp_redeemed = sum(-t["amount"] for t in hp_tx if t.get("type") == "spend")

    balance_q = db.table("hp_transactions").select("remaining_amount,status").in_("status", ["pending", "active"])
    if campus_id:
        balance_q = balance_q.eq("campus_id", campus_id)
    balances = balance_q.execute() or []
    pending_hp = sum(b.get("remaining_amount") or 0 for b in balances if b.get("status") == "pending")
    active_hp = sum(b.get("remaining_amount") or 0 for b in balances if b.get("status") == "active")
    hp_outstanding = pending_hp + active_hp

    hp_value = _get_econ_setting(db, "hp_liability_value", 0.185)
    theoretical_liability = round(hp_outstanding * hp_value, 2)

    cost_log_q = db.table("redemption_cost_log").select("actual_cost")
    if start_date:
        cost_log_q = cost_log_q.gte("created_at", start_date)
    if end_date:
        cost_log_q = cost_log_q.lte("created_at", end_date)
    if campus_id:
        cost_log_q = cost_log_q.eq("campus_id", campus_id)
    actual_cost = sum(float(r["actual_cost"] or 0) for r in (cost_log_q.execute() or []))

    target_pct = _get_econ_setting(db, "programme_cost_target_pct", 0.025)
    programme_cost_pct = round(actual_cost / food_revenue, 4) if food_revenue else 0

    return {
        "food_revenue": food_revenue,
        "hp_issued": hp_issued,
        "pending_hp": pending_hp,
        "active_hp": active_hp,
        "hp_redeemed": hp_redeemed,
        "hp_outstanding": hp_outstanding,
        "theoretical_liability": theoretical_liability,
        "actual_redemption_cost": round(actual_cost, 2),
        "actual_programme_cost_pct": programme_cost_pct,
        "target_programme_cost_pct": target_pct,
        "variance_from_target": round(programme_cost_pct - target_pct, 4),
        "programme_efficiency": round(actual_cost / theoretical_liability, 4) if theoretical_liability else None,
    }


def get_tier_breakdown(db, start_date: str = None, end_date: str = None, campus_id: str = None) -> list:
    tiers = db.table("hp_tiers").select("id,name,slug").order("sort_order").execute() or []
    rows = []
    for tier in tiers:
        profs_q = db.table("profiles").select("id").eq("current_tier_id", tier["id"])
        if campus_id:
            profs_q = profs_q.eq("campus_id", campus_id)
        user_ids = [p["id"] for p in (profs_q.execute() or [])]
        if not user_ids:
            rows.append({"tier": tier["name"], "revenue": 0, "hp_issued": 0, "hp_redeemed": 0, "actual_cost": 0, "effective_pct": 0})
            continue

        orders_q = db.table("orders").select("subtotal").eq("status", "delivered").in_("user_id", user_ids)
        if start_date:
            orders_q = orders_q.gte("created_at", start_date)
        if end_date:
            orders_q = orders_q.lte("created_at", end_date)
        orders = orders_q.execute() or []
        revenue = sum(float(o["subtotal"] or 0) for o in orders)

        hp_tx_q = db.table("hp_transactions").select("amount,type,source").in_("user_id", user_ids)
        if start_date:
            hp_tx_q = hp_tx_q.gte("created_at", start_date)
        if end_date:
            hp_tx_q = hp_tx_q.lte("created_at", end_date)
        hp_tx = hp_tx_q.execute() or []
        hp_issued = sum(t["amount"] for t in hp_tx if t.get("type") == "earn" and t.get("source") == "food_order")
        hp_redeemed = sum(-t["amount"] for t in hp_tx if t.get("type") == "spend")

        tier_redemptions = db.table("reward_redemptions").select("id").in_("user_id", user_ids).execute() or []
        redemption_ids = [r["id"] for r in tier_redemptions]
        actual_cost = 0
        if redemption_ids:
            cost_q = db.table("redemption_cost_log").select("actual_cost").in_("redemption_id", redemption_ids)
            if start_date:
                cost_q = cost_q.gte("created_at", start_date)
            if end_date:
                cost_q = cost_q.lte("created_at", end_date)
            cost_rows = cost_q.execute() or []
            actual_cost = sum(float(c["actual_cost"] or 0) for c in cost_rows)

        rows.append({
            "tier": tier["name"], "revenue": revenue, "hp_issued": hp_issued,
            "hp_redeemed": hp_redeemed, "actual_cost": round(actual_cost, 2),
            "effective_pct": round(actual_cost / revenue, 4) if revenue else 0,
        })
    return rows


def get_redemption_analytics(db, start_date: str = None, end_date: str = None, campus_id: str = None) -> dict:
    q = db.table("redemption_cost_log").select("actual_cost,reward_type,hp_spent")
    if start_date:
        q = q.gte("created_at", start_date)
    if end_date:
        q = q.lte("created_at", end_date)
    if campus_id:
        q = q.eq("campus_id", campus_id)
    rows = q.execute() or []
    by_type, total_cost, total_hp = {}, 0.0, 0
    for r in rows:
        t = r.get("reward_type") or "unknown"
        by_type[t] = by_type.get(t, 0) + float(r["actual_cost"] or 0)
        total_cost += float(r["actual_cost"] or 0)
        total_hp += r.get("hp_spent") or 0
    return {
        "cost_by_type": by_type,
        "total_actual_cost": round(total_cost, 2),
        "actual_cost_per_redeemed_hp": round(total_cost / total_hp, 4) if total_hp else 0,
    }
