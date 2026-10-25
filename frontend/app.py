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
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from frontend.local_backend import LocalBackend

# ----------------------------------------------------------------------
# Configuration & session bootstrap
# ----------------------------------------------------------------------

load_dotenv(PROJECT_ROOT / ".env")

# ----------------------------------------------------------------------
# Cloud mode (Streamlit Community Cloud): single-process deployment.
# Secrets set in the Streamlit Cloud UI are surfaced via st.secrets and
# injected into the environment before backend settings load.
# ----------------------------------------------------------------------
CLOUD_MODE = os.getenv("PALM_CLOUD", "").lower() in ("1", "true", "yes")
if CLOUD_MODE:
    try:
        for key in ("DATABASE_URL", "GLM_API_KEY", "SECRET_KEY"):
            value = st.secrets.get(key)
            if value:
                os.environ.setdefault(key, str(value))
    except st.errors.StreamlitAPIException:  # secrets file absent locally
        pass

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


@st.cache_resource(show_spinner=False)
def _cloud_backend() -> LocalBackend:
    from frontend.local_backend import LocalBackend

    return LocalBackend(
        database_url=os.environ["DATABASE_URL"],
        glm_api_key=os.environ.get("GLM_API_KEY", ""),
    )


def get_client() -> PalmMonitorClient | LocalBackend:
    """One authenticated client per browser session (or the shared cloud backend)."""
    if CLOUD_MODE:
        return _cloud_backend()
    if "client" not in st.session_state or st.session_state.get("client_token") != st.session_state.get("token"):
        st.session_state.client = PalmMonitorClient(
            API_BASE_URL, token=st.session_state.get("token")
        )
        st.session_state.client_token = st.session_state.get("token")
    return st.session_state.client


def is_logged_in() -> bool:
    return bool(st.session_state.get("token"))


def ctx_user() -> dict | None:
    """Signed-in user dict (cloud mode) or None (HTTP mode passes tokens)."""
    return st.session_state.get("cloud_user")


# ----------------------------------------------------------------------
# Authentication view
# ----------------------------------------------------------------------


def _do_login(email: str, password: str) -> None:
    """Shared login for both modes; raises with a friendly message."""
    if CLOUD_MODE:

        backend = _cloud_backend()
        st.session_state.cloud_user = backend.login_user(email.strip(), password)
        st.session_state.token = "local-session"
        return

    client = PalmMonitorClient(API_BASE_URL)
    token = client.login(email.strip(), password)
    st.session_state.token = token
    st.session_state.client = client
    st.session_state.client_token = token


def _do_register(email: str, password: str, full_name: str) -> None:
    if CLOUD_MODE:
        backend = _cloud_backend()
        backend.register(email.strip(), password, full_name.strip())
        _do_login(email, password)
        return

    client = PalmMonitorClient(API_BASE_URL)
    client.register(email.strip(), password, full_name.strip())
    token = client.login(email.strip(), password)
    st.session_state.token = token
    st.session_state.client = client
    st.session_state.client_token = token


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
                _do_login(email, password)
                st.rerun()
            except (APIError, Exception) as exc:  # noqa: BLE001 - friendly msg
                st.error(getattr(exc, "detail", None) or str(exc))

    with register_tab, st.form("register"):
        full_name = st.text_input("Full name", key="reg_name")
        email = st.text_input("Email", key="reg_email")
        password = st.text_input(
            "Password (min 8 chars)", type="password", key="reg_pw"
        )

    with register_tab:
        with st.form("register"):
            full_name = st.text_input("Full name", key="reg_name")
            email = st.text_input("Email", key="reg_email")
            password = st.text_input(
                "Password (min 8 chars)", type="password", key="reg_pw"
            )
            submitted = st.form_submit_button("Create account", use_container_width=True)
        if submitted:
            try:
                _do_register(email, password, full_name)
                st.success("Account created — welcome!")
                st.rerun()
            except (APIError, Exception) as exc:  # noqa: BLE001 - friendly msg
                st.error(getattr(exc, "detail", None) or str(exc))

    st.divider()
    if CLOUD_MODE:
        st.caption("🌴 Single-process cloud deployment · Neon PostgreSQL · Gemini AI")
    else:
        st.caption(f"Backend: {API_BASE_URL} — start it with `python run_api.py`")


# ----------------------------------------------------------------------
# Dashboard view
# ----------------------------------------------------------------------


def render_dashboard(client: PalmMonitorClient) -> None:
    st.subheader("Farm health overview")
    try:
        user = ctx_user()
        palms = client.list_palms(user=user) if CLOUD_MODE else client.list_palms()
        inspections = (
            client.recent_inspections(limit=100, user=user) if CLOUD_MODE
            else client.recent_inspections(limit=100)
        )
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
    st.subheader("New AI inspection · فحص جديد")

    # Provider health banner — tell the user which engine they'll get
    # BEFORE they photograph anything.
    try:
        provider = client.vision_status()
        if provider.get("provider") == "local_vlm":
            st.info(
                "ℹ️ **Local screening mode** — the cloud AI engine is "
                "temporarily unavailable (quota or connectivity). Inspections "
                "will use the on-device screening model: verdicts are "
                "provisional, so photograph the affected area up close.\n\n"
                "*وضع الفحص المحلي: المحرك السحابي غير متاح مؤقتاً، وسيُستخدم "
                "نموذج فرز محلي. النتائج مبدئية — صوّر المنطقة المصابة عن قرب.*"
            )
        elif not provider.get("authenticated"):
            st.error(
                f"⚠️ **AI diagnosis is offline** — {provider.get('detail') or 'provider misconfigured'}\n\n"
                "Inspections will fail until an administrator installs a valid "
                "API key. You can still register trees and browse history."
            )
        else:
            st.success(
                f"✨ **Premium AI engine active** — Google Gemini "
                f"(`{provider.get('model')}`): high-accuracy diagnosis with "
                "detailed agronomic insights."
            )
    except APIError:
        st.caption("Diagnosis provider status unknown.")

    if not palms:
        st.info("Register a palm tree first (Palm Trees page).")
        return

    options = {
        f"{p['tree_code']} — {p.get('variety') or 'unknown variety'}": p
        for p in palms
    }
    preselected = st.session_state.pop("preselected_palm_id", None)
    default_index = 0
    if preselected:
        for index, key in enumerate(options):
            if options[key]["id"] == preselected:
                default_index = index
                break
    selected_label = st.selectbox(
        "Palm tree · اختر الشجرة", list(options), index=default_index
    )
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
                result = (
                    client.inspect(palm["id"], image_bytes, filename,
                                   notes=notes or None, user=ctx_user())
                    if CLOUD_MODE else
                    client.inspect(palm["id"], image_bytes, filename,
                                   notes=notes or None)
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
    provider = diagnosis.get("provider", "")
    is_cloud = provider == "glm"  # Gemini (or any cloud vision API)

    st.markdown(
        f"<div class='palm-card' style='border-left:6px solid {color}'>"
        f"<h3>{label} — {diagnosis['detected_disease'] or 'No disease detected'}</h3>"
        f"<p>Confidence <b>{confidence * 100:.0f}%</b> · severity "
        f"<b>{SEVERITY_BADGES.get(diagnosis['severity'], '—')}</b></p></div>",
        unsafe_allow_html=True,
    )
    st.progress(min(confidence, 1.0), text=f"Confidence {confidence * 100:.0f}%")

    # --- Provider badge: premium (Gemini) vs local screening fallback ---
    if is_cloud:
        st.success(
            f"✨ **Premium AI diagnosis** — Google Gemini "
            f"(`{diagnosis['model']}`) · {diagnosis['latency_ms'] / 1000:.1f}s · "
            f"full agronomic analysis with detailed insights"
        )
    else:
        st.info(
            "ℹ️ **Lightweight local screening** — the high-accuracy cloud "
            "model is temporarily unavailable, so this verdict comes from "
            "the on-device screening model.\n\n"
            "**Tip:** upload a closer, clearer photo of the affected area "
            "(trunk base, crown, or individual fronds) for higher accuracy. "
            "The verdict is provisional — confirm with an agronomist.\n\n"
            "*تنبيه: هذه نتيجة فحص أوّلي من نموذج محلي خفيف. للحصول على دقة "
            "أعلى، ارفع صورة أقرب وأوضح للمنطقة المصابة، وتأكد من النتيجة مع "
            "مهندس زراعي.*"
        )

    left, right = st.columns([1, 2])
    with left:
        try:
            st.image(
                client_image_bytes(inspection["image_url"], log=inspection),
                width=280,
                caption=f"Inspected {inspection['inspected_at'][:16].replace('T', ' ')}",
            )
        except APIError:
            st.caption("(stored photo unavailable)")
        _quick_actions(report)

    with right:
        # --- Structured agronomic cards ---
        if diagnosis.get("cause"):
            with st.container(border=True):
                st.markdown(f"**🧬 Cause · السبب**\n\n{diagnosis['cause']}")
        if diagnosis["symptoms"]:
            with st.container(border=True):
                st.markdown("**🔍 Observed symptoms · الأعراض**")
                for symptom in diagnosis["symptoms"]:
                    st.markdown(f"- {symptom}")
        if diagnosis["treatment_steps"]:
            with st.container(border=True):
                st.markdown("**💊 Treatment · العلاج**")
                for number, step in enumerate(diagnosis["treatment_steps"], start=1):
                    st.markdown(f"{number}. {step}")
        if diagnosis.get("prevention"):
            with st.container(border=True):
                st.markdown("**🛡️ Preventive measures · الوقاية**")
                for measure in diagnosis["prevention"]:
                    st.markdown(f"- {measure}")
        if diagnosis.get("assessment"):
            st.info(diagnosis["assessment"])
        for warning in diagnosis.get("warnings", []):
            st.warning(warning)


def _quick_actions(report: dict) -> None:
    """Quick action buttons under the photo."""
    diagnosis = report["diagnosis"]
    inspection = report["inspection"]

    st.markdown("**⚡ Quick actions · إجراءات سريعة**")
    if st.button("🔍 Re-inspect this tree", use_container_width=True,
                 help="افحص هذا الشجرة مرة أخرى"):
        st.session_state.force_page = "🔍 New inspection"
        st.session_state.preselect_palm = inspection["palm_tree_id"]
        st.rerun()

    checklist = "\n".join(
        f"{i}. {step}" for i, step in enumerate(diagnosis.get("treatment_steps") or [], 1)
    ) or "No treatment required — maintain routine care."
    st.download_button(
        "📄 Download report",
        data=_report_markdown(report),
        file_name=f"palm-report-{inspection['id'][:8]}.md",
        mime="text/markdown",
        use_container_width=True,
        help="حمّل التقرير الكامل",
    )
    with st.expander("📋 Copy treatment checklist · نسخ خطة العلاج"):
        st.code(checklist or "—", language="markdown")


def _report_markdown(report: dict) -> str:
    """Full diagnosis report as downloadable Markdown."""
    diagnosis = report["diagnosis"]
    inspection = report["inspection"]
    lines = [
        "# 🌴 Date Palm Health Report",
        "",
        f"- **Inspected:** {inspection['inspected_at'][:16].replace('T', ' ')} UTC",
        f"- **Verdict:** {diagnosis['status'].upper()}",
        f"- **Disease:** {diagnosis.get('detected_disease') or 'None detected'}",
        f"- **Severity:** {diagnosis.get('severity') or '—'}",
        f"- **Confidence:** {diagnosis['confidence'] * 100:.0f}%",
        f"- **Engine:** {diagnosis.get('provider')} / {diagnosis.get('model')}",
        "",
    ]
    if diagnosis.get("cause"):
        lines += ["## Cause", diagnosis["cause"], ""]
    if diagnosis.get("symptoms"):
        lines += ["## Symptoms"] + [f"- {s}" for s in diagnosis["symptoms"]] + [""]
    if diagnosis.get("treatment_steps"):
        lines += ["## Treatment"] + [
            f"{i}. {s}" for i, s in enumerate(diagnosis["treatment_steps"], 1)
        ] + [""]
    if diagnosis.get("prevention"):
        lines += ["## Prevention"] + [f"- {s}" for s in diagnosis["prevention"]] + [""]
    if diagnosis.get("assessment"):
        lines += ["## Assessment", diagnosis["assessment"], ""]
    return "\n".join(lines)


def client_image_bytes(image_url: str, log: dict | None = None) -> bytes:
    if CLOUD_MODE:
        return _cloud_backend().get_image_bytes(image_url, log=log)
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
                        user=ctx_user() if CLOUD_MODE else None,
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
                col_img.image(client_image_bytes(log["image_url"], log=log), width=140)
            except Exception:  # noqa: BLE001 - missing embedded photo
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
        inspections = (
            client.recent_inspections(limit=100, user=ctx_user()) if CLOUD_MODE
            else client.recent_inspections(limit=100)
        )
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
        user = (
            client.me(st.session_state.cloud_user["id"]) if CLOUD_MODE
            else client.me()
        )
    except Exception as exc:  # noqa: BLE001 - friendly session message
        st.error(f"Session expired or backend unreachable ({getattr(exc, 'detail', exc)}). Sign in again.")
        st.session_state.pop("token", None)
        st.rerun()
        return

    with st.sidebar:
        st.markdown("## 🌴 Palm Monitor")
        st.caption(f"{user['full_name']} · {user['role'].title()}")
        st.divider()
        nav_options = ["📊 Dashboard", "🔍 New inspection", "🌳 Palm trees", "🚨 Alerts"]
        current = st.session_state.get("force_page") or "📊 Dashboard"
        if current not in nav_options:
            current = "📊 Dashboard"
        page = st.radio(
            "Navigation",
            nav_options,
            index=nav_options.index(current),
            label_visibility="collapsed",
            help="التنقل: لوحة المزرعة · فحص جديد · أشجار النخيل · التنبيهات",
        )
        st.session_state.pop("force_page", None)
        st.caption(
            "📊 لوحة المزرعة · 🔍 فحص جديد · 🌳 أشجار النخيل · 🚨 التنبيهات"
        )
        st.divider()
        if st.button("Sign out", use_container_width=True,
                     help="تسجيل الخروج"):
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
        preselect = st.session_state.pop("preselect_palm", None)
        if preselect:
            for palm in palms:
                if palm["id"] == preselect:
                    st.session_state["preselected_palm_id"] = preselect
                    break
        render_inspect(client, palms)
    elif page == "🌳 Palm trees":
        render_trees(client)


if __name__ == "__main__":
    main()
