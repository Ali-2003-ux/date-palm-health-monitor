"""Date Palm Health Monitor — Streamlit dashboard.

Run from the project root:
    streamlit run frontend/app.py
or via the launcher:
    python run_dashboard.py

Requires the FastAPI backend (python run_api.py); its URL comes from
STREAMLIT_API_URL in .env (default http://localhost:8000).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import folium
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from streamlit_folium import st_folium

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# `streamlit run frontend/app.py` puts only frontend/ on sys.path; make the
# project root importable so `frontend.api_client` resolves in any launch style.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from frontend.api_client import APIError, PalmMonitorClient

# ----------------------------------------------------------------------
# Configuration & session bootstrap
# ----------------------------------------------------------------------

load_dotenv(PROJECT_ROOT / ".env")

API_BASE_URL = os.getenv("STREAMLIT_API_URL", "http://localhost:8000")

STATUS_COLORS = {
    "healthy": ("#2e7d32", "🟢 Healthy"),
    "infected": ("#ef6c00", "🟠 Infected"),
    "critical": ("#c62828", "🔴 Critical"),
    None: ("#616161", "⚪ No inspections yet"),
}
SEVERITY_BADGES = {"low": "🟡 Low", "medium": "🟠 Medium", "high": "🔴 High"}

st.set_page_config(
    page_title="Date Palm Health Monitor",
    page_icon="🌴",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .palm-card { border:1px solid #e0e0e0; border-radius:12px; padding:16px;
                 margin-bottom:10px; background:#fafafa; }
    .palm-kpi  { text-align:center; padding:12px; border-radius:12px;
                 background:#f5f5f5; }
    .palm-kpi h2 { margin:0; font-size:2rem; }
    .palm-kpi p { margin:0; color:#555; }
    section[data-testid="stSidebar"] { background:#0e3b2e; }
    section[data-testid="stSidebar"] * { color:#f1f8f5 !important; }
    div[data-testid="stMetric"] { background:#f5f5f5; border-radius:10px;
                                  padding:10px; }
    </style>
    """,
    unsafe_allow_html=True,
)


def get_client() -> PalmMonitorClient:
    """One authenticated client per browser session."""
    if "client" not in st.session_state or st.session_state.get("client_token") != st.session_state.get("token"):
        st.session_state.client = PalmMonitorClient(
            API_BASE_URL, token=st.session_state.get("token")
        )
        st.session_state.client_token = st.session_state.get("token")
    return st.session_state.client


def is_logged_in() -> bool:
    return bool(st.session_state.get("token"))


# ----------------------------------------------------------------------
# Authentication view
# ----------------------------------------------------------------------


def render_login() -> None:
    st.markdown(
        "<h1 style='text-align:center'>🌴 Date Palm Health Monitor</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='text-align:center; color:#555'>AI-powered disease detection "
        "for Red Palm Weevil, fungal infections and nutrient disorders.</p>",
        unsafe_allow_html=True,
    )
    login_tab, register_tab = st.tabs(["Sign in", "Create a farmer account"])

    with login_tab:
        with st.form("login"):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_pw")
            submitted = st.form_submit_button("Sign in", use_container_width=True)
        if submitted:
            try:
                client = PalmMonitorClient(API_BASE_URL)
                token = client.login(email.strip(), password)
                st.session_state.token = token
                st.session_state.client = client
                st.session_state.client_token = token
                st.rerun()
            except APIError as exc:
                st.error(exc.detail)

    with register_tab:
        with st.form("register"):
            full_name = st.text_input("Full name", key="reg_name")
            email = st.text_input("Email", key="reg_email")
            password = st.text_input(
                "Password (min 8 chars)", type="password", key="reg_pw"
            )
            submitted = st.form_submit_button("Create account", use_container_width=True)
        if submitted:
            client = PalmMonitorClient(API_BASE_URL)
            try:
                client.register(email.strip(), password, full_name.strip())
                token = client.login(email.strip(), password)
                st.session_state.token = token
                st.session_state.client = client
                st.session_state.client_token = token
                st.success("Account created — welcome!")
                st.rerun()
            except APIError as exc:
                st.error(exc.detail)

    st.divider()
    st.caption(f"Backend: {API_BASE_URL} — start it with `python run_api.py`")


# ----------------------------------------------------------------------
# Dashboard view
# ----------------------------------------------------------------------


def render_dashboard(client: PalmMonitorClient) -> None:
    st.subheader("Farm health overview")
    try:
        palms = client.list_palms()
        inspections = client.recent_inspections(limit=100)
    except APIError as exc:
        st.error(f"Could not load farm data: {exc.detail}")
        return

    if not palms:
        st.info(
            "No palm trees registered yet. Go to **Palm Trees → Register a tree** "
            "to add your first tree with GPS coordinates."
        )
        return

    counts = {"healthy": 0, "infected": 0, "critical": 0, None: 0}
    for palm in palms:
        counts[palm.get("latest_status")] = counts.get(palm.get("latest_status"), 0) + 1

    cols = st.columns(4)
    kpis = [
        ("Total palms", len(palms), "#0e3b2e"),
        ("Healthy", counts["healthy"], STATUS_COLORS["healthy"][0]),
        ("Infected", counts["infected"], STATUS_COLORS["infected"][0]),
        ("Critical", counts["critical"], STATUS_COLORS["critical"][0]),
    ]
    for col, (label, value, color) in zip(cols, kpis, strict=True):
        col.markdown(
            f"<div class='palm-kpi'><h2 style='color:{color}'>{value}</h2>"
            f"<p>{label}</p></div>",
            unsafe_allow_html=True,
        )
    if counts[None]:
        st.caption(
            f"{counts[None]} palm(s) have no inspections yet — they are not "
            "classified. Run an inspection to get a verdict."
        )

    chart_col, map_col = st.columns([1, 2])

    with chart_col:
        st.markdown("**Health distribution**")
        labels, values, colors = [], [], []
        for status in ("healthy", "infected", "critical"):
            if counts[status]:
                labels.append(STATUS_COLORS[status][1].split()[1])
                values.append(counts[status])
                colors.append(STATUS_COLORS[status][0])
        if not labels:
            st.caption("No verdicts yet — run your first inspection.")
        else:
            fig = go.Figure(
                go.Pie(
                    labels=labels,
                    values=values,
                    hole=0.62,
                    marker={"colors": colors},
                    textinfo="label+value",
                )
            )
            fig.update_layout(
                showlegend=False, height=260, margin={"l": 10, "r": 10, "t": 10, "b": 10}
            )
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("**Inspections per day**")
        if inspections:
            per_day: dict[str, dict[str, int]] = {}
            for log in inspections:
                day = log["inspected_at"][:10]
                bucket = per_day.setdefault(
                    day, {"healthy": 0, "infected": 0, "critical": 0}
                )
                bucket[log["status"]] = bucket.get(log["status"], 0) + 1
            days = sorted(per_day)
            bar = go.Figure()
            for status, color in (
                ("healthy", STATUS_COLORS["healthy"][0]),
                ("infected", STATUS_COLORS["infected"][0]),
                ("critical", STATUS_COLORS["critical"][0]),
            ):
                bar.add_trace(
                    go.Bar(
                        x=days,
                        y=[per_day[d].get(status, 0) for d in days],
                        name=status.title(),
                        marker_color=color,
                    )
                )
            bar.update_layout(barmode="stack", height=240, margin={"l": 10, "r": 10, "t": 10, "b": 10})
            st.plotly_chart(bar, use_container_width=True)
        else:
            st.caption("No inspections recorded yet.")

    with map_col:
        st.markdown("**Palm map — colour = latest verdict**")
        render_map(palms)


def render_map(palms: list[dict]) -> None:
    located = [p for p in palms if p.get("latitude") is not None]
    if not located:
        st.caption("No GPS data available.")
        return

    center_lat = sum(float(p["latitude"]) for p in located) / len(located)
    center_lng = sum(float(p["longitude"]) for p in located) / len(located)
    palm_map = folium.Map(location=[center_lat, center_lng], zoom_start=14)

    icon_colors = {"healthy": "green", "infected": "orange", "critical": "darkred"}
    for palm in located:
        status = palm.get("latest_status")
        color = icon_colors.get(status, "gray")
        disease = palm.get("latest_disease") or "no disease detected"
        folium.Marker(
            location=[float(palm["latitude"]), float(palm["longitude"])],
            tooltip=f"{palm['tree_code']} — {disease}",
            popup=folium.Popup(
                f"<b>{palm['tree_code']}</b><br>"
                f"Status: {status or 'not inspected'}<br>"
                f"Last finding: {disease}<br>"
                f"Inspections: {palm.get('total_inspections', 0)}",
                max_width=220,
            ),
            icon=folium.Icon(color=color, icon="leaf", prefix="fa"),
        ).add_to(palm_map)

    st_folium(palm_map, height=420, use_container_width=True, returned_objects=[])


# ----------------------------------------------------------------------
# New inspection view
# ----------------------------------------------------------------------


def render_inspect(client: PalmMonitorClient, palms: list[dict]) -> None:
    st.subheader("New AI inspection")
    if not palms:
        st.info("Register a palm tree first (Palm Trees page).")
        return

    options = {
        f"{p['tree_code']} — {p.get('variety') or 'unknown variety'}": p
        for p in palms
    }
    selected_label = st.selectbox("Palm tree", list(options))
    palm = options[selected_label]

    upload_tab, camera_tab = st.tabs(["📤 Upload photo", "📸 Live camera"])
    image_bytes: bytes | None = None
    filename = "upload.jpg"

    with upload_tab:
        uploaded = st.file_uploader(
            "Trunk / frond / crown photo (JPG, PNG)",
            type=["jpg", "jpeg", "png", "webp"],
        )
        if uploaded is not None:
            image_bytes = uploaded.getvalue()
            filename = uploaded.name

    with camera_tab:
        captured = st.camera_input("Point at the trunk or affected frond")
        if captured is not None:
            image_bytes = captured.getvalue()
            filename = "camera.jpg"

    if image_bytes is not None:
        st.image(image_bytes, width=360, caption=filename)

    notes = st.text_area("Field notes (optional)", height=80)

    if st.button(
        "🔍 Run diagnosis",
        disabled=image_bytes is None,
        use_container_width=True,
        type="primary",
    ):
        with st.spinner("Analysing the image with the vision model…"):
            try:
                result = client.inspect(
                    palm["id"], image_bytes, filename, notes=notes or None
                )
            except APIError as exc:
                st.error(f"Inspection failed: {exc.detail}")
                return
        st.session_state.last_report = result
        st.rerun()

    report = st.session_state.get("last_report")
    if report:
        st.divider()
        render_diagnosis_report(report)


def render_diagnosis_report(report: dict) -> None:
    diagnosis = report["diagnosis"]
    inspection = report["inspection"]

    status = diagnosis["status"]
    color, label = STATUS_COLORS[status]
    confidence = diagnosis["confidence"]

    st.markdown(
        f"<div class='palm-card' style='border-left:6px solid {color}'>"
        f"<h3>{label} — {diagnosis['detected_disease'] or 'No disease detected'}</h3>"
        f"<p>Confidence <b>{confidence * 100:.0f}%</b> · severity "
        f"<b>{SEVERITY_BADGES.get(diagnosis['severity'], '—')}</b> · "
        f"model {diagnosis['model']} ({diagnosis['latency_ms']} ms)</p></div>",
        unsafe_allow_html=True,
    )
    st.progress(min(confidence, 1.0), text=f"Confidence {confidence * 100:.0f}%")

    left, right = st.columns([1, 2])
    with left:
        try:
            st.image(
                client_image_bytes(inspection["image_url"]), width=280,
                caption=f"Inspected {inspection['inspected_at'][:16].replace('T', ' ')}",
            )
        except APIError:
            st.caption("(stored photo unavailable)")
    with right:
        if diagnosis["symptoms"]:
            st.markdown("**Observed symptoms**")
            for symptom in diagnosis["symptoms"]:
                st.markdown(f"- {symptom}")
        if diagnosis["treatment_steps"]:
            st.markdown("**Recommended treatment**")
            for number, step in enumerate(diagnosis["treatment_steps"], start=1):
                st.markdown(f"{number}. {step}")
        if diagnosis.get("assessment"):
            st.info(diagnosis["assessment"])
        for warning in diagnosis.get("warnings", []):
            st.warning(warning)


def client_image_bytes(image_url: str) -> bytes:
    client: PalmMonitorClient = st.session_state.client
    return client.get_image_bytes(image_url)


# ----------------------------------------------------------------------
# Palm trees view
# ----------------------------------------------------------------------


def render_trees(client: PalmMonitorClient) -> None:
    st.subheader("Palm trees")

    with st.expander("➕ Register a new tree"):
        with st.form("new_palm"):
            code = st.text_input("Tree code", placeholder="PALM-0042")
            col1, col2 = st.columns(2)
            latitude = col1.number_input("Latitude", -90.0, 90.0, 24.7136, step=0.0001)
            longitude = col2.number_input("Longitude", -180.0, 180.0, 46.6753, step=0.0001)
            col3, col4 = st.columns(2)
            field = col3.text_input("Field / plot name")
            variety = col4.text_input("Variety", placeholder="Barhi, Khalas, …")
            submitted = st.form_submit_button("Register tree", use_container_width=True)
        if submitted:
            if not code.strip():
                st.error("Tree code is required.")
            else:
                try:
                    client.create_palm(
                        code.strip(), latitude, longitude,
                        field_name=field or None, variety=variety or None,
                    )
                    st.success(f"Tree {code.strip()} registered.")
                    st.rerun()
                except APIError as exc:
                    st.error(exc.detail)

    palms = client.list_palms()
    if not palms:
        st.info("No trees yet — register your first one above.")
        return

    options = {p["tree_code"]: p for p in palms}
    selected = st.selectbox(
        "Tree history", list(options), format_func=lambda c: f"{c} ({options[c].get('field_name') or '—'})"
    )
    palm = options[selected]

    history = client.palm_history(palm["id"])
    color, label = STATUS_COLORS.get(palm.get("latest_status"), STATUS_COLORS[None])
    st.markdown(
        f"<div class='palm-card' style='border-left:6px solid {color}'>"
        f"<b>{palm['tree_code']}</b> · {label} · {palm.get('variety') or 'unknown variety'} · "
        f"{len(history)} inspection(s) · planted "
        f"{palm.get('planted_on') or '—'}</div>",
        unsafe_allow_html=True,
    )

    if not history:
        st.caption("No inspections yet — run one from the New Inspection page.")
        return

    for log in history:
        log_color, log_label = STATUS_COLORS[log["status"]]
        date = log["inspected_at"][:16].replace("T", " ")
        with st.container(border=True):
            header = st.columns([2, 2, 2])
            header[0].markdown(
                f"<span style='color:{log_color}; font-weight:bold'>{log_label}</span>",
                unsafe_allow_html=True,
            )
            header[1].markdown(f"**{log['detected_disease'] or 'No disease'}**")
            header[2].caption(
                f"{date} · confidence {log['confidence'] * 100:.0f}%"
            )
            details = log.get("detection_details") or {}
            col_img, col_txt = st.columns([1, 3])
            try:
                col_img.image(client_image_bytes(log["image_url"]), width=140)
            except APIError:
                col_img.caption("photo missing")
            if log.get("treatment_recommendation"):
                col_txt.markdown("**Treatment**")
                for step in log["treatment_recommendation"].split("\n"):
                    if step.strip():
                        col_txt.markdown(f"- {step}")
            symptoms = (details or {}).get("symptoms") or []
            if symptoms:
                col_txt.caption("Symptoms: " + ", ".join(symptoms))
            for warning in (details or {}).get("warnings") or []:
                col_txt.warning(warning)


# ----------------------------------------------------------------------
# Alerts view
# ----------------------------------------------------------------------


def render_alerts(client: PalmMonitorClient) -> None:
    st.subheader("Alerts — trees needing attention")
    try:
        inspections = client.recent_inspections(limit=100)
    except APIError as exc:
        st.error(exc.detail)
        return

    flagged = [
        log for log in inspections if log["status"] in ("infected", "critical")
    ]
    flagged.sort(key=lambda log: (log["status"] != "critical", log["inspected_at"]), reverse=True)

    if not flagged:
        st.success("No infections detected in recent inspections. 🌴")
        return

    for log in flagged:
        color, _ = STATUS_COLORS[log["status"]]
        date = log["inspected_at"][:16].replace("T", " ")
        st.markdown(
            f"<div class='palm-card' style='border-left:6px solid {color}'>"
            f"<b>{log['detected_disease']}</b> — {log['status'].upper()} · "
            f"confidence {log['confidence'] * 100:.0f}% · {date}"
            f"</div>",
            unsafe_allow_html=True,
        )


# ----------------------------------------------------------------------
# Layout
# ----------------------------------------------------------------------


def main() -> None:
    if not is_logged_in():
        render_login()
        return

    client = get_client()
    try:
        user = client.me()
    except APIError as exc:
        st.error(f"Session expired or backend unreachable ({exc.detail}). Sign in again.")
        st.session_state.pop("token", None)
        st.rerun()
        return

    with st.sidebar:
        st.markdown("## 🌴 Palm Monitor")
        st.caption(f"{user['full_name']} · {user['role'].title()}")
        st.divider()
        page = st.radio(
            "Navigation",
            ["📊 Dashboard", "🔍 New inspection", "🌳 Palm trees", "🚨 Alerts"],
            label_visibility="collapsed",
        )
        st.divider()
        if st.button("Sign out", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    pages = {
        "📊 Dashboard": render_dashboard,
        "🚨 Alerts": render_alerts,
    }
    if page in pages:
        pages[page](client)
    elif page == "🔍 New inspection":
        try:
            palms = client.list_palms()
        except APIError as exc:
            st.error(exc.detail)
            palms = []
        render_inspect(client, palms)
    elif page == "🌳 Palm trees":
        render_trees(client)


if __name__ == "__main__":
    main()
