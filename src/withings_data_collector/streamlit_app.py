"""Streamlit UI for Withings data collection."""

from datetime import date, datetime, timedelta
from pathlib import Path

import streamlit as st

from withings_data_collector.get_auth_code import ConfigError
from withings_data_collector.get_data import (
    fetch_and_save_activity,
    fetch_and_save_measurements,
    get_access_token,
)

st.set_page_config(
    page_title="Withings Data Collector",
    page_icon="📊",
    layout="wide",
)


def _default_dates(days: int = 7) -> tuple[date, date]:
    today = date.today()
    return today - timedelta(days=days), today


def _date_range_to_timestamps(start: date, end: date) -> tuple[int, int]:
    start_ts = int(datetime.combine(start, datetime.min.time()).timestamp())
    end_ts = int(datetime.combine(end, datetime.min.time()).timestamp())
    return start_ts, end_ts


def _render_status(message: str, success: bool = True) -> None:
    if success:
        st.success(message)
    else:
        st.error(message)


def sidebar_actions(project_root: str) -> None:
    st.sidebar.header("Token")
    if st.sidebar.button("Refresh access token"):
        try:
            get_access_token(refresh=True)
            _render_status("Access token refreshed.")
        except Exception as exc:  # pragma: no cover - UI display
            _render_status(f"Token refresh failed: {exc}", success=False)

    st.sidebar.markdown("---")
    st.sidebar.caption(project_root)
    st.sidebar.write("Set fetch options below and click Fetch.")


def fetch_measurements_ui(project_root: str) -> None:
    st.subheader("Measurements")

    col1, col2 = st.columns(2)
    with col1:
        start_date, end_date = st.date_input(
            "Date range",
            value=_default_dates(),
            help="Pull measurements between these dates.",
        )
    with col2:
        meastype = st.number_input(
            "Measurement type (optional)",
            value=None,
            placeholder="Leave blank for all types",
        )

    save_json = st.checkbox("Save to JSON file", value=False)
    json_path = st.text_input(
        "JSON output path",
        value=f"{project_root}/data/measurements.json",
        disabled=not save_json,
    )

    save_sqlite = st.checkbox("Save to SQLite db", value=False)
    sqlite_path = st.text_input(
        "SQLite db path",
        value=f"{project_root}/data/withings.db",
        disabled=not save_sqlite,
    )

    if st.button("Fetch measurements", type="primary"):
        try:
            start_ts, end_ts = _date_range_to_timestamps(start_date, end_date)
            data = fetch_and_save_measurements(
                startdate=start_ts,
                enddate=end_ts,
                meastype=int(meastype) if meastype is not None else None,
                refresh_token=True,
                save_path=json_path if save_json else None,
                sqlite_db=sqlite_path if save_sqlite else None,
            )
            st.json(data)
            _render_status("Measurements fetched.")
        except ConfigError as exc:
            _render_status(f"Config error: {exc}", success=False)
        except Exception as exc:  # pragma: no cover - UI display
            _render_status(f"Fetch failed: {exc}", success=False)


def fetch_activity_ui(project_root: str) -> None:
    st.subheader("Activity")

    start_date, end_date = st.date_input(
        "Date range",
        value=_default_dates(),
        help="Pull activity between these dates.",
    )

    save_json = st.checkbox("Save to JSON file", value=False, key="activity_json")
    json_path = st.text_input(
        "JSON output path",
        value=f"{project_root}/data/activity.json",
        disabled=not save_json,
        key="activity_json_path",
    )

    save_sqlite = st.checkbox("Save to SQLite db", value=False, key="activity_sqlite")
    sqlite_path = st.text_input(
        "SQLite db path",
        value=f"{project_root}/data/withings.db",
        disabled=not save_sqlite,
        key="activity_sqlite_path",
    )

    if st.button("Fetch activity", type="primary"):
        try:
            data = fetch_and_save_activity(
                startdateymd=start_date,
                enddateymd=end_date,
                refresh_token=True,
                save_path=json_path if save_json else None,
                sqlite_db=sqlite_path if save_sqlite else None,
            )
            st.json(data)
            _render_status("Activity fetched.")
        except ConfigError as exc:
            _render_status(f"Config error: {exc}", success=False)
        except Exception as exc:  # pragma: no cover - UI display
            _render_status(f"Fetch failed: {exc}", success=False)


def main() -> None:
    project_root = str(Path(__file__).resolve().parents[2])

    st.title("Withings Data Collector")
    st.caption("Fetch and store your Withings data with a friendly UI.")

    sidebar_actions(project_root)

    tab1, tab2 = st.tabs(["Measurements", "Activity"])
    with tab1:
        fetch_measurements_ui(project_root)
    with tab2:
        fetch_activity_ui(project_root)


if __name__ == "__main__":
    main()

