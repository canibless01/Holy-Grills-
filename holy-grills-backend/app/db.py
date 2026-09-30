import os
import requests
from functools import lru_cache
from flask import current_app


class SupabaseClient:
    def __init__(self, url: str, service_key: str, anon_key: str, timeout: int = 15):
        self.url = url.rstrip("/")
        self.service_key = service_key
        self.anon_key = anon_key
        self.timeout = timeout
        self._session = requests.Session()

    def _service_headers(self) -> dict:
        return {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _user_headers(self, user_jwt: str = None) -> dict:
        token = user_jwt or self.anon_key
        return {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {token}",
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
            timeout=self.timeout,
        )
        _raise_for_status(resp)
        # 204 No Content or empty body — return None instead of crashing
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def auth_sign_up(self, email: str, password: str, user_metadata: dict = None, redirect_to: str = None) -> dict:
        resp = self._session.post(
            f"{self.url}/auth/v1/signup",
            params={"redirect_to": redirect_to} if redirect_to else None,
            headers={
                "apikey": self.anon_key,
                "Content-Type": "application/json",
            },
            json={"email": email, "password": password, "data": user_metadata or {}},
            timeout=self.timeout,
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
            timeout=self.timeout,
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
            timeout=self.timeout,
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
            timeout=self.timeout,
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
            timeout=self.timeout,
        )
        _raise_for_status(resp)
        return resp.json()

    def auth_resend_email(self, email: str, email_type: str = "signup", redirect_to: str = None) -> dict:
        """
        Ask Supabase to resend the verification email for an unconfirmed account.
        type must be 'signup' (re-send confirmation) or 'email_change'.
        Returns an empty dict on success; raises SupabaseError on failure.
        Always wraps in try/except at the call site — Supabase returns 422 if
        the address is already confirmed.
        """
        resp = self._session.post(
            f"{self.url}/auth/v1/resend",
            params={"redirect_to": redirect_to} if redirect_to else None,
            headers={
                "apikey": self.anon_key,
                "Content-Type": "application/json",
            },
            json={"type": email_type, "email": email},
            timeout=self.timeout,
        )
        if resp.status_code == 422:
            # Already confirmed — treat as success so we don't leak status
            return {}
        _raise_for_status(resp)
        return resp.json() if resp.content else {}

    def auth_reset_password(self, email: str, redirect_to: str = None) -> dict:
        resp = self._session.post(
            f"{self.url}/auth/v1/recover",
            params={"redirect_to": redirect_to} if redirect_to else None,
            headers={
                "apikey": self.anon_key,
                "Content-Type": "application/json",
            },
            json={"email": email},
            timeout=self.timeout,
        )
        _raise_for_status(resp)
        return resp.json()

    def auth_sign_out(self, access_token: str, scope: str = "local") -> bool:
        # GoTrue's default scope is GLOBAL: without an explicit scope, /logout would sign the
        # user out of EVERY device, not just this session.
        resp = self._session.post(
            f"{self.url}/auth/v1/logout",
            params={"scope": scope},
            headers={
                "apikey": self.anon_key,
                "Authorization": f"Bearer {access_token}",
            },
            timeout=self.timeout,
        )
        return resp.status_code in (200, 204)



class QueryResultList(list):
    def execute(self):
        return self

class QueryResultDict(dict):
    def execute(self):
        return self

def _wrap_result(res):
    if isinstance(res, list):
        return QueryResultList([_wrap_result(x) for x in res])
    elif isinstance(res, dict):
        d = QueryResultDict()
        for k, v in res.items():
            d[k] = _wrap_result(v)
        return d
    return res

class TableQuery:
    def __init__(self, client: SupabaseClient, table: str):
        self._client = client
        self._table = table
        self._select = "*"
        self._count: str | None = None
        self._filters: list[str] = []
        self._order: str | None = None
        self._limit: int | None = None
        self._offset: int | None = None
        self._single = False
        self._user_jwt: str | None = None
        self._auto_paginate = False

    def select(self, columns: str = "*", count: str | None = None) -> "TableQuery":
        self._select = columns
        self._count = count
        return self

    @staticmethod
    def _escape_val(v) -> str:
        """Format filter values for PostgREST query parameters."""
        if v is None:
            return ""
        s = str(v)
        # If value contains PostgREST reserved delimiter characters, wrap in double quotes
        if any(c in s for c in (",", "(", ")", "\"")):
            escaped = s.replace("\"", "\\\"")
            return f'"{escaped}"'
        return s

    def eq(self, column: str, value) -> "TableQuery":
        if value is None:
            self._filters.append(f"{column}=is.null")
        else:
            self._filters.append(f"{column}=eq.{self._escape_val(value)}")
        return self

    def neq(self, column: str, value) -> "TableQuery":
        if value is None:
            self._filters.append(f"{column}=is.not.null")
        else:
            self._filters.append(f"{column}=neq.{self._escape_val(value)}")
        return self

    def gt(self, column: str, value) -> "TableQuery":
        self._filters.append(f"{column}=gt.{self._escape_val(value)}")
        return self

    def gte(self, column: str, value) -> "TableQuery":
        self._filters.append(f"{column}=gte.{self._escape_val(value)}")
        return self

    def lt(self, column: str, value) -> "TableQuery":
        self._filters.append(f"{column}=lt.{self._escape_val(value)}")
        return self

    def lte(self, column: str, value) -> "TableQuery":
        self._filters.append(f"{column}=lte.{self._escape_val(value)}")
        return self

    def ilike(self, column: str, pattern: str) -> "TableQuery":
        self._filters.append(f"{column}=ilike.{self._escape_val(pattern)}")
        return self

    def in_(self, column: str, values: list) -> "TableQuery":
        val_str = "({})".format(",".join(self._escape_val(v) for v in values))
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

    def or_(self, filter_str: str) -> "TableQuery":
        """Add PostgREST or=(...) filter parameter."""
        self._filters.append(f"or=({filter_str})")
        return self

    def with_jwt(self, jwt: str) -> "TableQuery":
        self._user_jwt = jwt
        self._use_user_headers = True
        return self

    def _filter_params(self) -> dict:
        """
        Filters as PostgREST query parameters. Repeated keys (e.g. gte and lte range bounds on created_at)
        become lists so PostgREST receives every bound instead of the last one overwriting the others.
        Shared by select, update and delete.
        """
        params: dict = {}
        for f in self._filters:
            k, v = f.split("=", 1)
            if k in params:
                if isinstance(params[k], list):
                    params[k].append(v)
                else:
                    params[k] = [params[k], v]
            else:
                params[k] = v
        return params

    def _build_params(self) -> dict:
        """Build PostgREST query parameters from select, filters, ordering, and limit/offset."""
        params = {"select": self._select}
        params.update(self._filter_params())
        if self._order:
            params["order"] = self._order
        if self._limit is not None:
            params["limit"] = self._limit
        if self._offset is not None:
            params["offset"] = self._offset
        return params

    def _require_filter(self, verb: str) -> None:
        """Refuse an update()/delete() with no filter: PostgREST would apply it to EVERY row of the table."""
        if not self._filters:
            raise SupabaseError(f"{verb}() requires at least one filter", status_code=400, details={"code": "GUARD"})

    def _headers(self) -> dict:
        use_user = getattr(self, "_use_user_headers", False) or bool(self._user_jwt)
        h = self._client._user_headers(self._user_jwt) if use_user else self._client._service_headers()
        if self._single:
            h["Accept"] = "application/vnd.pgrst.object+json"
        if self._count:
            h["Prefer"] = f"count={self._count}"
        return h

    def execute(self) -> list | dict | None:
        if (self._auto_paginate and not self._single and not self._count
                and self._limit is None and self._offset is None):
            return self._execute_all_pages()
        return self._execute_once()

    def _execute_all_pages(self, page_size: int = 1000, max_rows: int = 50000) -> list:
        """Fetch EVERY page of a list query. PostgREST returns at most the project's Max Rows (1000) per request,
        so a plain execute() silently truncates. Only used by clients created with get_user_client(paginate=True).

        KNOWN LIMITATION (same family as the squads.py double-submit report): this is offset-based, not
        keyset-based. If a row is inserted or deleted in this table between one page's request and the next,
        a row can be double-counted or skipped at the page boundary. Every current caller (app/routes/analytics.py)
        uses this for reporting/export reads, not resource creation, so the consequence is an occasionally
        off-by-one report row, not a duplicated resource or a financial error — but it is a real race, not a
        theoretical one. A proper fix is keyset pagination on the query's actual order columns; deferred until
        analytics.py's real order() usage is audited, so the fix is shaped to what's actually called rather than
        guessed at here.
        """
        # Stable order, or pages can overlap / skip rows. Compare whole order terms: a column such as user_id.desc
        # must not be mistaken for the id tie-breaker.
        terms = [t for t in (self._order or "").split(",") if t]
        if not any(t.split(".", 1)[0] == "id" for t in terms):
            terms.append("id.asc")
        self._order = ",".join(terms)
        rows: list = []
        expected_total = None
        try:
            offset = 0
            while offset < max_rows:
                self._limit, self._offset = page_size, offset
                self._count = "exact" if offset == 0 else None      # first page tells us the real total
                res = self._execute_once()
                page = res["data"] if isinstance(res, dict) and "data" in res else res
                if offset == 0 and isinstance(res, dict):
                    expected_total = res.get("count")
                if not isinstance(page, list):
                    return page
                rows.extend(page)
                if not page or (expected_total is not None and len(rows) >= expected_total) \
                        or (expected_total is None and len(page) < page_size):
                    return rows
                offset += len(page)
            import logging
            logging.getLogger(__name__).warning("paginated query on %s stopped at %d rows (max_rows cap)", self._table, len(rows))
            return rows
        finally:
            self._limit = self._offset = self._count = None

    def _execute_once(self) -> list | dict | None:
        url = f"{self._client.url}/rest/v1/{self._table}"
        resp = self._client._session.get(url, headers=self._headers(), params=self._build_params(), timeout=self._client.timeout)
        if self._single and resp.status_code in (406, 404):
            return None
        _raise_for_status(resp)
        data = resp.json()
        if self._count:
            content_range = resp.headers.get("Content-Range") or resp.headers.get("content-range")
            total = None
            if content_range and "/" in content_range:
                total_str = content_range.split("/")[-1]
                if total_str.isdigit():
                    total = int(total_str)
            if total is None and isinstance(data, list):
                total = len(data)
            if isinstance(data, dict):
                data["count"] = total
                return data
            return {"data": data, "count": total}
        return data

    def insert(self, data: dict | list) -> list | dict:
        url = f"{self._client.url}/rest/v1/{self._table}"
        resp = self._client._session.post(url, headers=self._headers(), json=data, timeout=self._client.timeout)
        _raise_for_status(resp)
        return _wrap_result(resp.json()) if resp.content else QueryResultList()

    def update(self, data: dict) -> list | dict:
        url = f"{self._client.url}/rest/v1/{self._table}"
        self._require_filter("update")
        params = self._filter_params()
        resp = self._client._session.patch(url, headers=self._headers(), json=data, params=params, timeout=self._client.timeout)
        _raise_for_status(resp)
        return _wrap_result(resp.json()) if resp.content else QueryResultList()

    def delete(self) -> list | dict:
        url = f"{self._client.url}/rest/v1/{self._table}"
        self._require_filter("delete")
        params = self._filter_params()
        resp = self._client._session.delete(url, headers=self._headers(), params=params, timeout=self._client.timeout)
        _raise_for_status(resp)
        return _wrap_result(resp.json()) if resp.content else QueryResultList()

    def upsert(self, data: dict | list, on_conflict: str = "id") -> list | dict:
        url = f"{self._client.url}/rest/v1/{self._table}"
        headers = self._headers()
        headers["Prefer"] = f"resolution=merge-duplicates,return=representation"
        resp = self._client._session.post(url, headers=headers, json=data, params={"on_conflict": on_conflict}, timeout=self._client.timeout)
        _raise_for_status(resp)
        return _wrap_result(resp.json()) if resp.content else QueryResultList()


class _NotProxy:
    """Proxy to allow `.not_.is_(column, value)` → PostgREST `column=not.is.value` syntax."""
    __slots__ = ("_query",)

    def __init__(self, query: "TableQuery"):
        self._query = query

    def is_(self, column: str, value) -> "TableQuery":
        self._query._filters.append(f"{column}=not.is.{value}")
        return self._query

    def eq(self, column: str, value) -> "TableQuery":
        if value is None:
            self._query._filters.append(f"{column}=not.is.null")
        else:
            self._query._filters.append(f"{column}=not.eq.{TableQuery._escape_val(value)}")
        return self._query

    def in_(self, column: str, values: list) -> "TableQuery":
        val_str = "({})".format(",".join(TableQuery._escape_val(v) for v in values))
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
            body.get("message") or body.get("msg") or body.get("error_description") or body.get("error") or "Supabase error",
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


class UserSupabaseClient:
    """
    Wrapper around SupabaseClient that automatically passes the user's JWT token
    from g.jwt_token to all table queries and RPC calls for Row Level Security (RLS).
    """
    def __init__(self, client: SupabaseClient, jwt_token: str, paginate: bool = False):
        self._client = client
        self._jwt_token = jwt_token
        self._paginate = paginate

    def table(self, table_name: str) -> TableQuery:
        q = self._client.table(table_name).with_jwt(self._jwt_token)
        if self._paginate:
            q._auto_paginate = True        # list queries return ALL rows, not just the first 1000
        return q

    def rpc(self, function_name: str, params: dict = None) -> dict | list | None:
        # A guest has no JWT. Falling back to the anon key keeps the call as the anon role; passing None would make
        # SupabaseClient.rpc use the SERVICE key, i.e. a guest request running with full RLS bypass.
        return self._client.rpc(
            function_name,
            params=params,
            user_jwt=self._jwt_token or self._client.anon_key,
        )

    def __getattr__(self, name):
        return getattr(self._client, name)


def get_user_client(paginate: bool = False) -> SupabaseClient | UserSupabaseClient:
    """
    Returns a user-authenticated Supabase client using g.jwt_token if present in
    Flask request context. Unauthenticated guests receive visitor-scoped access using the anon key.
    """
    import sys
    try:
        caller_frame = sys._getframe(1)
        caller_get_db = caller_frame.f_globals.get("get_db", get_db)
        db = caller_get_db()
    except Exception:
        db = get_db()

    try:
        from flask import g, has_app_context
        if has_app_context():
            jwt = getattr(g, "jwt_token", None)
            if not isinstance(db, SupabaseClient):
                return db
            return UserSupabaseClient(db, jwt, paginate=paginate)
    except Exception:
        pass
    return db
