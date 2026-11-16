"""Global public social destinations. Campus settings must never override them."""
from urllib.parse import urlsplit
from app.messages import MSG

SOCIAL_LINKS_KEY = 'global_social_links'
SOCIAL_HOSTS = {
    'instagram': {'instagram.com', 'www.instagram.com'},
    'facebook': {'facebook.com', 'www.facebook.com'},
    'x': {'x.com', 'www.x.com', 'twitter.com', 'www.twitter.com'},
    'tiktok': {'tiktok.com', 'www.tiktok.com'},
    'youtube': {'youtube.com', 'www.youtube.com', 'youtu.be'},
}


def validate_social_links(value):
    if not isinstance(value, dict) or set(value) - SOCIAL_HOSTS.keys():
        raise ValueError(MSG.SOCIAL_LINKS_INVALID)
    links = {}
    for platform, raw in value.items():
        if not isinstance(raw, str):
            raise ValueError(MSG.SOCIAL_LINKS_INVALID)
        url = raw.strip()
        if not url:
            continue
        try:
            parsed = urlsplit(url)
            valid = (len(url) <= 512 and not any(c.isspace() for c in url)
                     and parsed.scheme == 'https' and parsed.hostname in SOCIAL_HOSTS[platform]
                     and not parsed.username and not parsed.password and parsed.port in (None, 443))
        except ValueError:
            valid = False
        if not valid:
            raise ValueError(MSG.SOCIAL_LINKS_INVALID)
        links[platform] = url
    return links


def public_social_links(settings):
    """Invalid historical data stays hidden rather than publishing unsafe links."""
    value = next((row.get('value') for row in settings
                  if row.get('key') == SOCIAL_LINKS_KEY and row.get('campus_id') is None), {})
    try:
        return validate_social_links(value)
    except ValueError:
        return {}
