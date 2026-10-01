"""
app/messages.py — Holy Grills Central Message Registry

Every user-facing string in the codebase lives here.
Import MSG (or the alias M) instead of writing string literals inline.

Usage:
    from app.messages import MSG

    return jsonify({"message": MSG.PASSWORD_CHANGED}), 200
    send_notification(title=MSG.ORDER_CONFIRMED_TITLE,
                      body=MSG.ORDER_CONFIRMED_BODY.format(order_id=...))

Rules for editing this file:
  * Add constants INSIDE class MSG (above the `M = MSG` alias). Anything placed after the class ends is not part
    of MSG. A constant defined twice silently keeps the LAST definition, so search before adding.
"""

class MSG:

    # ── API / Health ──────────────────────────────────────────────────────────
    API_VERSION              = "1.0.0"
    HEALTH_OK                = "ok"
    HEALTH_DEGRADED          = "degraded"
    HEALTH_CONNECTED         = "connected"
    HEALTH_NOT_CONFIGURED    = "not_configured"

    # ── Auth ─────────────────────────────────────────────────────────────────
    LOGGED_OUT               = "Logged out successfully"
    PASSWORD_CHANGED         = "Password changed successfully"
    ADDRESS_DELETED          = "Address deleted"
    ACCOUNT_DELETED          = "Account has been deleted. Your data will be purged within 30 days."

    # ── Order status — notification titles & bodies ───────────────────────────
    ORDER_CONFIRMED_TITLE        = "Order Confirmed!"
    ORDER_CONFIRMED_BODY         = "Your order #{order_id} is received! Expect delivery between {delivery_window_start}–{delivery_window_end}."

    ORDER_SCHEDULED_DEFERRED_TITLE = "Order Scheduled"
    ORDER_SCHEDULED_DEFERRED_BODY  = "Today's orders are full — your order is scheduled for {scheduled_date}, delivery between {delivery_window_start}–{delivery_window_end}."

    ORDER_PREPARING_TITLE        = "Your order is being prepared"
    ORDER_PREPARING_BODY         = "The kitchen is on it! Won't be long."

    ORDER_READY_TITLE            = "Order Ready!"
    ORDER_READY_BODY             = "Your order is ready and waiting for a rider."

    ORDER_ASSIGNED_TITLE         = "Rider Assigned!"
    ORDER_ASSIGNED_BODY          = "A rider has been assigned to your order."

    ORDER_OUT_FOR_DELIVERY_TITLE = "On The Way!"
    ORDER_OUT_FOR_DELIVERY_BODY  = "Your rider has picked up your order."

    ORDER_DELIVERED_TITLE        = "Order Delivered!"
    ORDER_DELIVERED_BODY         = "Your order has been delivered. Enjoy your meal!"
    ORDER_THANK_YOU_TITLE        = "Thanks for dining with us! 🙏"
    ORDER_THANK_YOU_BODY         = "We hope you loved your {platform} meal. Looking forward to serving you again!"
    SATISFACTION_CHECK_TITLE     = "How was your meal? 😊"
    SATISFACTION_CHECK_BODY      = "We'd love your feedback — rate your {platform} experience and help us improve."
    REENGAGEMENT_NUDGE_TITLE     = "Ready for another round? 🍖"
    REENGAGEMENT_NUDGE_BODY      = "It's been a day since your last order. Come back and earn {currency} with every bite!"

    ORDER_DELIVERY_ATTEMPTED_TITLE = "Delivery Attempted"
    ORDER_DELIVERY_ATTEMPTED_BODY  = "We tried to reach you. Please respond within 30 minutes."

    ORDER_UNCLAIMED_TITLE        = "Order Unclaimed"
    ORDER_UNCLAIMED_BODY         = "Your order was not collected. Please contact us."

    ORDER_CANCELLED_TITLE        = "Order Cancelled"
    ORDER_CANCELLED_BODY         = "Your order has been cancelled. Contact us for help."

    ORDER_REFUND_TITLE           = "Your refund is being processed"
    ORDER_REFUND_BODY_WALLET     = "\u20a6{amount} has been credited to your wallet. Reason: {reason}"
    ORDER_REFUND_SUCCESS         = "Refund processed"

    # ── Holy Points (HP) ──────────────────────────────────────────────────────
    HP_EARNED_TITLE          = "+{total_hp} {currency} Earned!"
    HP_UNLOCKED_TITLE        = "+{unlocked_hp} {currency} Unlocked!"
    HP_UNLOCKED_BODY         = "Your food order unlocked {unlocked_hp} {currency} from your pending pool."

    # ── Tier ──────────────────────────────────────────────────────────────────
    TIER_UPGRADE_TITLE       = "You reached {tier_name}!"
    TIER_UPGRADE_BODY        = "Congratulations! You've earned {tier_name} status. Enjoy your enhanced rewards."
    TIER_DROPPED_TITLE       = "Tier Update \u2014 {from_tier} \u2192 {to_tier}"
    TIER_DROPPED_BODY        = "Your grace period has ended. Keep ordering to climb back up!"
    TIER_GRACE_TITLE         = "{grace_days}-Day Grace Period Started \u2014 {tier_name}"
    TIER_GRACE_BODY          = "Your {currency} is below the {tier_name} maintenance threshold. Order within {grace_days} days to keep your tier!"

    # ── Birthday ──────────────────────────────────────────────────────────────
    BIRTHDAY_TITLE           = "Happy Birthday, {name}!"
    BIRTHDAY_BODY            = "You've received {hp} {currency} as a birthday gift! Valid for 30 days. Enjoy your special day."
    BIRTHDAY_REPORT_TITLE    = "\U0001f382 {count} Birthday{plural} This Month ({month})"

    # ── Abandoned Cart ───────────────────────────────────────────────────────
    ABANDONED_CART_TITLE          = "Your cart is waiting 🛒"
    ABANDONED_CART_BODY           = "You left items in your cart. Come back and complete your order before they sell out!"

    # ── Events ────────────────────────────────────────────────────────────────

    EVENT_CHECKIN_SUCCESS    = "Check-in successful"
    EVENT_HP_PENDING_TITLE   = "+{hp} {currency} Pending!"
    EVENT_HP_PENDING_BODY    = "You earned {currency} for attending {event_title}. Order food to unlock it!"
    EVENT_REGISTERED_TITLE   = "You're registered for {title}!"
    EVENT_REGISTERED_BODY    = "Show your ticket QR code at the door to check in and earn {currency}."
    EVENT_CATERING_TITLE     = "New Catering Request"
    EVENT_CATERING_BODY      = "{organizer} submitted a catering request for '{event_name}'"
    EVENT_CATERING_NOT_FOUND = "Catering request not found"
    EVENT_NOTES_INVALID      = "notes must be a string up to 2000 characters"
    EVENT_ASSIGNED_TO_INVALID = "assigned_to must be a valid user id"
    EVENT_ASSIGNED_TO_NOT_STAFF = "assigned_to must be an admin or staff user"
    EVENT_CAPACITY_INVALID   = "capacity must be a positive integer"
    EVENT_CAPACITY_BELOW_ISSUED = "capacity cannot be lower than tickets already issued ({issued})"
    EVENT_HP_REWARD_INVALID  = "hp_reward must be a non-negative integer"
    NO_VALID_FIELDS          = "No valid fields to update"

    GUEST_REGISTRATION_SUCCESS        = "Registration successful! Check your email for QR code."
    GUEST_ACCOUNT_PROMPT              = "Create an account to earn HP for this event!"
    GUEST_EMAIL_REQUIRED              = "Email is required for guest registration."
    GUEST_NAME_REQUIRED               = "Full name is required for guest registration."
    GUEST_PHONE_REQUIRED              = "Phone number is required for guest registration."
    TIER_FEATURES_INVALID             = "Features must be an array of strings."
    TIER_TERMS_INVALID                = "Terms must be an array of strings."
    TIER_EARLY_BIRD_DEADLINE_REQUIRED = "Early bird deadline is required when is_early_bird is true."
    REGISTRATION_FIELD_REQUIRED       = "{field} is required."
    TICKET_NOT_FOUND                  = "Ticket not found."
    TICKET_ALREADY_CHECKED_IN        = "This ticket has already been used for check-in."
    TICKET_LINKED_TO_ACCOUNT          = "Your guest ticket has been linked to your account. HP awarded!"

    # ── Marketplace ───────────────────────────────────────────────────────────
    MARKETPLACE_PURCHASE_TITLE           = "Purchase Confirmed"
    MARKETPLACE_PURCHASE_BODY            = "Purchase confirmed: {title}."
    MARKETPLACE_PURCHASE_CODE_SUFFIX     = " Your access code: {code}"
    MARKETPLACE_LOW_INVENTORY_TITLE      = "Low Code Inventory"
    MARKETPLACE_LOW_INVENTORY_BODY       = "'{title}' has only {remaining} code(s) left."
    MARKETPLACE_VENDOR_REQUEST_TITLE     = "New Vendor Listing Request"
    MARKETPLACE_VENDOR_REQUEST_BODY      = "{vendor_name} submitted a request: {service_title}"

    # ── Notifications ─────────────────────────────────────────────────────────
    NOTIF_ALL_READ           = "All notifications marked as read"
    NOTIF_TOKEN_REGISTERED   = "Device token registered"
    NOTIF_BLAST_NOT_FOUND    = "Notification blast not found"
    PUSH_SUBSCRIPTION_REQUIRED = "'subscription' is required"
    PUSH_UNSUBSCRIBED          = "Push subscription(s) deactivated"

    # ── Referrals ─────────────────────────────────────────────────────────────
    REFERRAL_NOT_FOUND       = "No referral found"
    REFERRAL_ALREADY_DONE    = "Referral already completed"
    REFERRAL_HP_EARNED_TITLE = "Referral Bonus!"
    REFERRAL_HP_EARNED_BODY  = "A friend you referred just placed their first order. You've earned {hp} {currency}!"

    # ── Storefront ────────────────────────────────────────────────────────────
    STOREFRONT_ALREADY_SUBSCRIBED = "Already subscribed"
    STOREFRONT_RESUBSCRIBED       = "Resubscribed successfully"
    STOREFRONT_UNSUBSCRIBED       = "Unsubscribed successfully"
    SECTION_NOT_FOUND             = "Storefront section not found"
    SECTION_DEACTIVATED           = "Storefront section deactivated"

    # ── Email subjects ────────────────────────────────────────────────────────
    EMAIL_ORDER_CONFIRMED    = "Your {platform} order is confirmed!"
    EMAIL_HP_EARNED          = "You just earned {currency}!"
    EMAIL_TIER_UPGRADE       = "You levelled up on {platform}!"
    EMAIL_WALLET_FUNDED      = "Wallet funded successfully"
    EMAIL_PASSWORD_RESET     = "Reset your {platform} password"
    EMAIL_BIRTHDAY_BONUS     = "Happy Birthday from {platform}! \U0001f382"
    EMAIL_REFERRAL_COMPLETED = "Your referral earned you {currency}!"
    EMAIL_ABANDONED_CART     = "Your cart is waiting for you"
    EMAIL_REWARD_REDEEMED    = "Reward redemption confirmed"
    EMAIL_TIER_GRACE         = "Your tier grace period has started"
    EMAIL_TIER_DROPPED       = "Your tier has changed"
    EMAIL_HP_EXPIRED         = "Some of your {currency} has expired"

    # ── Admin ─────────────────────────────────────────────────────────────────
    ADMIN_USER_DEACTIVATED       = "User deactivated"
    ADMIN_USER_ALREADY_ACTIVE    = "User is already active"
    ADMIN_USER_REACTIVATED       = "User reactivated"
    ADMIN_WINDOW_CLOSED          = "Window closed"
    ADMIN_WINDOW_ALREADY_OPEN    = "Window is already open"
    ADMIN_WINDOW_REOPENED        = "Window reopened"
    ADMIN_RECOVERY_NUDGE_SENT    = "Recovery nudge sent"
    ADMIN_NUDGE_TITLE            = "You left something behind!"
    ADMIN_NUDGE_BODY             = "Your cart is still waiting \u2014 and so is your {currency}. Complete your order today."
    ADMIN_JOB_RUNNING            = "Running in background \u2014 check server logs for result"

    # ── Wallet ────────────────────────────────────────────────────────────────
    WALLET_FUNDED_TITLE          = "Wallet Funded \u20a6{amount}"
    WALLET_FUNDED_BODY           = "Your wallet has been credited with \u20a6{amount}."

    # ── Menu ──────────────────────────────────────────────────────────────────
    MENU_ADDON_GROUP_DELETED     = "Add-on group deleted"
    MENU_ADDON_ARCHIVED          = "Add-on archived"
    MENU_ITEM_ARCHIVED           = "Item archived"
    MENU_CATEGORY_DEACTIVATED    = "Category '{name}' deactivated"
    MENU_CAPACITY_LIMIT_REMOVED  = "Daily capacity limit removed"
    MENU_ADDON_GROUP_NOT_FOUND   = "Add-on group not found"
    MENU_ITEM_SOLD_OUT_TITLE     = "Item Sold Out: {name}"
    MENU_ITEM_SOLD_OUT_BODY      = "'{name}' has been marked as unavailable. Update the menu if stock is replenished."

    # ── Rewards ───────────────────────────────────────────────────────────────
    REWARD_NEW_TITLE             = "🎁 New Reward Available!"
    REWARD_NEW_BODY              = "'{name}' is now in the rewards store. Redeem it with your {currency}!"
    REWARD_REDEEMED_TITLE        = "Reward Redeemed: {name}"
    REWARD_REDEEMED_BODY         = "You spent {hp} {currency}. Our team will fulfil your reward shortly."
    REWARD_FULFILLED_TITLE       = "Reward Fulfilled"
    REWARD_STATUS_TITLE          = "Reward Update"
    REWARD_STATUS_BODY           = "Your '{name}' redemption has been {status}."

    # ── Auth errors ───────────────────────────────────────────────────────────
    AUTH_PASSWORD_TOO_SHORT      = "Password must be at least 8 characters"
    AUTH_REGISTRATION_FAILED     = "Registration failed"
    AUTH_EMAIL_PASSWORD_REQUIRED = "Email and password are required"
    AUTH_LOGIN_FAILED            = "Login failed"
    AUTH_ADDRESS_NOT_FOUND       = "Address not found"
    AUTH_USER_NOT_FOUND          = "User not found"
    AUTH_CURRENT_PASSWORD_WRONG  = "Current password is incorrect"
    AUTH_PASSWORD_UPDATE_FAILED  = "Failed to update password"
    AUTH_PASSWORD_INCORRECT      = "Password is incorrect"
    AUTH_EMAIL_REQUIRED          = "Email is required"

    # ── Admin errors ──────────────────────────────────────────────────────────
    ADMIN_WINDOW_NOT_FOUND       = "Delivery window not found"
    ADMIN_CART_NOT_FOUND         = "Cart not found or guest cart"
    ADMIN_AUDIT_LOGS_FAILED      = "Could not read audit logs: {error}"
    ADMIN_TIER_NOT_FOUND         = "No tier found with slug '{slug}'"
    ADMIN_PROMO_NOT_FOUND        = "Promo code not found"
    ADMIN_PROMO_UPDATED          = "Promo code updated"
    ADMIN_BATCH_NOT_FOUND        = "Delivery batch not found"
    ADMIN_BATCH_NO_FIELDS        = "No valid fields to update"
    ADMIN_BATCH_INVALID_STATUS   = "Invalid status — must be one of: assigned, completed, cancelled"
    ADMIN_BATCH_CANCELLED        = "Delivery batch cancelled and orders unassigned"

    # ── Rewards ───────────────────────────────────────────────────────────────
    REWARD_NOT_FOUND             = "Reward not found"
    REWARD_NOT_AVAILABLE         = "Reward not available"
    REWARD_OUT_OF_STOCK          = "Reward is out of stock"
    REWARD_EXPIRED               = "Reward has expired"
    REWARD_TIER_TOO_LOW          = "Your tier is not high enough to redeem this reward"
    REWARD_MAX_PER_USER_REACHED  = "Maximum redemptions reached for this reward"
    REWARD_INSUFFICIENT_HP       = "Insufficient {currency}. Need {need}, have {have}"
    REWARD_DEACTIVATED           = "Reward deactivated"
    REWARD_REDEMPTION_NOT_FOUND  = "Redemption not found"
    REWARD_REDEMPTION_INVALID_STATUS = "status must be 'fulfilled' or 'rejected'"
    # The order RPC refuses the whole order when a reward cannot be spent; this is
    # the customer-facing wording for that refusal.
    REWARD_REDEMPTION_UNAVAILABLE = ("This reward isn't available — it's already used, "
                                     "isn't fulfilled yet, or belongs to another account")

    # ── Analytics ─────────────────────────────────────────────────────────────
    ANALYTICS_UNKNOWN_EXPORT     = "Unknown export type '{export_type}'. Valid: orders, hp_transactions, wallet_transactions, users"

    # ── HP bundles / spin ────────────────────────────────────────────────────
    HP_ADMIN_REQUIRED_FIELDS     = "user_id and amount are required"
    HP_BUNDLE_MIN                = "Minimum bundle purchase is {min_hp} {currency}"
    HP_BUNDLE_REF_REQUIRED       = "paystack_reference is required"
    HP_PAYMENT_NOT_CONFIRMED     = "Payment not confirmed. Transaction status: {status}"
    HP_PAYMENT_MISMATCH          = "Payment amount mismatch. Expected \u20a6{expected:.0f}, received \u20a6{received:.0f}"
    HP_PAYMENT_VERIFY_FAILED     = "Payment verification failed: {error}"
    # ── Riders ────────────────────────────────────────────────────────────────
    RIDER_AVAILABILITY_REQUIRED  = "'is_available' is required"
    RIDER_ORDER_NOT_FOUND        = "Order not found"
    RIDER_NO_PHONE               = "No phone number available"
    RIDER_NOT_ASSIGNED           = "No rider has been assigned to this order"
    RIDER_EARNINGS_INVALID_PERIOD = "Invalid period. Valid: today, week, month, all"

    # ── Gifts ─────────────────────────────────────────────────────────────────
    GIFT_ASSIGNED_TITLE          = "Your Gift is on the Way!"
    GIFT_ASSIGNED_BODY           = "A rider has been assigned to deliver your free hot dog gift."
    GIFT_RETURNED_TITLE          = "Gift Delivery Unsuccessful"
    GIFT_RETURNED_BODY           = "We were unable to deliver your gift. Please contact us to reschedule."
    GIFT_KITCHEN_TITLE           = "First-Order Gift Granted"
    GIFT_KITCHEN_BODY            = "Order #{order_id} qualifies for the first-order hot dog gift."

    # ── Referral signup ───────────────────────────────────────────────────────
    REFERRAL_SIGNUP_TITLE        = "Someone Used Your Referral!"
    REFERRAL_SIGNUP_BODY         = "A new user just signed up with your referral link. They need to place their first order to complete the referral."

    # ── Referral milestone ────────────────────────────────────────────────────
    REFERRAL_MILESTONE_TITLE     = "Milestone! {count} Referral{plural} Completed 🎉"
    REFERRAL_MILESTONE_BODY      = "You earned {hp} bonus {currency} for referring {count} friend{plural}!"

    # ── Leaderboard ───────────────────────────────────────────────────────────
    LEADERBOARD_RANK_TITLE       = "You Made the Top 10! 🏆"
    LEADERBOARD_RANK_BODY        = "You finished #{rank} on the {period} leaderboard with {hp} {currency} earned. Keep going!"

    # ── Order cancellation / placement window ─────────────────────────────────
    ORDER_CANCEL_WRONG_STATUS      = "Only orders in 'received' status can be cancelled by the customer"
    ORDER_OUTSIDE_ORDERING_HOURS   = "Orders can only be placed during operating hours"
    ORDERING_WINDOW_AT_CAPACITY    = "This ordering window has reached capacity."

    # ── Webhooks ──────────────────────────────────────────────────────────────
    WEBHOOK_INVALID_SIGNATURE    = "Invalid signature"
    WEBHOOK_INVALID_JSON         = "Invalid JSON"
    WEBHOOK_OK                   = "ok"
    WEBHOOK_ALREADY_PROCESSED    = "Already processed"
    WEBHOOK_ADMIN_FAILURE_TITLE  = "Webhook Processing Failure"
    WEBHOOK_ADMIN_FAILURE_BODY   = "Event '{event_type}' (ref: {reference}) failed: {error}"

    # ── Auth extra ────────────────────────────────────────────────────────────
    AUTH_REFRESH_TOKEN_REQUIRED   = "refresh_token is required"
    AUTH_CHANGE_PW_REQUIRED       = "current_password and new_password are required"
    AUTH_CONFIRM_DELETE_REQUIRED  = "password is required to confirm account deletion"
    AUTH_ADDRESS_FIELDS_REQUIRED  = "label, line1 (or address_line), and city are required"
    AUTH_FIELD_REQUIRED           = "'{field}' is required"
    AUTH_VERIFY_EMAIL_SENT        = "If your email is not yet confirmed, a new verification link has been sent. Check your inbox."
    AUTH_VERIFY_EMAIL_MISSING     = "email is required"
    DEVICE_TOKEN_REQUIRED         = "'token' is required"
    DEVICE_TOKEN_REGISTERED       = "Device token registered"
    DEVICE_TOKEN_UPDATED          = "Device token updated"
    LOGOUT_ALL_DEVICES_OK         = "Signed out from all devices"

    # ── Events ────────────────────────────────────────────────────────────────
    # ── Ticket Tiers ──────────────────────────────────────────────────────────
    TIER_NOT_FOUND               = "Ticket tier not found"
    ALREADY_REGISTERED_FOR_EVENT = "Already registered for this event"
    TIER_PRICE_INVALID            = "price_naira and price_hp must be non-negative"
    TIER_CAPACITY_INVALID_TIER    = "capacity must be a positive integer or null"
    TIER_NAME_REQUIRED            = "Tier name is required"
    TIER_DELETE_HAS_SALES         = "Cannot delete a tier with existing ticket sales"


    # ── Free Sides ────────────────────────────────────────────────────────────
    FREE_SIDE_NO_CREDITS         = "You have no free side credits"
    FREE_SIDE_REDEEMED           = "Free side credit redeemed"
    FREE_SIDE_INVALID_CHOICE     = "Invalid side choice"

    # ── Exclusive Spin ────────────────────────────────────────────────────────
    SPIN_NO_CREDITS              = "You have no exclusive spins available"
    SPIN_SUCCESS                 = "You spun and won: {prize}"

    # ── Challenges ────────────────────────────────────────────────────────────
    CHALLENGE_NOT_FOUND          = "Challenge not found or inactive"
    CHALLENGE_COMPLETE_TITLE     = "Challenge Complete: {title}"
    CHALLENGE_COMPLETE_BODY      = "You earned {hp} {currency} (pending). Order food to unlock!"
    CHALLENGE_DEACTIVATED        = "Challenge deactivated"

    # ── Feature Flags ─────────────────────────────────────────────────────────
    FEATURE_FLAG_NOT_FOUND       = "Feature flag not found"
    FEATURE_FLAG_UPDATED         = "Feature flag updated"
    FEATURE_FLAG_NAME_REQUIRED   = "feature_name is required"

    # ── Leaderboard Prizes / Hall of Fame ──────────────────────────────────────
    LEADERBOARD_PRIZE_FULFILLED  = "Reward marked as fulfilled"
    HOF_REWARD_FULFILLED         = "Hall of Fame reward fulfilled"
    HOF_REWARD_NOT_FOUND         = "Hall of Fame reward record not found"
    LEADERBOARD_REWARD_NOT_FOUND = "Leaderboard reward record not found"

    EVENT_NOT_FOUND              = "Event not found"

    # ── Marketplace ──────────────────────────────────────────────────────────
    LISTING_NOT_FOUND            = "Listing not found"
    LISTING_NOT_AVAILABLE        = "Listing not available"
    LISTING_OUT_OF_STOCK         = "Listing is out of stock"
    LISTING_NO_CODES             = "No codes available. Listing is now out of stock."
    LISTING_TIER_TOO_LOW         = "Your tier is not high enough to purchase this item."
    LISTING_VENDOR_UNAVAILABLE   = "Vendor listing requests are not currently available. Please contact us directly."
    MARKETPLACE_REQUEST_SUBMITTED = "Your listing request has been submitted for review."
    MARKETPLACE_REQUEST_NOT_FOUND = "Vendor request not found"
    MARKETPLACE_REQUEST_ALREADY_REVIEWED = "This request has already been reviewed"

    # ── Menu ─────────────────────────────────────────────────────────────────
    MENU_SLUG_EXISTS             = "Slug '{slug}' already exists"
    MENU_CATEGORY_NOT_FOUND      = "Category not found"
    MENU_NO_VALID_FIELDS         = "No valid fields provided"
    MENU_ITEM_NOT_FOUND          = "Menu item not found"
    MENU_ITEM_CREATE_FAILED      = "Failed to create menu item: {error}"

    # ── Notifications ─────────────────────────────────────────────────────────
    NOTIF_NO_VALID_PREFS         = "No valid preference fields provided"

    # ── Orders ────────────────────────────────────────────────────────────────
    ORDER_WALLET_LOGIN_REQUIRED  = "Wallet payment requires a logged-in account"
    ORDER_CREATE_FAILED          = "Order creation failed"
    ORDER_NOT_FOUND              = "Order not found"
    ORDER_ACCESS_DENIED          = "Access denied"
    ORDER_INVALID_CLAIM          = "Invalid claim token"
    ORDER_REVIEW_DELIVERED_ONLY  = "Can only review delivered orders"
    ORDER_ALREADY_REVIEWED       = "Order already reviewed"
    ORDER_ADDON_GROUP_REQUIRED   = "'{group_name}' requires at least {min_select} selection(s) for '{item_name}'"
    ORDER_ADDON_GROUP_TOO_MANY   = "'{group_name}' allows at most {max_select} selection(s) for '{item_name}'"
    ORDER_ADDON_NOT_FOUND        = "Add-on {addon_id} not found"
    ORDER_ADDON_UNAVAILABLE      = "Add-on '{name}' is not currently available"
    ORDER_ADDON_WRONG_ITEM       = "Add-on '{name}' does not belong to '{item_name}'"

    # ── Storefront ────────────────────────────────────────────────────────────
    STOREFRONT_INVALID_DAY       = "Invalid day '{day}'. Must be a full weekday name."
    STOREFRONT_PROMO_INVALID     = "Invalid or expired promo code"
    STOREFRONT_PROMO_EXPIRED     = "Promo code has expired"
    STOREFRONT_PROMO_NOT_ACTIVE  = "Promo code is not yet active"
    STOREFRONT_PROMO_LIMIT       = "Promo code has reached its usage limit"
    STOREFRONT_PROMO_MIN_ORDER   = "Minimum order \u20a6{min_amount:.0f} required"

    # ── Wallet ─────────────────────────────────────────────────────────────────
    WALLET_NOT_FOUND             = "Wallet not found"
    WALLET_MIN_TOPUP             = "Minimum top-up is \u20a6{min:.0f}"
    WALLET_USER_NOT_FOUND        = "User not found"
    WALLET_PROFILE_NOT_FOUND     = "Profile not found"
    WALLET_VA_FAILED             = "Could not provision virtual account: {error}"

    # ── Cart ──────────────────────────────────────────────────────────────────
    CART_ITEM_ADDED          = "Item added to cart"
    CART_ITEM_UPDATED        = "Cart item updated"
    CART_ITEM_REMOVED        = "Item removed from cart"
    CART_CLEARED             = "Cart cleared"
    CART_ITEM_NOT_FOUND      = "Cart item not found"

    # ── Scheduled orders ──────────────────────────────────────────────────────
    SCHEDULED_ORDER_DUE_TITLE    = "Scheduled Order Due"
    SCHEDULED_ORDER_DUE_BODY     = "Order #{order_id} is now due for preparation."

    # ── Order cancellation / reorder ──────────────────────────────────────────
    ORDER_CANCELLED_OK       = "Order cancelled"
    ORDER_CANCEL_NOT_OWNER   = "You can only cancel your own orders"
    ORDER_REORDER_ITEMS      = "Reorder items fetched"
    ORDER_NOT_SCHEDULED_PENDING = "Order is not a pending scheduled order"

    # ── Rider ─────────────────────────────────────────────────────────────────
    RIDER_PICKUP_OK          = "Order pickup confirmed"
    RIDER_PICKUP_NOT_READY   = "Order is not ready for pickup"

    # ── Kitchen settings ──────────────────────────────────────────────────────
    KITCHEN_SETTINGS_UPDATED = "Kitchen settings updated"

    KITCHEN_SETTING_NOT_FOUND = "Kitchen setting not found"
    KITCHEN_SETTINGS_REQUIRED = "'settings' object with at least one key is required"

    # ── Generic ───────────────────────────────────────────────────────────────
    REQUIRED_FIELD_MISSING   = "Required field(s) missing"

    # ── HP transfer ───────────────────────────────────────────────────────────
    HP_TRANSFER_OK           = "{currency} transferred successfully"
    HP_TRANSFER_INSUFFICIENT = "Insufficient active {currency}. Have {have}, need {need}"
    HP_TRANSFER_SELF         = "Cannot transfer {currency} to yourself"
    HP_TRANSFER_USER_NOT_FOUND = "Recipient not found"

    # ── Saved For Later ────────────────────────────────────────────────────────
    SAVED_ITEM_ADDED         = "Item saved for later"
    SAVED_ITEM_UPDATED       = "Saved item quantity updated"
    SAVED_ITEM_REMOVED       = "Item removed from saved list"
    SAVED_ITEM_NOT_FOUND     = "Saved item not found"
    SAVED_MOVED_TO_CART      = "Item moved to cart"
    CART_MOVED_TO_SAVED      = "Item moved to saved-for-later"

    # ── Order Locks ────────────────────────────────────────────────────────────
    ORDER_LOCK_CREATED           = "Order lock created"
    ORDER_LOCK_CANCELLED         = "Order lock cancelled"
    ORDER_LOCK_RESCHEDULED       = "Order lock rescheduled"
    ORDER_LOCK_NOT_FOUND         = "Order lock not found"
    ORDER_LOCK_NOT_ACTIVE        = "Order lock is not active"
    ORDER_LOCK_DATE_REQUIRED     = "'locked_date' is required"
    ORDER_LOCK_DATE_INVALID      = "Invalid date format. Use YYYY-MM-DD"
    ORDER_LOCK_DATE_FUTURE       = "locked_date must be a future date"
    ORDER_LOCK_RESCHEDULE_LIMIT  = "This lock has already been rescheduled once"
    ORDER_LOCK_REMINDER_TITLE    = "🔒 Locked Order Reminder — {days} day{plural} to go"
    ORDER_LOCK_REMINDER_BODY     = "Your {pct:.0f}% discount is reserved for {date}. Don't miss it!"
    ORDER_LOCK_EXPIRY_TITLE      = "Order Lock Expired"
    ORDER_LOCK_EXPIRY_BODY       = "Your locked order date ({date}) has passed. The lock has expired."
    ORDER_LOCK_REDEEMED_TITLE    = "🔒 Order Lock Discount Applied!"
    ORDER_LOCK_REDEEMED_BODY     = "Your {pct:.0f}% locked-date discount saved you ₦{saved:.0f} on this order!"
    ORDER_LOCK_REDEEMED_HP_TITLE = "🔒 Order Lock {currency} Reward!"
    ORDER_LOCK_REDEEMED_HP_BODY  = "You earned {hp} {currency} for placing your order on your locked date!"
    ORDER_LOCK_REMINDER_BODY_HP  = "Your {hp} {currency} reward is waiting for {date}. Place an order to claim it!"
    BIRTHDAY_BLAST_TITLE         = "🎂 It's {name}'s Birthday Today!"
    BIRTHDAY_BLAST_BODY          = "Celebrate {name}'s birthday — tap to send them {currency} as a gift! 🎉"

    # ── First-Order Gift ───────────────────────────────────────────────────────
    GIFT_NOT_FOUND               = "Gift not found"
    GIFT_INVALID_STATUS          = "Status must be one of: fulfilled, cancelled, claimed, redeemed, returned"
    GIFT_UPDATED                 = "Gift status updated"
    FIRST_ORDER_GIFT_TITLE       = "🌭 Free Hot Dog!"
    FIRST_ORDER_GIFT_BODY        = "Congrats on your first order! A free hot dog is on us. Collect it with your delivery."

    # ── System Settings ────────────────────────────────────────────────────────
    SETTING_NOT_FOUND            = "Setting not found"
    SETTING_VALUE_REQUIRED       = "'value' is required"
    SETTING_KEY_VALUE_REQUIRED   = "'key' and 'value' are required"
    SETTING_UPDATED              = "Setting updated"
    SETTING_CREATED              = "Setting created"
    SETTING_KEY_EXISTS           = "A setting with this key already exists"

    # ── Login Streak ───────────────────────────────────────────────────────────
    LOGIN_STREAK_TITLE           = "🔥 {streak}-Day Login Streak!"
    LOGIN_STREAK_BODY            = "You've logged in {streak} days in a row. Keep it up — you earned {hp} {currency}!"

    # ── Order Share Prompt ─────────────────────────────────────────────────────
    SHARE_PROMPT_HP_TITLE        = "+{hp} {currency} for Sharing!"
    SHARE_PROMPT_HP_BODY         = "Thanks for sharing your order! {hp} {currency} added to your pending pool."
    SHARE_PROMPT_ALREADY_TODAY   = "Share reward already claimed today. Come back tomorrow!"
    SHARE_PROMPT_ORDER_NOT_FOUND = "Order not found or not yours"

    # ── Squad HP Split ─────────────────────────────────────────────────────────
    SQUAD_HP_SPLIT_TITLE         = "Squad {currency} Earned!"
    SQUAD_HP_SPLIT_BODY          = "You earned {hp} {currency} from the squad order placed by {organizer}."
    SQUAD_ORDER_ADDED_BODY       = "{organizer} added you to a squad order."
    SQUAD_MAX_MEMBERS_REACHED    = "This squad has reached its member limit."
    SQUAD_ORGANIZER_ONLY         = "Only the squad organizer can do this."
    SQUAD_NAME_REQUIRED          = "Squad name is required."
    SQUAD_EMAIL_REQUIRED         = "Email is required."
    SQUAD_CROSS_CAMPUS_BLOCKED   = "This person is on a different campus and can't join your squad."

    # ── Monthly HP Cap ─────────────────────────────────────────────────────────

    # ── Dormancy Win-Back ──────────────────────────────────────────────────────
    WINBACK_DAY70_TITLE          = "We miss you! 👋"
    WINBACK_DAY70_BODY           = "It's been a while! Come back and place an order to protect your {currency} balance."
    WINBACK_DAY95_TITLE          = "Your {currency} is at risk ⚠️"
    WINBACK_DAY95_BODY           = "You haven't ordered in a while. {currency} decay starts in {days} days — place an order now!"
    WINBACK_DAY118_TITLE         = "⏰ Last chance — {currency} decay starts in 2 days"
    WINBACK_DAY118_BODY          = "Your {currency} will start decaying in 2 days. Place an order to protect them!"

    # ── HP Decay ──────────────────────────────────────────────────────────────
    HP_DECAY_TITLE               = "{currency} Decay — {amount} {currency} Reduced"
    HP_DECAY_BODY                = "Your {currency} decreased by {amount} due to {days} days of inactivity. Stay active to stop decay!"

    # ── HP Transfer ──────────────────────────────────────────────────────────────
    HP_TRANSFER_MIN          = "Minimum {currency} transfer is {min} {currency}"

    # ── Password change (all devices) ─────────────────────────────────────────
    PASSWORD_CHANGED_LOGGED_OUT = "Password changed. All other sessions have been signed out."

    # ── Cart validation ───────────────────────────────────────────────────────
    CART_MENU_ITEM_REQUIRED       = "'menu_item_id' is required"

    # ── Marketplace validation ─────────────────────────────────────────────────
    MARKETPLACE_CODES_REQUIRED    = "codes list is required"
    MARKETPLACE_LISTING_NOT_FOUND = "Listing not found"
    MARKETPLACE_REJECTION_REASON_REQUIRED = "rejection_reason is required when rejecting a listing"

    # ── Menu validation ────────────────────────────────────────────────────────
    MENU_ADDON_NAME_REQUIRED      = "'name' is required"
    MENU_ADDON_MAX_SELECT_INVALID = "'max_select' cannot be less than 'min_select'"
    MENU_ITEM_IDS_REQUIRED        = "'item_ids' must be a non-empty array"
    MENU_AVAILABILITY_REQUIRED    = "'is_available' is required"
    MENU_CAPACITY_POSITIVE        = "daily_order_capacity must be a positive integer"

    # ── Order validation ───────────────────────────────────────────────────────
    ORDER_ITEMS_REQUIRED           = "'items' is required"
    ORDER_PAYMENT_METHOD_REQUIRED  = "'payment_method' is required"
    ORDER_STATUS_REQUIRED          = "status is required"
    ORDER_TARGET_STATUS_REQUIRED   = "target_status is required"
    ORDER_CLAIM_TOKEN_REQUIRED     = "claim_token is required"
    ORDER_REFUND_REASON_REQUIRED   = "'reason' is required"

    # ── Referral validation ────────────────────────────────────────────────────
    REFERRAL_FIELDS_REQUIRED      = "referred_user_id and order_id are required"

    # ── Storefront validation ──────────────────────────────────────────────────
    STOREFRONT_DAY_REQUIRED       = "day is required"
    STOREFRONT_EMAIL_REQUIRED     = "email is required"

    # ── Admin validation ───────────────────────────────────────────────────────
    ADMIN_AMOUNT_POSITIVE         = "'amount' must be a positive integer"
    ADMIN_REASON_REQUIRED         = "'reason' is required"

    # ── Generic API errors ────────────────────────────────────────────────────
    ERR_BAD_REQUEST          = "Bad request"

    # ── Event (checkin fallback path) ─────────────────────────────────────────

    # ── Paid event ticket ─────────────────────────────────────────────────────

    # ── HP Transfer — recipient notification ──────────────────────────────────
    HP_TRANSFER_RECEIVED_TITLE   = "You received {amount} {currency}! 🎉"
    HP_TRANSFER_RECEIVED_BODY    = "{sender} sent you {amount} {currency}."

    # ── Social follow milestone ───────────────────────────────────────────────
    SOCIAL_FOLLOW_NOT_CONFIGURED = "Social follow milestone not configured"
    SOCIAL_FOLLOW_ALREADY_DONE   = "Social follow already recorded"

    # ── Graduation ────────────────────────────────────────────────────────────
    GRADUATION_PROFILE_NOT_FOUND = "Profile not found"
    GRADUATION_ALREADY_CLAIMED   = "Graduation {currency} has already been claimed"
    GRADUATION_LEVEL_REQUIRED    = "Graduation claim requires academic_level {required}+. Your level: {actual}."
    GRADUATION_BONUS_TITLE       = "🎓 Graduation Bonus Claimed!"
    GRADUATION_BONUS_BODY        = "{name}, you've earned {hp} {currency} for reaching Level {level}!"
    GRADUATION_CLAIMED_OK        = "Graduation {currency} claimed successfully"

    # ── HP flash sale ─────────────────────────────────────────────────────────
    HP_FLASH_NO_ACTIVE_SALE      = "No active flash sale for this reward"
    HP_FLASH_WINDOW_CLOSED       = "Flash sale window has closed"
    HP_FLASH_LIMIT_REACHED       = "Flash sale limit of {qty} redemptions reached"
    HP_INSUFFICIENT              = "Insufficient {currency}: have {have}, need {need}"
    HP_FLASH_INSUFFICIENT        = "Insufficient {currency} for flash deal: need {need}, have {have}"

    # ── HP Transfer (min orders) ──────────────────────────────────────────────
    HP_TRANSFER_MIN_ORDERS       = "{currency} transfer requires at least {min_orders} completed orders. You have {completed}."

    # ── Hall of Fame ──────────────────────────────────────────────────────────
    HALL_OF_FAME_TITLE           = "🏛️ Hall of Fame!"
    HALL_OF_FAME_BODY            = "Congratulations! You've reached the top 3 in three different months — you've been inducted into the {platform} Hall of Fame!"

    # ── Phase 3 notification titles/bodies ────────────────────────────────────
    LEADERBOARD_PRIZE_TITLE      = "🎁 Your Leaderboard Prize is Ready!"
    LEADERBOARD_PRIZE_BODY       = "You ranked #{rank} in {period}! You've earned: {prize}. Your reward is being processed."
    EXCLUSIVE_SPIN_WON_TITLE     = "🎡 Spin Result!"
    EXCLUSIVE_SPIN_WON_BODY      = "You spun the exclusive wheel and won: {prize}! Check the app for details."
    ADMIN_HOF_INDUCTION_TITLE    = "🏅 New Hall of Fame Inductee"
    ADMIN_HOF_INDUCTION_BODY     = "{inducted_name} has been inducted into the Hall of Fame! Fulfil their reward box when ready."

    # ── Membership Anniversary ────────────────────────────────────────────────
    ANNIVERSARY_FALLBACK_NAME    = "Valued Member"
    ANNIVERSARY_TITLE            = "🎉 {months}-Month Anniversary!"
    ANNIVERSARY_BODY             = "Happy {months}-month anniversary, {name}! You've earned {hp} {currency} as a thank-you."

    # ── Login streak week ─────────────────────────────────────────────────────
    LOGIN_STREAK_WEEK_COMPLETE_TITLE = "Week {week} Streak Complete! 🔥"
    LOGIN_STREAK_WEEK_COMPLETE_BODY  = "You earned {hp} {currency} for completing your check-in week. Keep it going!"

    # ── Login streak reclaim ──────────────────────────────────────────────────
    LOGIN_STREAK_RECLAIM_TITLE       = "Missed Day Recovered ✅"
    LOGIN_STREAK_RECLAIM_BODY_ORDER  = "Your order recovered your missed check-in today. Streak saved!"

    # ── Order streak ──────────────────────────────────────────────────────────
    ORDER_STREAK_TITLE               = "Order Streak: {weeks} Week{plural}! 🔥"
    ORDER_STREAK_BODY                = "You earned {hp} {currency} for ordering every week for {weeks} week{plural}!"
    MULTIPLIER_LIVE_TITLE            = "🔥 {currency} Multiplier Is LIVE!"
    MULTIPLIER_LIVE_BODY             = "Earn {multiplier}x {currency} on all food orders right now — don't miss it!"
    MARKETPLACE_PURCHASE_STATUS_TITLE = "🛒 Purchase Update"
    MARKETPLACE_PURCHASE_STATUS_BODY  = "Your {title} order is now marked as {status}."

    # ── Milestone / Badge notifications ───────────────────────────────────────
    MILESTONE_ACHIEVED_TITLE     = "Milestone Reached! 🎉"
    MILESTONE_ACHIEVED_BODY      = "Congratulations, {name}! You've hit a new milestone."
    MILESTONE_CHALLENGE_TITLE    = "Challenge Unlocked! 🏆"
    MILESTONE_BADGE_TITLE        = "Milestone Unlocked! 🎖️"
    MILESTONE_HP_SUFFIX          = " — {hp} {currency} earned!"

    # ── Validation — generic field-level ─────────────────────────────────────
    FIELD_MUST_BE_INTEGER        = "{field} must be an integer"
    FIELD_MUST_BE_NONEMPTY_STR   = "{field} must be a non-empty string"
    MARKETPLACE_STATUS_INVALID   = "'status' must be one of: pending, active, paused, rejected, archived, draft"
    MARKETPLACE_APPROVE_REJECT   = "'status' must be 'approved' or 'rejected'"
    CHALLENGE_TIME_WINDOW_INVALID = "time_window must be 'weekly', 'monthly', or omitted (badge)"

    # ── Wallet / Payment errors ───────────────────────────────────────────────
    ORDER_WALLET_INSUFFICIENT    = "Insufficient wallet balance: need ₦{need:.2f}"

    # ── Order / Menu validation errors ────────────────────────────────────────
    ORDER_KITCHEN_AT_CAPACITY    = "The kitchen has reached its daily order capacity. Please try again tomorrow or check back later."
    ORDER_ITEMS_EMPTY            = "Order must contain at least one item"
    ORDER_MENU_ITEM_NOT_FOUND    = "Menu item {id} not found"
    ORDER_MENU_ITEM_UNAVAILABLE  = "'{name}' is not currently available"
    ORDER_MENU_ITEM_SOLD_OUT_TODAY = "'{name}' only has {remaining} serving(s) left today"
    ORDER_VARIATION_UNAVAILABLE  = "Variation option '{name}' is not currently available"
    ORDER_PROMO_INVALID          = "Promo code '{code}' is not valid"
    ORDER_PROMO_MIN_ORDER        = "Minimum order value ₦{min_amount:.0f} required for this code"


    # ── Notification titles & bodies (push / in-app template registry) ─────────
    # These are the display strings for push notifications and in-app inbox.
    # They are referenced by notification_templates.py — never hardcoded there.

    # Auth / Account (personalized)
    NOTIF_PASSWORD_CHANGED_TITLE    = "Security Alert — Password Changed"
    NOTIF_PASSWORD_CHANGED_BODY     = "Your password was just changed, {name}. If this wasn't you, contact us immediately."
    NOTIF_ACCOUNT_DEACTIVATED_TITLE = "Account Deactivated"
    NOTIF_ACCOUNT_DEACTIVATED_BODY  = "Hi {name}, your {platform} account has been deactivated. Contact support if this was a mistake."
    NOTIF_ACCOUNT_REACTIVATED_TITLE = "You're Back, {name}!"
    NOTIF_ACCOUNT_REACTIVATED_BODY  = "Your {platform} account is active again. Welcome back!"
    NOTIF_ACCOUNT_DELETED_TITLE     = "Account Deleted"
    NOTIF_ACCOUNT_DELETED_BODY      = "Hi {name}, your account has been deleted. Your data will be purged within 30 days."

    # Login streak (personalized)
    NOTIF_LOGIN_STREAK_CHECKIN_TITLE  = "\U0001f525 {streak_count}-Day Streak!"
    NOTIF_LOGIN_STREAK_CHECKIN_BODY   = "You checked in {streak_count} days in a row, {name}. Keep it up!"
    NOTIF_LOGIN_STREAK_CYCLE_FAILED_TITLE = "\U0001f494 Check-In Cycle Reset"
    NOTIF_LOGIN_STREAK_CYCLE_FAILED_BODY  = "Too many missed days this week, {name} — you're back to Week 1. Fresh start! \U0001f4aa"
    NOTIF_LOGIN_STREAK_RECLAIM_TITLE  = "Missed Day Recovered \u2705"
    NOTIF_LOGIN_STREAK_RECLAIM_BODY   = "Your missed check-in was recovered, {name}. Streak saved!"

    # Reviews (personalized)
    REVIEW_REQUEST_TITLE       = "How was your order? \u2b50"
    REVIEW_REQUEST_BODY        = "Order #{order_id} is delivered! Leave a review and earn {currency}."
    REVIEW_SUBMITTED_TITLE     = "Review Submitted"
    REVIEW_SUBMITTED_BODY      = "Thanks for your feedback, {name}! Your review on order #{order_id} is live."

    # HP Earned — source-specific (personalized)
    HP_EARNED_FOOD_BODY        = "You earned {hp} {currency} from your food order, {name}. Keep ordering to unlock more!"
    HP_EARNED_WELCOME_TITLE    = "Welcome Bonus!"
    HP_EARNED_WELCOME_BODY     = "You earned {hp} {currency} for your first order delivery. Welcome to {platform}, {name}!"
    HP_EARNED_CHALLENGE_BODY   = "You completed a challenge and earned {hp} {currency}, {name}!"
    HP_EARNED_TOPUP_TITLE      = "+{hp} {currency} Earned!"
    HP_EARNED_TOPUP_BODY       = "You earned {hp} {currency} for topping up your wallet, {name}."
    HP_EARNED_ANNIVERSARY_BODY = "Membership anniversary bonus — {hp} {currency} added to your account, {name}!"
    HP_EARNED_SOCIAL_TITLE     = "+{hp} {currency} for Following Us!"
    HP_EARNED_SOCIAL_BODY      = "Thanks for following us on {platform}, {name}! {hp} {currency} has been added to your account."
    HP_EARNED_LOGIN_BODY       = "You earned {hp} {currency} for your login streak, {name}. Keep checking in!"
    HP_EARNED_CHALLENGE_BODY   = "You earned {hp} {currency} for completing a challenge, {name}!"

    # HP Gift (personalized)
    HP_GIFT_RECEIVED_TITLE     = "\U0001f381 {currency} Gift Received!"
    HP_GIFT_RECEIVED_BODY      = "{gift_sender} sent you {hp} {currency} as a gift, {name}!"
    HP_GIFT_SENT_TITLE         = "{currency} Gift Sent"
    HP_GIFT_SENT_BODY          = "You sent {hp} {currency} to a friend successfully."

    # Flash sale (personalized)
    FLASH_REDEEMED_TITLE       = "Flash Deal Redeemed!"
    FLASH_REDEEMED_BODY        = "You redeemed a {discount_pct}% discount on your order, {name}. Enjoy!"
    HP_SPIN_EXTRA_TITLE          = "Extra Spin Purchased! 🎡"
    HP_SPIN_EXTRA_BODY           = "You bought an extra exclusive spin, {name}. Good luck!"

    # HP Decay warning (personalized, separate from winback body copy)
    HP_DECAY_WARNING_TITLE     = "\u26a0\ufe0f Your {currency} is at Risk, {name}"
    HP_DECAY_WARNING_BODY      = "Place an order soon to protect your {currency} balance — decay starts in {days} days!"

    # Tier (personalized)
    TIER_GRACE_ENDED_TITLE     = "Grace Period Ended — Tier Changed"
    TIER_GRACE_ENDED_BODY      = "Hi {name}, your grace period ended. You've moved from {from_tier} to {to_tier}. Keep ordering to climb back!"

    # Events — user-facing (personalized)
    EVENT_TICKET_PURCHASED_TITLE = "Ticket Confirmed! \U0001f3ab"
    EVENT_TICKET_PURCHASED_BODY  = "You're all set for {event_title}, {name}. Show your QR code at the door."
    EVENT_CATERING_SUBMITTED_TITLE = "Catering Request Submitted"
    EVENT_CATERING_SUBMITTED_BODY  = "Your catering request for '{event_title}' has been submitted, {name}. We'll be in touch soon."
    EVENT_CATERING_STATUS_TITLE  = "Catering Request Update"
    EVENT_CATERING_STATUS_BODY   = "Your catering request for '{event_title}' has been updated, {name}."

    # Marketplace — user-facing (personalized)
    MARKETPLACE_ACCESS_CODE_TITLE = "Your Access Code"
    MARKETPLACE_ACCESS_CODE_BODY  = "Here's your access code for {reward_name}: {code}"
    MARKETPLACE_ESCROW_TITLE      = "Purchase Update"
    MARKETPLACE_ESCROW_BODY       = "Your order for {reward_name} has been updated, {name}."
    VENDOR_REQUEST_SUBMITTED_TITLE = "Listing Request Submitted"
    VENDOR_REQUEST_SUBMITTED_BODY  = "Hi {name}, your vendor listing request has been submitted for review."
    VENDOR_REQUEST_APPROVED_TITLE  = "Listing Request Approved! \U0001f389"
    VENDOR_REQUEST_APPROVED_BODY   = "Hi {name}, your vendor listing is approved and now live on the marketplace."
    VENDOR_REQUEST_REJECTED_TITLE  = "Listing Request Update"
    VENDOR_REQUEST_REJECTED_BODY   = "Hi {name}, your vendor listing request was not approved at this time. Contact us for details."

    # Wallet — channel-specific titles (personalized)
    WALLET_FUNDED_CARD_TITLE       = "Wallet Funded \u20a6{amount}"
    WALLET_FUNDED_CARD_BODY        = "Hi {name}, \u20a6{amount} has been credited to your wallet via card."
    WALLET_FUNDED_BANK_TITLE       = "Wallet Funded \u20a6{amount}"
    WALLET_FUNDED_BANK_BODY        = "Hi {name}, your bank transfer of \u20a6{amount} has been confirmed."
    WALLET_LOW_TITLE               = "Wallet Balance Low"
    WALLET_LOW_BODY                = "Hi {name}, your wallet balance is running low. Top up to keep ordering without interruption."

    # Rider-specific (personalized)
    RIDER_BATCH_TITLE              = "New Batch Assigned"
    RIDER_BATCH_BODY               = "Batch {batch_id} has been assigned to you. Check the app for order details."
    RIDER_ORDER_READY_TITLE        = "Order Ready for Pickup"
    RIDER_ORDER_READY_BODY         = "Order #{order_id} is ready at the kitchen. Head over for pickup."
    RIDER_PICKUP_CONFIRMED_TITLE   = "Pickup Confirmed"
    RIDER_PICKUP_CONFIRMED_BODY    = "You've confirmed pickup of order #{order_id}. Safe ride!"
    RIDER_DELIVERY_CONFIRMED_TITLE = "Delivery Confirmed \u2705"
    RIDER_DELIVERY_CONFIRMED_BODY  = "Order #{order_id} marked as delivered. Great job!"
    RIDER_DELIVERY_ATTEMPTED_TITLE = "Delivery Attempted"
    RIDER_DELIVERY_ATTEMPTED_BODY  = "You marked order #{order_id} as delivery attempted. Customer has been notified."
    RIDER_EARNINGS_TITLE           = "Earnings Update"
    RIDER_EARNINGS_BODY            = "Your earnings have been updated. Check the app for your latest balance."

    # Kitchen / operational (personalized — rider/staff context)
    KITCHEN_ORDER_TITLE            = "New Order Received"
    KITCHEN_ORDER_BODY             = "Order #{order_id} has been placed and needs preparation."
    KITCHEN_BATCH_TITLE            = "Batch Ready"
    KITCHEN_BATCH_BODY             = "Batch {batch_id} is ready for rider pickup."

    # Leaderboard (personalized)
    LEADERBOARD_TOP4_TITLE         = "Top 4! \U0001f3c5"
    LEADERBOARD_TOP4_BODY          = "Incredible, {name}! You finished in the top 4 on the {period} leaderboard. You're in contention for the Hall of Fame!"
    SQUAD_LEADERBOARD_TITLE        = "Squad Leaderboard Update"
    SQUAD_LEADERBOARD_BODY         = "Your squad's leaderboard rank has changed. Check the app!"
    HALL_OF_FAME_CARD_TITLE        = "\U0001f3db\ufe0f Share Your Achievement!"
    HALL_OF_FAME_CARD_BODY         = "You've been inducted into the Hall of Fame, {name}! Share your achievement card."

    # Order streak (personalized)
    ORDER_STREAK_BROKEN_TITLE      = "Order Streak Broken \U0001f494"
    ORDER_STREAK_BROKEN_BODY       = "Your order streak has ended, {name}. Start a new one today!"
    ORDER_STREAK_THRESHOLD_TITLE   = "Order Streak Milestone! 🔥"
    ORDER_STREAK_THRESHOLD_BODY    = "You've hit a new order streak milestone, {name}. Keep it up!"

    # Graduation (personalized)
    GRADUATION_DECLARED_TITLE      = "\U0001f393 Graduation Declared!"
    GRADUATION_DECLARED_BODY       = "Hi {name}, you've declared graduation. Complete the process to claim your {currency} bonus."

    # Share (personalized)
    SHARE_COMPLETED_TITLE          = "Share Recorded!"
    SHARE_COMPLETED_BODY           = "Thanks for sharing your {platform} experience, {name}!"

    # Multiplier events (personalized)
    MULTIPLIER_EXPIRES_TITLE       = "\u23f0 {currency} Multiplier Ending Soon!"
    MULTIPLIER_EXPIRES_BODY        = "The {currency} multiplier event ends soon, {name}. Place an order now to earn bonus {currency}!"
    MULTIPLIER_REMINDER_TITLE      = "\U0001f525 {currency} Multiplier Is Still LIVE!"
    MULTIPLIER_REMINDER_BODY       = "Don't forget, {name} — you're still earning {multiplier}x {currency} on food orders!"

    # Scheduled content — now personalized (moved from non-personalized)
    DAILY_GREETING_TITLE           = "Good Morning, {name}! \u2600\ufe0f"
    DAILY_GREETING_BODY            = "Start your day right — check out today's menu and earn {currency} with every order!"
    WEEKLY_PRAYER_TITLE            = "\U0001f64f Weekly Prayer"
    WEEKLY_PRAYER_BODY             = "May this week bring you blessings, good food, and great opportunities, {name}. Have a wonderful week!"

    # Squads (personalized)
    SQUAD_ORDER_READY_TITLE        = "Squad Order Ready!"
    SQUAD_ORDER_READY_BODY         = "Your squad order is ready and being dispatched, {name}!"
    GUEST_ORDER_CLAIMED_TITLE      = "Guest Order Linked!"
    GUEST_ORDER_CLAIMED_BODY       = "Your guest order #{order_id} has been linked to your account, {name}."

    # Scheduled orders (personalized)
    SCHEDULED_ORDER_PROMOTED_TITLE = "Scheduled Order Confirmed!"
    SCHEDULED_ORDER_PROMOTED_BODY  = "Your scheduled order #{order_id} has been added to the next delivery batch."
    SCHEDULED_ORDER_CANCELLED_TITLE = "Scheduled Order Cancelled"
    SCHEDULED_ORDER_CANCELLED_BODY  = "Hi {name}, your scheduled order #{order_id} has been cancelled."

    # Non-personalized notifications (include_name=False)
    NOTIF_WELCOME_TITLE            = "Welcome to {platform}!"
    NOTIF_WELCOME_BODY             = "You're in! Start exploring the menu and earn {currency} with every order."
    NOTIF_EMAIL_VERIFY_TITLE       = "Verify Your Email"
    NOTIF_EMAIL_VERIFY_BODY        = "Click the link in your email to activate your {platform} account."
    NOTIF_PASSWORD_RESET_TITLE     = "Password Reset Request"
    NOTIF_PASSWORD_RESET_BODY      = "We received a request to reset your password. Check your email for the reset link. If you didn't request this, ignore this message."
    NOTIF_SYSTEM_TITLE             = "\U0001f4e2 System Announcement"
    NOTIF_SYSTEM_BODY              = "An important update from {platform}. Check the app for details."
    NOTIF_SQUAD_INVITE_TITLE       = "You've Been Invited!"
    NOTIF_SQUAD_INVITE_BODY        = "You've been invited to join a {platform} squad order. Check the app to join."
    NOTIF_SQUAD_MEMBER_ADDED_TITLE = "You're in a Squad Order!"

    # ── Challenges / Gamification (personalized) ─────────────────────────────
    CHALLENGE_PROGRESS_TITLE       = "Challenge Progress 💪"
    CHALLENGE_PROGRESS_BODY        = "Great work, {name}! Keep going to complete the challenge and earn {currency}."

    # ── Admin API errors ──────────────────────────────────────────────────────
    ADMIN_INVALID_ROLE             = "Invalid role. Must be one of: {roles}"
    ADMIN_FIELD_REQUIRED           = "'{field}' is required"
    ADMIN_FIELD_MUST_BE_POSITIVE   = "{field} must be a positive integer"
    ADMIN_UNKNOWN_CRON_JOB         = "Unknown cron job: '{job}'"

    # ── Event messages ────────────────────────────────────────────────────────
    EVENT_DELETED                  = "Event '{title}' deleted"

    # ── Phase 2 Success Messages ──────────────────────────────────────────────
    REGISTER_SUCCESS               = "Welcome to {platform}! Your account is ready."
    LOGIN_SUCCESS                  = "Welcome back!"
    SESSION_REFRESHED              = "Session refreshed"
    PROFILE_PHOTO_UPDATED          = "Profile photo updated"
    PROFILE_UPDATED                = "Profile updated"
    ADDRESS_ADDED                  = "Address saved"
    ADDRESS_UPDATED                = "Address updated"
    VERIFICATION_EMAIL_SENT        = "Verification email sent — check your inbox"
    PASSWORD_RESET_SENT            = "If that email exists, a reset link is on its way"
    PWA_INSTALL_RECORDED           = "Thanks for installing the app!"
    PUSH_SUBSCRIBED                = "Push notifications enabled"
    DELIVERY_FEE_CALCULATED        = "Delivery fee calculated"
    FLASH_REWARD_REDEEMED          = "Flash reward redeemed!"
    MARKETPLACE_PURCHASE_SUCCESS   = "Purchase complete!"
    NOTIFICATION_MARKED_READ       = "Marked as read"
    NOTIFICATION_PREFERENCES_UPDATED = "Notification preferences updated"
    ORDER_PLACED                   = "Order placed! We'll keep you posted."
    REVIEW_IMAGES_UPLOADED         = "Photos added to your review"
    REVIEW_SUBMITTED               = "Thanks for your review!"
    ORDER_CLAIMED                  = "Order linked to your account"
    PROMO_CODE_VALID               = "Promo code applied"
    UPLOAD_SIGNATURE_ISSUED        = "Ready to upload"
    WALLET_CARD_FUNDING_INITIATED  = "Redirecting you to complete payment"
    WALLET_BANK_TRANSFER_INITIATED = "Transfer details ready"

    # ── Phase 1b Centralized Error Messages ───────────────────────────────────
    PHONE_FORMAT_INVALID           = "Invalid phone number format. Use international format e.g. +2348012345678."
    DOB_FORMAT_INVALID             = "Invalid date of birth. Use YYYY-MM-DD format."
    REGISTER_EMAIL_AMBIGUOUS       = "If this email can be registered, you'll receive a confirmation shortly. If you already have an account, try logging in or resetting your password."
    REGISTER_FAILED_RETRY          = "Registration failed. Please try again."
    NO_VALID_FIELDS_TO_UPDATE      = "No valid fields to update"
    MILESTONE_NOT_FOUND            = "Milestone not found or inactive"
    MILESTONE_ADMIN_ONLY           = "This milestone is awarded by admins only"
    DELIVERY_TYPE_VALUE_INVALID    = "Invalid delivery type"
    ADDRESS_ACCESS_UNAUTHORIZED    = "This isn't one of your saved addresses"
    GUEST_NO_WALLET_PAYMENTS       = "Guest orders cannot use wallet payments."
    GUEST_DETAILS_REQUIRED         = "Guest orders require your name, phone, and email."
    PROMO_CODE_MAX_USES            = "You've already used this promo code the maximum number of times"
    COORDINATES_INVALID            = "Latitude and longitude must be valid numbers"
    COORDINATES_OUT_OF_BOUNDS      = "Latitude and longitude must be within standard bounds"
    COORDINATES_UNSUPPORTED_REGION = "This location is outside our supported delivery region"
    TICKET_NOT_FOUND               = "Ticket not found"
    ACCOUNT_DEACTIVATED            = "Your account has been deactivated. Contact support if you think this is a mistake."
    SESSION_INVALID                = "Your session has expired — please log in again"
    SESSION_MALFORMED              = "Please log in again"
    DELIVERY_OUTSIDE_AREA          = "This location is outside our delivery area."
    # ── Centralized consumer-facing error messages ───────────────────────────
    RESOURCE_ACCESS_DENIED = "You don't have permission to access this resource"
    UPDATE_NOT_PERMITTED = "Update not permitted or record not found"
    CART_MENU_ITEM_NOT_FOUND = "Menu item not found"
    DELIVERY_TYPE_INVALID = "Delivery type must be 'on_campus' or 'off_campus'"
    DELIVERY_OUTSIDE_AREA = "This location is outside our delivery area."
    DELIVERY_HOSTEL_NOT_FOUND = "Hostel not found"
    DELIVERY_GATE_NOT_FOUND = "Gate not found"
    TICKET_NO_HP_DISCOUNT = "This ticket has no HP discount available"
    TICKET_ACCESS_DENIED = "You do not have access to this ticket"
    CAMPUS_ID_REQUIRED = "campus_id is required"
    SPIN_NO_CREDITS_RETRY = "No spin credits available or concurrent update occurred. Please try again."
    FREE_SIDE_ORDER_ID_REQUIRED = "order_id is required"
    ORDER_NOT_MODIFIABLE = "This order can no longer be modified"
    FREE_SIDE_NO_CREDITS_RETRY = "No credits available or concurrent update occurred. Please try again."
    FREE_SIDE_APPLY_FAILED = "Failed to apply free side to order — your credit has not been used, please try again"
    GRADUATION_HP_CLAIM_FAILED = "Failed to award graduation HP — please try again"
    HP_TRANSFER_FAILED_NO_REFUND = "Transfer failed and could not be auto-refunded — contact support"
    HP_TRANSFER_FAILED_REFUNDED = "Transfer failed — your HP has been refunded, please try again"
    PROFILE_EMAIL_REQUIRED_FOR_PAYMENT = "Your profile has no registered email — add one to complete payment"
    ORDER_LOCK_ALREADY_ACTIVE = "You already have an active lock"
    ORDER_LOCK_REWARD_TYPE_INVALID = "reward_type must be 'discount' or 'hp'"
    REVIEW_IMAGES_REQUIRED = "image_urls is required"
    ORDER_ALREADY_CLAIMED = "This order is already owned or claimed"
    REFUND_UNPAID_CANCELLED = "Cannot refund an unpaid cancelled order"
    REFUND_AMOUNT_INVALID = "Invalid refund amount"
    REFUND_ALREADY_FULL = "This order has already been fully refunded."
    SAVED_QUANTITY_INVALID = "quantity must be a valid integer"
    UPLOAD_NOT_CONFIGURED = "Uploads are not configured on this server"
    UPLOAD_FOLDER_INVALID = "Invalid upload folder"
    CARD_PAYMENTS_NOT_CONFIGURED = "Card payments are not configured on this server."
    PAYMENT_GATEWAY_UNAVAILABLE = "Payment gateway unavailable. Please try again later."

    # ══ Audit additions ═══════════════════════════════════════════════════════════════════════
    MILESTONE_NOT_ELIGIBLE                 = "Not yet eligible: need {needed}, have {have} for '{trigger_type}'"
    MILESTONE_CHECK_FAILED                 = "Milestone check failed"
    MILESTONE_CONFIG_ERROR                 = "Configuration error for {trigger_type} — please try again later"
    MILESTONE_TRIGGER_TYPE_INVALID         = "trigger_type must be one of: {valid}"
    REFERRAL_COMPLETE_FAILED               = "Failed to complete referral"
    SQUAD_ORDERS_DISABLED                  = "Group ordering is not available right now"
    SQUAD_ALREADY_MEMBER                   = "Already a member"
    SQUAD_MEMBER_REMOVED                   = "Member removed"
    REWARD_FULFILLMENT_TYPE_INVALID        = "fulfillment_type must be one of: pickup, delivery"
    REWARD_ECONOMICS_INVALID               = "Reward economics (cost, HP value) are invalid"
    REWARD_DELIVERY_NEXT_ORDER             = "Delivery will be added to your next order"
    REDEMPTION_ACTUAL_COST_INVALID         = "actual_cost must be a non-negative number"
    FLASH_WINDOW_INVALID                   = "Flash sale window is invalid"
    FLASH_QUANTITY_INVALID                 = "quantity must be a positive whole number"

    MARKETPLACE_NOT_OPEN                   = "Marketplace is not open yet"
    SUBSCRIPTION_CODES_NOT_AVAILABLE       = "Subscription code redemption is not available right now"
    SETTINGS_WRITE_FORBIDDEN               = "Only super_admin may modify global settings, or your own campus's admin for campus-specific ones"

    STOREFRONT_CONFIG_UNAVAILABLE          = "Configuration is temporarily unavailable"
    STOREFRONT_HOURS_FIELDS_REQUIRED       = "At least one of open_time, close_time, is_closed is required"
    STOREFRONT_HOURS_CREATE_REQUIRES_TIMES = "open_time and close_time are required to create hours for this campus/weekday"
    STOREFRONT_TIME_INVALID                = "'{field}' must be a valid time (HH:MM)"
    STOREFRONT_HOURS_ORDER_INVALID         = "close_time must be later than open_time"
    STOREFRONT_DATE_REQUIRED               = "date (or override_date) is required"
    STOREFRONT_DATE_INVALID                = "'{field}' must be a valid date (YYYY-MM-DD)"
    STOREFRONT_CAMPUS_REQUIRED             = "campus_id is required for this action"
    STOREFRONT_NOTHING_TO_UPDATE           = "No updatable fields were provided"
    STOREFRONT_SUPPORTER_NOT_FOUND         = "Early supporter not found"
    STOREFRONT_SUPPORTER_ADDED             = "Early supporter added"
    STOREFRONT_SUPPORTER_REMOVED           = "Early supporter removed"
    STOREFRONT_BANNER_NOT_FOUND            = "Banner not found"
    STOREFRONT_BANNER_DELETED              = "Banner '{title}' deleted"
    STOREFRONT_IMAGES_INVALID              = "'images' must be a list of URL strings"
    STOREFRONT_IMAGE_URL_REQUIRED          = "image_url is required"
    STOREFRONT_PHOTO_URL_REQUIRED          = "photo_url is required"
    STOREFRONT_EMAIL_INVALID               = "email is invalid"
    STOREFRONT_SUBSCRIBED                  = "Subscribed successfully"
    STOREFRONT_PROMO_AMOUNT_INVALID        = "order_subtotal must be a non-negative number"
    STOREFRONT_UNSUB_TOKEN_REQUIRED        = "An unsubscribe token is required"
    STOREFRONT_UNSUB_TOKEN_INVALID         = "This unsubscribe link is invalid"
    STOREFRONT_CAMPAIGN_TEXT_LIMITS        = "subject must be 1-200 characters and body 1-20000 characters"
    STOREFRONT_CAMPAIGN_TARGET_REQUIRED    = "super_admin must pass campus_id or all_campuses=true"
    STOREFRONT_CAMPAIGN_DUPLICATE          = "An identical newsletter was already queued in the last 10 minutes"
    STOREFRONT_CAMPAIGN_QUEUED             = "Newsletter queued for delivery"
    STOREFRONT_CAMPAIGN_NOT_FOUND          = "Newsletter campaign not found"
    STOREFRONT_CAMPAIGN_NOT_CANCELLABLE    = "Only queued or sending newsletters can be cancelled"
    STOREFRONT_CAMPAIGN_CANCELLED          = "Newsletter cancelled"
    STOREFRONT_TEST_NO_EMAIL               = "Your account has no email address to send a test to"
    STOREFRONT_CAMPAIGN_TEST_SENT          = "Test newsletter sent to your email"
    CAMPUS_NOT_FOUND                       = "Campus not found"
    CAMPUS_LOCATION_INVALID                = "Send lat and lon as numbers (latitude -90 to 90, longitude -180 to 180), or coordinates as \"lat, lon\" - or both null to clear"
    CAMPUS_LOCATION_OUTSIDE_NIGERIA        = "These coordinates are outside Nigeria - check that latitude and longitude are not swapped (send force=true to save anyway)"
    CAMPUS_LOCATION_SAVED                  = "Campus location saved"
    CAMPUS_LOCATION_CLEARED                = "Campus location cleared - the delivery radius is no longer enforced"
    RIDER_NOT_ASSIGNED_TO_ORDER            = "Unauthorized: Rider is not assigned to this order"
    ORDER_STATUS_CONFLICT                  = "The order status changed - refresh and try again"
    RIDER_DELIVERED_NOTE                   = "Marked delivered by rider"
    RIDER_PICKUP_NOTE                      = "Picked up from kitchen"
    RIDER_ATTEMPT_DEFAULT_NOTE             = "Delivery attempted - customer unreachable"
    ORDER_KITCHEN_CAMPUS_MISMATCH          = "Unauthorized: Kitchen staff is scoped to a different campus"
    ORDER_ADMIN_CAMPUS_MISMATCH            = "Unauthorized: Admin is scoped to a different campus"
    ORDER_INVALID_TRANSITION               = "Cannot transition '{current}' to '{new}'"
    ORDER_UPDATE_FAILED                    = "Order status update failed - no matching order or insufficient permissions"
    RIDER_LOCATION_INVALID                 = "location_lat and location_lng must be numbers (latitude -90 to 90, longitude -180 to 180)"
    RIDER_ORDER_NOT_ACTIVE                 = "This order is no longer active"
    RIDER_NOTES_INVALID                    = "notes must be text of at most 500 characters"
    RIDER_QUERY_INVALID                    = "limit and offset must be whole numbers (limit 1-100, offset 0 or more)"
    GUEST_ORDER_OUT_SUBJECT                = "Your order {order_number} is on its way"
    GUEST_ORDER_OUT_BODY                   = "Good news - order {order_number} is out for delivery. Please keep your phone close so the rider can reach you."
    GUEST_ORDER_DELIVERED_SUBJECT          = "Your order {order_number} was delivered"
    GUEST_ORDER_DELIVERED_BODY             = "Order {order_number} has been delivered. Enjoy your meal!"
    GUEST_ORDER_ATTEMPTED_SUBJECT          = "We could not deliver order {order_number}"
    GUEST_ORDER_ATTEMPTED_BODY             = "Our rider tried to deliver order {order_number} but could not reach you. Please contact us so we can arrange another attempt."
    NEWSLETTER_UNSUBSCRIBE_FOOTER          = "You are receiving this because you subscribed to {app_name} updates."
    NEWSLETTER_UNSUBSCRIBE_LINK            = "Unsubscribe"
    NEWSLETTER_FRONTEND_URL_MISSING        = "FRONTEND_URL is not configured for production - refusing to send emails without a working unsubscribe link"
    ERR_UNEXPECTED                         = "An unexpected error occurred"
    CONFLICT_ALREADY_EXISTS                = "This record already exists"
    REQUEST_BODY_INVALID                   = "Request body must be a JSON object."
    AUTH_FIELD_INVALID                     = "{field} has an invalid value."
    CAMPUS_INVALID                         = "The selected campus is not available."
    DEPARTMENT_INVALID                     = "Please select a valid department."
    ACADEMIC_LEVEL_INVALID                 = "'{level}' is not a valid academic level."
    REGISTER_MIN_AGE                       = "You must be at least {minimum_age} years old to register."
    NICKNAME_INVALID                       = "Nickname must be 2-20 characters: letters, numbers, underscores, and spaces only."
    REGISTER_FAILED_REASON                 = "Registration failed: {reason}"
    REGISTER_NO_USER_ID                    = "Registration failed. Please try again."
    AUTH_EMAIL_NOT_CONFIRMED               = "Please verify your email address before logging in."
    AUTH_ME_FAILED                         = "Could not load your account. Please try again."
    PHOTO_URL_REQUIRED                     = "photo_url is required."
    PHOTO_URL_INVALID                      = "photo_url must be a valid https URL."
    PROFILE_UPDATE_FAILED                  = "Could not update your profile. Please check your details and try again."
    LOGOUT_FAILED                          = "Could not log you out. Please try again."
    LOGOUT_ALL_FAILED                      = "Could not sign you out of every device. Please try again."
    ADDRESS_COORDINATES_INVALID            = "Latitude/longitude are out of range."
    ADDRESS_SAVE_FAILED                    = "Could not save the address. Please try again."
    AUTH_NEW_PASSWORD_SAME                 = "Your new password must be different from the current one."
    ACCOUNT_DELETE_WALLET_BALANCE          = "Withdraw or spend your wallet balance before deleting your account."
    ACCOUNT_DELETE_ACTIVE_ORDERS           = "You have orders in progress. Deleting your account is possible once they are completed."
    ACCOUNT_DELETE_FAILED                  = "Account deletion failed. Please try again."
    AUTH_RESET_CONFIRM_REQUIRED            = "access_token and new_password are required."
    AUTH_RESET_FAILED                      = "This reset link is invalid or has expired. Please request a new one."
    DEVICE_TOKEN_INVALID                   = "Invalid device token."
    DEVICE_PLATFORM_INVALID                = "platform must be ios, android or web."
    SEARCH_FAILED                          = "Search is temporarily unavailable."
    STOCK_FIELD_REQUIRED                   = "'{field}' is required"
    STOCK_NUMERIC_FIELDS_INVALID           = "conversion_factor/low_stock_threshold/current_balance must be numbers"
    STOCK_CONVERSION_FACTOR_INVALID        = "'conversion_factor' must be greater than 0"
    STOCK_ITEM_CREATE_FAILED               = "Could not create stock item: {detail}"
    STOCK_ITEM_NOT_FOUND                   = "Stock item not found"
    STOCK_QUANTITY_COST_INVALID            = "'quantity'/'cost' must be numbers"
    STOCK_QUANTITY_INVALID                 = "'quantity' must be a number"
    STOCK_ENTRY_TYPE_INVALID               = "type must be one of: usage, waste, correction"
    STOCK_PURCHASE_LOGGED                  = "Stock purchase logged successfully"
    STOCK_USAGE_LOGGED                     = "Stock usage logged successfully"
    KITCHEN_CAMPUS_UNRESOLVED              = "Could not resolve a campus for this request"
    PAGINATION_INVALID                     = "limit and offset must be whole numbers"
    WALLET_AMOUNT_INVALID                  = "wallet_amount must be a number that is 0 or more"
    PURCHASE_NOT_FOUND                     = "Purchase not found"
    PURCHASE_STATUS_INVALID                = "status must be one of: cancelled, completed, pending, refunded"
    PURCHASE_STATUS_FINAL                  = "Refunded or cancelled purchases cannot be changed"
    PURCHASE_NO_CHANGE                     = "No change"
    PURCHASE_UPDATED                       = "Purchase updated"
    PURCHASE_INSUFFICIENT_HP               = "You do not have enough HP for this purchase"
    PURCHASE_INSUFFICIENT_WALLET           = "Your wallet balance is too low for this purchase"
    PURCHASE_PRICE_CHANGED                 = "The price changed. Please review it and try again."
    PURCHASE_FAILED                        = "Purchase could not be completed. Please try again."
    PURCHASE_REFUND_FAILED                 = "Refund could not be completed. Nothing was changed."
    PURCHASE_REFUND_PARTIAL                = "Refund was only partly completed. Run the same request again to finish it."
    PURCHASE_REFUND_MANUAL                 = "Refund failed part-way and the reversal also failed. Manual correction needed."
    PURCHASE_CODE_DELIVERED_NO_REFUND      = "This purchase cannot be refunded because the access code was delivered. If the code does not work, report it from the purchase."
    PURCHASE_REPORT_REASON_INVALID         = "Tell us what is wrong (5 to 500 characters)"
    PURCHASE_REPORT_NOT_ALLOWED            = "Only completed purchases can be reported"
    PURCHASE_REPORT_ALREADY_OPEN           = "You already have an open report for this purchase"
    PURCHASE_REPORT_SENT                   = "Thanks. We will review this and get back to you."
    PURCHASE_REPORT_NOT_FOUND              = "Report not found"
    PURCHASE_REPORT_CLOSED                 = "This report has already been resolved"
    PURCHASE_REPORT_ACTION_INVALID         = "action must be one of: replace, refund, reject"
    PURCHASE_REPORT_RESOLVED               = "Report resolved"
    LISTING_INVALID_NUMBER                 = "{field} must be a number that is 0 or more"
    LISTING_CAMPUS_REQUIRED                = "campus_id is required"
    LISTING_IMAGE_REQUIRED                 = "image_url is required"
    LISTING_AVAILABILITY_FIELD_REQUIRED    = "At least one availability field is required"
    LISTING_HAS_PURCHASES                  = "Cannot delete a listing that has purchase history"
    LISTING_DELETED                        = "Listing '{title}' deleted"
    LISTING_NOT_CODE_TYPE                  = "This listing does not use access codes"
    LISTING_CODES_INVALID                  = "codes must be a list of non-empty text values"
    LISTING_CODES_TOO_MANY                 = "Upload at most 500 codes at a time"
    LISTING_CODES_ALL_EXIST                = "All submitted codes already exist for this listing"
    LISTING_CODES_UPLOAD_FAILED            = "Codes could not be uploaded. Please try again."
    FIELD_MUST_BE_BOOLEAN                  = "{field} must be true or false"
    VENDOR_EMAIL_INVALID                   = "vendor_email must be a valid email address"
    MARKETPLACE_PENDING_TITLE              = "Marketplace order to fulfil"
    MARKETPLACE_PENDING_BODY               = "A purchase of '{title}' is waiting for fulfilment."
    MARKETPLACE_REPORT_ADMIN_TITLE         = "Access code reported"
    MARKETPLACE_REPORT_ADMIN_BODY          = "A buyer reported that the code for '{title}' does not work."
    MARKETPLACE_REPORT_UPDATE_TITLE        = "Report update"
    MARKETPLACE_REPORT_UPDATE_BODY         = "Your report about {title} was reviewed: {outcome}."
    MARKETPLACE_CODE_REPLACED_TITLE        = "Your new access code"
    MARKETPLACE_CODE_REPLACED_BODY         = "Your replacement code for {title}: {code}"
    REWARD_ID_REQUIRED                     = "reward_id is required"
    FLASH_WINDOW_END_REQUIRED              = "window_ends_at is required"
    FLASH_DISCOUNT_RANGE_INVALID           = "discount_pct must be between 0 and 1"
    FLASH_SALE_WINDOW_OVERLAP              = "An active flash sale already overlaps this window for this reward"
    DELIVERY_MODE_INVALID                  = "delivery_mode must be 'instant' or 'next_order'"
    REWARD_NOT_READY_FOR_DELIVERY          = "Reward isn't ready for delivery yet"
    DELIVERY_ALREADY_CHOSEN                = "Delivery already chosen for this reward"
    FREE_SIDE_NAME_REQUIRED                = "name is required"
    FREE_SIDE_ITEM_NOT_FOUND               = "Free side item not found"
    FREE_SIDE_ITEM_ID_REQUIRED             = "free_side_item_id is required"
    FREE_SIDE_SELECTION_NOT_FOUND          = "Selection not found"
    REDEMPTION_UPDATE_CONFLICT             = "Redemption was already updated by someone else — refresh and retry"
    SQUAD_MEMBER_ALREADY_ACTIVE            = "Already a member"
    SQUAD_MEMBER_NOT_FOUND                 = "Member not found"
    GENERIC_UNEXPECTED_ERROR               = "An unexpected error occurred"
    DELIVERY_GATE_OR_LOCATION_REQUIRED     = "Select a gate or share your location for off-campus delivery"
    SQUAD_NOT_FOUND                        = "Squad not found"
    RIDER_UNAUTHORIZED_ORDER               = "Unauthorized: Rider is not assigned to this order"
    REFUND_USE_DEDICATED_ENDPOINT          = "Use the refund endpoint to refund an order — status cannot be set to 'refunded' directly"
    PAGINATION_PARAMS_INVALID              = "limit and offset must be integers"
    REVIEW_REQUIRED_BEFORE_IMAGES          = "Submit a review before adding images"
    GUEST_REFUND_MANUAL_REQUIRED           = "Guest orders have no wallet to refund to — process this refund manually through the payment provider"
    SQUAD_INVITE_RESEND_FAILED             = "Could not resend invite — try again"
    EVENT_CHECKIN_FAILED                   = "Check-in failed — please try again"
    ANALYTICS_INVALID_DATE                 = "Dates must be in YYYY-MM-DD format"
    ANALYTICS_INVALID_DATETIME             = "shared_at must be an ISO 8601 date-time"
    ANALYTICS_INVALID_NUMBER               = "{param} must be a whole number"
    ANALYTICS_INVALID_CAMPUS               = "campus_id must be a valid UUID"
    ANALYTICS_BRAND_NOT_FOUND              = "Brand partnership request not found"
    ACCOUNT_NO_CAMPUS                      = "Your account is not assigned to a campus. Ask a super admin to assign one."
    HP_VALUE_NOT_CONFIGURED                = "The HP value setting (hp_liability_value) is missing or invalid. Ask a super admin to set it in system settings."
    BRAND_NAME_INVALID                     = "brand_name is required (up to 200 characters)"
    BRAND_EMAIL_INVALID                    = "contact_email must be a valid email address"
    BRAND_REQUESTED_DATA_INVALID           = "requested_data must be a JSON object of at most 10,000 characters"
    TIER_FACE_VALUE_INVALID                = "price_naira_full must be a number and at least price_naira"
    SESSION_PROFILE_NOT_FOUND              = "User profile not found"
    AUTH_ROLE_REQUIRED                     = "Requires one of roles: {roles}"
    NOTIFICATION_NOT_FOUND                 = "Notification not found"
    MILESTONE_ALREADY_COMPLETED            = "Already completed"
    PWA_MILESTONE_NOT_CONFIGURED           = "PWA install milestone not configured or inactive"
    PUSH_MILESTONE_NOT_CONFIGURED          = "Push subscribe milestone not configured or inactive"
    PUSH_SUBSCRIPTION_UPDATE_FAILED        = "Failed to update subscription"
    HP_ADMIN_AMOUNT_MUST_BE_POSITIVE       = "amount must be a positive number — use /admin/expire to reduce HP"
    HP_ADMIN_TARGET_NOT_FOUND              = "Target user profile not found"
    HP_ADMIN_GRANT_CROSS_CAMPUS            = "Cannot grant HP outside your campus"
    HP_ADMIN_EXPIRE_CROSS_CAMPUS           = "Cannot expire HP outside your campus"
    HP_ADMIN_NO_ACTIVE_HP                  = "No active HP to expire"
    HP_TRANSFER_CROSS_CAMPUS               = "You can only transfer HP to students on your own campus."
    SETTINGS_SUPER_ADMIN_ONLY              = "Only super_admin may modify system settings"
    HP_MULTIPLIER_INVALID                  = "hp_multiplier must be 0.5, 1.0, or 2.0"
    NOTIFICATION_BLAST_CAMPUS_DENIED       = "Unable to create blast for the specified campus"
    MILESTONE_ADMIN_GRANT_CROSS_CAMPUS     = "Cannot grant milestone outside your campus"
    NOTIFICATION_BLAST_CREATE_FAILED       = "Failed to create blast"
    PUSH_SUBSCRIPTION_FAILED               = "Failed to register subscription"
    REFERRAL_DATA_LOAD_FAILED              = "Failed to load referral data"
    PRIZE_FULFILMENT_TITLE                 = "Update on your prize"
    PRIZE_FULFILMENT_BODY                  = "Your {prize} is now {status}."
    SERVICE_UNAVAILABLE                    = "Service temporarily unavailable. Please try again."
    PROFILE_NOT_FOUND                      = "User profile not found"
    ROLE_NOT_PERMITTED                     = "You don't have permission to perform this action"
    JSON_OBJECT_REQUIRED                   = "Request body must be a JSON object"
    INVALID_INPUT                          = "One or more fields are invalid"
    REQUEST_FAILED_RETRY                   = "Something went wrong. Please try again."
    FIELD_REQUIRED                         = "'{field}' is required"
    RATE_LIMIT_EXCEEDED                    = "Rate limit exceeded"
    RATE_LIMIT_DETAIL                      = "Maximum {max} requests per {window}s window. Try again later."
    UPLOAD_URL_INVALID                     = "Invalid upload URL"
    REFERENCE_DATA_UNAVAILABLE             = "This list is temporarily unavailable. Please try again."
    INVALID_CAMPUS_ID                      = "campus_id must be a valid UUID"
    RESOURCE_NOT_FOUND                     = "Not found"
    ORDERING_WINDOW_NOT_FOUND              = "Ordering window not found"
    WINDOW_LABEL_INVALID                   = "label must be 1 to 100 characters"
    WINDOW_WEEKDAY_INVALID                 = "weekday must be a whole number from 0 to 6"
    WINDOW_DATE_INVALID                    = "date must use the format YYYY-MM-DD"
    WINDOW_TIME_INVALID                    = "times must use the format HH:MM"
    WINDOW_CAPACITY_INVALID                = "capacity must be a whole number (at least 1 for a delivery window, 0 or more for an ordering window)"
    WINDOW_FLAG_INVALID                    = "{field} must be true or false"
    WINDOW_DAY_REQUIRED                    = "Give exactly one of weekday or date"
    WINDOW_TIMES_ORDER                     = "closes_at must be after opens_at"
    WINDOW_EXISTS                          = "A window with the same campus, day and hours already exists"
    WINDOW_CANNOT_CHANGE                   = "A window that is {current} cannot be changed this way"
    WINDOW_ALREADY_ENDED                   = "This window has already ended and cannot be reopened"
    RIDER_NOT_FOUND                        = "Rider not found"
    RIDER_DEACTIVATED                      = "That rider account is deactivated"
    RIDER_ROLE_REQUIRED                    = "That user is not a rider"
    RIDER_CAMPUS_MISMATCH                  = "That rider belongs to a different campus"
    BATCH_ORDERS_NOT_FOUND                 = "Some orders were not found"
    BATCH_ORDERS_NOT_ELIGIBLE              = "Only ready orders of this window and campus that are not in another batch can be added"
    BATCH_ORDERS_CHANGED                   = "Some orders changed while the batch was being created. Nothing was assigned; please try again."
    BATCH_USE_DELETE                       = "To cancel a batch use the cancel action so its orders are released"
    BATCH_HAS_OPEN_ORDERS                  = "The batch still has orders that are not finished"
    BATCH_STATUS_INVALID_TRANSITION        = "A batch that is {current} cannot be set to {new}"
    BATCH_ALREADY_FINISHED                 = "This batch is already finished"
    BATCH_IN_PROGRESS                      = "Some orders are already out for delivery, so this batch cannot be cancelled"
    BATCH_RELEASE_FAILED                   = "Some orders could not be released. Nothing else was changed; please try again."
    PROMO_UNKNOWN_FIELDS                   = "These fields are not supported: {fields}"
    PROMO_VALUE_INVALID                    = "discount_value must be a number greater than 0"
    PROMO_PERCENT_TOO_HIGH                 = "A percentage discount cannot be more than 100"
    PROMO_MIN_ORDER_INVALID                = "min_order_amount must be 0 or more"
    PROMO_MAX_USES_BELOW_USED              = "max_uses cannot be lower than the {used} uses so far"
    PROMO_DATE_INVALID                     = "{field} must be a valid date and time"
    PROMO_IDS_INVALID                      = "{field} must be a list of up to 200 valid ids"
    PROMO_CODE_INVALID                     = "code must be 3 to 40 characters: letters, numbers, - or _"
    PROMO_CODE_EXISTS                      = "That promo code already exists"
    PROMO_FIELD_LOCKED                     = "{field} cannot be changed after the code is created"
    ADMIN_CART_ALREADY_RECOVERED           = "This customer has already ordered, so no reminder is needed"
    ADMIN_CART_GUEST_NO_NUDGE              = "This cart belongs to a guest (no account), so it cannot be nudged from here"
    ADMIN_CART_USER_INACTIVE               = "This customer's account is deactivated"
    ADMIN_NUDGE_TOO_SOON                   = "This customer was already sent a cart reminder in the last 24 hours"
    ADMIN_NUDGE_FAILED                     = "The reminder could not be sent. Please try again."
    BULK_GRANT_TOO_MANY                    = "This would grant HP to more than {max} users at once. Narrow the filters or run it in batches."
    BULK_GRANT_NO_RECIPIENTS               = "No matching, active users were found for this grant"
    BULK_GRANT_USER_FAILED                 = "Could not grant HP to this user. Please try again."
    HP_ADMIN_GRANT_TITLE                   = "You received {hp} bonus {currency}! 🎁"
    HP_ADMIN_GRANT_BODY                    = "{name}, you've been awarded {hp} {currency}: {reason}"
    ADMIN_CANNOT_CHANGE_OWN_ROLE           = "Cannot change your own role"
    ADMIN_ROLE_CHANGE_SUPER_ONLY           = "Only super_admin can assign or change admin roles"
    ADMIN_CANNOT_DEACTIVATE_SELF           = "You cannot deactivate your own account"
    ADMIN_ACCOUNT_CHANGE_SUPER_ONLY        = "Only super_admin can deactivate or reactivate admin accounts"
    ADMIN_ACCOUNT_ANONYMIZED               = "This account was deleted by its owner and cannot be reactivated"
    ACCOUNT_DELETE_OPEN_ORDERS             = "You still have orders in progress. You can delete your account once they are completed or cancelled."
    ADMIN_USER_ALREADY_DEACTIVATED         = "User is already deactivated"
    CAMPUS_REQUIRED                        = "Please choose your campus"
    CAMPUS_NOT_AVAILABLE                   = "That campus is not available"
    ACADEMIC_CALENDAR_UNAVAILABLE          = "The academic calendar is temporarily unavailable. Please try again."
    NO_ACTIVE_ACADEMIC_TERM                = "No active term for current date"
    ACADEMIC_CALENDAR_ENTRY_NOT_FOUND      = "Academic calendar entry not found"
    ACADEMIC_CALENDAR_ENTRY_EXISTS         = "An entry with this campus, type, name and academic year already exists"
    INVALID_DATE_FORMAT                    = "Dates must use the format YYYY-MM-DD"
    END_DATE_BEFORE_START                  = "end_date must not be before start_date"
    ACADEMIC_LEVEL_NOT_FOUND               = "Academic level not found"
    ACADEMIC_LEVEL_NAME_VALUE_REQUIRED     = "'name' and 'value' are required"
    ACADEMIC_LEVEL_EXISTS                  = "An academic level with value '{value}' already exists"
    ACADEMIC_LEVEL_DEACTIVATED             = "Academic level '{name}' deactivated"
    ACADEMIC_LEVEL_RESTORED                = "Academic level '{name}' restored"
    DEPARTMENT_NOT_FOUND                   = "Department not found"
    DEPARTMENT_NAME_FACULTY_REQUIRED       = "'name' and 'faculty' are required"
    DEPARTMENT_EXISTS                      = "A department with that name or slug already exists here"
    DEPARTMENT_DEACTIVATED                 = "Department '{name}' deactivated"
    DEPARTMENT_RESTORED                    = "Department '{name}' restored"
    INVALID_SLUG                           = "slug may contain only lowercase letters, digits and hyphens"
    ADMIN_REQUEST_BODY_INVALID             = "Request body must be a JSON object."
    PRIZE_STATUS_INVALID                   = "Invalid status for this record."
    PRIZE_NOTES_INVALID                    = "Notes must be text of at most 1000 characters."
    PRIZE_ALREADY_CLOSED                   = "This record is already closed (fulfilled or cancelled) and its status cannot change."
    PRIZE_UPDATED                          = "Record updated."
    SPIN_PRIZE_NOT_FOUND                   = "Prize record not found."
    SPIN_PRIZE_FULFILLED                   = "Prize marked fulfilled."
    FEATURE_FLAG_ACTIVE_INVALID            = "is_active must be true or false."
    FEATURE_FLAG_DESCRIPTION_INVALID       = "description must be text of at most 500 characters."
    FEATURE_FLAG_CAMPUS_INVALID            = "campus_id is not valid for this flag."
    FEATURE_FLAG_NAME_INVALID              = "Flag names use lowercase letters, numbers and underscores (max 64)."
    DEPARTMENTS_UNAVAILABLE                = "Departments are temporarily unavailable. Please try again."
    SPIN_POOL_NAME_REQUIRED                = "name is required"
    SPIN_POOL_WEIGHT_INVALID               = "weight must be a positive integer"
    SPIN_POOL_PRIZE_NOT_FOUND              = "Prize not found"
    SPIN_POOL_NO_VALID_FIELDS              = "No valid fields to update"
    SPIN_POOL_UPDATE_FAILED                = "Update failed"
    SPIN_POOL_DEACTIVATION_FAILED          = "Deactivation failed"
    RIDER_LOCATION_REQUIRED                = "location_lat and location_lng are required"
    RIDER_COORDINATES_INVALID              = "location_lat and location_lng must be valid coordinates"
    RIDER_LOCATION_UPDATED                 = "Location updated"
    RIDER_AVAILABILITY_INVALID             = "is_available must be true or false"
    RIDER_CALL_NOT_ALLOWED                 = "The customer's number is only available while the order is being delivered"
    RIDER_BATCH_ASSIGNED_TITLE             = "New delivery batch"
    RIDER_BATCH_ASSIGNED_BODY              = "You have been assigned a batch of {count} order(s)."
    RIDER_ORDER_REMOVED_TITLE              = "Order removed from your batch"
    RIDER_ORDER_REMOVED_BODY               = "An order in your batch was cancelled or refunded. Check your batch before you head out."
    ADMIN_RIDER_UNAVAILABLE                = "That rider is offline. Pick an available rider, or send force=true to assign anyway."
    RIDER_PAY_INVALID                      = "rider_pay_total must be a number that is 0 or more"
    RIDER_PAY_ALREADY_PAID                 = "This batch is already marked paid. Mark it unpaid first to change the amount."
    RIDER_PAY_BATCH_CANCELLED              = "A cancelled batch has no rider pay"
    RIDER_PAY_BATCH_IDS_INVALID            = "batch_ids must be a list of 1 to 100 batch ids"
    CART_QUANTITY_INVALID                  = "quantity must be a whole number"
    REWARD_FULFILLED_CHOOSE_DELIVERY_TITLE = "Your reward is ready - choose delivery"
    REWARD_FULFILLED_CHOOSE_DELIVERY_BODY  = "Your {name} is ready. Choose how you would like to receive it."


# Short alias
M = MSG


# ── Message resolver ──────────────────────────────────────────────────────────
import os as _os


class _PassthroughDict(dict):
    """Return '{key}' for any missing key so unrelated placeholders pass through."""
    def __missing__(self, key):
        return '{' + key + '}'


def resolve_msg(text: str, **kwargs) -> str:
    """Resolve {currency} and {platform} from env, plus caller-supplied kwargs.

    Unknown placeholders (e.g. {order_id}, {name}) are left as-is so the
    caller doesn't need to supply every placeholder in advance.

    Usage (replaces raw MSG.CONSTANT.format(...) calls in route/service code):
        resolve_msg(MSG.HP_INSUFFICIENT, have=bal, need=cost)
    """
    if '{' not in text:
        return text
    defaults = {
        'currency': _os.environ.get('HP_CURRENCY_NAME', 'HP'),
        'platform': _os.environ.get('APP_NAME', 'Holy Grills'),
    }
    defaults.update(kwargs)
    return text.format_map(_PassthroughDict(defaults))
