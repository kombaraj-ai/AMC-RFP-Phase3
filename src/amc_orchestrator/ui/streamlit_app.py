"""Streamlit front-end for the AMC RFP & Portfolio Insight Orchestrator.

A thin HTTP client over the FastAPI layer (`api/routes/rfp.py`) - it never
imports `workflows.graph_build` or talks to Ollama/Bedrock directly, the same
way `cli.py` and the API route are the only two callers of the graph. This
means the API server must already be running (`uv run python -m
amc_orchestrator.main`) before this app is launched.

No graph-failure handling is needed here beyond network/HTTP errors: the API
route already applies the try/except-around-`graph(...)` safety net (see
CLAUDE.md "Bug #2") and always returns a well-formed `RfpOutcome` with HTTP
200, even on escalation. Only connection/timeout errors are this layer's
problem.

Run with: `uv run streamlit run src/amc_orchestrator/ui/streamlit_app.py`
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import httpx
import streamlit as st

from amc_orchestrator.config.settings import get_settings

# Status palette (fixed, never themed - see dataviz skill's palette.md).
# Paired with an icon + label everywhere it's used, so status is never
# color-alone.
STATUS_GOOD = "#0ca30c"
STATUS_CRITICAL = "#d03b3b"
STATUS_MUTED = "#898781"

FUND_REFERENCE = [
    {"Ticker": "EQG1", "Fund": "Global Equity Growth Fund", "Category": "Largecap"},
    {"Ticker": "SMC3", "Fund": "Alpha Prime Smallcap Direct Fund", "Category": "Smallcap / high-risk"},
    {"Ticker": "INC2", "Fund": "Fixed Income Core Bond Fund", "Category": "Debt / Conservative"},
    {"Ticker": "BLN4", "Fund": "Balanced Conservative Wealth Fund", "Category": "Hybrid"},
]

EXAMPLE_QUESTIONS = {
    "INC2 — risk metrics & macro strategy": (
        "Please provide the current risk metrics for the Fixed Income Core "
        "Bond Fund (INC2) and its current macroeconomic strategy."
    ),
    "EQG1 — performance summary": (
        "Summarize the trailing 1-year and 3-year performance and "
        "risk-adjusted return profile of the Global Equity Growth Fund "
        "(EQG1) for an institutional RFP."
    ),
    "SMC3 — suitability for a conservative mandate": (
        "Given its elevated volatility, is the Alpha Prime Smallcap Direct "
        "Fund (SMC3) suitable for a capital-preservation mandate?"
    ),
    "BLN4 — allocation strategy": (
        "Describe the Balanced Conservative Wealth Fund (BLN4)'s current "
        "asset allocation strategy and downside protection metrics."
    ),
}
CUSTOM_LABEL = "Custom / edit below"


def fetch_json(base_url: str, path: str, timeout: float = 3.0) -> dict[str, Any] | None:
    try:
        response = httpx.get(f"{base_url}{path}", timeout=timeout)
        return response.json()
    except (httpx.ConnectError, httpx.TimeoutException, ValueError):
        return None


def refresh_status() -> None:
    base_url = st.session_state.api_base_url.rstrip("/")
    st.session_state.health = fetch_json(base_url, "/health")
    st.session_state.readiness = fetch_json(base_url, "/health/ready")
    st.session_state.status_checked_at = datetime.now().strftime("%H:%M:%S")


def apply_example() -> None:
    label = st.session_state.example_select
    if label != CUSTOM_LABEL:
        st.session_state.question_text = EXAMPLE_QUESTIONS[label]


def status_badge(ok: bool, good_label: str, bad_label: str) -> str:
    color = STATUS_GOOD if ok else STATUS_CRITICAL
    icon = "✅" if ok else "⛔"
    label = good_label if ok else bad_label
    return (
        f'<span style="display:inline-flex;align-items:center;gap:6px;'
        f"padding:4px 12px;border-radius:999px;border:1px solid {color}55;"
        f'background:{color}1A;color:{color};font-weight:600;font-size:0.9rem;">'
        f"{icon} {label}</span>"
    )


def render_sidebar(settings) -> None:
    st.sidebar.header("Connection")
    st.sidebar.text_input(
        "API base URL",
        key="api_base_url",
        on_change=refresh_status,
        help="Where the FastAPI server (`amc-orchestrator`) is listening.",
    )
    st.sidebar.button("Refresh status", on_click=refresh_status, width="stretch")

    health = st.session_state.get("health")
    readiness = st.session_state.get("readiness")
    checked_at = st.session_state.get("status_checked_at")

    st.sidebar.markdown(status_badge(health is not None, "API online", "API unreachable"), unsafe_allow_html=True)
    if readiness is not None:
        st.sidebar.markdown(
            status_badge(bool(readiness.get("ready")), "Ready", "Not ready"),
            unsafe_allow_html=True,
        )
        with st.sidebar.expander("Readiness checks"):
            for check, passed in readiness.get("checks", {}).items():
                st.write(("✅ " if passed else "❌ ") + check)
    if health is not None:
        st.sidebar.caption(f"Environment: `{health.get('environment', 'unknown')}`")
    if checked_at:
        st.sidebar.caption(f"Last checked {checked_at}")
    if health is None:
        st.sidebar.warning(
            "Can't reach the API. Start it with:\n\n"
            "`uv run python -m amc_orchestrator.main`",
            icon="⚠️",
        )

    st.sidebar.divider()
    st.sidebar.header("Request settings")
    st.sidebar.slider(
        "Request timeout (seconds)",
        min_value=30,
        max_value=900,
        step=30,
        key="request_timeout",
        help=(
            "DEV Ollama generation can take 5-10+ minutes end-to-end on "
            "CPU-only hardware (see CLAUDE.md). Raise this if requests time "
            "out. Bedrock runs typically finish in well under a minute."
        ),
    )

    st.sidebar.divider()
    st.sidebar.header("Fund reference")
    st.sidebar.dataframe(FUND_REFERENCE, hide_index=True, width="stretch")


def render_result(outcome: dict[str, Any], elapsed: float) -> None:
    escalated = bool(outcome.get("escalated"))
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**Outcome**")
        st.markdown(
            status_badge(not escalated, "Approved", "Escalated"),
            unsafe_allow_html=True,
        )
    with col2:
        st.metric("Compliance attempts", outcome.get("compliance_attempts", "—"))
    with col3:
        st.metric("Elapsed time", f"{elapsed:.1f}s")

    st.caption(f"Graph status: `{outcome.get('graph_status', 'unknown')}`")

    if escalated:
        st.info(
            "This request was escalated to manual compliance review instead "
            "of an automated response - see the message below.",
            icon="🔎",
        )

    with st.container(border=True):
        st.markdown(outcome.get("response_text", ""))

    with st.expander("Raw response JSON"):
        st.json(outcome)


def submit_rfp(base_url: str, question: str, timeout: float) -> tuple[dict[str, Any], float]:
    start = time.perf_counter()
    response = httpx.post(
        f"{base_url}/api/v1/rfp",
        json={"question": question},
        timeout=timeout,
    )
    elapsed = time.perf_counter() - start
    response.raise_for_status()
    return response.json(), elapsed


def main() -> None:
    settings = get_settings()

    st.set_page_config(
        page_title="AMC RFP & Portfolio Insight Orchestrator",
        page_icon="🏛️",
        layout="wide",
    )

    if "api_base_url" not in st.session_state:
        st.session_state.api_base_url = f"http://localhost:{settings.api_port}"
    if "request_timeout" not in st.session_state:
        st.session_state.request_timeout = 600
    if "question_text" not in st.session_state:
        st.session_state.question_text = next(iter(EXAMPLE_QUESTIONS.values()))
    if "example_select" not in st.session_state:
        st.session_state.example_select = next(iter(EXAMPLE_QUESTIONS.keys()))
    if "health" not in st.session_state:
        refresh_status()

    render_sidebar(settings)

    st.title("AMC RFP & Portfolio Insight Orchestrator")
    st.caption(
        "Institutional RFP and portfolio-query responses, generated by a "
        "self-correcting, compliance-reviewed multi-agent pipeline."
    )

    st.selectbox(
        "Example queries",
        [CUSTOM_LABEL, *EXAMPLE_QUESTIONS.keys()],
        key="example_select",
        on_change=apply_example,
    )

    with st.form("rfp_form"):
        st.text_area("RFP question", key="question_text", height=140)
        submitted = st.form_submit_button("Submit RFP", type="primary")

    if submitted:
        question = st.session_state.question_text.strip()
        if not question:
            st.error("Enter a question before submitting.")
        else:
            base_url = st.session_state.api_base_url.rstrip("/")
            try:
                with st.spinner(
                    "Running quant + qual retrieval, compliance review, and "
                    "synthesis - this can take several minutes on DEV Ollama..."
                ):
                    outcome, elapsed = submit_rfp(
                        base_url, question, st.session_state.request_timeout
                    )
            except httpx.ConnectError:
                st.error(
                    "Could not connect to the API. Confirm it's running at "
                    f"`{base_url}` (`uv run python -m amc_orchestrator.main`)."
                )
            except httpx.TimeoutException:
                st.error(
                    "Request timed out before the graph finished. Raise "
                    "'Request timeout' in the sidebar, or check `ollama ps` "
                    "for a stuck generation."
                )
            except httpx.HTTPStatusError as exc:
                st.error(f"API returned {exc.response.status_code}: {exc.response.text}")
            else:
                st.session_state.setdefault("history", []).insert(
                    0,
                    {
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "question": question,
                        "outcome": outcome,
                        "elapsed": elapsed,
                    },
                )
                render_result(outcome, elapsed)

    history = st.session_state.get("history", [])
    if history:
        st.divider()
        with st.expander(f"Session history ({len(history)})"):
            for entry in history:
                escalated = entry["outcome"].get("escalated")
                icon = "⛔" if escalated else "✅"
                st.markdown(f"**{entry['time']}** {icon} — {entry['question']}")
                st.caption(
                    f"Attempts: {entry['outcome'].get('compliance_attempts')} · "
                    f"Elapsed: {entry['elapsed']:.1f}s"
                )
                st.divider()


main()
