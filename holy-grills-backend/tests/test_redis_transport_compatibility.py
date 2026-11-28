"""Exercise Kombu's actual Redis client selection without opening a socket."""
from functools import partial
from types import SimpleNamespace

import redis
from kombu.transport.redis import Channel


def test_installed_transport_accepts_installed_redis_client():
    client_type = Channel._get_client(SimpleNamespace(global_keyprefix=""))
    assert client_type is redis.Redis


def test_prefixed_transport_accepts_installed_redis_client():
    client_type = Channel._get_client(SimpleNamespace(global_keyprefix="holy-grills:"))
    assert isinstance(client_type, partial)
    client = client_type(host="127.0.0.1", port=9)
    assert isinstance(client, redis.Redis)
    client.close()
