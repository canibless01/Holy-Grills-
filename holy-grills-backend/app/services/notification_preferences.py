"""Canonical category/channel policy shared by inbox, email and push dispatch."""
PREFERENCE_KEYS = ('push_enabled','email_enabled','order_updates','delivery_updates','hp_updates','promotions')
DELIVERY_TYPES = frozenset({'order_assigned','order_ready','order_out_for_delivery','order_delivered','order_delivery_attempted','order_unclaimed'})
ACCOUNT_TYPES = frozenset({'password_changed','password_reset','email_verification','account_deleted','account_deactivated','account_reactivated'})
REQUEST_TYPES = frozenset({'catering_request','marketplace_request','admin_catering_request','admin_vendor_request','vendor_request_submitted'})


def category_for_notification(kind):
    if kind in ACCOUNT_TYPES or kind.startswith('wallet_'):
        return None
    if kind.startswith(('order_streak','order_lock')):
        return 'hp_updates'
    if kind in DELIVERY_TYPES or kind.startswith(('rider_','kitchen_')):
        return 'delivery_updates'
    if kind in REQUEST_TYPES or kind in ('event_registered','event_catering_submitted','event_catering_status') or kind.startswith(('order_','guest_order','scheduled_order','squad_order','marketplace_purchase','marketplace_code','marketplace_report')):
        return 'order_updates'
    if kind.startswith(('hp_','tier_','reward_','free_side','exclusive_spin','milestone_','referral_','squad_','birthday_','checkin_','login_streak','first_order_gift','graduation_','membership_','prize_fulfilment','flash_sale_redeemed')):
        return 'hp_updates'
    return 'promotions'


def effective_preferences(db,user_id,profile=None):
    if profile is None:
        profile=db.table('profiles').select('campus_id,push_enabled,email_notifications').eq('id',user_id).single().execute() or {}
    row=db.table('notification_preferences').select('*').eq('user_id',user_id).single().execute() or {}
    result={key:row.get(key,True) for key in PREFERENCE_KEYS}
    # Either saved opt-out must be respected. Canonical PATCH updates both rows
    # atomically, so enabling a channel clears its old profile opt-out too.
    result['push_enabled']=result['push_enabled'] is not False and profile.get('push_enabled') is not False
    result['email_enabled']=result['email_enabled'] is not False and profile.get('email_notifications') is not False
    return {**row,**result,'user_id':user_id}


def permitted_channels(kind,channels,prefs):
    category=category_for_notification(kind)
    if category and prefs.get(category) is False:
        return []
    return [c for c in channels if c in ('in_app','email','push') and not (c=='push' and prefs.get('push_enabled') is False) and not (c=='email' and prefs.get('email_enabled') is False)]
