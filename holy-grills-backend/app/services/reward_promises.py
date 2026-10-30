"""Display and fulfill the earned definition, preserving explicit legacy fallback."""
from app.messages import MSG


def earned_reward(row):
    snapshot = row.get('reward_snapshot')
    if snapshot is None:
        return None
    if (not isinstance(snapshot, dict) or snapshot.get('version') != 1
            or snapshot.get('id') != row.get('reward_id') or not snapshot.get('name')):
        raise ValueError(MSG.REWARD_REDEMPTION_UNAVAILABLE)
    return snapshot


def display_earned_reward(row):
    reward = earned_reward(row)
    if reward is None:
        return row
    return {**row, 'rewards': {key: reward.get(key) for key in
            ('id', 'name', 'reward_type', 'image_url')}
            | {'hp_cost': row.get('hp_cost_snapshot')}}
