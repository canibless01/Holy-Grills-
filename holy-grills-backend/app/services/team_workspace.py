"""Team-only workflows; existing commerce roles and provider transports stay authoritative."""
from app.messages import MSG

ERRORS = {'forbidden': (403, 'TEAM_FORBIDDEN'), 'campus_required': (400, 'TEAM_CAMPUS_REQUIRED'),
          'stale': (409, 'TEAM_STALE'), 'closed': (409, 'TEAM_CLOSED'),
          'submitted': (409, 'TEAM_SUBMITTED'), 'incomplete': (400, 'TEAM_INCOMPLETE'),
          'request_conflict': (409, 'TEAM_REQUEST_CONFLICT'), 'conflict': (409, 'TEAM_CONFLICT')}


def metric_status(target, result):
    actual = result.get('actual') if isinstance(result, dict) else None
    if actual is None or actual == '':
        return {'status': 'not_reported', 'attainment': None}
    if target.get('tracking_only'):
        return {'status':'reported','attainment':None,'target_met':None}
    actual, goal = float(actual), float(target['target'])
    if target['direction'] == 'lower':
        state = 'on_track' if actual <= goal else 'watch' if actual <= goal + float(target.get('tolerance', 0)) else 'below_target'
        return {'status': state, 'attainment': None, 'target_met': actual <= goal}
    ratio = actual / goal if goal > 0 else None
    return {'status': 'on_track' if ratio is None or ratio >= .9 else 'watch' if ratio >= .8 else 'below_target',
            'attainment': round(ratio * 100, 1) if ratio is not None else None, 'target_met': actual >= goal}


def decorate(data):
    if not isinstance(data, dict) or data.get('error'):
        return data
    for entry in data.get('entries', []):
        entry['scores'] = {t['id']: metric_status(t, (entry.get('results') or {}).get(t['id'])) for t in entry.get('targets', []) if t.get('cadence') != 'daily'}
        entry['daily_scores'] = {day:{t['id']:metric_status(t,values.get(t['id'])) for t in entry.get('targets',[]) if t.get('cadence')=='daily'} for day,values in (entry.get('daily_results') or {}).items()}
    return data


def capture_due(db):
    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo
    rows = db.rpc('hg_team_due_candidates')
    if not isinstance(rows, list):
        raise ValueError('Team notice capture is unavailable')
    stats = {'queued': 0, 'duplicates': 0, 'skipped': 0}
    for row in rows:
        values = {'nickname': row.get('nickname') or 'friend', 'responsibility': row['responsibility'],
                  'deadline': datetime.fromisoformat(row['due_at']).astimezone(ZoneInfo('Africa/Lagos')).strftime('%a %d %b, %H:%M WAT')}
        if row['kind'] == 'digest':
            title = MSG.TEAM_DIGEST_TITLE
            values.update({key:int(row['counts'].get(key) or 0) for key in ('members','submitted','approved','signups','own_targets','own_reported')})
            body = MSG.TEAM_DIGEST_BODY.format(**values)
        else:
            title = row.get('title') or MSG.TEAM_REMINDER_TITLE
            body = row.get('body') or MSG.TEAM_REMINDER_BODY
            # Only known placeholders are interpolated. Braces in custom copy stay literal.
            for key, value in values.items():
                title = title.replace('{'+key+'}', str(value))
                body = body.replace('{'+key+'}', str(value))
        metadata = {key:row.get(key) for key in ('member_id','week_id','week_version','kind','rule_id','rule_version')}
        metadata['expires_at'] = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        result = db.rpc('hg_team_queue_notice', {'p_user':row['user_id'],'p_metadata':metadata,'p_key':row['notice_key'],'p_title':title[:200],'p_body':body[:12000]})
        if not isinstance(result,dict) or result.get('error'):
            raise ValueError('Team notice queue is unavailable')
        if result.get('queued'):stats['queued']+=1
        elif result.get('duplicate'):stats['duplicates']+=1
        else:stats['skipped']+=1
    return stats
