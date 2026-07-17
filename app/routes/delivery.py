"""Delivery Location routes — hostels, gates, fee calculation, admin CRUD."""

import math
from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_role
from app.db import get_db
from datetime import datetime, timezone

delivery_bp = Blueprint("delivery", __name__)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Return the great-circle distance in kilometres between two lat/lon points."""
    R = 6371.0
    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlam = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


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
            dist = haversine_km(gate_lat, gate_lon, user_lat, user_lon)
            fee = base_fee + (dist * rate_per_km)
            return round(max(fee, min_fee), 2), round(dist, 3)
        except Exception:
            pass
    return round(min_fee, 2), None


# ─────────────────────────────────────────────────────────────────────────────
# Public user endpoints
# ─────────────────────────────────────────────────────────────────────────────

@delivery_bp.route("/hostels", methods=["GET"])
def list_hostels():
    """
    List all active on-campus hostels with their delivery fees.
    ---
    tags: [Delivery]
    security: []
    responses:
      200:
        description: |
          { hostels: [{ id, name, gate_id, delivery_fee, is_active, gates: {...} }] }
    """
    db = get_db()
    try:
        hostels = (
            db.table("hostels")
            .select("*,gates(name,lat,lon)")
            .eq("is_active", "true")
            .order("name")
            .execute()
        ) or []
    except Exception:
        # Table may not exist yet — return empty list gracefully
        hostels = []
    return jsonify({"hostels": hostels}), 200


@delivery_bp.route("/gates", methods=["GET"])
def list_gates():
    """
    List all active delivery gates (used for off-campus fee calculation).
    ---
    tags: [Delivery]
    security: []
    responses:
      200:
        description: |
          { gates: [{ id, name, lat, lon, base_fee, rate_per_km, min_fee }] }
    """
    db = get_db()
    try:
        gates = (
            db.table("gates")
            .select("*")
            .eq("is_active", "true")
            .order("name")
            .execute()
        ) or []
    except Exception:
        gates = []
    return jsonify({"gates": gates}), 200


@delivery_bp.route("/calculate-fee", methods=["POST"])
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
    db = get_db()
    data = request.get_json(force=True) or {}
    delivery_type = data.get("delivery_type")

    if delivery_type not in ("on_campus", "off_campus"):
        return jsonify({"error": "delivery_type must be 'on_campus' or 'off_campus'"}), 400

    location_id = data.get("delivery_location_id")
    if not location_id:
        return jsonify({"error": "'delivery_location_id' is required"}), 400

    user_lat = data.get("lat")
    user_lon = data.get("lon")

    try:
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
                return jsonify({"error": "Hostel not found"}), 404
            return jsonify({
                "delivery_type": "on_campus",
                "delivery_fee": float(hostel.get("delivery_fee") or 0),
                "hostel": hostel,
                "distance_km": None,
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
            return jsonify({"error": "Gate not found"}), 404
        fee, distance_km = calculate_off_campus_fee(gate, user_lat, user_lon)
        return jsonify({
            "delivery_type": "off_campus",
            "delivery_fee": fee,
            "gate": gate,
            "distance_km": distance_km,
        }), 200

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


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
    db = get_db()
    try:
        hostels = (
            db.table("hostels")
            .select("*,gates(name)")
            .order("name")
            .execute()
        ) or []
    except Exception:
        hostels = []
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
    db = get_db()
    data = request.get_json(force=True) or {}
    for f in ["name", "delivery_fee"]:
        if data.get(f) is None:
            return jsonify({"error": f"'{f}' is required"}), 400

    record = {
        "name": data["name"],
        "delivery_fee": float(data["delivery_fee"]),
        "is_active": bool(data.get("is_active", True)),
    }
    if data.get("gate_id"):
        record["gate_id"] = data["gate_id"]

    try:
        result = db.table("hostels").insert(record)
        return jsonify(result[0] if isinstance(result, list) else result), 201
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


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
    db = get_db()
    data = request.get_json(force=True) or {}
    allowed = {"name", "gate_id", "delivery_fee", "is_active"}
    update = {k: v for k, v in data.items() if k in allowed}
    if not update:
        return jsonify({"error": "No valid fields to update"}), 400
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        result = db.table("hostels").eq("id", hostel_id).update(update)
        if not result:
            return jsonify({"error": "Hostel not found"}), 404
        return jsonify(result[0] if isinstance(result, list) else result), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


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
    db = get_db()
    try:
        result = db.table("hostels").eq("id", hostel_id).update({
            "is_active": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        if not result:
            return jsonify({"error": "Hostel not found"}), 404
        return jsonify({"message": "Hostel deactivated", "hostel_id": hostel_id}), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


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
    db = get_db()
    try:
        gates = db.table("gates").select("*").order("name").execute() or []
    except Exception:
        gates = []
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
    db = get_db()
    data = request.get_json(force=True) or {}
    if not data.get("name"):
        return jsonify({"error": "'name' is required"}), 400

    record = {
        "name": data["name"],
        "base_fee": float(data.get("base_fee") or 0),
        "rate_per_km": float(data.get("rate_per_km") or 0),
        "min_fee": float(data.get("min_fee") or 0),
        "is_active": bool(data.get("is_active", True)),
    }
    if data.get("lat") is not None:
        record["lat"] = float(data["lat"])
    if data.get("lon") is not None:
        record["lon"] = float(data["lon"])

    try:
        result = db.table("gates").insert(record)
        return jsonify(result[0] if isinstance(result, list) else result), 201
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


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
    db = get_db()
    data = request.get_json(force=True) or {}
    allowed = {"name", "lat", "lon", "base_fee", "rate_per_km", "min_fee", "is_active"}
    update = {k: v for k, v in data.items() if k in allowed}
    if not update:
        return jsonify({"error": "No valid fields to update"}), 400
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        result = db.table("gates").eq("id", gate_id).update(update)
        if not result:
            return jsonify({"error": "Gate not found"}), 404
        return jsonify(result[0] if isinstance(result, list) else result), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


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
    db = get_db()
    try:
        result = db.table("gates").eq("id", gate_id).update({
            "is_active": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        if not result:
            return jsonify({"error": "Gate not found"}), 404
        return jsonify({"message": "Gate deactivated", "gate_id": gate_id}), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
