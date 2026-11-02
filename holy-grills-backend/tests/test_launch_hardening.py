"""Launch-hardening behaviour: shared rate limits, masked health detail, API headers.

Each of these closes a gap that only shows at launch:

* The in-process rate limiter multiplied its own limits by the number of gunicorn
  workers (2) and services, and reset to zero on every deploy — so "5 password resets
  per 15 minutes" was not 5. Counters now live in Redis, with the old store as the
  fallback so a Redis outage degrades instead of failing open.
* `/api/health` is unauthenticated and echoed driver text, which carries hostnames and
  ports.
* The API returned no security headers at all — the frontend only gets them from
  vercel.json.
* Any `holy-grills*.vercel.app` preview origin was allowed by CORS by default.
"""
import os
import unittest
from unittest import mock

from app.utils.redis_url import normalize_redis_url

SUPA = {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_ANON_KEY": "t",
        "SUPABASE_SERVICE_ROLE_KEY": "t", "JWT_SECRET": "t", "SECRET_KEY": "t"}


def _app(config="production", **extra):
    env = {k: v for k, v in os.environ.items() if k not in ("REDIS_URL", "API_DOCS_ENABLED")}
    env.update(SUPA)
    env.update(extra)
    with mock.patch.dict(os.environ, env, clear=True):
        from app import create_app
        from app.config import config_map
        return create_app(config_map[config])


class RateLimitBackingTests(unittest.TestCase):
    def setUp(self):
        from app.middleware import rate_limit as module
        module.reset_redis_client()
        module._request_counts.clear()

    def tearDown(self):
        from app.middleware import rate_limit as module
        module.reset_redis_client()
        module._request_counts.clear()

    def test_without_redis_the_in_process_store_is_used(self):
        from app.middleware import rate_limit as module
        app = _app()
        with app.app_context():
            self.assertIsNone(module._redis())

    def test_a_redis_counter_is_preferred_and_shared_across_workers(self):
        from app.middleware import rate_limit as module
        client = mock.MagicMock()
        client.pipeline.return_value.execute.return_value = (1, True)
        with mock.patch.object(module, "_redis", return_value=client), \
             mock.patch.dict(os.environ, {"REDIS_URL": "redis://r:6379/0"}):
            app = _app()
            with app.app_context():
                self.assertEqual(1, module._redis_count("auth.login:1.2.3.4", 60))
        key = client.pipeline.return_value.incr.call_args.args[0]
        self.assertTrue(key.startswith("hg:rl:auth.login:1.2.3.4:"), key)

    def test_a_redis_failure_falls_back_instead_of_letting_requests_through(self):
        from app.middleware import rate_limit as module
        broken = mock.MagicMock()
        broken.pipeline.side_effect = RuntimeError("connection lost")
        with mock.patch.object(module, "_redis", return_value=broken):
            app = _app()
            with app.app_context():
                self.assertEqual(-1, module._redis_count("x:y", 60))
        self.assertEqual(1, module._memory_count("x:y", 60, __import__("time").time()))


class HealthDetailTests(unittest.TestCase):
    def _checks(self, config):
        app = _app(config)
        with mock.patch("app.routes.health._req.get",
                        side_effect=RuntimeError("connect to db.internal:5432 failed")):
            return app.test_client().get("/api/health").get_json()["checks"]

    def test_production_reports_the_failure_class_only(self):
        checks = self._checks("production")
        self.assertNotIn("db.internal", str(checks))
        self.assertTrue(checks["supabase"].startswith("unreachable:"))

    def test_debug_keeps_the_full_text_for_developers(self):
        checks = self._checks("development")
        self.assertIn("db.internal", checks["supabase"])


class SecurityHeaderTests(unittest.TestCase):
    def test_every_api_response_carries_the_baseline_headers(self):
        client = _app().test_client()
        res = client.get("/api/health")
        self.assertEqual("nosniff", res.headers.get("X-Content-Type-Options"))
        self.assertEqual("DENY", res.headers.get("X-Frame-Options"))
        self.assertEqual("strict-origin-when-cross-origin", res.headers.get("Referrer-Policy"))
        self.assertIn("geolocation=(self)", res.headers.get("Permissions-Policy", ""))

    def test_hsts_is_not_sent_over_plain_http(self):
        client = _app().test_client()
        self.assertIsNone(client.get("/api/health").headers.get("Strict-Transport-Security"))

    def test_hsts_is_sent_over_tls(self):
        client = _app().test_client()
        res = client.get("/api/health", base_url="https://api.holygrills.online")
        self.assertEqual("max-age=31536000; includeSubDomains",
                         res.headers.get("Strict-Transport-Security"))


class PreviewOriginTests(unittest.TestCase):
    """Preview deployments are the test surface, so preview origins are allowed.

    The switch exists so the pattern can be closed once testing moves off previews —
    it matches every `holy-grills*.vercel.app` host, including forks.
    """

    def test_preview_origins_are_allowed_by_default(self):
        from app.config import Config
        self.assertTrue(Config.ALLOW_VERCEL_PREVIEWS)
        self.assertEqual(1, len(Config.CORS_ORIGIN_PATTERNS))
        pattern = Config.CORS_ORIGIN_PATTERNS[0]
        self.assertTrue(pattern.match("https://holy-grills-git-main-scope.vercel.app"))
        self.assertTrue(pattern.match("https://holy-grills-abc123.vercel.app"))
        self.assertIsNone(pattern.match("https://evil-vercel.app"))
        self.assertIsNone(pattern.match("https://holygrills.online"))

    def test_the_switch_closes_them(self):
        env = {k: v for k, v in os.environ.items() if k != "ALLOW_VERCEL_PREVIEWS"}
        env.update(SUPA)
        env["ALLOW_VERCEL_PREVIEWS"] = "false"
        with mock.patch.dict(os.environ, env, clear=True):
            import importlib

            import app.config as config_module
            reloaded = importlib.reload(config_module)
            self.assertFalse(reloaded.Config.ALLOW_VERCEL_PREVIEWS)
            self.assertEqual([], list(reloaded.Config.CORS_ORIGIN_PATTERNS))
        importlib.reload(config_module)


class RedisUrlSharedTests(unittest.TestCase):
    def test_the_app_uses_the_same_normaliser_as_the_health_check(self):
        with mock.patch.dict(os.environ, {"REDIS_URL": "roundhouse.proxy.rlwy.net:12345"}, clear=False):
            import importlib

            import app.config as config_module
            reloaded = importlib.reload(config_module)
            self.assertEqual("redis://roundhouse.proxy.rlwy.net:12345", reloaded.Config.REDIS_URL)
        importlib.reload(config_module)
        self.assertEqual("redis://h:6379", normalize_redis_url("h:6379"))


if __name__ == "__main__":
    unittest.main()
