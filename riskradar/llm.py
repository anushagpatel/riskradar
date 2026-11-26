"""OpenAI integration. The LLM only interprets evidence handed to it; it never calculates.

Configure with environment variables: OPENAI_API_KEY, OPENAI_MODEL, OPENAI_BASE_URL (optional).
"""
from __future__ import annotations

import os
import re

from .engine import IndicatorResult

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_BASE_URL = "https://api.openai.com/v1"

SYSTEM_PROMPT = """You are a financial stability research assistant. You support analysts; you do not give personalized \
investment advice and you do not predict financial crises.

STRICT RULES
1. Use ONLY the EVIDENCE block in the user message. Every factual statement or number must cite evidence IDs in \
square brackets, e.g. [M3] or [A1][R2]. M = calculated metric, A = alert, R = regulatory report excerpt, \
S = stress-test result.
2. Never invent statistics, dates, source names, URLs or report quotes. Do not compute new numbers; quote the \
provided ones. If the evidence does not contain something, write "Not available in the provided data."
3. Label content clearly: "Observed:" for facts in the evidence, "Hypothetical:" for scenarios or plausible \
mechanisms. Present causal links as possible transmission channels (e.g. "could", "may"), never as established fact, \
unless a cited report excerpt states the relationship.
4. Indicator classifications are heuristic threshold signals, not validated risk ratings. Say so where relevant.
5. If an indicator is 'Insufficient data' or unavailable, say it cannot be assessed."""

ANALYSIS_INSTRUCTIONS = """Write a structured financial risk assessment in Markdown with exactly these sections:
1. Executive summary
2. Emerging risk factors
3. Supporting financial evidence
4. Potential causes
5. Potential implications for banks, hedge funds and asset managers
6. Possible transmission channels between risk categories (for example, how AI infrastructure financing growth \
could interact with wider corporate credit spreads through debt-servicing pressure) - mark as Hypothetical
7. Indicators requiring further monitoring
8. Limitations and uncertainties
9. Source references (list only the evidence IDs you cited, with their source names/URLs from the evidence)"""


class LLMError(Exception):
    pass


def model_name() -> str:
    return os.getenv("OPENAI_MODEL", DEFAULT_MODEL)


def is_configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def chat(messages: list[dict], max_tokens: int = 1800) -> str:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise LLMError("OPENAI_API_KEY is not set. Add it to your .env file.")
    import httpx  # lazy import

    base = os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    try:
        r = httpx.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model_name(), "messages": messages, "max_completion_tokens": max_tokens},
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except httpx.HTTPStatusError as exc:
        detail = ""
        try:
            detail = exc.response.json().get("error", {}).get("message", "")
        except Exception:  # noqa: BLE001
            pass
        raise LLMError(f"OpenAI request failed (HTTP {exc.response.status_code}). {detail}".strip()) from None
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"OpenAI request failed: {type(exc).__name__}") from None


# ------------------------------------------------------------------ evidence

def _fmt(x, nd=2):
    return "n/a" if x is None else f"{x:,.{nd}f}"


def build_evidence(results: list[IndicatorResult], alerts: list[dict], excerpts: list[dict],
                   stress: list[str] | None = None) -> tuple[str, set[str]]:
    """Render evidence with stable IDs. Returns (text, set_of_valid_ids)."""
    lines, ids = [], set()
    lines.append("METRICS (calculated deterministically in Python; classification = heuristic threshold signal)")
    for i, r in enumerate(results, 1):
        eid = f"M{i}"
        ids.add(eid)
        if r.latest is None:
            lines.append(f"[{eid}] {r.category} | {r.label} | DATA UNAVAILABLE ({r.error or 'no data'}) | "
                         f"classification: Insufficient data | source: {r.source_url}")
            continue
        chg = "n/a" if r.change is None else (f"{r.change:+.2f}%" if r.change_kind == "pct" else f"{r.change:+.2f} {r.unit}")
        sigs = "; ".join(f"{s.name}={s.value:.2f} ({s.status})" for s in r.signals) or "no signals"
        lines.append(f"[{eid}] {r.category} | {r.label} | latest {_fmt(r.latest)} {r.unit} (obs {r.obs_date}) | "
                     f"previous {_fmt(r.previous)} | change {chg} | classification: {r.classification} | "
                     f"signals: {sigs} | source: {r.source_url}")
    lines.append("\nALERTS")
    if not alerts:
        lines.append("(none)")
    for i, a in enumerate(alerts, 1):
        eid = f"A{i}"
        ids.add(eid)
        lines.append(f"[{eid}] {a['severity']} | {a['category']} | {a['indicator']} | current {_fmt(a['current_value'])} | "
                     f"previous {_fmt(a['previous_value'])} | {a['condition']} | obs {a['obs_date']} | source: {a['source_url']}")
    lines.append("\nREGULATORY REPORT EXCERPTS")
    if not excerpts:
        lines.append("(none available)")
    for i, e in enumerate(excerpts, 1):
        eid = f"R{i}"
        ids.add(eid)
        lines.append(f"[{eid}] {e['title']} | {e['url']}\n    \"{e['text']}\"")
    if stress:
        lines.append("\nHYPOTHETICAL STRESS-TEST RESULTS (user-chosen assumptions; not forecasts)")
        for i, s in enumerate(stress, 1):
            ids.add(f"S{i}")
            lines.append(f"[S{i}] {s}")
    return "\n".join(lines), ids


def analysis_messages(evidence: str) -> list[dict]:
    return [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"EVIDENCE\n{evidence}\n\n{ANALYSIS_INSTRUCTIONS}"}]


def chat_messages(history: list[dict], question: str, evidence: str) -> list[dict]:
    msgs = [{"role": "system", "content": SYSTEM_PROMPT + "\nAnswer concisely, in plain language, with citations."}]
    msgs += history[-6:]
    msgs.append({"role": "user", "content": f"EVIDENCE\n{evidence}\n\nQUESTION: {question}"})
    return msgs


# ------------------------------------------------------------------ output guards

_CITE = re.compile(r"\[([MARS]\d+)\]")
_NUM = re.compile(r"(?<![\w.])-?\d[\d,]*\.?\d*")


def validate_citations(answer: str, valid_ids: set[str]) -> list[str]:
    """Citation IDs used in the answer that do not exist in the evidence."""
    return sorted({c for c in _CITE.findall(answer) if c not in valid_ids})


def _numbers(text: str) -> list[float]:
    out = []
    for m in _NUM.findall(_CITE.sub("", text)):
        try:
            out.append(float(m.replace(",", "").rstrip(".")))
        except ValueError:
            continue
    return out


def find_unsupported_numbers(answer: str, evidence: str) -> list[float]:
    """Numbers in the answer that match nothing in the evidence (tolerant of rounding).

    Ignores years, small integers (list numbering, counts up to 12) and citation IDs.
    This is a heuristic warning for the reader, not proof of fabrication.
    """
    ev = _numbers(evidence)
    flagged = []
    for n in _numbers(answer):
        if 1900 <= n <= 2100 and float(n).is_integer():
            continue
        if float(n).is_integer() and abs(n) <= 12:
            continue
        if not any(abs(abs(n) - abs(e)) <= max(0.051, 0.01 * abs(e)) for e in ev):
            flagged.append(n)
    return sorted(set(flagged))
