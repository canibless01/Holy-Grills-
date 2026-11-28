"""Durable event admission; the database owns the reward amount and receipt."""
from flask import current_app
from app.db import get_db


def admit_event_ticket(event_id, ticket_id, actor_id, door_token, campus_id):
    result = get_db().rpc("hg_admit_event_ticket", {
        "p_event_id": event_id, "p_ticket_id": ticket_id,
        "p_actor_id": actor_id, "p_door_token": door_token,
        "p_campus_id": campus_id,
        "p_default_hp": current_app.config.get("EVENT_CHECKIN_HP", 50),
    })
    if (not isinstance(result, dict) or result.get("error")
            or not result.get("completed") or not result.get("checkin_id")):
        raise RuntimeError("Event admission could not be completed")
    return result
