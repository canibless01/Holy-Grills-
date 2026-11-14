"""Bounded, short-lived public academic snapshots. Signup still validates live IDs."""
from copy import deepcopy
from threading import Lock
from time import monotonic
from flask import current_app


def registration_snapshot(db, campus_id):
    state = current_app.extensions.setdefault('registration_reference_cache', {'lock': Lock(), 'rows': {}})
    with state['lock']:
        now = monotonic()
        rows = state['rows']
        cached = rows.get(campus_id)
        if cached and cached[0] > now:
            return deepcopy(cached[1])
        result = db.rpc('hg_registration_options', {'p_campus_id': campus_id})
        # Errors never poison a later retry. Signup always validates live IDs.
        if isinstance(result, dict) and not result.get('error'):
            rows = {key: value for key, value in rows.items() if value[0] > now}
            if len(rows) >= 32:
                rows.pop(next(iter(rows)))
            rows[campus_id] = (monotonic() + 30, deepcopy(result))
            state['rows'] = rows
        return result
