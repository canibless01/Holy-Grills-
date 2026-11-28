"""Shared native-push identity; native layout remains controlled by the OS."""
from app.messages import MSG


def push_heading(title):
    text = str(title or '').strip()
    if not text:
        return MSG.NOTIFICATION_BRAND_NAME
    if MSG.NOTIFICATION_BRAND_NAME.casefold() in text.casefold():
        return text
    return MSG.NOTIFICATION_BRANDED_TITLE.format(title=text)
