"""Generic webhook ATS sync (Greenhouse/Lever-style REST webhooks).

Outbound: we POST signed JSON events to the org's configured URL.
Inbound: the ATS POSTs to our per-org tokenized endpoint (see routers/ats.py).
Payloads are HMAC-SHA256 signed with the shared secret when one is set
(X-RecruitAI-Signature: sha256=<hex>).
"""
import hashlib
import hmac
import ipaddress
import json
import socket
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from ..db import service_client


class UnsafeURL(ValueError):
    pass


def check_outbound_url(url: str) -> str:
    """Refuse webhook targets that point back inside our own network.

    The outbound URL is typed by a customer and fetched by this server, so
    without this any account could aim it at the database port, the local
    Supabase admin API or a cloud metadata endpoint, and read the HTTP status
    back from the event log. Every address the name resolves to is checked,
    and the check runs again at send time because DNS can change between
    saving the URL and using it.
    """
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https"):
        raise UnsafeURL("Webhook URL must start with http:// or https://")
    if not parts.hostname or parts.username or parts.password:
        raise UnsafeURL("Webhook URL must be a plain host name, without credentials")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    except (socket.gaierror, UnicodeError):
        raise UnsafeURL("Webhook host name does not resolve")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global or ip.is_multicast:
            raise UnsafeURL("Webhook URL must point to a public internet address")
    return url.strip()


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify_signature(secret: str, body: bytes, header_value: str | None) -> bool:
    if not secret:
        return True  # no secret configured -> token-only auth
    return bool(header_value) and hmac.compare_digest(sign(secret, body), header_value)


def get_connection(org_id: str) -> dict | None:
    rows = (
        service_client().table("ats_connections").select("*")
        .eq("organization_id", org_id).eq("active", True)
        .execute().data
    )
    return rows[0] if rows else None


def log_event(org_id: str, direction: str, event_type: str, payload: dict,
              result: str, detail: str = "", connection_id: str | None = None,
              candidate_id: str | None = None) -> None:
    service_client().table("ats_events").insert({
        "organization_id": org_id,
        "connection_id": connection_id,
        "direction": direction,
        "event_type": event_type,
        "candidate_id": candidate_id,
        "payload": payload,
        "result": result,
        "detail": detail[:1000],
    }).execute()


def send_outbound(org_id: str, event_type: str, data: dict, candidate_id: str | None = None) -> None:
    """Fire-and-log a signed webhook to the org's ATS. Never raises — sync
    failures must not break the recruiter action that triggered them."""
    conn = get_connection(org_id)
    if not conn or not conn.get("outbound_url"):
        return
    payload = {
        "event": event_type,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "RecruitAI-Webhook/1.0"}
    if conn.get("secret"):
        headers["X-RecruitAI-Signature"] = sign(conn["secret"], body)
    result, detail = "delivered", ""
    try:
        url = check_outbound_url(conn["outbound_url"])
        # Redirects stay off: following one would let a public URL bounce the
        # request to an internal address after the check above.
        resp = httpx.post(url, content=body, headers=headers, timeout=10, follow_redirects=False)
        detail = f"HTTP {resp.status_code}"
        if resp.status_code >= 400:
            result = "failed"
    except Exception as e:
        result, detail = "failed", str(e)
    try:
        log_event(org_id, "outbound", event_type, payload, result, detail,
                  connection_id=conn["id"], candidate_id=candidate_id)
    except Exception:
        pass
