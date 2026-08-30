"""Additional Python egress checks. Docker no-masquerade networking is the primary boundary.

No arbitrary RFC1918 ranges, external DNS, host gateway, proxies or model downloads.
This is defense in depth, not a sandbox for malicious Python/native code.
"""
import json
import os
import socket
import sys
import threading

HOST_PORTS = {
    "postgres": {5432}, "redis": {6379}, "kafka": {9092},
    "neo4j": {7474, 7687}, "elasticsearch": {9200}, "minio": {9000, 9001},
    **{"layer%d-api" % i: {8000 + i} for i in range(1, 7)},
}
LOCAL_PORTS = {5432, 6379, 7474, 7687, 9092, 9200, 9000, 9001,
               8001, 8002, 8003, 8004, 8005, 8006}
_addresses = {}
_resolving = threading.local()
_installed = False


def _deny():
    raise PermissionError("LOCAL SAFE MODE: destination is not an approved Satorix service")


def check_host(host):
    if isinstance(host, bytes):
        host = host.decode("ascii")
    if host not in HOST_PORTS and host not in _addresses and host not in ("localhost", "127.0.0.1", "::1"):
        _deny()


def _remember_service(host):
    if isinstance(host, bytes):
        host = host.decode("ascii")
    if host not in HOST_PORTS:
        return
    _resolving.active = True
    try:
        for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM):
            _addresses.setdefault(item[4][0], set()).update(HOST_PORTS[host])
    except socket.gaierror:
        pass
    finally:
        _resolving.active = False


def check_destination(address):
    if not isinstance(address, tuple):
        return  # Unix sockets are local; no host sockets are mounted.
    host, port = address[:2]
    if host in HOST_PORTS and port in HOST_PORTS[host]:
        return
    if host in ("localhost", "127.0.0.1", "::1") and port in LOCAL_PORTS:
        return
    if port in _addresses.get(host, set()):
        return
    _deny()


def _audit(event, args):
    if getattr(_resolving, "active", False):
        return
    if event in ("socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr"):
        # getaddrinfo(None / wildcard, AI_PASSIVE) is server-side binding, not dialing.
        if event == "socket.getaddrinfo" and args[0] in (None, "0.0.0.0", "::"):
            return
        check_host(args[0])
        _remember_service(args[0])
    elif event == "socket.connect":
        check_destination(args[1])
    elif event == "socket.sendto":
        check_destination(args[-1])


def install():
    global _installed
    if _installed:
        return
    if os.environ.get("LOCAL_SAFE_MODE", "true").lower() != "true":
        raise RuntimeError("Safe launcher refuses LOCAL_SAFE_MODE=false")
    for key in list(os.environ):
        if key.lower().endswith("_proxy"):
            os.environ.pop(key, None)
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY",
                "GROQ_API_KEY", "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ.pop(key, None)
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE",
                "HF_HUB_DISABLE_TELEMETRY", "DO_NOT_TRACK", "AWS_EC2_METADATA_DISABLED"):
        os.environ[key] = "1" if key != "AWS_EC2_METADATA_DISABLED" else "true"
    # Resolve only literal approved Docker names before application imports.
    for host in HOST_PORTS:
        _remember_service(host)
    sys.addaudithook(_audit)
    _installed = True


class ReadOnlyLocalMiddleware:
    """Read-only/login; Layer 1 may opt into the closed fixture-import exception."""
    def __init__(self, app, fixture_import=False):
        self.app = app
        self.fixture_import = fixture_import

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        fixture_allowed = False
        if (self.fixture_import and scope["type"] == "http" and
                path == "/api/v1/fixtures/import" and scope.get("method") == "POST"):
            from shared.fixture_operation import authorize_fixture
            try:
                if scope.get("query_string"):
                    raise PermissionError("Fixture import does not accept query parameters")
                body = b""
                while True:
                    message = await receive()
                    if message["type"] != "http.request":
                        raise PermissionError("Incomplete fixture request")
                    body += message.get("body", b"")
                    if len(body) > 1024:
                        raise PermissionError("Fixture request too large")
                    if not message.get("more_body", False):
                        break
                authorize_fixture(json.loads(body))
                original_receive = receive
                delivered = False

                async def fixture_receive():
                    nonlocal delivered
                    if not delivered:
                        delivered = True
                        return {"type": "http.request", "body": body, "more_body": False}
                    return await original_receive()

                receive = fixture_receive
                fixture_allowed = True
            except (PermissionError, ValueError, TypeError):
                pass  # Remain blocked by the existing read-only rule below.
        blocked = (scope["type"] == "websocket" or
                   (scope["type"] == "http" and
                    ("/webhook" in path or "/llm" in path or
                     (scope.get("method") not in ("GET", "HEAD", "OPTIONS") and
                      path != "/api/v1/auth/login" and not fixture_allowed))))
        if blocked:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
                return
            payload = json.dumps({"detail": "Disabled in LOCAL SAFE MODE"}).encode()
            await send({"type": "http.response.start", "status": 403,
                        "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": payload})
            return
        await self.app(scope, receive, send)
