"""The Celery broker must never resolve to an empty URL.

`os.environ.get(key, default)` only falls back when the key is *absent*; a key that
exists but is empty returns "". With an empty broker URL kombu falls back to
amqp://guest@localhost:5672, so a blank Railway variable reference shows up as
"Cannot connect to amqp://guest:**@127.0.0.1:5672" — a RabbitMQ error for an app that
only ever uses Redis. These tests pin the resolution order.
"""
import os
import unittest
from unittest.mock import patch

from app.tasks.celery_app import _FALLBACK_REDIS_URL, _redis_url


class BrokerResolutionTests(unittest.TestCase):
    def test_the_broker_url_wins(self):
        with patch.dict(os.environ, {"CELERY_BROKER_URL": "redis://primary:6379/0",
                                     "REDIS_URL": "redis://secondary:6379/0"}):
            self.assertEqual(_redis_url(), "redis://primary:6379/0")

    def test_an_empty_broker_url_falls_through_to_redis_url(self):
        with patch.dict(os.environ, {"CELERY_BROKER_URL": "", "REDIS_URL": "redis://railway:6379/0"}):
            self.assertEqual(_redis_url(), "redis://railway:6379/0")

    def test_whitespace_is_not_a_url(self):
        with patch.dict(os.environ, {"CELERY_BROKER_URL": "   ", "REDIS_URL": "redis://railway:6379/0"}):
            self.assertEqual(_redis_url(), "redis://railway:6379/0")

    def test_surrounding_whitespace_is_trimmed(self):
        with patch.dict(os.environ, {"CELERY_BROKER_URL": " redis://railway:6379/0\n"}):
            self.assertEqual(_redis_url(), "redis://railway:6379/0")

    def test_both_empty_gives_the_documented_local_default_never_amqp(self):
        with patch.dict(os.environ, {"CELERY_BROKER_URL": "", "REDIS_URL": ""}):
            self.assertEqual(_redis_url(), _FALLBACK_REDIS_URL)
        self.assertTrue(_FALLBACK_REDIS_URL.startswith("redis://"))

    def test_missing_variables_are_the_same_as_empty_ones(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("CELERY_BROKER_URL", "REDIS_URL")}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(_redis_url(), _FALLBACK_REDIS_URL)

    def test_the_app_is_built_from_the_resolved_url(self):
        """An empty CELERY_BROKER_URL must not reach Celery as an empty broker."""
        import importlib

        import app.tasks.celery_app as module
        with patch.dict(os.environ, {"CELERY_BROKER_URL": "", "REDIS_URL": "redis://railway:6379/0",
                                     "CELERY_RESULT_BACKEND": ""}):
            reloaded = importlib.reload(module)
            self.assertEqual(reloaded.celery_app.conf.broker_url, "redis://railway:6379/0")
            self.assertEqual(reloaded.celery_app.conf.result_backend, "redis://railway:6379/0")
        importlib.reload(module)   # leave the module as the rest of the suite expects it


if __name__ == "__main__":
    unittest.main()
