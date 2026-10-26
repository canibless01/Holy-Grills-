"""
Application email dispatch with preferred provider and quota-only failover.
The caller receives False for an unavailable or uncertain outcome; no speculative retry.

Resend REST API: POST https://api.resend.com/emails
Auth: Authorization: Bearer <RESEND_API_KEY>
"""

import os
import requests
from app.messages import MSG
from app.utils.logger import get_logger

logger = get_logger(__name__)

RESEND_BASE = "https://api.resend.com"

TEMPLATES = {
    "order_confirmed": {
        "subject": MSG.EMAIL_ORDER_CONFIRMED,
        "body": lambda d: f"""Your order #{d.get('order_id','')[:8].upper()} has been received and is heading to the kitchen.

Total: ₦{d.get('total', 0):,.0f}
Estimated delivery: {d.get('window_label', 'your selected window')}""",
        "cta_buttons": lambda d: [{"label": "Track Your Order", "url": f"https://holygrills.online/orders/{d.get('order_id', '')}", "primary": True}],
    },
    "hp_earned": {
        "subject": MSG.EMAIL_HP_EARNED,
        "body": lambda d: f"""You earned {d.get('hp', 0)} {d.get('currency', 'HP')} on your recent order. Keep ordering to build your {d.get('currency', 'HP')} balance and unlock rewards!

Your balance: {d.get('active_hp', 0)} {d.get('currency', 'HP')} active | {d.get('pending_hp', 0)} {d.get('currency', 'HP')} pending""",
        "cta_buttons": lambda d: [{"label": "See What You Can Unlock", "url": "https://holygrills.online/rewards", "primary": True}],
    },
    "tier_upgrade": {
        "subject": MSG.EMAIL_TIER_UPGRADE,
        "body": lambda d: f"""Congratulations — you've reached {d.get('tier_name', '')} tier!

Your new benefits:
{d.get('perks', '')}

Enjoy your new perks!""",
        "cta_buttons": lambda d: [{"label": "View Your Perks", "url": "https://holygrills.online/rewards", "primary": True}],
    },
    "wallet_funded": {
        "subject": "Your Wallet is Funded! 🎉",
        "body": lambda d: f"""Your {d.get('app_name', '')} wallet has been credited with ₦{d.get('amount', 0):,.0f}.

New balance: ₦{d.get('new_balance', 0):,.0f}""",
        "cta_buttons": lambda d: [{"label": "Treat Yourself", "url": "https://holygrills.online/menu", "primary": True}],
    },
    "password_reset": {
        "subject": MSG.EMAIL_PASSWORD_RESET,
        "body": lambda d: f"""We received a request to reset your password.

This link expires in 1 hour. If you didn't request this, you can safely ignore this email.""",
        "cta_buttons": lambda d: [{"label": "Reset Password", "url": d.get('reset_link', ''), "primary": True}],
    },
    "birthday_bonus": {
        "subject": MSG.EMAIL_BIRTHDAY_BONUS,
        "body": lambda d: f"""Happy Birthday! As a gift, we've added {d.get('hp', 150)} {d.get('currency', 'HP')} to your account.

Treat yourself on us!""",
        "cta_buttons": lambda d: [{"label": "Order Now", "url": "https://holygrills.online/menu", "primary": True}],
    },
    "referral_completed": {
        "subject": MSG.EMAIL_REFERRAL_COMPLETED,
        "body": lambda d: f"""Great news — a friend you referred just placed their first order on {d.get('app_name', '')}.

You've earned {d.get('hp', 75)} {d.get('currency', 'HP')} (active, no monthly cap). Spend it on your next order!""",
        "cta_buttons": lambda d: [{"label": "Order Now", "url": "https://holygrills.online/menu", "primary": True}],
    },
    "abandoned_cart": {
        "subject": MSG.EMAIL_ABANDONED_CART,
        "body": lambda d: f"""You left some items in your cart. Come back and complete your order — your {d.get('currency', 'HP')} is waiting!

{d.get('items_summary', '')}""",
        "cta_buttons": lambda d: [{"label": "Complete Your Order", "url": "https://holygrills.online/checkout", "primary": True}],
    },
    "reward_redeemed": {
        "subject": "Your Reward is Confirmed! 🎁",
        "body": lambda d: f"""You redeemed: {d.get('reward_name', '')} for {d.get('hp_spent', 0)} {d.get('currency', 'HP')}.

Our team will fulfil your reward within {d.get('fulfilment_time', '24 hours')}.""",
    },
    "tier_grace_period": {
        "subject": MSG.EMAIL_TIER_GRACE,
        "body": lambda d: f"""Your {d.get('currency', 'HP')} activity has dipped below the {d.get('tier_name', 'your tier')} threshold.
You have {d.get('grace_days', 7)} days to place an order and keep your tier status.

You've got this!""",
        "cta_buttons": lambda d: [{"label": "Place an Order", "url": "https://holygrills.online/menu", "primary": True}],
    },
    "tier_dropped": {
        "subject": "Your Tier Status Updated",
        "body": lambda d: f"""Your grace period has ended and your tier has been updated.

Start earning to climb back — we're rooting for you!""",
        "cta_buttons": lambda d: [{"label": "Start Climbing", "url": "https://holygrills.online/menu", "primary": True}],
    },
    "hp_expired": {
        "subject": MSG.EMAIL_HP_EXPIRED,
        "body": lambda d: f"""{d.get('amount', 0)} {d.get('currency', 'HP')} has decayed due to {d.get('inactivity_days', 120)} days of inactivity.

Order now to protect your remaining balance!""",
        "cta_buttons": lambda d: [{"label": "Order Now", "url": "https://holygrills.online/menu", "primary": True}],
    },
    "monthly_birthday_report": {
        "subject": lambda d: f"🎂 Birthday Report — {d.get('month', 'This Month')} ({d.get('count', 0)} users)",
        "body": lambda d: f"""Here are the {d.get('app_name', '')} users with birthdays in {d.get('month', 'this month')}:

{d.get('summary_text', 'No birthdays this month.')}

Total: {d.get('count', 0)} user{'s' if d.get('count', 0) != 1 else ''}

Use this list for birthday outreach.""",
        "skip_greeting": True,
        "skip_signoff": True,
    },
    "event_tickets_export": {
        "subject": lambda d: f"Event Registrants — {d.get('event_title', 'Event')}",
        "body": lambda d: f"""Please find attached the registrant list for {d.get('event_title', 'your event')}.

Total registrants: {d.get('count', 0)}

{d.get('registrant_table', '')}""",
        "skip_greeting": True,
        "skip_signoff": True,
    },
    "event_ticket_qr": {
        "subject": lambda d: f"🎟️ Your Ticket for {d.get('event_title', 'Event')}",
        "body": lambda d: f"""Here is your ticket for {d.get('event_title', '')}!

Date: {d.get('event_date', 'TBA')}
Location: {d.get('event_location', 'TBA')}
Ticket ID: {d.get('ticket_id', '')}

Please show your QR code at the door to check in.

Create an account to earn HP for this event!""",
    },
    "squad_invite": {
        "subject": lambda d: f"You've been invited to join a squad order on {d.get('app_name', 'Holy Grills')}!",
        "body": lambda d: f"""{d.get('organizer', 'A friend')} added you to a squad order on {d.get('app_name', 'Holy Grills')}!

Join the squad order in the app to choose your meal and earn {d.get('currency', 'HP')}.""",
        "cta_buttons": lambda d: [{"label": "Accept Invitation", "url": d.get('invite_link', ''), "primary": True}],
    },
    "guest_order_confirmed": {
        "subject": lambda d: f"Your Order #{d.get('order_id', '')[:8].upper()} is Confirmed!",
        "body": lambda d: f"""Your order #{d.get('order_id', '')[:8].upper()} has been placed successfully!

Tracking code: {d.get('claim_token', '')}

You can use this code to track your order or create an account with this email to claim your order and earn {d.get('currency', 'HP')}.""",
        "cta_buttons": lambda d: [{"label": "Track Your Order", "url": f"https://holygrills.online/track-orders?order_number={d.get('order_id', '')}&claim_token={d.get('claim_token', '')}", "primary": True}],
    },
}


def _resend_api_key() -> str:
    """Return RESEND_API_KEY from env. Empty string if not configured."""
    return os.environ.get("RESEND_API_KEY", "")


import html as _html

def _wrap_url_with_tracking(url: str, blast_id: str, label: str = "") -> str:
    """Wrap a URL with tracking redirect if blast_id is provided."""
    if not blast_id or not url:
        return url
    
    # Get API base URL
    api_base = os.environ.get("API_PUBLIC_URL", "https://holygrills.online/api")
    if api_base.endswith("/"):
        api_base = api_base[:-1]
    
    # Don't track mailto: or tel: links
    if url.startswith("mailto:") or url.startswith("tel:"):
        return url
    
    # Wrap URL with tracking endpoint
    import urllib.parse
    tracking_url = f"{api_base}/notifications/tracking/click?blast_id={blast_id}&url={urllib.parse.quote(url, safe='')}&label={urllib.parse.quote(label, safe='')}"
    return tracking_url


def _build_html(name: str, body_text: str, app_tagline: str, **kwargs) -> str:
    """Build a branded responsive HTML email with inline CSS."""
    safe_name = _html.escape(str(name or "there"))
    safe_tagline = _html.escape(str(app_tagline or "The Holy Grills Team"))
    
    # Extract optional components
    hero_image = kwargs.get("hero_image")
    headline = kwargs.get("headline")
    cta_buttons = kwargs.get("cta_buttons", [])  # List of {"label": "...", "url": "...", "primary": True/False}
    secondary_section = kwargs.get("secondary_section")  # {"title": "...", "text": "...", "link": "...", "link_text": "..."}
    social_links = kwargs.get("social_links", {})  # {"whatsapp": "...", "tiktok": "...", etc.}
    unsubscribe_url = kwargs.get("unsubscribe_url")
    
    # Control greeting/sign-off visibility (prevents duplication when templates include their own)
    skip_greeting = kwargs.get("skip_greeting", False)
    skip_signoff = kwargs.get("skip_signoff", False)
    skip_thank_you = kwargs.get("skip_thank_you", False)  # For transactional emails
    
    # Email tracking parameters
    blast_id = kwargs.get("blast_id")  # For tracking opens/clicks
    track_links = kwargs.get("track_links", False)  # Whether to wrap links with tracking
    
    # Brand colors
    brand_red = "#E01616"
    brand_red_hover = "#B81212"
    bg_color = "#FFF5F0"
    card_bg = "#FFFFFF"
    text_color = "#1A1A1A"
    muted_color = "#666666"
    
    # Build body HTML
    body_html = _html.escape(body_text.strip()).replace("\n", "<br>")
    
    # Wordmark URL (absolute)
    wordmark_url = "https://holygrills.online/brand/wordmark.png"
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <title>Holy Grills</title>
    <!--[if mso]>
    <noscript>
        <xml>
            <o:OfficeDocumentSettings>
                <o:PixelsPerInch>96</o:PixelsPerInch>
            </o:OfficeDocumentSettings>
        </xml>
    </noscript>
    <![endif]-->
    <style>
        /* Reset */
        body, table, td, a {{ -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }}
        table, td {{ mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
        img {{ -ms-interpolation-mode: bicubic; border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; }}
        
        /* All-screen responsive — ensures proper rendering on all devices */
        @media only screen and (max-width: 768px) {{
            .email-container {{ width: 100% !important; max-width: 100% !important; }}
            .fluid {{ max-width: 100% !important; height: auto !important; }}
            .stack-column {{ display: block !important; width: 100% !important; max-width: 100% !important; }}
        }}
        
        /* Tablet responsive */
        @media only screen and (min-width: 621px) and (max-width: 768px) {{
            .email-container {{ width: 100% !important; max-width: 600px !important; }}
        }}
        
        /* Mobile responsive */
        @media only screen and (max-width: 620px) {{
            .email-container {{ width: 100% !important; max-width: 100% !important; }}
            .email-padding {{ padding: 20px 16px !important; }}
            .email-header {{ padding: 24px 20px 16px !important; }}
            .email-footer {{ padding: 24px 20px !important; }}
            .fluid {{ max-width: 100% !important; height: auto !important; }}
            .stack-column {{ display: block !important; width: 100% !important; max-width: 100% !important; }}
            h1 {{ font-size: 24px !important; }}
            h2 {{ font-size: 18px !important; }}
            p {{ font-size: 15px !important; }}
            .cta-button {{ padding: 12px 24px !important; font-size: 15px !important; }}
        }}
        
        /* Small mobile */
        @media only screen and (max-width: 400px) {{
            .email-padding {{ padding: 16px 12px !important; }}
            .email-header {{ padding: 20px 16px 12px !important; }}
            .email-footer {{ padding: 20px 16px !important; }}
            h1 {{ font-size: 22px !important; }}
            p {{ font-size: 14px !important; }}
        }}
        
        /* Dark mode */
        @media (prefers-color-scheme: dark) {{
            .email-bg {{ background-color: #1A1A1A !important; }}
            .email-card {{ background-color: #2A2A2A !important; }}
            .email-text {{ color: #F5F5F5 !important; }}
            .email-muted {{ color: #AAAAAA !important; }}
            .email-footer {{ background-color: #1F1F1F !important; }}
        }}
    </style>
</head>
<body style="margin: 0; padding: 0; background-color: {bg_color}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;" class="email-bg">
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: {bg_color};" class="email-bg">
        <tr>
            <td align="center" style="padding: 20px 10px;">
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="max-width: 600px;" class="email-container">
                    <!-- Card -->
                    <tr>
                        <td style="background-color: {card_bg}; border-radius: 16px; border: 1px solid rgba(0,0,0,0.08); overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.04);" class="email-card">
                            <!-- Header with wordmark -->
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                <tr>
                                    <td style="padding: 32px 40px 24px 40px; text-align: center;">
                                        <a href="https://holygrills.online" style="text-decoration: none;">
                                            <img src="{wordmark_url}" alt="Holy Grills" width="180" style="display: block; margin: 0 auto; max-width: 180px; height: auto;">
                                        </a>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding: 0 40px;">
                                        <div style="height: 1px; background: linear-gradient(to right, transparent, rgba(0,0,0,0.1), transparent);"></div>
                                    </td>
                                </tr>
                            </table>"""
    
    # Hero image (optional)
    if hero_image:
        html += f"""
                            <!-- Hero Image -->
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                <tr>
                                    <td style="padding: 24px 40px 0 40px;">
                                        <img src="{_html.escape(hero_image)}" alt="" width="520" style="display: block; width: 100%; max-width: 520px; height: auto; border-radius: 12px;" class="fluid">
                                    </td>
                                </tr>
                            </table>"""
    
    # Main content
    html += f"""
                            <!-- Content -->
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                <tr>
                                    <td style="padding: 32px 40px;">"""
    
    # Greeting (optional — skip for emails that have their own greeting in body)
    if not skip_greeting:
        html += f"""
                                        <p style="margin: 0 0 16px 0; font-size: 18px; color: {text_color};" class="email-text">Hello {safe_name} 👋</p>"""
    
    # Headline (optional)
    if headline:
        html += f"""
                                        <h1 style="margin: 0 0 20px 0; font-size: 28px; font-weight: 700; color: {text_color}; line-height: 1.3;" class="email-text">{_html.escape(headline)}</h1>"""
    
    # Body text
    html += f"""
                                        <div style="margin: 0 0 24px 0; font-size: 16px; line-height: 1.6; color: {text_color};" class="email-text">
                                            {body_html}
                                        </div>"""
    
    # CTA buttons
    if cta_buttons:
        html += """
                                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin: 0 0 24px 0;">
                                            <tr>"""
        for btn in cta_buttons:
            is_primary = btn.get("primary", True)
            btn_bg = brand_red if is_primary else "transparent"
            btn_color = "#FFFFFF" if is_primary else brand_red
            btn_border = f"2px solid {brand_red}" if not is_primary else "none"
            
            # Wrap URL with tracking if enabled
            btn_url = btn.get("url", "")
            if track_links and blast_id:
                btn_url = _wrap_url_with_tracking(btn_url, blast_id, btn.get("label", ""))
            
            html += f"""
                                                <td style="padding: 0 8px 8px 0;">
                                                    <table role="presentation" cellspacing="0" cellpadding="0" border="0">
                                                        <tr>
                                                            <td style="border-radius: 12px; background-color: {btn_bg}; border: {btn_border};">
                                                                <a href="{_html.escape(btn_url)}" style="display: inline-block; padding: 14px 28px; font-size: 16px; font-weight: 600; color: {btn_color}; text-decoration: none; border-radius: 12px;" target="_blank">{_html.escape(btn['label'])}</a>
                                                            </td>
                                                        </tr>
                                                    </table>
                                                </td>"""
        html += """
                                            </tr>
                                        </table>"""
    
    # Secondary section (optional)
    if secondary_section:
        html += f"""
                                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin: 24px 0; padding: 24px; background-color: {bg_color}; border-radius: 12px;">
                                            <tr>
                                                <td>
                                                    <h2 style="margin: 0 0 12px 0; font-size: 20px; font-weight: 600; color: {text_color};" class="email-text">{_html.escape(secondary_section.get('title', ''))}</h2>
                                                    <p style="margin: 0 0 16px 0; font-size: 15px; line-height: 1.5; color: {muted_color};" class="email-muted">{_html.escape(secondary_section.get('text', ''))}</p>
                                                    <a href="{_html.escape(secondary_section.get('link', '#'))}" style="font-size: 15px; font-weight: 600; color: {brand_red}; text-decoration: none;">{_html.escape(secondary_section.get('link_text', 'Learn more'))} →</a>
                                                </td>
                                            </tr>
                                        </table>"""
    
    # Sign-off (optional — skip for emails that have their own sign-off in body)
    if not skip_signoff:
        html += f"""
                                        <p style="margin: 32px 0 8px 0; font-size: 15px; color: {muted_color};" class="email-muted">With love,</p>
                                        <p style="margin: 0; font-size: 16px; font-weight: 600; color: {text_color};" class="email-text">{safe_tagline}</p>"""
    else:
        # Still need to close the content table cell
        html += ""
    html += """
                                    </td>
                                </tr>
                            </table>"""
    
    # Footer
    html += f"""
                            <!-- Footer -->
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #F5F5F5; border-top: 1px solid rgba(0,0,0,0.08);" class="email-footer">
                                <tr>
                                    <td style="padding: 32px 40px; text-align: center;">"""
    
    # Social icons
    if social_links:
        html += """
                                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin: 0 auto 20px auto;">
                                            <tr>"""
        social_icons = {
            "whatsapp": "https://cdn.jsdelivr.net/npm/simple-icons@v11/icons/whatsapp.svg",
            "tiktok": "https://cdn.jsdelivr.net/npm/simple-icons@v11/icons/tiktok.svg",
            "facebook": "https://cdn.jsdelivr.net/npm/simple-icons@v11/icons/facebook.svg",
            "instagram": "https://cdn.jsdelivr.net/npm/simple-icons@v11/icons/instagram.svg",
            "youtube": "https://cdn.jsdelivr.net/npm/simple-icons@v11/icons/youtube.svg"
        }
        for platform, url in social_links.items():
            if url and platform in social_icons:
                html += f"""
                                                <td style="padding: 0 6px;">
                                                    <a href="{_html.escape(url)}" style="display: inline-block; width: 32px; height: 32px; background-color: {brand_red}; border-radius: 50%; text-align: center; line-height: 32px;" target="_blank">
                                                        <img src="{social_icons[platform]}" alt="{platform}" width="18" height="18" style="display: inline-block; vertical-align: middle; filter: brightness(0) invert(1);">
                                                    </a>
                                                </td>"""
        html += """
                                            </tr>
                                        </table>"""
    
    # Thank you line (optional — skip for transactional emails where it's not relevant)
    if not skip_thank_you:
        html += f"""
                                        <p style="margin: 0 0 12px 0; font-size: 14px; color: {muted_color};" class="email-muted">Thank you for being part of our community!</p>"""
    html += f"""
                                        <p style="margin: 0 0 12px 0; font-size: 14px; color: {muted_color};" class="email-muted">
                                            <a href="mailto:support@holygrills.online" style="color: {brand_red}; text-decoration: none;">support@holygrills.online</a>
                                        </p>"""
    
    # Unsubscribe link
    if unsubscribe_url:
        html += f"""
                                        <p style="margin: 0 0 12px 0; font-size: 12px; color: {muted_color};" class="email-muted">
                                            <a href="{_html.escape(unsubscribe_url)}" style="color: {muted_color}; text-decoration: underline;">Unsubscribe from these emails</a>
                                        </p>"""
    
    # Copyright
    html += f"""
                                        <p style="margin: 0; font-size: 12px; color: {muted_color};" class="email-muted">Copyright © 2026 Holy Grills. All rights reserved.</p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>"""
    
    # Add tracking pixel if blast_id is provided
    if blast_id:
        api_base = os.environ.get("API_PUBLIC_URL", "https://holygrills.online/api")
        if api_base.endswith("/"):
            api_base = api_base[:-1]
        tracking_pixel_url = f"{api_base}/notifications/tracking/open/{blast_id}.png"
        html += f"""
                    <tr>
                        <td style="padding: 0;">
                            <img src="{tracking_pixel_url}" width="1" height="1" style="display: block; width: 1px; height: 1px;" alt="" />
                        </td>
                    </tr>"""
    
    html += f"""
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""
    
    return html


def _build_rich_html(name: str, body_html: str, images: list, cta_blocks: list, app_tagline: str) -> str:
    """
    Build a branded responsive HTML email with rich content (images, CTA buttons).
    
    Args:
        name: Recipient's name
        body_html: Rich HTML content (already formatted)
        images: List of image blocks {url, alt, link?}
        cta_blocks: List of CTA blocks {label, url, style}
        app_tagline: App tagline for footer
    
    Returns:
        Complete HTML email string
    """
    safe_name = _html.escape(str(name or "there"))
    safe_tagline = _html.escape(str(app_tagline or "The Holy Grills Team"))
    
    # Brand colors
    brand_red = "#E01616"
    brand_red_hover = "#B81212"
    
    # Wordmark URL (absolute)
    wordmark_url = "https://holygrills.online/brand/wordmark.png"
    
    # Build images section
    images_html = ""
    if images:
        images_html = '<div style="padding: 24px 40px 0;">'
        for img in images:
            img_url = img.get("url", "")
            img_alt = _html.escape(img.get("alt", ""))
            img_link = img.get("link")
            
            if img_link:
                images_html += f'''
                <div style="margin-bottom: 16px;">
                    <a href="{_html.escape(img_link)}" target="_blank" rel="noopener noreferrer">
                        <img src="{_html.escape(img_url)}" alt="{img_alt}" style="width: 100%; height: auto; border-radius: 12px; display: block;" />
                    </a>
                </div>
                '''
            else:
                images_html += f'''
                <div style="margin-bottom: 16px;">
                    <img src="{_html.escape(img_url)}" alt="{img_alt}" style="width: 100%; height: auto; border-radius: 12px; display: block;" />
                </div>
                '''
        images_html += '</div>'
    
    # Build CTA buttons section
    cta_html = ""
    if cta_blocks:
        cta_html = '<table style="margin: 0 0 24px 0;"><tbody><tr>'
        for cta in cta_blocks:
            label = _html.escape(cta.get("label", "Click here"))
            url = _html.escape(cta.get("url", "#"))
            style = cta.get("style", "primary")
            is_primary = style == "primary"
            
            bg_color = brand_red if is_primary else "transparent"
            text_color = "#FFFFFF" if is_primary else brand_red
            border = "none" if is_primary else f"2px solid {brand_red}"
            
            cta_html += f'''
            <td style="padding: 0 8px 8px 0;">
                <table>
                    <tbody>
                        <tr>
                            <td style="border-radius: 12px; background-color: {bg_color}; border: {border};">
                                <a href="{url}" style="display: inline-block; padding: 14px 28px; font-size: 16px; font-weight: 600; color: {text_color}; text-decoration: none; border-radius: 12px;" target="_blank" rel="noopener noreferrer">
                                    {label}
                                </a>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </td>
            '''
        cta_html += '</tr></tbody></table>'
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <title>Holy Grills</title>
    <!--[if mso]>
    <noscript>
        <xml>
            <o:OfficeDocumentSettings>
                <o:PixelsPerInch>96</o:PixelsPerInch>
            </o:OfficeDocumentSettings>
        </xml>
    </noscript>
    <![endif]-->
    <style>
        /* Reset */
        body, table, td, a {{ -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }}
        table, td {{ mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
        img {{ -ms-interpolation-mode: bicubic; border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; }}
        
        /* All-screen responsive — ensures proper rendering on all devices */
        @media only screen and (max-width: 768px) {{
            .email-container {{ width: 100% !important; max-width: 100% !important; }}
        }}
        
        /* Tablet responsive */
        @media only screen and (min-width: 621px) and (max-width: 768px) {{
            .email-container {{ width: 100% !important; max-width: 600px !important; }}
        }}
        
        /* Mobile responsive */
        @media only screen and (max-width: 620px) {{
            .email-container {{ width: 100% !important; max-width: 100% !important; }}
            .email-padding {{ padding: 20px 16px !important; }}
            .email-header {{ padding: 24px 20px 16px !important; }}
            .email-footer {{ padding: 24px 20px !important; }}
            h1 {{ font-size: 24px !important; }}
            h2 {{ font-size: 18px !important; }}
            p {{ font-size: 15px !important; }}
        }}
        
        /* Small mobile */
        @media only screen and (max-width: 400px) {{
            .email-padding {{ padding: 16px 12px !important; }}
            .email-header {{ padding: 20px 16px 12px !important; }}
            .email-footer {{ padding: 20px 16px !important; }}
            h1 {{ font-size: 22px !important; }}
            p {{ font-size: 14px !important; }}
        }}
    </style>
</head>
<body style="margin: 0; padding: 0; background-color: #FFF5F0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
    <table role="presentation" style="width: 100%; border-collapse: collapse; border: 0; border-spacing: 0; background-color: #FFF5F0;">
        <tr>
            <td align="center" style="padding: 20px 10px;">
                <table role="presentation" class="email-container" style="width: 600px; max-width: 600px; border-collapse: collapse; border: 0; border-spacing: 0; background-color: #FFFFFF; border-radius: 16px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.04);">
                    
                    <!-- Header with wordmark -->
                    <tr>
                        <td class="email-header" style="padding: 32px 40px 24px; text-align: center;">
                            <img src="{wordmark_url}" alt="Holy Grills" style="max-width: 180px; height: auto;" />
                        </td>
                    </tr>
                    
                    <!-- Divider -->
                    <tr>
                        <td style="padding: 0 40px;">
                            <div style="height: 1px; background: linear-gradient(to right, transparent, rgba(0,0,0,0.1), transparent);"></div>
                        </td>
                    </tr>
                    
                    <!-- Images -->
                    {images_html}
                    
                    <!-- Content -->
                    <tr>
                        <td class="email-padding" style="padding: 32px 40px;">
                            <!-- Greeting -->
                            <p style="margin: 0 0 16px 0; font-size: 18px; color: #1A1A1A;">
                                Hello {safe_name} 👋
                            </p>
                            
                            <!-- Body HTML -->
                            <div style="margin: 0 0 24px 0; font-size: 16px; line-height: 1.6; color: #1A1A1A;">
                                {body_html}
                            </div>
                            
                            <!-- CTA Buttons -->
                            {cta_html}
                            
                            <!-- Sign-off -->
                            <p style="margin: 32px 0 8px 0; font-size: 15px; color: #666666;">
                                With love,
                            </p>
                            <p style="margin: 0; font-size: 16px; font-weight: 600; color: #1A1A1A;">
                                {safe_tagline}
                            </p>
                        </td>
                    </tr>
                    
                    <!-- Footer -->
                    <tr>
                        <td class="email-footer" style="background-color: #F5F5F5; border-top: 1px solid rgba(0,0,0,0.08); padding: 32px 40px; text-align: center;">
                            <p style="margin: 0 0 12px 0; font-size: 14px; color: #666666;">
                                Thank you for being part of our community!
                            </p>
                            <p style="margin: 0 0 12px 0; font-size: 14px; color: #666666;">
                                <a href="mailto:support@holygrills.online" style="color: {brand_red}; text-decoration: none;">support@holygrills.online</a>
                            </p>
                            <p style="margin: 0; font-size: 12px; color: #666666;">
                                Copyright © 2026 Holy Grills. All rights reserved.
                            </p>
                        </td>
                    </tr>
                    
                </table>
            </td>
        </tr>
    </table>
</body>
</html>'''
    
    return html


def send_email(to_email: str, to_name: str, template_key: str, data: dict = None, provider: str = None, blast_id: str = None) -> bool:
    """
    Send a transactional email via whichever provider get_email_provider
    resolves to. Template resolution: email_templates DB row (admin-edited)
    takes precedence; falls back to the hardcoded TEMPLATES dict if no row
    exists for this template_key.
    
    Args:
        blast_id: Optional blast ID for tracking opens/clicks (for notification blasts)
    """
    data = data or {}
    data.setdefault("name", to_name)
    data.setdefault("app_tagline", os.environ.get("APP_TAGLINE", "The Holy Grills Team"))
    data.setdefault("app_name", os.environ.get("APP_NAME", "Holy Grills"))
    data.setdefault("currency", os.environ.get("HP_CURRENCY_NAME", "HP"))

    db_template = None
    try:
        from app.db import get_db
        db_template = get_db().table("email_templates").select("subject,body").eq("template_key", template_key).single().execute()
    except Exception:
        db_template = None

    class _SafeDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"  # leave unresolvable placeholders visible rather than raising

    if db_template:
        try:
            subject = db_template["subject"].format_map(_SafeDict(data))
            body_text = db_template["body"].format_map(_SafeDict(data))
        except Exception as e:
            logger.error("send_email: malformed admin template '%s': %s — falling back to hardcoded", template_key, e)
            db_template = None

    if not db_template:
        template = TEMPLATES.get(template_key)
        if not template:
            logger.warning("send_email: unknown template_key '%s'", template_key)
            return False
        subject_tpl = template["subject"]
        subject = subject_tpl(data) if callable(subject_tpl) else subject_tpl
        body_text = template["body"](data)
        # Extract optional template parameters
        cta_buttons_tpl = template.get("cta_buttons")
        cta_buttons = cta_buttons_tpl(data) if callable(cta_buttons_tpl) else cta_buttons_tpl or []
        skip_greeting = template.get("skip_greeting", False)
        skip_signoff = template.get("skip_signoff", False)
        skip_thank_you = template.get("skip_thank_you", False)
    else:
        cta_buttons = []
        skip_greeting = False
        skip_signoff = False
        skip_thank_you = False

    _app_name = data.get("app_name", os.environ.get("APP_NAME", "Holy Grills"))
    _currency = data.get("currency", os.environ.get("HP_CURRENCY_NAME", "HP"))
    if isinstance(subject, str):
        subject = subject.replace("{platform}", _app_name).replace("{currency}", _currency)
    body_text = body_text.replace("{platform}", _app_name).replace("{currency}", _currency)

    # Determine if we should track links (only for notification blasts with tracking enabled)
    track_links = False
    if blast_id:
        try:
            from app.db import get_db
            db = get_db()
            blast = db.table("notification_blasts").select("tracking_enabled").eq("id", blast_id).single().execute()
            track_links = blast.get("tracking_enabled", False) if blast else False
        except Exception:
            track_links = False
    
    html_body = _build_html(
        to_name or "there",
        body_text,
        data.get("app_tagline", ""),
        cta_buttons=cta_buttons,
        skip_greeting=skip_greeting,
        skip_signoff=skip_signoff,
        skip_thank_you=skip_thank_you,
        blast_id=blast_id,
        track_links=track_links,
    )

    from app.services.notification_service import get_email_provider
    chosen = get_email_provider(scope="transactional", override=provider)
    return send_email_routed(to_email, to_name, subject, html_body, provider=chosen)


def _email_quota_rejection(response):
    """Only an explicit provider refusal may switch transports safely."""
    if response.status_code == 429:
        return True
    if response.status_code not in (400, 403):
        return False
    try:
        detail = response.json()
    except (ValueError, TypeError):
        return False
    if not isinstance(detail, dict):
        return False
    name = str(detail.get("name") or detail.get("code") or "").lower()
    if name in {"daily_quota_exceeded", "monthly_quota_exceeded", "quota_exceeded", "rate_limit_exceeded"}:
        return True
    # OneSignal reports its monthly email allowance in the errors field.
    errors = detail.get("errors")
    if isinstance(errors, str):
        errors = [errors]
    return isinstance(errors, list) and any(
        isinstance(value, str) and "email" in value.lower()
        and "limit" in value.lower() and "exceed" in value.lower()
        and ("monthly" in value.lower() or "daily" in value.lower())
        for value in errors)


def _email_attempt(provider, to_email, to_name, subject, html_body, headers=None):
    """Return (accepted, definitely_quota_rejected). Never retry ambiguity."""
    try:
        if provider == "onesignal":
            from app.services.notification_service import _get_onesignal_creds, _onesignal_email_post, _ONESIGNAL_BASE
            app_id, api_key = _get_onesignal_creds()
            if not app_id or not api_key:
                return False, False
            # Custom RFC unsubscribe headers cannot safely be translated to an
            # undocumented provider field. Preserve the caller's Resend path.
            if headers:
                return False, False
            payload = {"app_id": app_id, "target_channel": "email", "include_email_tokens": [to_email],
                       "email_subject": subject, "email_body": html_body}
            response = _onesignal_email_post(f"{_ONESIGNAL_BASE}/notifications",
                                      headers={"Authorization": f"Key {api_key}", "Content-Type": "application/json"},
                                      payload=payload)
            accepted = response.status_code in (200, 202)
            if accepted:
                try:
                    detail = response.json()
                    accepted = (isinstance(detail, dict) and bool(detail.get("id"))
                                and not detail.get("errors")
                                and isinstance(detail.get("recipients"), (int, float))
                                and not isinstance(detail.get("recipients"), bool)
                                and detail["recipients"] > 0)
                except (ValueError, TypeError):
                    accepted = False
        else:
            api_key = _resend_api_key()
            if not api_key:
                return False, False
            from_email = os.environ.get("EMAIL_FROM", "noreply@holygrills.online")
            from_name = os.environ.get("EMAIL_FROM_NAME", "Holy Grills")
            payload = {"from": f"{from_name} <{from_email}>", "to": [to_email], "subject": subject, "html": html_body}
            if headers:
                payload["headers"] = dict(headers)
            response = requests.post(f"{RESEND_BASE}/emails",
                                     headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                                     json=payload, timeout=10)
            accepted = response.status_code in (200, 201)
            if accepted:
                try:
                    detail = response.json()
                    accepted = isinstance(detail, dict) and bool(detail.get("id")) and not detail.get("error")
                except (ValueError, TypeError):
                    accepted = False
        if accepted:
            return True, False
        quota = _email_quota_rejection(response)
        logger.warning("Email provider %s rejected delivery with status %s (quota=%s)", provider, response.status_code, quota)
        return False, quota
    except Exception as exc:
        # A timeout/connection reset may follow provider acceptance. A second
        # transport here could deliver the same message twice.
        logger.warning("Email provider %s outcome unavailable: %s", provider, type(exc).__name__)
        return False, False


def send_email_routed(to_email, to_name, subject, html_body, *, provider="resend", headers=None):
    """One preferred attempt, then one alternate only after a quota refusal.

    No counters, global configuration changes or speculative timeout retries.
    This is application email routing; Supabase Auth SMTP is independent.
    """
    chosen = "onesignal" if provider == "onesignal" else "resend"
    if headers:
        chosen = "resend"  # Retain explicit unsubscribe/custom headers.
    accepted, quota = _email_attempt(chosen, to_email, to_name, subject, html_body, headers)
    if accepted:
        return True
    if not quota or headers:
        return False
    alternate = "resend" if chosen == "onesignal" else "onesignal"
    accepted, _ = _email_attempt(alternate, to_email, to_name, subject, html_body)
    return accepted


def send_email_raw(to_email: str, to_name: str, subject: str, html_body: str, headers: dict = None) -> bool:
    """Raw transactional email prefers Resend, with quota-only fallback."""
    return send_email_routed(to_email, to_name, subject, html_body, provider="resend", headers=headers)


def get_user_email_and_name(user_id: str) -> tuple:
    """Fetch user email + display name (nickname-first) from profiles."""
    from app.db import get_db
    from app.services.squad_service import resolve_display_name
    db = get_db()
    try:
        profile = (
            db.table("profiles")
            .select("id,nickname,full_name,email,department,campus_id")
            .eq("id", user_id)
            .single()
            .execute()
        )
        if profile:
            return profile.get("email", ""), resolve_display_name(profile=profile)
        return "", ""
    except Exception:
        return "", ""


def send_qr_ticket_email(email: str, name: str, event_title: str, ticket_id: str, event_id: str, event_date: str = "", event_location: str = "") -> bool:
    """
    Send QR ticket email to guest or registered user.
    Generates QR code payload (hg-event:{event_id}:{ticket_id}) locally as base64 PNG.
    Does NOT leak ticket IDs to third-party QR generation APIs.
    """
    qr_payload = f"hg-event:{event_id}:{ticket_id}"

    try:
        import qrcode
        import io, base64
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(qr_payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        qr_img_tag = f'<img src="data:image/png;base64,{img_str}" alt="QR Ticket Code" style="width:200px;height:200px;display:block;margin:15px auto;" />'
    except Exception as e:
        logger.error("send_qr_ticket_email: Failed to generate local base64 QR code for ticket %s: %s", ticket_id, e)
        # Fail closed instead of leaking ticket_id to third-party external server
        return False

    safe_title = _html.escape(str(event_title or ""))
    safe_date = _html.escape(str(event_date or "TBA"))
    safe_location = _html.escape(str(event_location or "TBA"))
    safe_ticket_id = _html.escape(str(ticket_id or ""))

    app_tagline = os.environ.get("APP_TAGLINE", "The Holy Grills Team")
    subject = f"🎟️ Your Ticket for {event_title}"

    body_text = f"""Here is your ticket for {safe_title}!

Date: {safe_date}
Location: {safe_location}
Ticket ID: {safe_ticket_id}

Your QR code is shown below — please show it at the door for check-in.

Create an account to earn HP for this event!"""

    # Build HTML with shared layout, but we need to embed the QR code
    # So we'll build a custom HTML that uses the shared layout structure
    brand_red = "#E01616"
    bg_color = "#FFF5F0"
    card_bg = "#FFFFFF"
    text_color = "#1A1A1A"
    muted_color = "#666666"
    wordmark_url = "https://holygrills.online/brand/wordmark.png"
    safe_name = _html.escape(str(name or "there"))
    safe_tagline = _html.escape(app_tagline)

    html_body = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <title>Holy Grills</title>
    <style>
        body, table, td, a {{ -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }}
        table, td {{ mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
        img {{ -ms-interpolation-mode: bicubic; border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; }}
        @media only screen and (max-width: 768px) {{
            .email-container {{ width: 100% !important; max-width: 100% !important; }}
        }}
        @media only screen and (max-width: 620px) {{
            .email-container {{ width: 100% !important; max-width: 100% !important; }}
            .email-padding {{ padding: 20px 16px !important; }}
            .email-header {{ padding: 24px 20px 16px !important; }}
            .email-footer {{ padding: 24px 20px !important; }}
            h1 {{ font-size: 24px !important; }}
            p {{ font-size: 15px !important; }}
        }}
        @media (prefers-color-scheme: dark) {{
            .email-bg {{ background-color: #1A1A1A !important; }}
            .email-card {{ background-color: #2A2A2A !important; }}
            .email-text {{ color: #F5F5F5 !important; }}
            .email-muted {{ color: #AAAAAA !important; }}
            .email-footer {{ background-color: #1F1F1F !important; }}
        }}
    </style>
</head>
<body style="margin: 0; padding: 0; background-color: {bg_color}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;" class="email-bg">
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: {bg_color};" class="email-bg">
        <tr>
            <td align="center" style="padding: 20px 10px;">
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="max-width: 600px;" class="email-container">
                    <tr>
                        <td style="background-color: {card_bg}; border-radius: 16px; border: 1px solid rgba(0,0,0,0.08); overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.04);" class="email-card">
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                <tr>
                                    <td style="padding: 32px 40px 24px 40px; text-align: center;" class="email-header">
                                        <a href="https://holygrills.online" style="text-decoration: none;">
                                            <img src="{wordmark_url}" alt="Holy Grills" width="180" style="display: block; margin: 0 auto; max-width: 180px; height: auto;">
                                        </a>
                                    </td>
                                </tr>
                                <tr>
                                    <td style="padding: 0 40px;">
                                        <div style="height: 1px; background: linear-gradient(to right, transparent, rgba(0,0,0,0.1), transparent);"></div>
                                    </td>
                                </tr>
                            </table>
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                <tr>
                                    <td style="padding: 32px 40px;" class="email-padding">
                                        <p style="margin: 0 0 16px 0; font-size: 18px; color: {text_color};" class="email-text">Hello {safe_name} 👋</p>
                                        <h1 style="margin: 0 0 20px 0; font-size: 28px; font-weight: 700; color: {text_color}; line-height: 1.3;" class="email-text">🎟️ Your Ticket for {safe_title}</h1>
                                        <div style="margin: 0 0 24px 0; font-size: 16px; line-height: 1.6; color: {text_color};" class="email-text">
                                            <p style="margin: 0 0 12px 0;"><strong>Date:</strong> {safe_date}</p>
                                            <p style="margin: 0 0 12px 0;"><strong>Location:</strong> {safe_location}</p>
                                            <p style="margin: 0 0 12px 0;"><strong>Ticket ID:</strong> <code>{safe_ticket_id}</code></p>
                                        </div>
                                        <div style="text-align: center; margin: 24px 0;">
                                            <p style="margin: 0 0 12px 0; font-size: 15px; color: {text_color};" class="email-text">Show this QR code at the door for check-in:</p>
                                            {qr_img_tag}
                                        </div>
                                        <div style="margin: 24px 0; padding: 20px; background-color: #FFF5F0; border-radius: 12px; border-left: 4px solid {brand_red};">
                                            <p style="margin: 0; font-size: 15px; color: {text_color};" class="email-text"><strong>Earn Rewards!</strong> Create an account with this email to earn HP for this event and unlock exclusive perks!</p>
                                        </div>
                                        <p style="margin: 32px 0 8px 0; font-size: 15px; color: {muted_color};" class="email-muted">With love,</p>
                                        <p style="margin: 0; font-size: 16px; font-weight: 600; color: {text_color};" class="email-text">{safe_tagline}</p>
                                    </td>
                                </tr>
                            </table>
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #F5F5F5; border-top: 1px solid rgba(0,0,0,0.08);" class="email-footer">
                                <tr>
                                    <td style="padding: 32px 40px; text-align: center;" class="email-footer">
                                        <p style="margin: 0 0 12px 0; font-size: 14px; color: {muted_color};" class="email-muted">
                                            <a href="mailto:support@holygrills.online" style="color: {brand_red}; text-decoration: none;">support@holygrills.online</a>
                                        </p>
                                        <p style="margin: 0; font-size: 12px; color: {muted_color};" class="email-muted">Copyright © 2026 Holy Grills. All rights reserved.</p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""

    return send_email_raw(to_email=email, to_name=name, subject=subject, html_body=html_body)
