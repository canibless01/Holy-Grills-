from urllib.parse import urlparse
from flask import current_app


def is_trusted_upload_url(url, folder_prefix=None):
    """True only for https Cloudinary URLs on our own cloud (optionally inside folder_prefix)."""
    if not isinstance(url, str) or len(url) > 2048:
        return False
    cloud_name = current_app.config.get("CLOUDINARY_CLOUD_NAME")
    parsed = urlparse(url)
    if not cloud_name or parsed.scheme != "https" or parsed.hostname != "res.cloudinary.com":
        return False
    if not parsed.path.startswith(f"/{cloud_name}/"):
        return False
    return not folder_prefix or f"/{folder_prefix}/" in parsed.path
