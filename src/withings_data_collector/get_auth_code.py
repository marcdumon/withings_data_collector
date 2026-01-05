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
import urllib.parse

import requests
import dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"
CONFIG_FILE = PROJECT_ROOT / "withings_config.toml"

logger = logging.getLogger(__name__)


class ConfigError(RuntimeError):
    """Raised when configuration loading or validation fails."""


class OAuthError(RuntimeError):
    """Raised when OAuth authorization or token exchange fails."""


class TokenRateLimitError(RuntimeError):
    """Raised when token refresh hits provider-imposed cooldown (status 601)."""

    def __init__(self, wait_seconds: int | None = None):
        self.wait_seconds = wait_seconds
        msg = f"Token refresh rate limited. Wait_seconds={wait_seconds}"
        super().__init__(msg)


def load_config() -> dict:
    """Load configuration from TOML file.

    Returns:
        dict: Configuration dictionary loaded from withings_config.toml

    Raises:
        ConfigError: If config file is missing or cannot be read
    """
    if not CONFIG_FILE.is_file():
        raise ConfigError(f"Missing config file: {CONFIG_FILE}")
    with CONFIG_FILE.open('rb') as f:
        return tomllib.load(f)


def load_credentials() -> tuple[str, str, str]:
    """Load OAuth credentials from environment variables.

    Returns:
        tuple[str, str, str]: Tuple of (client_id, client_secret, redirect_uri)

    Raises:
        ConfigError: If .env file is missing or required credentials are not set
    """
    if not ENV_FILE.is_file():
        raise ConfigError(f"Missing env file: {ENV_FILE}")
    dotenv.load_dotenv(ENV_FILE, override=True)
    client_id = os.getenv('WITHINGS_CLIENT_ID')
    client_secret = os.getenv('WITHINGS_CLIENT_SECRET')
    redirect_uri = os.getenv('WITHINGS_REDIRECT_URI')
    if not (client_id and client_secret and redirect_uri):
        raise ConfigError("Missing OAuth credentials")
    return client_id, client_secret, redirect_uri


def save_tokens(access_token: str, refresh_token: str) -> None:
    """Save access and refresh tokens to .env file.

    Args:
        access_token: The OAuth access token
        refresh_token: The OAuth refresh token
    """
    dotenv.set_key(ENV_FILE, 'WITHINGS_ACCESS_TOKEN', access_token)
    dotenv.set_key(ENV_FILE, 'WITHINGS_REFRESH_TOKEN', refresh_token)


def load_refresh_token() -> str:
    """Load refresh token from environment variables.

    Returns:
        str: The refresh token

    Raises:
        ConfigError: If .env file is missing or refresh token is not set
    """
    if not ENV_FILE.is_file():
        raise ConfigError(f"Missing env file: {ENV_FILE}")
    dotenv.load_dotenv(ENV_FILE, override=True)
    refresh_token = os.getenv('WITHINGS_REFRESH_TOKEN')
    if not refresh_token:
        raise ConfigError("Missing refresh token in .env")
    return refresh_token


def parse_token_response(data: dict) -> tuple[str, str, str, int]:
    """Parse token response from Withings API.

    Args:
        data: Response dictionary from token endpoint

    Returns:
        tuple[str, str, str, int]: Tuple of (access_token, refresh_token, userid, expires_in)

    Raises:
        OAuthError: If response format is invalid
    """
    body = data.get('body')
    if not isinstance(body, dict):
        raise OAuthError(f"Invalid token response: {data}")
    return (body['access_token'], body['refresh_token'], body['userid'], body['expires_in'])


@dataclass
class CallbackResult:
    """Container for OAuth callback parameters received from authorization redirect."""
    code: str | None = None
    state: str | None = None


class OAuthRedirectServer(socketserver.TCPServer):
    """TCP server for handling OAuth redirect callbacks."""
    allow_reuse_address = True


def make_callback_handler(
    result: CallbackResult,
    event: threading.Event,
    expected_state: str,
    expected_path: str,
) -> type[http.server.BaseHTTPRequestHandler]:
    """Create an HTTP request handler class for OAuth callbacks.

    Args:
        result: CallbackResult instance to store received parameters
        event: Threading event to signal when callback is received
        expected_state: Expected OAuth state parameter for CSRF protection
        expected_path: Expected callback URL path

    Returns:
        HTTP request handler class configured for OAuth callback handling
    """
    class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
        """HTTP request handler for OAuth authorization code callbacks."""
        server_version = 'WithingsAuthServer/1.0'
        sys_version = ''

        def log_message(self, format: str, *args) -> None:  # Suppress logging noise
            return

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != expected_path:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not found.")
                return

            params = urllib.parse.parse_qs(parsed.query)
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

    return OAuthCallbackHandler


def obtain_authorization_code_via_browser(
    auth_url: str,
    redirect_uri: str,
    expected_state: str,
    timeout: float,
) -> str:
    """Obtain authorization code by opening browser and handling redirect callback.

    Args:
        auth_url: Full authorization URL to open in browser
        redirect_uri: OAuth redirect URI with host and port
        expected_state: Expected OAuth state parameter for validation
        timeout: Timeout in seconds to wait for callback

    Returns:
        str: Authorization code received from callback

    Raises:
        ConfigError: If redirect URI is malformed
        OAuthError: If authorization times out or state validation fails
    """
    parsed = urllib.parse.urlparse(redirect_uri)
    if not parsed.hostname or not parsed.port:
        raise ConfigError("WITHINGS_REDIRECT_URI must include host and port.")

    expected_path = parsed.path or '/'
    result = CallbackResult()
    event = threading.Event()
    handler_cls = make_callback_handler(result, event, expected_state, expected_path)

    with OAuthRedirectServer((parsed.hostname, parsed.port), handler_cls) as httpd:
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
    timeout: float,
) -> tuple[str, str, str | None, int]:
    """Exchange authorization code for access and refresh tokens.

    Args:
        code: Authorization code received from OAuth callback
        client_id: OAuth client ID
        client_secret: OAuth client secret
        redirect_uri: OAuth redirect URI
        token_url: Withings token endpoint URL
        timeout: HTTP request timeout in seconds

    Returns:
        tuple[str, str, str | None, int]: Tuple of (access_token, refresh_token, userid, expires_in)

    Raises:
        requests.HTTPError: If token request fails
    """
    payload = {
        'action': 'requesttoken',
        'grant_type': 'authorization_code',
        'client_id': client_id,
        'client_secret': client_secret,
        'code': code,
        'redirect_uri': redirect_uri,
    }
    r = requests.post(token_url, data=payload, timeout=timeout)
    r.raise_for_status()

    return parse_token_response(r.json())


def get_authorization_tokens(scopes: str | None = None) -> dict[str, str | int | None]:
    """Perform complete OAuth authorization flow to obtain access tokens.

    Args:
        scopes: Comma-separated string of OAuth scopes. If None, uses default scopes
               from config. Must be subset of allowed_scopes in config.

    Returns:
        dict[str, str | int | None]: Dictionary containing access_token, refresh_token,
                                    userid, and expires_in

    Raises:
        OAuthError: If invalid scopes provided or authorization fails
    """
    config = load_config()
    client_id, client_secret, redirect_uri = load_credentials()

    api = config['api']
    oauth = config['oauth']
    http_timeout = float(oauth['http_timeout'])
    callback_timeout = float(oauth['callback_timeout'])

    if scopes is None:
        scopes = oauth['default_scopes']
    else:
        scope_list = scopes.split(',')
        for scope in scope_list:
            if scope not in oauth['allowed_scopes']:
                raise OAuthError(f"Invalid scope: {scope}")
        scopes = ','.join(scope_list)  # Join the list back into a string

    state = secrets.token_urlsafe(32)

    auth_params = {
        'response_type': 'code',
        'client_id': client_id,
        'state': state,
        'scope': scopes,
        'redirect_uri': redirect_uri,
    }

    auth_url = f"{api['account_url']}{api['auth_endpoint']}?{urllib.parse.urlencode(auth_params)}"
    code = obtain_authorization_code_via_browser(
        auth_url=auth_url,
        redirect_uri=redirect_uri,
        expected_state=state,
        timeout=callback_timeout,
    )

    token_url = f"{api['wbsapi_url']}{api['token_endpoint']}"
    access_token, refresh_token, userid, expires_in = exchange_code(
        code,
        client_id,
        client_secret,
        redirect_uri,
        token_url,
        http_timeout,
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


def refresh_authorization_tokens(timeout: float | None = None) -> dict[str, str | int | None]:
    """Refresh OAuth access token using stored refresh token.

    Args:
        timeout: HTTP request timeout in seconds. If None, uses config default.

    Returns:
        dict[str, str | int | None]: Dictionary containing access_token, refresh_token,
                                    userid, and expires_in

    Raises:
        TokenRateLimitError: If token refresh is rate limited by provider
        OAuthError: If refresh fails for other reasons
    """
    config = load_config()
    client_id, client_secret, _ = load_credentials()
    refresh_token = load_refresh_token()

    api = config['api']
    oauth = config['oauth']
    http_timeout = float(oauth['http_timeout'])
    timeout = float(timeout) if timeout is not None else http_timeout

    token_url = f"{api['wbsapi_url']}{api['token_endpoint']}"
    payload = {
        'action': 'requesttoken',
        'grant_type': 'refresh_token',
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_token,
    }

    r = requests.post(token_url, data=payload, timeout=timeout)
    r.raise_for_status()
    response_json = r.json()
    if not isinstance(response_json, dict):
        raise OAuthError(f'Invalid token response (not dict): {response_json}')

    status = response_json.get('status')
    body = response_json.get('body')
    if status != 0:
        if status == 601:
            wait_seconds = None
            if isinstance(body, dict):
                wait_seconds = body.get('wait_seconds')
            raise TokenRateLimitError(wait_seconds=wait_seconds)
        raise OAuthError(f'Refresh failed with status {status}: {response_json}')
    access_token, new_refresh_token, userid, expires_in = parse_token_response(response_json)

    save_tokens(access_token, new_refresh_token)
    logger.info("Tokens refreshed and saved to %s", ENV_FILE)
    logger.info("Access token expires in %s hours", expires_in // 3600)
    if userid:
        logger.info("User ID: %s", userid)

    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "userid": userid,
        "expires_in": expires_in,
    }


def main() -> None:
    """Main entry point for OAuth authorization flow.

    Performs authorization with default scopes for user info, metrics, and activity.
    """
    get_authorization_tokens("user.info,user.metrics,user.activity")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
