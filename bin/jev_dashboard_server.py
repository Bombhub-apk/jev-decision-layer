"""Loopback-only, read-only HTTP service for the Jev usage dashboard."""

from __future__ import annotations

import json
import math
import re
import socket
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
from jev_ledger_store import LedgerError, load_ledger


FONT_FILES = {
    "Vazirmatn[wght].woff2",
    "Estedad[wght].woff2",
    "Outfit[wght].woff2",
}
KEY_FIELDS = (
    "name",
    "masked",
    "status",
    "calls",
    "tokens",
    "is_active_target",
    "is_next",
)
RECORD_FIELDS = (
    "record_origin",
    "timestamp",
    "client",
    "client_name",
    "model",
    "question_types",
    "input_tokens",
    "output_tokens",
    "confidence",
    "summary",
    "duration_ms",
    "attempt_count",
    "usage_source",
    "cost_usd",
    "cost_source",
    "comparison",
)
COMPARISON_BASELINE_FIELDS = (
    "provider",
    "model",
    "usage_source",
    "input_tokens",
    "output_tokens",
    "cost_usd",
    "cost_source",
    "pricing_snapshot",
)
HOST_PATTERN = re.compile(r"^(?:127\.0\.0\.1|localhost|\[::1\])(?::[0-9]{1,5})?$", re.IGNORECASE)
LOOPBACK_HOST = "127.0.0.1"
IPV6_LOOPBACK_HOST = "::1"


class SnapshotUnavailable(RuntimeError):
    """Raised when a consistent, valid ledger snapshot cannot be read."""


class _IPv6LoopbackThreadingHTTPServer(ThreadingHTTPServer):
    """IPv6-only HTTP server; never expose a dual-stack or wildcard listener."""

    address_family = socket.AF_INET6

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        super().server_bind()


def _iso_timestamp(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def _read_ledger_consistently(ledger_path, attempts=3):
    del attempts  # load_ledger serializes reads with the same lock used by writers.
    try:
        return load_ledger(ledger_path, create=False)
    except (LedgerError, OSError) as error:
        raise SnapshotUnavailable("The usage ledger is temporarily unavailable.") from error


def _safe_comparison(value):
    """Project only provider-measured, explicitly equivalent baseline fields."""
    if not isinstance(value, dict) or value.get("equivalent") is not True:
        return None
    comparison_id = value.get("comparison_id")
    baseline = value.get("baseline")
    if not isinstance(comparison_id, str) or not comparison_id.strip() or not isinstance(baseline, dict):
        return None
    if baseline.get("usage_source") != "provider":
        return None
    projected = {}
    for field in COMPARISON_BASELINE_FIELDS:
        item = baseline.get(field)
        if field in ("provider", "model"):
            if isinstance(item, str) and item.strip():
                projected[field] = item.strip()[:120]
        elif field in ("input_tokens", "output_tokens"):
            if isinstance(item, int) and not isinstance(item, bool) and item >= 0:
                projected[field] = item
        elif field == "usage_source":
            projected[field] = "provider"
        elif field == "cost_usd":
            if isinstance(item, (int, float)) and not isinstance(item, bool) and 0 <= item < float("inf"):
                projected[field] = item
        elif field == "cost_source":
            if item in ("provider_reported", "calculated_from_pricing_snapshot"):
                projected[field] = item
        elif field == "pricing_snapshot" and isinstance(item, dict):
            safe_pricing = {}
            for key in ("provider", "source", "checked_on"):
                entry = item.get(key)
                if isinstance(entry, str):
                    safe_pricing[key] = entry[:300]
            for key in ("input_usd_per_million", "output_usd_per_million"):
                entry = item.get(key)
                if isinstance(entry, (int, float)) and not isinstance(entry, bool) and 0 <= entry < float("inf"):
                    safe_pricing[key] = entry
            projected[field] = safe_pricing
    if not all(field in projected for field in ("provider", "model", "input_tokens", "output_tokens")):
        return None
    return {
        "comparison_id": comparison_id.strip()[:160],
        "equivalent": True,
        "baseline": projected,
    }


def _safe_keys(key_rows):
    safe_rows = []
    if not isinstance(key_rows, (list, tuple)):
        return safe_rows
    for row in key_rows:
        if not isinstance(row, dict):
            continue
        safe = {}
        for field in KEY_FIELDS:
            value = row.get(field)
            if field in ("name", "masked", "status") and isinstance(value, str):
                if field in row:
                    safe[field] = value[:160]
            elif field in ("calls", "tokens") and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                safe[field] = value
            elif field in ("is_active_target", "is_next") and isinstance(value, bool):
                safe[field] = value
            elif field in row and value is None:
                safe[field] = None
        safe_rows.append(safe)
    return safe_rows


def _safe_records(records):
    projected = []
    for row in records:
        safe = {}
        for field in RECORD_FIELDS:
            if field not in row:
                continue
            value = row[field]
            if field == "comparison":
                safe_comparison = _safe_comparison(value)
                if safe_comparison:
                    safe[field] = safe_comparison
            elif field == "timestamp":
                parsed_timestamp = _iso_timestamp(value)
                if parsed_timestamp is not None:
                    safe[field] = parsed_timestamp.isoformat(timespec="seconds")
            elif field in ("record_origin", "client", "client_name", "model", "summary", "usage_source", "cost_source"):
                if isinstance(value, str):
                    safe[field] = value[:500]
            elif field == "question_types":
                if isinstance(value, list):
                    safe[field] = [entry[:120] for entry in value if isinstance(entry, str)][:40]
            elif field in ("input_tokens", "output_tokens", "confidence", "duration_ms", "attempt_count", "cost_usd") and value is None:
                safe[field] = value
            elif field in ("input_tokens", "output_tokens", "confidence", "duration_ms", "attempt_count", "cost_usd") and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                safe[field] = value
        projected.append(safe)
    return projected


def build_snapshot(ledger_path, key_rows, strategy, now=None):
    """Build a safe response from the actual ledger and already-masked key rows."""
    records, ledger_state = _read_ledger_consistently(ledger_path)
    current = now or datetime.now().astimezone()
    if current.tzinfo is None:
        current = current.astimezone()
    runtime_dates = [
        parsed
        for row in records
        if row.get("record_origin") == "runtime"
        if (parsed := _iso_timestamp(row.get("timestamp"))) is not None
    ]
    latest = max(runtime_dates).isoformat(timespec="seconds") if runtime_dates else None
    safe_strategy = strategy if strategy in ("round_robin", "single") else "unknown"
    verified_savings = {}
    try:
        import jev_tracker
        metrics = jev_tracker.get_metrics()
        verified_savings = {
            "tokens_saved": metrics.get("tokens_saved"),
            "cost_saved_usd": metrics.get("cost_saved_usd"),
            "token_saving_pct": metrics.get("token_saving_pct"),
            "cost_saving_pct": metrics.get("cost_saving_pct"),
            "paired_comparisons": metrics.get("paired_comparisons"),
        }
    except Exception:
        pass
    return {
        "generated_at": current.isoformat(timespec="seconds"),
        "latest_event_at": latest,
        "records": _safe_records(records),
        "ledger_recovered": bool(ledger_state.get("recovered")),
        "ledger_recovery_warning": bool(ledger_state.get("has_recovery_artifacts")),
        "keys": _safe_keys(key_rows),
        "strategy": safe_strategy,
        "verified_savings": verified_savings,
    }


def make_handler(project_root, page_html, snapshot_provider):
    """Create an injectable HTTP handler for local dashboard tests and runtime."""
    root = Path(project_root).resolve()
    fonts_dir = root / "assets" / "fonts"

    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "JevDashboard"
        sys_version = ""

        def log_message(self, _format, *_args):
            return

        def _host_is_local(self):
            host = self.headers.get("Host", "").strip()
            if not HOST_PATTERN.fullmatch(host):
                return False
            try:
                parsed = urlsplit("//" + host)
                hostname = (parsed.hostname or "").lower()
                port = parsed.port
            except ValueError:
                return False
            return hostname in ("127.0.0.1", "localhost", IPV6_LOOPBACK_HOST) and port in (
                None,
                self.server.server_port,
            )

        def _origin_is_local(self):
            origin = self.headers.get("Origin")
            if origin is None:
                return True
            try:
                parsed = urlsplit(origin)
                port = parsed.port
            except ValueError:
                return False
            return (
                parsed.scheme == "http"
                and (parsed.hostname or "").lower() in ("127.0.0.1", "localhost", IPV6_LOOPBACK_HOST)
                and port in (None, self.server.server_port)
            )

        def _respond(self, status, body, content_type="application/json; charset=utf-8"):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data: https:; font-src 'self' https: data:; "
                "style-src 'self' 'unsafe-inline' https:; script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net; "
                "connect-src 'self' http://127.0.0.1:* http://localhost:*; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status, payload):
            self._respond(
                status,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            )

        def do_GET(self):
            if not self._host_is_local() or not self._origin_is_local():
                self._json(403, {"error": "local_access_only"})
                return

            path = unquote(urlsplit(self.path).path)
            if path == "/":
                self._respond(200, page_html, "text/html; charset=utf-8")
                return
            if path == "/api/snapshot":
                try:
                    snapshot = snapshot_provider()
                except SnapshotUnavailable:
                    self._json(503, {"error": "snapshot_unavailable"})
                    return
                except Exception:
                    self._json(503, {"error": "snapshot_unavailable"})
                    return
                self._json(200, snapshot)
                return

            prefix = "/assets/fonts/"
            if path.startswith(prefix):
                name = path[len(prefix) :]
                if name not in FONT_FILES or "/" in name or "\\" in name:
                    self._json(404, {"error": "not_found"})
                    return
                font_path = fonts_dir / name
                try:
                    body = font_path.read_bytes()
                except OSError:
                    self._json(404, {"error": "not_found"})
                    return
                self._respond(200, body, "font/woff2")
                return

        def do_POST(self):
            if not self._host_is_local() or not self._origin_is_local():
                self._json(403, {"error": "local_access_only"})
                return

            path = unquote(urlsplit(self.path).path)
            content_length = int(self.headers.get("Content-Length", 0))
            body_bytes = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
            except Exception:
                self._json(400, {"error": "invalid_json"})
                return

            import jev_key_manager

            if path == "/api/keys/add":
                name = payload.get("name", "").strip()
                key = payload.get("key", "").strip()
                if not name or not key:
                    self._json(400, {"error": "name_and_key_required"})
                    return
                try:
                    res = jev_key_manager.add_key(name, key)
                    snapshot = snapshot_provider()
                    self._json(200, {"status": "ok", "result": res, "snapshot": snapshot})
                except Exception as e:
                    self._json(400, {"error": str(e)})
                return

            elif path == "/api/keys/remove":
                name = payload.get("name", "").strip()
                if not name:
                    self._json(400, {"error": "name_required"})
                    return
                ok = jev_key_manager.remove_key(name)
                snapshot = snapshot_provider()
                self._json(200, {"status": "ok" if ok else "not_found", "snapshot": snapshot})
                return

            elif path == "/api/keys/edit":
                name = payload.get("name", "").strip()
                new_name = payload.get("new_name")
                key_val = payload.get("key") or payload.get("new_key")
                status = payload.get("status")
                try:
                    ok = jev_key_manager.edit_key(name, new_name=new_name, key_val=key_val, status=status)
                    snapshot = snapshot_provider()
                    self._json(200, {"status": "ok" if ok else "not_found", "snapshot": snapshot})
                except Exception as e:
                    self._json(400, {"error": str(e)})
                return

            elif path == "/api/keys/use":
                name = payload.get("name", "").strip()
                ok = jev_key_manager.set_active_key(name)
                snapshot = snapshot_provider()
                self._json(200, {"status": "ok" if ok else "not_found", "snapshot": snapshot})
                return

            elif path == "/api/keys/strategy":
                strategy = payload.get("strategy", "").strip()
                if strategy not in ("round_robin", "single"):
                    self._json(400, {"error": "invalid_strategy"})
                    return
                res = jev_key_manager.set_strategy(strategy)
                snapshot = snapshot_provider()
                self._json(200, {"status": "ok", "strategy": res, "snapshot": snapshot})
                return

            elif path == "/api/keys/toggle":
                name = payload.get("name", "").strip()
                try:
                    res = jev_key_manager.toggle_key_status(name)
                    snapshot = snapshot_provider()
                    self._json(200, {"status": "ok", "new_status": res, "snapshot": snapshot})
                except Exception as e:
                    self._json(400, {"error": str(e)})
                return

            self._json(404, {"error": "not_found"})

        def _method_not_allowed(self):
            self.send_response(405)
            self.send_header("Allow", "GET, POST")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_PUT = _method_not_allowed
        do_PATCH = _method_not_allowed
        do_DELETE = _method_not_allowed
        do_OPTIONS = _method_not_allowed

    return DashboardHandler


def _create_loopback_server(port, handler):
    """Prefer browser-compatible IPv6 loopback, falling back to IPv4 loopback."""
    ipv6_issue = None
    try:
        server = _IPv6LoopbackThreadingHTTPServer((IPV6_LOOPBACK_HOST, port), handler)
    except OSError as error:
        ipv6_issue = error
    else:
        bound_host = server.server_address[0]
        if bound_host == IPV6_LOOPBACK_HOST:
            return server
        server.server_close()
        ipv6_issue = RuntimeError(
            f"requested {IPV6_LOOPBACK_HOST} but the operating system bound {bound_host}"
        )

    try:
        server = ThreadingHTTPServer((LOOPBACK_HOST, port), handler)
    except OSError as error:
        raise RuntimeError(
            "Refusing to serve the Jev dashboard: IPv6 loopback was unavailable "
            f"({ipv6_issue}); IPv4 loopback failed ({error})."
        ) from error

    bound_host = server.server_address[0]
    if bound_host != LOOPBACK_HOST:
        server.server_close()
        raise RuntimeError(
            "Refusing to serve the Jev dashboard: requested IPv4 loopback "
            f"but the operating system bound {bound_host}."
        )
    return server


def _dashboard_url(server):
    """Format an HTTP URL for either IPv4 or IPv6 loopback server addresses."""
    bound_host = server.server_address[0]
    if ":" in bound_host:
        bound_host = f"[{bound_host}]"
    return f"http://{bound_host}:{server.server_port}/"


def serve_dashboard(port=0, open_browser=True, refresh_seconds=5):
    """Serve Jev's read-only dashboard on an ephemeral or caller-selected loopback port."""
    if not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("port must be an integer from 0 to 65535")
    if not isinstance(refresh_seconds, int) or not 1 <= refresh_seconds <= 300:
        raise ValueError("refresh_seconds must be an integer from 1 to 300")

    import jev_key_manager
    import jev_tracker
    import jev_dashboard_ui

    root = Path(__file__).resolve().parent
    page = jev_dashboard_ui.render_dashboard_html(
        [], [], "unknown", live=True, refresh_seconds=refresh_seconds
    )

    def snapshot_provider():
        config = jev_key_manager.load_config()
        return build_snapshot(
            jev_tracker.LEDGER_PATH,
            jev_key_manager.list_keys(),
            config.get("strategy"),
        )

    server = _create_loopback_server(
        port,
        make_handler(root, page, snapshot_provider),
    )
    server.daemon_threads = True
    url = _dashboard_url(server)
    print(f"Jev live dashboard: {url}")
    print("Press Ctrl+C in this terminal to stop the panel.")
    if open_browser and not webbrowser.open(url, new=2):
        print("The browser did not open automatically; use the URL above.")
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nStopping Jev dashboard.")
    finally:
        server.server_close()
