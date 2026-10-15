from urllib.parse import urlparse, unquote
from flask import current_app


def is_trusted_upload_url(url, folder_prefix=None):
    """True only for https Cloudinary URLs on our own cloud (optionally inside folder_prefix)."""
    if not isinstance(url, str) or len(url) > 2048:
        return False
    cloud_name = current_app.config.get("CLOUDINARY_CLOUD_NAME")
    try:
        parsed = urlparse(url)
        if parsed.username or parsed.password or parsed.port not in (None, 443):
            return False
    except ValueError:
        return False
    if not cloud_name or parsed.scheme != "https" or parsed.hostname != "res.cloudinary.com":
        return False
    path = unquote(parsed.path)
    if not path.startswith(f"/{cloud_name}/image/upload/"):
        return False
    if any(part in (".", "..") for part in path.split("/")):
        return False
    return not folder_prefix or f"/{folder_prefix}/" in path


def is_cms_image_url(url):
    """CMS images use the application's Cloudinary cloud, like profile images."""
    return is_trusted_upload_url(url)
