"""Streamlit UI for Withings data collection."""

from datetime import date, datetime, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from withings_data_collector.get_auth_code import ConfigError
from withings_data_collector.get_data import (
    fetch_activity,
    fetch_measurements,
    get_access_token,
)
from withings_data_collector.measures import (
    MEASURE_TYPES,
    _compute_actual_value,
    format_measure_for_display,
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


def _parse_date_input(date_input_result) -> tuple[date | None, date | None]:
    if len(date_input_result) == 1:
        st.warning("Please select both start and end dates.")
        return None, None
    elif len(date_input_result) == 2:
        return date_input_result
    else:
        st.error("Invalid date range selection.")
        return None, None


def _process_measurements_to_dataframe(api_response: dict) -> pd.DataFrame:
    """Convert raw API response to a pandas DataFrame for charting."""
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
    """Create and display an interactive Plotly line chart for a specific measurement type."""
    mtype_data = df[df['mtype_id'] == measurement_type].copy()

    if mtype_data.empty:
        return

    mtype_data = mtype_data.sort_values('datetime')

    meta = MEASURE_TYPES.get(measurement_type, {})
    name = meta.get('name', f'Type {measurement_type}')
    unit = meta.get('unit', '')
    precision = meta.get('precision', 2)

    fig = px.line(
        mtype_data,
        x='datetime',
        y='value',
        markers=True,
        title=name,
        labels={'datetime': '', 'value': unit or 'Value'},
    )
    fig.update_traces(
        hovertemplate=f'%{{x|%b %d, %Y}}<br>{name}: %{{y:.{precision}f}} {unit}<extra></extra>',
        line=dict(width=2),
        marker=dict(size=6),
    )
    fig.update_layout(
        height=260,
        margin=dict(l=0, r=0, t=36, b=0),
        title_font_size=14,
        hovermode='x unified',
        showlegend=False,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        yaxis=dict(gridcolor='rgba(128,128,128,0.15)'),
        xaxis=dict(gridcolor='rgba(128,128,128,0.15)'),
    )

    st.plotly_chart(fig, use_container_width=True)


def _render_metric_cards(df: pd.DataFrame, mtype_ids: list[int]) -> None:
    """Render a row of st.metric cards showing the latest value for each measurement type."""
    present = [mid for mid in mtype_ids if mid in df['mtype_id'].values]
    if not present:
        return

    cols = st.columns(len(present))
    for col, mtype_id in zip(cols, present):
        mtype_data = df[df['mtype_id'] == mtype_id].sort_values('datetime')
        latest = mtype_data.iloc[-1]
        meta = MEASURE_TYPES.get(mtype_id, {})
        unit = meta.get('unit', '')
        precision = meta.get('precision', 2)
        label = meta.get('name', f'Type {mtype_id}')
        value_str = f"{latest['value']:.{precision}f} {unit}".strip()
        with col:
            st.metric(label=label, value=value_str)


def dashboard_ui() -> None:
    """Render the Dashboard tab with metric cards and charts grouped by category."""
    st.subheader("Measurement Dashboard")

    with st.sidebar:
        st.markdown("---")
        st.subheader("Dashboard Options")
        date_input_result = st.date_input(
            "Date range",
            value=_default_dates(days=30),
            help="Pull measurements between these dates.",
            key="dashboard_date_range",
        )
        start_date, end_date = _parse_date_input(date_input_result)

    if not (start_date and end_date):
        return

    try:
        with st.spinner("Fetching measurements…"):
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

        for category, mtype_ids in MEASUREMENT_CATEGORIES.items():
            present = [mid for mid in mtype_ids if mid in df['mtype_id'].values]
            if not present:
                continue

            with st.expander(f"📈 {category}", expanded=True):
                _render_metric_cards(df, present)
                st.divider()
                # Two-column chart grid
                pairs = [present[i:i + 2] for i in range(0, len(present), 2)]
                for pair in pairs:
                    cols = st.columns(len(pair))
                    for col, mtype_id in zip(cols, pair):
                        with col:
                            _plot_measurement_chart(df, mtype_id)

    except ConfigError as exc:
        _render_status(f"Config error: {exc}", success=False)
    except Exception as exc:  # pragma: no cover - UI display
        _render_status(f"Dashboard fetch failed: {exc}", success=False)


def sidebar_actions() -> None:
    st.sidebar.header("Token")
    if st.sidebar.button("Refresh access token"):
        try:
            get_access_token(refresh=True)
            _render_status("Access token refreshed.")
        except Exception as exc:  # pragma: no cover - UI display
            _render_status(f"Token refresh failed: {exc}", success=False)


def fetch_measurements_ui() -> None:
    st.subheader("Measurements")

    col1, col2 = st.columns(2)
    with col1:
        date_input_result = st.date_input(
            "Date range",
            value=_default_dates(),
            help="Pull measurements between these dates.",
        )
        start_date, end_date = _parse_date_input(date_input_result)
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
            with st.spinner("Fetching measurements…"):
                start_ts, end_ts = _date_range_to_timestamps(start_date, end_date)
                data = fetch_measurements(
                    startdate=start_ts,
                    enddate=end_ts,
                    meastype=int(meastype) if meastype is not None else None,
                    refresh_token=True,
                )

            measuregrps = data.get('body', {}).get('measuregrps', [])
            if measuregrps:
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
                        rows.append({
                            'Datetime': dt,
                            'Measurement': f"{mtype} — {name}",
                            'Value': format_measure_for_display(m),
                        })
                if rows:
                    table_df = pd.DataFrame(rows)
                    table_df['Datetime'] = pd.to_datetime(table_df['Datetime'])
                    st.dataframe(table_df, use_container_width=True, hide_index=True)

            with st.expander("Raw JSON response"):
                st.json(data)

            _render_status("Measurements fetched.")
        except ConfigError as exc:
            _render_status(f"Config error: {exc}", success=False)
        except Exception as exc:  # pragma: no cover - UI display
            _render_status(f"Fetch failed: {exc}", success=False)


def fetch_activity_ui() -> None:
    st.subheader("Activity")

    date_input_result = st.date_input(
        "Date range",
        value=_default_dates(),
        help="Pull activity between these dates.",
        key="activity_date_range",
    )
    start_date, end_date = _parse_date_input(date_input_result)

    if st.button(
        "Fetch activity",
        type="primary",
        disabled=(start_date is None or end_date is None),
    ):
        try:
            with st.spinner("Fetching activity…"):
                data = fetch_activity(
                    startdateymd=start_date,
                    enddateymd=end_date,
                    refresh_token=True,
                )

            activities = data.get('body', {}).get('activities', [])
            if activities:
                activity_df = pd.DataFrame(activities)
                st.dataframe(activity_df, use_container_width=True, hide_index=True)

            with st.expander("Raw JSON response"):
                st.json(data)

            _render_status("Activity fetched.")
        except ConfigError as exc:
            _render_status(f"Config error: {exc}", success=False)
        except Exception as exc:  # pragma: no cover - UI display
            _render_status(f"Fetch failed: {exc}", success=False)


def main() -> None:
    st.title("Withings Data Collector")
    st.caption("Fetch and visualise your Withings health data.")

    sidebar_actions()

    tab1, tab2, tab3 = st.tabs(["Dashboard", "Measurements", "Activity"])
    with tab1:
        dashboard_ui()
    with tab2:
        fetch_measurements_ui()
    with tab3:
        fetch_activity_ui()


if __name__ == "__main__":
    main()
