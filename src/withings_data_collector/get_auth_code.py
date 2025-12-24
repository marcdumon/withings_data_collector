#!/usr/bin/env python3
"""OAuth2 authorization flow for Withings API."""

import os
import secrets
import sys
import tomllib
import webbrowser
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv, set_key

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"
CONFIG_FILE = PROJECT_ROOT / "withings_config.toml"
DEFAULT_EXPIRES_IN = 10800
HTTP_TIMEOUT = 10.0


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
    webbrowser.open(auth_url)

    code = input("Paste authorization code: ").strip()
    if not code:
        raise OAuthError("Authorization code missing")

    token_url = f"{api['wbsapi_url']}{api['token_endpoint']}"
    access_token, refresh_token, userid, expires_in = exchange_code(
        code,
        client_id,
        client_secret,
        redirect_uri,
        token_url,
    )

    save_tokens(access_token, refresh_token)
    masked_access = f"{access_token[:3]}...{access_token[-3:]}"
    masked_refresh = f"{refresh_token[:3]}...{refresh_token[-3:]}"
    print(f"Access Token:  {masked_access}")
    print(f"Refresh Token: {masked_refresh}")
    print(f"Expires in:    {expires_in // 3600} hours")
    if userid:
        print(f"User ID:       {userid}")

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
