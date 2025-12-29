"""Data fetching utilities for Withings API."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from withings_data_collector.get_auth_code import (
    ConfigError,
    TokenRateLimitError,
    load_config,
    refresh_authorization_tokens,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / '.env'


class WithingsApiError(RuntimeError):
    pass


def _load_access_token() -> str:
    if not ENV_FILE.is_file():
        raise ConfigError(f"Missing env file: {ENV_FILE}")
    load_dotenv(ENV_FILE, override=True)
    access_token = os.getenv('WITHINGS_ACCESS_TOKEN')
    if not access_token:
        raise ConfigError("Missing access token in .env")
    return access_token


def get_access_token(refresh: bool = False) -> str:
    """Return a valid access token, optionally refreshing first."""
    if refresh:
        try:
            refresh_authorization_tokens()
        except TokenRateLimitError:
            # Fall back to existing token when rate limited
            token = _load_access_token()
            return token
        except Exception:
            raise
    token = _load_access_token()
    return token


def _authorized_get(url: str, access_token: str, params: dict[str, Any], timeout: float) -> dict:
    headers = {'Authorization': f'Bearer {access_token}'}
    response = requests.get(url, headers=headers, params=params, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if data.get('status') != 0:
        raise WithingsApiError(f"Withings API returned status {data.get('status')}: {data}")
    return data


def get_user_devices(access_token: str, api_base: str, timeout: float) -> dict:
    url = f'{api_base}/v2/user'
    params = {'action': 'getdevice'}
    return _authorized_get(url, access_token, params, timeout)


def get_measurements(
    access_token: str,
    api_base: str,
    timeout: float,
    startdate: int | None = None,
    enddate: int | None = None,
    lastupdate: int | None = None,
    meastype: int | None = None,
) -> dict:
    params: dict[str, Any] = {'action': 'getmeas'}
    if startdate is not None:
        params['startdate'] = startdate
    if enddate is not None:
        params['enddate'] = enddate
    if lastupdate is not None:
        params['lastupdate'] = lastupdate
    if meastype is not None:
        params['meastype'] = meastype
    url = f'{api_base}/measure'
    return _authorized_get(url, access_token, params, timeout)


def get_activity(
    access_token: str,
    api_base: str,
    timeout: float,
    startdateymd: str | date | None = None,
    enddateymd: str | date | None = None,
    lastupdate: int | None = None,
) -> dict:
    params: dict[str, Any] = {'action': 'getactivity'}
    if lastupdate is not None:
        params['lastupdate'] = lastupdate
    else:
        if not startdateymd or not enddateymd:
            raise ValueError("Provide startdateymd and enddateymd or lastupdate.")
        params['startdateymd'] = startdateymd.isoformat() if isinstance(startdateymd, date) else startdateymd
        params['enddateymd'] = enddateymd.isoformat() if isinstance(enddateymd, date) else enddateymd
    url = f'{api_base}/v2/measure'
    return _authorized_get(url, access_token, params, timeout)



def fetch_measurements(
    startdate: int | None = None,
    enddate: int | None = None,
    lastupdate: int | None = None,
    meastype: int | None = None,
    refresh_token: bool = False,
) -> dict:
    config = load_config()
    api = config['api']
    oauth = config['oauth']
    timeout = float(oauth.get('http_timeout', 10.0))

    access_token = get_access_token(refresh=refresh_token)
    data = get_measurements(
        access_token=access_token,
        api_base=api['wbsapi_url'],
        timeout=timeout,
        startdate=startdate,
        enddate=enddate,
        lastupdate=lastupdate,
        meastype=meastype,
    )

    return data


def fetch_activity(
    startdateymd: str | date | None = None,
    enddateymd: str | date | None = None,
    lastupdate: int | None = None,
    refresh_token: bool = False,
) -> dict:
    config = load_config()
    api = config['api']
    oauth = config['oauth']
    timeout = float(oauth.get('http_timeout', 10.0))

    access_token = get_access_token(refresh=refresh_token)
    data = get_activity(
        access_token=access_token,
        api_base=api['wbsapi_url'],
        timeout=timeout,
        startdateymd=startdateymd,
        enddateymd=enddateymd,
        lastupdate=lastupdate,
    )

    return data


def _demo() -> None:
    """Simple demo fetch when running this module directly."""
    today = date.today()
    start = today - timedelta(days=7)
    start_ts = int(datetime.combine(start, datetime.min.time()).timestamp())
    end_ts = int(datetime.combine(today, datetime.min.time()).timestamp())

    measures = fetch_measurements(
        startdate=start_ts,
        enddate=end_ts,
        refresh_token=True,
    )
    print("Measurements demo (last 7 days):")
    print(json.dumps(measures, indent=2))


if __name__ == '__main__':
    _demo()
