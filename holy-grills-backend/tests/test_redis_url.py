"""REDIS_URL handling: accept dashboard shapes, refuse nonsense clearly.

Production reported

    error:Redis URL must specify one of the following schemes (redis://, rediss://, unix:/

which is redis-py's own ValueError from `from_url()`. The code never built a URL from
parts and never stripped a scheme — the value itself was a bare `host:port`, the shape
Railway's Connect tab offers for the public proxy. These tests pin both the repair and
the honest failure.
"""
import os
import unittest
from unittest import mock

from app.utils.redis_url import normalize_broker_url, normalize_redis_url


class NormalizeRedisUrlTests(unittest.TestCase):
    def test_a_proper_url_is_untouched(self):
        for value in ("redis://localhost:6379/0",
                      "rediss://default:secret@redis.railway.internal:6379/0",
                      "unix:///var/run/redis/redis.sock"):
            with self.subTest(value=value):
                self.assertEqual(normalize_redis_url(value), value)

    def test_the_railway_connect_tab_shape_is_repaired(self):
        """This exact string is what produced the reported error."""
        self.assertEqual(normalize_redis_url("roundhouse.proxy.rlwy.net:12345"),
                         "redis://roundhouse.proxy.rlwy.net:12345")

    def test_host_port_and_db_is_repaired(self):
        self.assertEqual(normalize_redis_url("localhost:6379/1"), "redis://localhost:6379/1")

    def test_a_bare_host_still_produces_a_usable_url(self):
        self.assertEqual(normalize_redis_url("redis"), "redis://redis")

    def test_an_http_endpoint_becomes_a_redis_url(self):
        self.assertEqual(normalize_redis_url("http://cache.internal:6379"),
                         "redis://cache.internal:6379")
        self.assertEqual(normalize_redis_url("https://cache.internal:6379"),
                         "rediss://cache.internal:6379")

    def test_quotes_and_whitespace_from_a_paste_are_removed(self):
        self.assertEqual(normalize_redis_url('  "redis://h:6379/0"  '), "redis://h:6379/0")

    def test_empty_values_mean_not_configured(self):
        for value in (None, "", "   ", '""'):
            with self.subTest(value=value):
                self.assertEqual(normalize_redis_url(value), "")

    def test_a_non_redis_scheme_is_refused_rather_than_rewritten(self):
        for value in ("amqp://guest:guest@rabbit:5672//", "postgres://db:5432/x", "not a url"):
            with self.subTest(value=value):
                self.assertEqual(normalize_redis_url(value), "")


class NormalizeBrokerUrlTests(unittest.TestCase):
    def test_a_deliberate_amqp_broker_passes_through(self):
        self.assertEqual(normalize_broker_url("amqp://guest:guest@rabbit:5672//"),
                         "amqp://guest:guest@rabbit:5672//")

    def test_a_schemeless_broker_is_treated_as_redis(self):
        self.assertEqual(normalize_broker_url("roundhouse.proxy.rlwy.net:12345"),
                         "redis://roundhouse.proxy.rlwy.net:12345")


class HealthCheckTests(unittest.TestCase):
    def _checks(self, **env):
        from app.routes.health import health_bp  # noqa: F401  (import cost paid once)
        from app import create_app
        from app.config import config_map

        base = {k: v for k, v in os.environ.items() if k != "REDIS_URL"}
        base.update(env)
        # The health route reads REDIS_URL per request, so the patch has to still be
        # active while the request is served — not just while the app is built.
        with mock.patch.dict(os.environ, base, clear=True):
            app = create_app(config_map["development"])
            with mock.patch("app.routes.health._req.get", side_effect=RuntimeError("skip network")):
                return app.test_client().get("/api/health").get_json()["checks"]

    def test_a_bare_host_port_is_not_reported_as_a_scheme_error(self):
        checks = self._checks(REDIS_URL="127.0.0.1:6379")
        self.assertNotIn("schemes", checks["redis"])
        self.assertNotIn("invalid_url", checks["redis"])

    def test_a_set_but_unusable_value_says_so_instead_of_not_configured(self):
        checks = self._checks(REDIS_URL="this is not a redis url")
        self.assertEqual(checks["redis"], "error:invalid_url_missing_redis_scheme")

    def test_an_absent_value_is_reported_as_not_configured(self):
        checks = self._checks()
        self.assertEqual(checks["redis"], "not_configured")


class CeleryBrokerTests(unittest.TestCase):
    def test_a_bare_host_port_reaches_celery_as_a_redis_url(self):
        from app.tasks.celery_app import _redis_url
        env = {"CELERY_BROKER_URL": "roundhouse.proxy.rlwy.net:12345"}
        with mock.patch.dict(os.environ, env):
            self.assertEqual(_redis_url(), "redis://roundhouse.proxy.rlwy.net:12345")

    def test_a_blank_broker_falls_through_to_redis_url(self):
        from app.tasks.celery_app import _redis_url
        with mock.patch.dict(os.environ, {"CELERY_BROKER_URL": "", "REDIS_URL": "redis://r:6379/0"}):
            self.assertEqual(_redis_url(), "redis://r:6379/0")


if __name__ == "__main__":
    unittest.main()
