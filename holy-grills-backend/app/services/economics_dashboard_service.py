"""
Economics Dashboard Service — aggregation queries for admin economics reporting.
"""

from app.services.economics_service import _get_econ_setting, get_hp_value

# What counts as "HP issued": food-order earning, the FIFO unlock of pending HP, and (per the tier
# rewards spec) each tier's flat monthly HP perk -- it's real liability the moment it's credited,
# same as order-earned HP, even though no order caused it. Renamed from _HP_ISSUED_SOURCES now that
# it covers a non-order source too.
# B-9: include squad splits, claimed splits, and bonus so economics reflects squad orders
_HP_ISSUED_SOURCES = ("food_order", "order_earn", "unlock", "tier_monthly_hp", "squad_split", "squad_split_claimed", "squad_bonus")


def get_economics_overview(db, start_date: str = None, end_date: str = None, campus_id: str = None) -> dict:
    orders_q = db.table("orders").select("subtotal").eq("status", "delivered")
    if start_date:
        orders_q = orders_q.gte("created_at", start_date)
    if end_date:
        orders_q = orders_q.lt("created_at", end_date)
    if campus_id:
        orders_q = orders_q.eq("campus_id", campus_id)
    orders = orders_q.execute() or []
    food_revenue = sum(float(o["subtotal"] or 0) for o in orders)

    hp_tx_q = db.table("hp_transactions").select("amount,type,source")
    if start_date:
        hp_tx_q = hp_tx_q.gte("created_at", start_date)
    if end_date:
        hp_tx_q = hp_tx_q.lt("created_at", end_date)
    if campus_id:
        hp_tx_q = hp_tx_q.eq("campus_id", campus_id)
    hp_tx = hp_tx_q.execute() or []
    # B-9: exclude transfers from earned/spent, report separately
    hp_issued = sum(t["amount"] for t in hp_tx if t.get("type") == "earn" and t.get("source") in _HP_ISSUED_SOURCES and t.get("source") != "hp_transfer_received")
    hp_redeemed = sum(t["amount"] for t in hp_tx if t.get("type") == "spend" and t.get("source") != "hp_transfer_sent")
    hp_transfer_received = sum(t["amount"] for t in hp_tx if t.get("source") == "hp_transfer_received")
    hp_transfer_sent = sum(t["amount"] for t in hp_tx if t.get("source") == "hp_transfer_sent")

    # [B-14] Spendable HP = profiles.hp_balance (kept current by every HP RPC). hp_transactions.remaining_amount is
    # NOT reliable: record_hp_transaction_atomic never sets it and spends never reduce it.
    bal_q = db.table("profiles").select("hp_balance")
    if campus_id:
        bal_q = bal_q.eq("campus_id", campus_id)
    active_hp = sum(int(p.get("hp_balance") or 0) for p in (bal_q.execute() or []))
    pend_q = db.table("hp_transactions").select("amount").eq("type", "earn").eq("status", "pending")
    if campus_id:
        pend_q = pend_q.eq("campus_id", campus_id)
    pending_hp = sum(int(t.get("amount") or 0) for t in (pend_q.execute() or []))
    hp_outstanding = pending_hp + active_hp

    hp_value = get_hp_value()
    theoretical_liability = round(hp_outstanding * hp_value, 2)

    cost_log_q = db.table("redemption_cost_log").select("actual_cost")
    if start_date:
        cost_log_q = cost_log_q.gte("created_at", start_date)
    if end_date:
        cost_log_q = cost_log_q.lt("created_at", end_date)
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
        "hp_transfer_received": hp_transfer_received,
        "hp_transfer_sent": hp_transfer_sent,
        "hp_outstanding": hp_outstanding,
        "theoretical_liability": theoretical_liability,
        "actual_redemption_cost": round(actual_cost, 2),
        "actual_programme_cost_pct": programme_cost_pct,
        "target_programme_cost_pct": target_pct,
        "variance_from_target": round(programme_cost_pct - target_pct, 4),
        "programme_efficiency": round(actual_cost / theoretical_liability, 4) if theoretical_liability else None,
    }


def _in_chunks(build, ids, size: int = 200) -> list:
    """Run build(chunk).execute() over slices of `ids` (keeps the request URL short) and concatenate the rows."""
    rows = []
    for i in range(0, len(ids), size):
        rows.extend(build(ids[i:i + size]).execute() or [])
    return rows


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

        def _orders(chunk):
            q = db.table("orders").select("subtotal").eq("status", "delivered").in_("user_id", chunk)
            if start_date:
                q = q.gte("created_at", start_date)
            if end_date:
                q = q.lt("created_at", end_date)
            return q
        revenue = sum(float(o["subtotal"] or 0) for o in _in_chunks(_orders, user_ids))

        def _hp(chunk):
            q = db.table("hp_transactions").select("amount,type,source").in_("user_id", chunk)
            if start_date:
                q = q.gte("created_at", start_date)
            if end_date:
                q = q.lt("created_at", end_date)
            return q
        hp_tx = _in_chunks(_hp, user_ids)
        hp_issued = sum(t["amount"] for t in hp_tx if t.get("type") == "earn" and t.get("source") in _HP_ISSUED_SOURCES and t.get("source") != "hp_transfer_received")
        hp_redeemed = sum(t["amount"] for t in hp_tx if t.get("type") == "spend" and t.get("source") != "hp_transfer_sent")

        def _cost(chunk):
            q = db.table("redemption_cost_log").select("actual_cost").in_("user_id", chunk)
            if start_date:
                q = q.gte("created_at", start_date)
            if end_date:
                q = q.lt("created_at", end_date)
            return q
        actual_cost = sum(float(c["actual_cost"] or 0) for c in _in_chunks(_cost, user_ids))

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
        q = q.lt("created_at", end_date)
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
