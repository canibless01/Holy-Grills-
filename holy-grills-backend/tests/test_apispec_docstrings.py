"""Flasgger builds /api/docs/apispec.json by YAML-parsing every view docstring.

One malformed docstring does not break its own route — it breaks the WHOLE
spec: flasgger raises while generating, /api/docs/apispec.json answers 500, and
Swagger UI shows nothing but "Fetch error undefined /api/docs/apispec.json" with
no hint about which endpoint caused it.

This pins both halves: every docstring must parse, and the spec endpoint must
return 200.
"""

import os
import unittest

for _k, _v in (
    ("SUPABASE_URL", "https://example.supabase.co"),
    ("SUPABASE_ANON_KEY", "test-anon"),
    ("SUPABASE_SERVICE_ROLE_KEY", "test-service"),
    ("SUPABASE_JWT_SECRET", "test-jwt"),
    ("SESSION_SECRET", "test-session"),
    ("JWT_SECRET", "test-jwt-secret"),
):
    os.environ.setdefault(_k, _v)

import inspect  # noqa: E402

import yaml  # noqa: E402

from app import create_app  # noqa: E402
from app.config import config_map  # noqa: E402


def _spec_blocks(doc):
    """The YAML chunks that follow a `---` separator in a view docstring."""
    parts = (doc or "").split("---")
    return [chunk for chunk in parts[1:] if chunk.strip()]


class TestApiSpecDocstrings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app(config_map["production"])
        cls.client = cls.app.test_client()

    def test_every_docstring_yaml_parses(self):
        """The regression: an orphaned `400:` block in messages.py took the whole
        spec down with a bare ParserError naming no endpoint."""
        broken = []
        for rule in self.app.url_map.iter_rules():
            fn = self.app.view_functions.get(rule.endpoint)
            if fn is None:
                continue
            for chunk in _spec_blocks(inspect.getdoc(fn)):
                try:
                    yaml.safe_load(chunk)
                except Exception as exc:  # noqa: BLE001 - any YAML error is the bug
                    broken.append(f"{rule.endpoint} ({rule}): {str(exc).splitlines()[0]}")
                    break
        self.assertEqual([], broken, "malformed Swagger docstring(s):\n  " + "\n  ".join(broken))

    def test_apispec_returns_200(self):
        res = self.client.get("/api/docs/apispec.json")
        self.assertEqual(200, res.status_code, "the API docs cannot be generated")
        spec = res.get_json()
        self.assertTrue(spec.get("paths"), "the spec generated but contains no paths")

    def test_documented_routes_carry_tags(self):
        """A spec block with no `tags` lands in the default group, which is how
        endpoints quietly disappear from the list admins actually read."""
        untagged = []
        for rule in self.app.url_map.iter_rules():
            fn = self.app.view_functions.get(rule.endpoint)
            if fn is None:
                continue
            for chunk in _spec_blocks(inspect.getdoc(fn)):
                parsed = yaml.safe_load(chunk)
                if isinstance(parsed, dict) and "tags" not in parsed:
                    untagged.append(f"{rule.endpoint} ({rule})")
                break
        self.assertEqual([], untagged, "spec block(s) missing tags:\n  " + "\n  ".join(untagged))


if __name__ == "__main__":
    unittest.main()
