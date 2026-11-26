"""Federal Reserve Financial Stability Report: fetch, store and retrieve excerpts.

Retrieval is plain keyword scoring over paragraphs (no vector database). If the report cannot be
fetched automatically (page layout change, PDF-only), the app lets the user paste an excerpt,
which is stored and used the same way.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin

FSR_URL = "https://www.federalreserve.gov/publications/financial-stability-report.htm"
_LINK_RE = re.compile(r'href="([^"]*financial-stability-report-(\d{8})[^"]*)"', re.I)

TOPIC_TERMS = {
    "hedge_fund": ["hedge fund", "leverage", "gross notional", "prime broker", "basis trade", "margin"],
    "ai": ["artificial intelligence", " ai ", "data center", "data-center", "hyperscaler", "technology firms"],
    "ndfi": ["nondepository", "nonbank", "non-bank", "private credit", "ndfi", "nonbank financial"],
    "agriculture": ["farm", "agricultur", "farmland", "crop"],
    "valuation": ["valuation", "asset price", "equity price", "price-to-earnings", "risk premium", "spread"],
    "banks": ["bank", "capital", "liquidity", "loan", "delinquen"],
}
_QUESTION_TOPICS = {
    "hedge_fund": ["hedge", "leverage", "leveraged"],
    "ai": [" ai", "artificial", "data center"],
    "ndfi": ["ndfi", "nonbank", "non-bank", "nondepository", "private credit"],
    "agriculture": ["agricult", "farm"],
    "valuation": ["valuation", "price", "correction", "spread"],
    "banks": ["bank", "lending", "loan"],
}


class ReportError(Exception):
    pass


class _TextExtractor(HTMLParser):
    BLOCK = {"p", "li", "h1", "h2", "h3", "h4", "div", "br", "tr"}
    SKIP = {"script", "style", "nav", "header", "footer", "noscript"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _TextExtractor()
    p.feed(html)
    text = "".join(p.parts)
    return re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t\r\f\v]+", " ", text)).strip()


def find_report_links(html: str, base: str = FSR_URL) -> list[tuple[str, str]]:
    """[(YYYYMMDD, absolute_url)] newest first; .htm preferred over .pdf for the same date."""
    by_date: dict[str, str] = {}
    for href, date in _LINK_RE.findall(html):
        url = urljoin(base, href)
        if date not in by_date or (by_date[date].lower().endswith(".pdf") and not url.lower().endswith(".pdf")):
            by_date[date] = url
    return sorted(((d, u) for d, u in by_date.items()), reverse=True)


def split_paragraphs(text: str, min_chars: int = 120) -> list[str]:
    paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", text)]
    return [p for p in paras if len(p) >= min_chars]


def terms_for_question(question: str) -> list[str]:
    q = " " + question.lower() + " "
    terms: list[str] = []
    for topic, triggers in _QUESTION_TOPICS.items():
        if any(t in q for t in triggers):
            terms += TOPIC_TERMS[topic]
    terms += [w for w in re.findall(r"[a-z]{5,}", q) if w not in {"which", "about", "latest", "available", "currently"}]
    return list(dict.fromkeys(terms))


def select_excerpts(paragraphs: list[str], terms: list[str], k: int = 5, max_chars: int = 900) -> list[str]:
    scored = []
    for i, p in enumerate(paragraphs):
        low = " " + p.lower() + " "
        score = sum(low.count(t) for t in terms)
        if score:
            scored.append((score, -i, p))
    scored.sort(reverse=True)
    return [p[:max_chars] for _, _, p in scored[:k]]


def fetch_latest_reports(client, n: int = 2) -> list[dict]:
    """Fetch up to n most recent report pages (HTML only). Raises ReportError with a clear message."""
    try:
        r = client.get(FSR_URL, timeout=30, follow_redirects=True)
        r.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise ReportError(f"Could not load the Fed report index ({type(exc).__name__})") from None
    links = find_report_links(r.text)
    if not links:
        raise ReportError("No report links found on the Fed page; paste an excerpt manually instead")
    out = []
    for date, url in links[:n]:
        if url.lower().endswith(".pdf"):
            continue  # PDF parsing would need an extra dependency; use the manual paste fallback
        try:
            page = client.get(url, timeout=45, follow_redirects=True)
            page.raise_for_status()
        except Exception:  # noqa: BLE001
            continue
        text = html_to_text(page.text)
        if len(text) > 2000:
            out.append({"url": url, "report_date": f"{date[:4]}-{date[4:6]}-{date[6:]}",
                        "title": f"Federal Reserve Financial Stability Report ({date[:4]}-{date[4:6]}-{date[6:]})",
                        "text": text})
    if not out:
        raise ReportError("Report pages were found but none were readable HTML; paste an excerpt manually instead")
    return out
