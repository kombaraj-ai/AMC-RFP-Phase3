"""Streamlit front-end for the AMC RFP & Portfolio Insight Orchestrator.

Two connection modes, selected in the sidebar:

- **Local API server**: a thin HTTP client over the FastAPI layer
  (`api/routes/rfp.py`) - no separate agent logic, no direct Ollama/Bedrock
  access, the same way `cli.py` and the API route are the only two callers
  of the graph. Requires the API server already running (`uv run python -m
  amc_orchestrator.main`).
- **Deployed AgentCore Runtime (AWS)**: calls the real, deployed Phase 02
  Runtime directly via `boto3`'s `invoke_agent_runtime` (SigV4-signed,
  no local server involved at all) - uses whatever AWS credentials are
  already active in this environment, the same ones used for
  `terraform apply`. Both modes return the exact same `RfpOutcome` JSON
  shape (`runtime_entrypoint.py`'s `invoke()` and the API route both return
  `dataclasses.asdict(outcome)`), so `render_result` never needs to know
  which mode produced it.

No graph-failure handling is needed here beyond network/HTTP/AWS errors: the
API route and the Runtime entrypoint both already apply the
try/except-around-`graph(...)` safety net (see CLAUDE.md "Bug #2") and
always return a well-formed `RfpOutcome`, even on escalation. Only
connection/timeout/credential errors are this layer's problem.

A sidebar "Admin: Upload KB documents" expander is independent of connection
mode (it's a plain S3 `PutObject`, same active AWS credentials as Runtime
mode) - lets a tester drop fund-commentary docs straight into the KB docs
bucket without leaving the UI. No manual ingestion call needed afterward;
`infra/terraform/modules/kb-ingestion-sync` auto-triggers a Bedrock
ingestion job on upload (see `docs/sample_invocation_walkthrough.md`'s
"S3 Auto Sync - Inner working" section).

Run with: `uv run streamlit run src/amc_orchestrator/ui/streamlit_app.py`
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

import boto3
import httpx
import streamlit as st
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from amc_orchestrator.config.settings import get_settings

LOCAL_MODE = "Local API server"
RUNTIME_MODE = "Deployed AgentCore Runtime (AWS)"

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


def fetch_runtime_status(region: str, arn: str) -> dict[str, Any] | None:
    """Check the deployed Runtime's real status via the control-plane API.

    `get_agent_runtime` takes an id, not the ARN `invoke_agent_runtime` uses -
    the id is just the ARN's last path segment (confirmed against a real
    Phase 02 deployment, e.g. `.../runtime/amc_orchestrator_dev_agent_runtime-X1c5y89vze`).
    """
    if not arn.strip():
        return None
    runtime_id = arn.rsplit("/", 1)[-1]
    try:
        client = boto3.client("bedrock-agentcore-control", region_name=region)
        response = client.get_agent_runtime(agentRuntimeId=runtime_id)
        return {"status": response.get("status"), "error": None}
    except (ClientError, BotoCoreError) as exc:
        return {"status": None, "error": str(exc)}


def refresh_status() -> None:
    if st.session_state.connection_mode == LOCAL_MODE:
        base_url = st.session_state.api_base_url.rstrip("/")
        st.session_state.health = fetch_json(base_url, "/health")
        st.session_state.readiness = fetch_json(base_url, "/health/ready")
    else:
        st.session_state.runtime_status = fetch_runtime_status(
            st.session_state.aws_region, st.session_state.agent_runtime_arn
        )
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


def render_local_connection() -> None:
    st.sidebar.text_input(
        "API base URL",
        key="api_base_url",
        value=st.session_state.api_base_url,
        on_change=refresh_status,
        help="Where the FastAPI server (`amc-orchestrator`) is listening.",
    )
    st.sidebar.button("Refresh status", on_click=refresh_status, width="stretch")

    health = st.session_state.get("health")
    readiness = st.session_state.get("readiness")

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
    if health is None:
        st.sidebar.warning(
            "Can't reach the API. Start it with:\n\n"
            "`uv run python -m amc_orchestrator.main`",
            icon="⚠️",
        )


def render_runtime_connection() -> None:
    st.sidebar.text_input(
        "AWS region", key="aws_region", value=st.session_state.aws_region, on_change=refresh_status
    )
    st.sidebar.text_input(
        "Agent Runtime ARN",
        key="agent_runtime_arn",
        value=st.session_state.agent_runtime_arn,
        on_change=refresh_status,
        help=(
            "From `terraform output agent_runtime_arn` in "
            "`infra/terraform/environments/<env>/` after pass 3."
        ),
    )
    st.sidebar.caption(
        "Uses whatever AWS credentials are already active in this "
        "environment (e.g. `aws configure` or an SSO login) - the same "
        "ones used for `terraform apply`. No separate login here."
    )
    st.sidebar.button("Refresh status", on_click=refresh_status, width="stretch")

    status = st.session_state.get("runtime_status")
    arn_entered = bool(st.session_state.agent_runtime_arn.strip())
    if not arn_entered:
        st.sidebar.warning("Enter an Agent Runtime ARN above to check its status.", icon="⚠️")
    elif status is None:
        st.sidebar.info("Status not checked yet.", icon="ℹ️")
    elif status["error"]:
        st.sidebar.markdown(status_badge(False, "", "Status check failed"), unsafe_allow_html=True)
        st.sidebar.caption(status["error"])
    else:
        runtime_state = status["status"] or "UNKNOWN"
        label = f"Runtime {runtime_state}"
        st.sidebar.markdown(
            status_badge(runtime_state == "READY", label, label),
            unsafe_allow_html=True,
        )


def upload_docs_to_s3(
    region: str, bucket: str, files: list
) -> list[tuple[str, bool, str | None]]:
    """Upload each file as-is to the KB docs bucket via a direct S3 PutObject.

    Uses whatever AWS credentials are already active, same as Runtime mode.
    No separate ingestion call is needed afterward - the bucket has an S3
    event notification wired to `modules/kb-ingestion-sync`, which
    auto-triggers a Bedrock ingestion job within its ~5 minute batching
    window (see `docs/sample_invocation_walkthrough.md`'s "S3 Auto Sync -
    Inner working" section for the full chain).
    """
    client = boto3.client("s3", region_name=region)
    results: list[tuple[str, bool, str | None]] = []
    for f in files:
        try:
            client.put_object(Bucket=bucket, Key=f.name, Body=f.getvalue())
            results.append((f.name, True, None))
        except (ClientError, BotoCoreError) as exc:
            results.append((f.name, False, str(exc)))
    return results


def list_docs_in_bucket(region: str, bucket: str) -> list[dict[str, Any]] | None:
    try:
        client = boto3.client("s3", region_name=region)
        response = client.list_objects_v2(Bucket=bucket)
    except (ClientError, BotoCoreError):
        return None
    return [
        {
            "Key": obj["Key"],
            "Size (bytes)": obj["Size"],
            "Last modified": obj["LastModified"].strftime("%Y-%m-%d %H:%M:%S"),
        }
        for obj in response.get("Contents", [])
    ]


def render_docs_admin() -> None:
    with st.sidebar.expander("📄 Admin: Upload KB documents"):
        st.text_input(
            "S3 docs bucket",
            key="kb_docs_bucket",
            value=st.session_state.kb_docs_bucket,
            help=(
                "From `terraform output kb_docs_bucket_name` in "
                "`infra/terraform/environments/<env>/`."
            ),
        )
        uploaded = st.file_uploader(
            "Fund commentary documents",
            accept_multiple_files=True,
            key="kb_upload_widget",
            help="Uploaded as-is to the KB docs bucket; auto-sync ingestion picks them up within ~5 minutes.",
        )
        bucket = st.session_state.kb_docs_bucket.strip()

        if st.button("Upload to S3", width="stretch", disabled=not (bucket and uploaded)):
            results = upload_docs_to_s3(st.session_state.aws_region, bucket, uploaded)
            for name, ok, error in results:
                if ok:
                    st.success(f"Uploaded `{name}`")
                else:
                    st.error(f"`{name}` failed: {error}")
            if any(ok for _, ok, _ in results):
                st.info(
                    "Auto-sync ingestion will pick this up within ~5 minutes "
                    "(no manual `start_ingestion_job` needed).",
                    icon="🔄",
                )

        if st.button("List documents in bucket", width="stretch", disabled=not bucket):
            docs = list_docs_in_bucket(st.session_state.aws_region, bucket)
            if docs is None:
                st.error("Could not list bucket - check bucket name/region/credentials.")
            elif not docs:
                st.caption("Bucket is empty.")
            else:
                st.dataframe(docs, hide_index=True, width="stretch")


def render_sidebar(settings) -> None:
    st.sidebar.header("Connection")
    st.sidebar.radio(
        "Target", [LOCAL_MODE, RUNTIME_MODE], key="connection_mode", on_change=refresh_status
    )

    if st.session_state.connection_mode == LOCAL_MODE:
        render_local_connection()
    else:
        render_runtime_connection()

    checked_at = st.session_state.get("status_checked_at")
    if checked_at:
        st.sidebar.caption(f"Last checked {checked_at}")

    st.sidebar.divider()
    st.sidebar.header("Request settings")
    st.sidebar.slider(
        "Request timeout (seconds)",
        min_value=30,
        max_value=900,
        step=30,
        key="request_timeout",
        help=(
            "DEV Ollama generation (Local API server mode) can take 5-10+ "
            "minutes end-to-end on CPU-only hardware (see CLAUDE.md). Raise "
            "this if requests time out. Bedrock runs - whether via a local "
            "API server with MODEL_PROVIDER=bedrock, or the deployed "
            "Runtime - typically finish in well under a minute."
        ),
    )

    st.sidebar.divider()
    st.sidebar.header("Fund reference")
    st.sidebar.dataframe(FUND_REFERENCE, hide_index=True, width="stretch")

    st.sidebar.divider()
    render_docs_admin()


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


def submit_rfp_local(base_url: str, question: str, timeout: float) -> tuple[dict[str, Any], float]:
    start = time.perf_counter()
    response = httpx.post(
        f"{base_url}/api/v1/rfp",
        json={"question": question},
        timeout=timeout,
    )
    elapsed = time.perf_counter() - start
    response.raise_for_status()
    return response.json(), elapsed


def submit_rfp_runtime(
    region: str, arn: str, question: str, timeout: float
) -> tuple[dict[str, Any], float]:
    """Invoke the deployed AgentCore Runtime directly via SigV4-signed boto3.

    `invoke_agent_runtime`'s response body is the exact same `RfpOutcome`
    JSON `runtime_entrypoint.py`'s `invoke()` returns - no separate parsing
    needed, `render_result` handles it identically to the local API path.
    """
    client = boto3.client(
        "bedrock-agentcore",
        region_name=region,
        config=BotoConfig(connect_timeout=min(timeout, 30), read_timeout=timeout),
    )
    start = time.perf_counter()
    response = client.invoke_agent_runtime(
        agentRuntimeArn=arn,
        payload=json.dumps({"prompt": question}).encode("utf-8"),
        contentType="application/json",
    )
    body = response["response"].read()
    elapsed = time.perf_counter() - start
    return json.loads(body), elapsed


def main() -> None:
    settings = get_settings()

    st.set_page_config(
        page_title="AMC RFP & Portfolio Insight Orchestrator",
        page_icon="🏛️",
        layout="wide",
    )

    if "connection_mode" not in st.session_state:
        st.session_state.connection_mode = LOCAL_MODE
    if "api_base_url" not in st.session_state:
        st.session_state.api_base_url = f"http://localhost:{settings.api_port}"
    if "aws_region" not in st.session_state:
        st.session_state.aws_region = settings.aws_region
    if "agent_runtime_arn" not in st.session_state:
        st.session_state.agent_runtime_arn = ""
    if "kb_docs_bucket" not in st.session_state:
        st.session_state.kb_docs_bucket = ""
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
        mode = st.session_state.connection_mode
        if not question:
            st.error("Enter a question before submitting.")
        elif mode == RUNTIME_MODE and not st.session_state.agent_runtime_arn.strip():
            st.error("Enter an Agent Runtime ARN in the sidebar first.")
        else:
            spinner_text = "Running quant + qual retrieval, compliance review, and synthesis - " + (
                "this can take several minutes on DEV Ollama..."
                if mode == LOCAL_MODE
                else "typically 5-15s against the deployed Runtime..."
            )
            try:
                with st.spinner(spinner_text):
                    if mode == LOCAL_MODE:
                        base_url = st.session_state.api_base_url.rstrip("/")
                        outcome, elapsed = submit_rfp_local(
                            base_url, question, st.session_state.request_timeout
                        )
                    else:
                        outcome, elapsed = submit_rfp_runtime(
                            st.session_state.aws_region,
                            st.session_state.agent_runtime_arn.strip(),
                            question,
                            st.session_state.request_timeout,
                        )
            except httpx.ConnectError:
                st.error(
                    "Could not connect to the API. Confirm it's running at "
                    f"`{st.session_state.api_base_url.rstrip('/')}` "
                    "(`uv run python -m amc_orchestrator.main`)."
                )
            except httpx.TimeoutException:
                st.error(
                    "Request timed out before the graph finished. Raise "
                    "'Request timeout' in the sidebar, or check `ollama ps` "
                    "for a stuck generation."
                )
            except httpx.HTTPStatusError as exc:
                st.error(f"API returned {exc.response.status_code}: {exc.response.text}")
            except ClientError as exc:
                error = exc.response.get("Error", {})
                st.error(
                    f"AWS returned {error.get('Code', 'an error')}: "
                    f"{error.get('Message', str(exc))}"
                )
            except BotoCoreError as exc:
                st.error(
                    "Could not reach the deployed Runtime - confirm AWS "
                    "credentials are active in this environment (e.g. "
                    f"`aws configure` or SSO login) and the region/ARN are "
                    f"correct. Details: {exc}"
                )
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
