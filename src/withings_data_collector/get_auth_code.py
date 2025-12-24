"""OAuth2 authorization flow for Withings API."""

import http.server
import logging
import os
import secrets
import socketserver
import sys
import threading
import tomllib
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import load_dotenv, set_key

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"
CONFIG_FILE = PROJECT_ROOT / "withings_config.toml"
DEFAULT_EXPIRES_IN = 10800
HTTP_TIMEOUT = 10.0
CALLBACK_TIMEOUT = 300.0

logger = logging.getLogger(__name__)


class ConfigError(RuntimeError):
    pass


class OAuthError(RuntimeError):
    pass


def load_config() -> dict:
    if not CONFIG_FILE.is_file():
        raise ConfigError(f"Missing config file: {CONFIG_FILE}")
    with CONFIG_FILE.open("rb") as f:
        return tomllib.load(f)


def load_credentials() -> tuple[str, str, str]:
    if not ENV_FILE.is_file():
        raise ConfigError(f"Missing env file: {ENV_FILE}")
    load_dotenv(ENV_FILE)
    client_id = os.getenv("WITHINGS_CLIENT_ID")
    client_secret = os.getenv("WITHINGS_CLIENT_SECRET")
    redirect_uri = os.getenv("WITHINGS_REDIRECT_URI")
    if not all((client_id, client_secret, redirect_uri)):
        raise ConfigError("Missing OAuth credentials")
    return client_id, client_secret, redirect_uri


def save_tokens(access_token: str, refresh_token: str) -> None:
    set_key(ENV_FILE, "WITHINGS_ACCESS_TOKEN", access_token)
    set_key(ENV_FILE, "WITHINGS_REFRESH_TOKEN", refresh_token)


def parse_token_response(data: dict) -> tuple[str, str, str | None, int]:
    body = data.get("body")
    if not isinstance(body, dict):
        raise OAuthError(f"Invalid token response: {data}")
    return (
        body["access_token"],
        body["refresh_token"],
        body.get("userid"),
        int(body.get("expires_in", DEFAULT_EXPIRES_IN)),
    )


@dataclass
class CallbackResult:
    code: str | None = None
    state: str | None = None


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def make_callback_handler(
    result: CallbackResult,
    event: threading.Event,
    expected_state: str,
    expected_path: str,
) -> type[http.server.BaseHTTPRequestHandler]:
    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        server_version = 'WithingsAuthServer/1.0'
        sys_version = ''

        def log_message(self, fmt: str, *args) -> None:
            return

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != expected_path:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not found.")
                return

            params = parse_qs(parsed.query)
            code = params.get('code', [None])[0]
            state = params.get('state', [None])[0]

            if not code:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing authorization code.")
                return
            result.code = code
            result.state = state
            event.set()

            if state != expected_state:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"State mismatch. Authorization denied.")
                return

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Authorization received. You may close this tab.")

    return CallbackHandler


def wait_for_authorization_code(
    auth_url: str,
    redirect_uri: str,
    expected_state: str,
    timeout: float,
) -> str:
    parsed = urlparse(redirect_uri)
    if not parsed.hostname or not parsed.port:
        raise ConfigError("WITHINGS_REDIRECT_URI must include host and port.")

    expected_path = parsed.path or '/'
    result = CallbackResult()
    event = threading.Event()
    handler_cls = make_callback_handler(result, event, expected_state, expected_path)

    with ReusableTCPServer((parsed.hostname, parsed.port), handler_cls) as httpd:
        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()

        webbrowser.open(auth_url)
        if not event.wait(timeout):
            httpd.shutdown()
            server_thread.join()
            raise OAuthError("Authorization timed out waiting for callback.")

        httpd.shutdown()
        server_thread.join()

    if result.state != expected_state:
        raise OAuthError("State validation failed.")
    if not result.code:
        raise OAuthError("Authorization code missing from callback.")

    return result.code


def exchange_code(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    token_url: str,
) -> tuple[str, str, str | None, int]:
    payload = {
        "action": "requesttoken",
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
    }
    r = requests.post(token_url, data=payload, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return parse_token_response(r.json())


def get_authorization_tokens(scope: str | None = None) -> dict[str, str | int | None]:
    config = load_config()
    client_id, client_secret, redirect_uri = load_credentials()

    api = config["api"]
    oauth = config["oauth"]

    scope = scope or oauth["default_scopes"]
    state = secrets.token_urlsafe(32)

    auth_params = {
        "response_type": "code",
        "client_id": client_id,
        "state": state,
        "scope": scope,
        "redirect_uri": redirect_uri,
    }

    auth_url = f"{api['account_url']}{api['auth_endpoint']}?{urlencode(auth_params)}"
    code = wait_for_authorization_code(
        auth_url=auth_url,
        redirect_uri=redirect_uri,
        expected_state=state,
        timeout=CALLBACK_TIMEOUT,
    )

    token_url = f"{api['wbsapi_url']}{api['token_endpoint']}"
    access_token, refresh_token, userid, expires_in = exchange_code(
        code,
        client_id,
        client_secret,
        redirect_uri,
        token_url,
    )

    save_tokens(access_token, refresh_token)
    logger.info("Tokens saved to %s", ENV_FILE)
    logger.info("Access token expires in %s hours", expires_in // 3600)
    if userid:
        logger.info("User ID: %s", userid)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "userid": userid,
        "expires_in": expires_in,
    }


def main() -> None:
    get_authorization_tokens()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
