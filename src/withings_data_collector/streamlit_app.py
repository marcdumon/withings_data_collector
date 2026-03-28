"""Streamlit UI for Withings data collection."""

from datetime import date, datetime, timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from withings_data_collector.get_auth_code import ConfigError
from withings_data_collector.get_data import (
    fetch_activity,
    fetch_measurements,
    get_access_token,
)
from withings_data_collector.measures import (
    MEASURE_TYPES,
    format_measure_for_display,
    _compute_actual_value,
)

st.set_page_config(
    page_title="Withings Data Collector",
    page_icon="📊",
    layout="wide",
)


# Measurement categories for dashboard organization
MEASUREMENT_CATEGORIES = {
    'Body Composition': [1, 4, 5, 6, 8, 76, 77, 88, 168, 169, 170, 173, 174, 175],
    'Cardiovascular & Blood Pressure': [9, 10, 11, 130, 155],
    'Temperature & Oxygen': [12, 54, 71, 73],
    'Advanced Metrics': [123, 167, 196, 226, 227, 229],
}


def _default_dates(days: int = 7) -> tuple[date, date]:
    today = date.today()
    return today - timedelta(days=days), today


def _date_range_to_timestamps(start: date | None, end: date | None) -> tuple[int, int]:
    if not start:
        start = date.today() - timedelta(days=7)
    if not end:
        end = date.today()

    start_ts = int(datetime.combine(start, datetime.min.time()).timestamp())
    end_ts = int(datetime.combine(end, datetime.min.time()).timestamp())
    return start_ts, end_ts


def _render_status(message: str, success: bool = True) -> None:
    if success:
        st.success(message)
    else:
        st.error(message)


def _process_measurements_to_dataframe(api_response: dict) -> pd.DataFrame:
    """Convert raw API response to a pandas DataFrame for charting.
    
    Returns a DataFrame with columns: datetime, measurement_type, value, unit, mtype_id
    """
    rows = []
    measuregrps = api_response.get('body', {}).get('measuregrps', [])
    
    for grp in measuregrps:
        ts = int(grp.get('date', 0))
        dt = datetime.fromtimestamp(ts)
        
        for m in grp.get('measures', []):
            try:
                mtype = int(m.get('type'))
            except Exception:
                continue
            
            meta = MEASURE_TYPES.get(mtype, {})
            actual_value = _compute_actual_value(m)
            
            rows.append({
                'datetime': dt,
                'measurement_type': meta.get('name', f'Type {mtype}'),
                'value': actual_value,
                'unit': meta.get('unit', ''),
                'mtype_id': mtype,
            })
    
    if not rows:
        return pd.DataFrame(columns=['datetime', 'measurement_type', 'value', 'unit', 'mtype_id'])
    
    return pd.DataFrame(rows)


def _plot_measurement_chart(df: pd.DataFrame, measurement_type: int) -> None:
    """Create and display a line chart for a specific measurement type."""
    mtype_data = df[df['mtype_id'] == measurement_type].copy()
    
    if mtype_data.empty:
        return
    
    mtype_data = mtype_data.sort_values('datetime')
    
    meta = MEASURE_TYPES.get(measurement_type, {})
    name = meta.get('name', f'Type {measurement_type}')
    unit = meta.get('unit', '')
    
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(mtype_data['datetime'], mtype_data['value'], marker='o', linewidth=2, label=name)
    ax.set_xlabel('Date')
    ax.set_ylabel(f'Value ({unit})' if unit else 'Value')
    ax.set_title(name)
    ax.grid(True, alpha=0.3)
    ax.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    st.pyplot(fig)
    plt.close(fig)


def dashboard_ui() -> None:
    """Render the Dashboard tab with charts for each measurement grouped by category."""
    st.subheader("Measurement Dashboard")
    
    # Date range selection in sidebar
    with st.sidebar:
        st.markdown("---")
        st.subheader("Dashboard Options")
        date_input_result = st.date_input(
            "Dashboard date range",
            value=_default_dates(days=30),  # Default 30 days
            help="Pull measurements between these dates for dashboard display.",
            key="dashboard_date_range",
        )
        
        # Handle the case where only one date is selected
        if len(date_input_result) == 1:
            st.warning("Please select both start and end dates for the date range.")
            start_date = end_date = None
        elif len(date_input_result) == 2:
            start_date, end_date = date_input_result
        else:
            st.error("Invalid date range selection.")
            start_date = end_date = None
    
    # Fetch and display dashboard
    if start_date and end_date:
        try:
            start_ts, end_ts = _date_range_to_timestamps(start_date, end_date)
            data = fetch_measurements(
                startdate=start_ts,
                enddate=end_ts,
                meastype=None,
                refresh_token=True,
            )
            
            df = _process_measurements_to_dataframe(data)
            
            if df.empty:
                st.info("No measurements found for the selected date range.")
                return
            
            # Display charts grouped by category
            for category, mtype_ids in MEASUREMENT_CATEGORIES.items():
                # Filter for measurements that exist in this category
                category_mtypes = [mid for mid in mtype_ids if mid in df['mtype_id'].unique()]
                
                if not category_mtypes:
                    continue
                
                with st.expander(f"📈 {category}", expanded=True):
                    for mtype_id in category_mtypes:
                        _plot_measurement_chart(df, mtype_id)
        
        except ConfigError as exc:
            _render_status(f"Config error: {exc}", success=False)
        except Exception as exc:  # pragma: no cover - UI display
            _render_status(f"Dashboard fetch failed: {exc}", success=False)


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
        date_input_result = st.date_input(
            "Date range",
            value=_default_dates(),
            help="Pull measurements between these dates.",
        )

        # Handle the case where only one date is selected
        if len(date_input_result) == 1:
            st.warning("Please select both start and end dates for the date range.")
            start_date = end_date = None
        elif len(date_input_result) == 2:
            start_date, end_date = date_input_result
        else:
            st.error("Invalid date range selection.")
            start_date = end_date = None
    with col2:
        meastype = st.number_input(
            "Measurement type (optional)",
            value=None,
            placeholder="Leave blank for all types",
        )

    if st.button(
        "Fetch measurements",
        type="primary",
        disabled=(start_date is None or end_date is None),
    ):
        try:
            start_ts, end_ts = _date_range_to_timestamps(start_date, end_date)
            data = fetch_measurements(
                startdate=start_ts,
                enddate=end_ts,
                meastype=int(meastype) if meastype is not None else None,
                refresh_token=True,
            )
            st.json(data)
            # Render a compact, SI-only formatted table of measurements using our
            # canonical mapping. We do not change stored payloads here; this is
            # display-only formatting.
            measuregrps = data.get('body', {}).get('measuregrps', [])
            if measuregrps:
                st.markdown('---')
                st.write("Formatted measurements:")
                rows = []
                for grp in measuregrps:
                    ts = int(grp.get('date', 0))
                    dt = datetime.fromtimestamp(ts)
                    for m in grp.get('measures', []):
                        try:
                            mtype = int(m.get('type'))
                        except Exception:
                            mtype = -1
                        name = MEASURE_TYPES.get(mtype, {}).get('name', f'Type {mtype}')
                        name = f"{mtype} - {name}"
                        formatted = format_measure_for_display(m)
                        rows.append(
                            {
                                'datetime': dt.isoformat(),
                                'measurement': name,
                                'value': formatted,
                            }
                        )
                if rows:
                    st.table(rows)
            _render_status("Measurements fetched.")
        except ConfigError as exc:
            _render_status(f"Config error: {exc}", success=False)
        except Exception as exc:  # pragma: no cover - UI display
            _render_status(f"Fetch failed: {exc}", success=False)


def fetch_activity_ui(project_root: str) -> None:
    st.subheader("Activity")

    date_input_result = st.date_input(
        "Date range",
        value=_default_dates(),
        help="Pull activity between these dates.",
        key="activity_date_range",  # Add unique key to avoid conflicts
    )

    # Handle the case where only one date is selected
    if len(date_input_result) == 1:
        st.warning("Please select both start and end dates for the date range.")
        start_date = end_date = None
    elif len(date_input_result) == 2:
        start_date, end_date = date_input_result
    else:
        st.error("Invalid date range selection.")
        start_date = end_date = None

    if st.button(
        "Fetch activity",
        type="primary",
        disabled=(start_date is None or end_date is None),
    ):
        try:
            data = fetch_activity(
                startdateymd=start_date,
                enddateymd=end_date,
                refresh_token=True,
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

    tab1, tab2, tab3 = st.tabs(["Dashboard", "Measurements", "Activity"])
    with tab1:
        dashboard_ui()
    with tab2:
        fetch_measurements_ui(project_root)
    with tab3:
        fetch_activity_ui(project_root)


if __name__ == "__main__":
    main()
