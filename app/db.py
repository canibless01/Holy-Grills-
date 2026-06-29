"""
Supabase client wrapper. All database operations go through the Supabase REST API
using the service role key (full bypass of RLS) for server-side operations,
or the anon key + user JWT for client-authenticated operations.

Direct psycopg2 connections are NOT used because the Replit sandbox blocks
outbound port 5432. All queries use Supabase PostgREST REST endpoints and
RPCs via the requests library.
"""

import os
import requests
from functools import lru_cache
from flask import current_app


class SupabaseClient:
    def __init__(self, url: str, service_key: str, anon_key: str):
        self.url = url.rstrip("/")
        self.service_key = service_key
        self.anon_key = anon_key
        self._session = requests.Session()

    def _service_headers(self) -> dict:
        return {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _user_headers(self, user_jwt: str) -> dict:
        return {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {user_jwt}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def table(self, table_name: str) -> "TableQuery":
        return TableQuery(self, table_name)

    def rpc(self, function_name: str, params: dict = None, user_jwt: str = None) -> dict | list | None:
        headers = self._user_headers(user_jwt) if user_jwt else self._service_headers()
        resp = self._session.post(
            f"{self.url}/rest/v1/rpc/{function_name}",
            headers=headers,
            json=params or {},
        )
        _raise_for_status(resp)
        # 204 No Content or empty body — return None instead of crashing
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def auth_sign_up(self, email: str, password: str, user_metadata: dict = None) -> dict:
        resp = self._session.post(
            f"{self.url}/auth/v1/signup",
            headers={
                "apikey": self.anon_key,
                "Content-Type": "application/json",
            },
            json={"email": email, "password": password, "data": user_metadata or {}},
        )
        _raise_for_status(resp)
        return resp.json()

    def auth_sign_in(self, email: str, password: str) -> dict:
        resp = self._session.post(
            f"{self.url}/auth/v1/token?grant_type=password",
            headers={
                "apikey": self.anon_key,
                "Content-Type": "application/json",
            },
            json={"email": email, "password": password},
        )
        _raise_for_status(resp)
        return resp.json()

    def auth_refresh(self, refresh_token: str) -> dict:
        resp = self._session.post(
            f"{self.url}/auth/v1/token?grant_type=refresh_token",
            headers={
                "apikey": self.anon_key,
                "Content-Type": "application/json",
            },
            json={"refresh_token": refresh_token},
        )
        _raise_for_status(resp)
        return resp.json()

    def auth_get_user(self, access_token: str) -> dict:
        resp = self._session.get(
            f"{self.url}/auth/v1/user",
            headers={
                "apikey": self.anon_key,
                "Authorization": f"Bearer {access_token}",
            },
        )
        _raise_for_status(resp)
        return resp.json()

    def auth_update_user(self, access_token: str, data: dict) -> dict:
        resp = self._session.put(
            f"{self.url}/auth/v1/user",
            headers={
                "apikey": self.anon_key,
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=data,
        )
        _raise_for_status(resp)
        return resp.json()

    def auth_reset_password(self, email: str) -> dict:
        resp = self._session.post(
            f"{self.url}/auth/v1/recover",
            headers={
                "apikey": self.anon_key,
                "Content-Type": "application/json",
            },
            json={"email": email},
        )
        _raise_for_status(resp)
        return resp.json()

    def auth_sign_out(self, access_token: str) -> None:
        self._session.post(
            f"{self.url}/auth/v1/logout",
            headers={
                "apikey": self.anon_key,
                "Authorization": f"Bearer {access_token}",
            },
        )


class TableQuery:
    def __init__(self, client: SupabaseClient, table: str):
        self._client = client
        self._table = table
        self._select = "*"
        self._filters: list[str] = []
        self._order: str | None = None
        self._limit: int | None = None
        self._offset: int | None = None
        self._single = False
        self._user_jwt: str | None = None

    def select(self, columns: str = "*") -> "TableQuery":
        self._select = columns
        return self

    def eq(self, column: str, value) -> "TableQuery":
        self._filters.append(f"{column}=eq.{value}")
        return self

    def neq(self, column: str, value) -> "TableQuery":
        self._filters.append(f"{column}=neq.{value}")
        return self

    def gt(self, column: str, value) -> "TableQuery":
        self._filters.append(f"{column}=gt.{value}")
        return self

    def gte(self, column: str, value) -> "TableQuery":
        self._filters.append(f"{column}=gte.{value}")
        return self

    def lt(self, column: str, value) -> "TableQuery":
        self._filters.append(f"{column}=lt.{value}")
        return self

    def lte(self, column: str, value) -> "TableQuery":
        self._filters.append(f"{column}=lte.{value}")
        return self

    def ilike(self, column: str, pattern: str) -> "TableQuery":
        self._filters.append(f"{column}=ilike.{pattern}")
        return self

    def in_(self, column: str, values: list) -> "TableQuery":
        val_str = "({})".format(",".join(str(v) for v in values))
        self._filters.append(f"{column}=in.{val_str}")
        return self

    def is_(self, column: str, value) -> "TableQuery":
        self._filters.append(f"{column}=is.{value}")
        return self

    @property
    def not_(self) -> "_NotProxy":
        return _NotProxy(self)

    def order(self, column: str, ascending: bool = True) -> "TableQuery":
        direction = "asc" if ascending else "desc"
        self._order = f"{column}.{direction}"
        return self

    def limit(self, n: int) -> "TableQuery":
        self._limit = n
        return self

    def offset(self, n: int) -> "TableQuery":
        self._offset = n
        return self

    def single(self) -> "TableQuery":
        self._single = True
        return self

    def with_jwt(self, jwt: str) -> "TableQuery":
        self._user_jwt = jwt
        return self

    def _build_params(self) -> dict:
        params = {"select": self._select}
        for f in self._filters:
            k, v = f.split("=", 1)
            params[k] = v
        if self._order:
            params["order"] = self._order
        if self._limit is not None:
            params["limit"] = self._limit
        if self._offset is not None:
            params["offset"] = self._offset
        return params

    def _headers(self) -> dict:
        h = self._client._user_headers(self._user_jwt) if self._user_jwt else self._client._service_headers()
        if self._single:
            h["Accept"] = "application/vnd.pgrst.object+json"
        return h

    def execute(self) -> list | dict | None:
        url = f"{self._client.url}/rest/v1/{self._table}"
        resp = self._client._session.get(url, headers=self._headers(), params=self._build_params())
        if self._single and resp.status_code in (406, 404):
            return None
        _raise_for_status(resp)
        return resp.json()

    def insert(self, data: dict | list) -> list | dict:
        url = f"{self._client.url}/rest/v1/{self._table}"
        resp = self._client._session.post(url, headers=self._client._service_headers(), json=data)
        _raise_for_status(resp)
        return resp.json()

    def update(self, data: dict) -> list | dict:
        url = f"{self._client.url}/rest/v1/{self._table}"
        params = {}
        for f in self._filters:
            k, v = f.split("=", 1)
            params[k] = v
        resp = self._client._session.patch(url, headers=self._client._service_headers(), json=data, params=params)
        _raise_for_status(resp)
        return resp.json()

    def delete(self) -> list | dict:
        url = f"{self._client.url}/rest/v1/{self._table}"
        params = {}
        for f in self._filters:
            k, v = f.split("=", 1)
            params[k] = v
        resp = self._client._session.delete(url, headers=self._client._service_headers(), params=params)
        _raise_for_status(resp)
        return resp.json()

    def upsert(self, data: dict | list, on_conflict: str = "id") -> list | dict:
        url = f"{self._client.url}/rest/v1/{self._table}"
        headers = self._client._service_headers()
        headers["Prefer"] = f"resolution=merge-duplicates,return=representation"
        resp = self._client._session.post(url, headers=headers, json=data, params={"on_conflict": on_conflict})
        _raise_for_status(resp)
        return resp.json()


class _NotProxy:
    """Proxy to allow `.not_.is_(column, value)` → PostgREST `column=not.is.value` syntax."""
    __slots__ = ("_query",)

    def __init__(self, query: "TableQuery"):
        self._query = query

    def is_(self, column: str, value) -> "TableQuery":
        self._query._filters.append(f"{column}=not.is.{value}")
        return self._query

    def eq(self, column: str, value) -> "TableQuery":
        self._query._filters.append(f"{column}=not.eq.{value}")
        return self._query

    def in_(self, column: str, values: list) -> "TableQuery":
        val_str = "({})".format(",".join(str(v) for v in values))
        self._query._filters.append(f"{column}=not.in.{val_str}")
        return self._query


class SupabaseError(Exception):
    def __init__(self, message: str, status_code: int = 500, details: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


def _raise_for_status(resp: requests.Response):
    if resp.status_code >= 400:
        try:
            body = resp.json()
        except Exception:
            body = {"message": resp.text}
        raise SupabaseError(
            body.get("message", "Supabase error"),
            status_code=resp.status_code,
            details=body,
        )


@lru_cache(maxsize=1)
def _get_client_cached(url: str, service_key: str, anon_key: str) -> SupabaseClient:
    return SupabaseClient(url, service_key, anon_key)


def get_db() -> SupabaseClient:
    return _get_client_cached(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        os.environ["SUPABASE_ANON_KEY"],
    )
