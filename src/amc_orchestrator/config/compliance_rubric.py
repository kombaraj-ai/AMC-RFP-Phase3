"""Single source of truth for the AMC compliance rubric.

Imported by the compliance agent's system prompt, by a regression test that
guards against silent drift, and rendered verbatim into `docs/compliance_rubric.md`
so the prompt and the documentation can never diverge.
"""

COMPLIANCE_RUBRIC = """\
AMC COMPLIANCE RUBRIC

1. NO GUARANTEES: Never imply or state that investment returns are guaranteed, \
assured, or certain. Flag any language that promises a specific future outcome.

2. PAST PERFORMANCE DISCLAIMER: Whenever historical performance, NAV, Alpha, \
Beta, Sharpe Ratio, Sortino Ratio, Standard Deviation, R-Squared, or returns are \
mentioned, the text MUST include the disclaimer: \
"Past performance is not indicative of future results."

3. PROMISSORY LANGUAGE: Flag words and phrases such as "promise", "ensure", \
"foolproof", "risk-free", "guaranteed", or "will sustain" when applied to future \
performance.

4. FORWARD-LOOKING STATEMENTS: Any macroeconomic outlook, strategy commentary, \
or forward-looking statement must be framed as an expectation or opinion \
(e.g. "we anticipate", "our current outlook is"), never as a certainty \
(e.g. "will happen", "is set to deliver").

5. RISK CONTEXTUALIZATION: When a fund exhibits elevated risk metrics (e.g. high \
Standard Deviation, high Beta), the response must not omit or understate that \
risk profile in favor of only highlighting attractive returns.
"""
