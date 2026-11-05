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
from unittest import mock

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
        # Production serves no API docs unless the flag is on (see create_app), so the
        # spec has to be opened deliberately for these tests to exercise it at all.
        cls._docs_flag = mock.patch.dict(os.environ, {"API_DOCS_ENABLED": "true"})
        cls._docs_flag.start()
        cls.app = create_app(config_map["production"])
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls._docs_flag.stop()

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


class ApiDocsAreClosedByDefaultTests(unittest.TestCase):
    """The docs map the whole API surface, so production must not serve them.

    Anyone who guesses /api/docs/ would otherwise get every route, admin path and
    payload example in one page. They open only for DEBUG/TESTING or when
    API_DOCS_ENABLED is set.
    """

    def _app_without_flag(self):
        env = {k: v for k, v in os.environ.items() if k != "API_DOCS_ENABLED"}
        with mock.patch.dict(os.environ, env, clear=True):
            return create_app(config_map["production"])

    def test_the_ui_and_the_spec_both_404(self):
        client = self._app_without_flag().test_client()
        for path in ("/api/docs/", "/api/docs/apispec.json", "/api/docs/static/swagger-ui.css"):
            with self.subTest(path=path):
                self.assertEqual(404, client.get(path).status_code)

    def test_the_flag_opens_them(self):
        env = {k: v for k, v in os.environ.items() if k != "API_DOCS_ENABLED"}
        env["API_DOCS_ENABLED"] = "true"
        with mock.patch.dict(os.environ, env, clear=True):
            client = create_app(config_map["production"]).test_client()
        self.assertEqual(200, client.get("/api/docs/apispec.json").status_code)

    def test_debug_alone_is_enough_for_local_work(self):
        env = {k: v for k, v in os.environ.items() if k != "API_DOCS_ENABLED"}
        with mock.patch.dict(os.environ, env, clear=True):
            client = create_app(config_map["development"]).test_client()
        self.assertEqual(200, client.get("/api/docs/apispec.json").status_code)
