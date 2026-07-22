from functools import lru_cache

import httpx
from supabase import Client, create_client

from .config import settings


class _RetryTransport(httpx.HTTPTransport):
    """Supabase's free tier intermittently drops idle keep-alive connections
    (ReadError: 'connection forcibly closed') or responds slowly (ReadTimeout).
    Retry once: always for dead-connection errors (they occur before the
    server processes anything), and for timeouts only on idempotent methods."""

    _DEAD_CONNECTION = (httpx.ReadError, httpx.RemoteProtocolError, httpx.ConnectError, httpx.ConnectTimeout)

    def handle_request(self, request):
        try:
            return super().handle_request(request)
        except self._DEAD_CONNECTION:
            return super().handle_request(request)
        except httpx.ReadTimeout:
            if request.method in ("GET", "HEAD"):
                return super().handle_request(request)
            raise


@lru_cache
def service_client() -> Client:
    """Service-role client. Bypasses RLS — every query in this codebase MUST
    filter by organization_id derived from the caller's JWT (see auth.py)."""
    client = create_client(settings.supabase_url, settings.supabase_secret_key)
    # Short keepalive expiry + transparent retry to survive upstream resets.
    client.postgrest.session._transport = _RetryTransport(
        limits=httpx.Limits(max_keepalive_connections=10, keepalive_expiry=15)
    )
    return client
