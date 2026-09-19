#!/usr/bin/env python3
"""
fetch_papers.py — Download PDFs from URLs or DOIs.

Usage:
    python fetch_papers.py paper1.txt           # file with one URL/DOI per line
    python fetch_papers.py 10.1038/s41586-021-03380-y https://arxiv.org/abs/2303.08774
    python fetch_papers.py --out ./pdfs 10.1145/3442188.3445922

Strategy per input type:
  arXiv URL or ID   → direct PDF from arxiv.org
  DOI               → Unpaywall → Semantic Scholar → Europe PMC → DOI page sniff
  bioRxiv/medRxiv   → direct PDF from preprint server
  OpenReview        → direct PDF from openreview.net
  Direct PDF URL    → download as-is
  Other URL         → sniff page for PDF links, then try Semantic Scholar
"""

import argparse
import re
import time
import urllib.parse
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

# ── Config ────────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; paper-fetcher/1.0; "
        "mailto:your@email.com)"
    )
}
TIMEOUT = 20
UNPAYWALL_EMAIL = ""        # ← change this for Unpaywall


# ── Helpers ───────────────────────────────────────────────────────────────────

session = requests.Session()
session.headers.update(HEADERS)


def url_to_filename(url: str) -> str:
    name = re.sub(r'^https?://', '', url)
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    name = re.sub(r'_+', '_', name)
    name = name[:200]
    if not name.endswith('.pdf'):
        name += '.pdf'
    return name


def download_pdf(url: str, dest: Path) -> bool:
    """Stream a URL to dest. Returns True on success."""
    try:
        r = session.get(url, timeout=TIMEOUT, stream=True, allow_redirects=True)
        r.raise_for_status()
        ct = r.headers.get("content-type", "")
        if "pdf" not in ct and not url.endswith(".pdf"):
            chunk = next(r.iter_content(512), b"")
            if not chunk.startswith(b"%PDF"):
                return False
            with open(dest, "wb") as f:
                f.write(chunk)
                for c in r.iter_content(8192):
                    f.write(c)
            return True
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return True
    except Exception:
        return False


# ── Source-specific resolvers ─────────────────────────────────────────────────

def resolve_arxiv(arxiv_id: str) -> str | None:
    return f"https://arxiv.org/pdf/{arxiv_id}.pdf"


def resolve_unpaywall(doi: str) -> str | None:
    url = f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi, safe='')}?email={UNPAYWALL_EMAIL}"
    try:
        r = session.get(url, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        data = r.json()
        best = data.get("best_oa_location") or {}
        pdf = best.get("url_for_pdf")
        if pdf:
            return pdf
        for loc in data.get("oa_locations", []):
            if loc.get("url_for_pdf"):
                return loc["url_for_pdf"]
    except Exception:
        pass
    return None


def resolve_semantic_scholar(query: str) -> str | None:
    """Try by DOI, then by URL, then by title search."""
    candidates = []
    if re.match(r"10\.\d{4,}/", query):
        candidates.append(
            f"https://api.semanticscholar.org/graph/v1/paper/DOI:{urllib.parse.quote(query, safe='')}?fields=openAccessPdf"
        )
    candidates.append(
        f"https://api.semanticscholar.org/graph/v1/paper/URL:{urllib.parse.quote(query, safe='')}?fields=openAccessPdf"
    )
    candidates.append(
        f"https://api.semanticscholar.org/graph/v1/paper/search?query={urllib.parse.quote(query)}&fields=openAccessPdf&limit=1"
    )
    for api in candidates:
        try:
            r = session.get(api, timeout=TIMEOUT)
            if r.status_code != 200:
                continue
            data = r.json()
            oa = data.get("openAccessPdf")
            if oa and oa.get("url"):
                return oa["url"]
            for item in data.get("data", []):
                oa = item.get("openAccessPdf")
                if oa and oa.get("url"):
                    return oa["url"]
        except Exception:
            continue
    return None


def resolve_europe_pmc(doi: str) -> str | None:
    """Europe PMC is great for biomedical/life sciences papers."""
    try:
        api = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:{urllib.parse.quote(doi)}&format=json&resultType=core"
        r = session.get(api, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        data = r.json()
        for result in data.get("resultList", {}).get("result", []):
            pmcid = result.get("pmcid")
            if pmcid:
                return f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf"
    except Exception:
        pass
    return None


def resolve_doi_page(doi: str) -> str | None:
    """Follow doi.org and sniff the landing page for a PDF link."""
    doi_url = f"https://doi.org/{doi}"
    try:
        r = session.get(doi_url, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code != 200:
            return None
        # Check if the redirect itself is already a PDF
        if "pdf" in r.headers.get("content-type", ""):
            return r.url
        soup = BeautifulSoup(r.text, "lxml")
        # citation_pdf_url meta tag (most reliable)
        for attr in ["citation_pdf_url", "citation_pdf"]:
            meta = soup.find("meta", attrs={"name": re.compile(attr, re.I)})
            if meta and meta.get("content"):
                return meta["content"]
        # <a> links containing "pdf"
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.endswith(".pdf") or "pdf" in href.lower():
                return urllib.parse.urljoin(r.url, href)
    except Exception:
        pass
    return None


def sniff_page_for_pdf(url: str) -> str | None:
    """Fetch a webpage and look for embedded PDF links or citation_pdf meta."""
    try:
        r = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        if "pdf" in r.headers.get("content-type", ""):
            return r.url
        soup = BeautifulSoup(r.text, "lxml")
        for attr in ["citation_pdf_url", "citation_pdf"]:
            meta = soup.find("meta", attrs={"name": re.compile(attr, re.I)})
            if meta and meta.get("content"):
                return meta["content"]
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.endswith(".pdf") or "/pdf/" in href.lower():
                return urllib.parse.urljoin(r.url, href)
    except Exception:
        pass
    return None


# ── Entry-point classifier ─────────────────────────────────────────────────────

# Strict arXiv: only match real arXiv URLs or bare IDs, not arbitrary DOIs
ARXIV_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)")
ARXIV_ID_RE = re.compile(r"^([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)$")
DOI_RE = re.compile(r"(10\.\d{4,}/[^\s]+)")
BIORXIV_RE = re.compile(r"(bio|med)rxiv\.org")
OPENREVIEW_RE = re.compile(r"openreview\.net.*[?&]id=([^&\s]+)")


def classify(entry: str) -> dict:
    entry = entry.strip()
    # Must be an actual arXiv URL or a bare arXiv ID (not just any number pattern)
    if m := ARXIV_RE.search(entry):
        return {"type": "arxiv", "id": m.group(1).split("v")[0]}
    if m := ARXIV_ID_RE.match(entry):
        return {"type": "arxiv", "id": m.group(1).split("v")[0]}
    if OPENREVIEW_RE.search(entry):
        oid = OPENREVIEW_RE.search(entry).group(1)
        return {"type": "openreview", "id": oid}
    if BIORXIV_RE.search(entry):
        doi = DOI_RE.search(entry)
        return {"type": "biorxiv", "url": entry, "doi": doi.group(1) if doi else None}
    if m := DOI_RE.search(entry):
        return {"type": "doi", "doi": m.group(1)}
    if entry.lower().endswith(".pdf"):
        return {"type": "direct_pdf", "url": entry}
    if entry.startswith("http"):
        return {"type": "url", "url": entry}
    return {"type": "unknown", "raw": entry}


# ── Main fetcher ───────────────────────────────────────────────────────────────

def fetch_entry(entry: str, out_dir: Path, pdf_id: str | None = None) -> tuple[bool, str]:
    """Fetch a single entry. Returns (success, message) — prints nothing."""
    info = classify(entry)
    kind = info["type"]
    pdf_url = None

    if kind == "arxiv":
        pdf_url = resolve_arxiv(info["id"])

    elif kind == "openreview":
        pdf_url = f"https://openreview.net/pdf?id={info['id']}"

    elif kind == "biorxiv":
        base = re.sub(r"\?.*", "", info["url"])
        pdf_url = base + ".full.pdf" if not base.endswith(".pdf") else base

    elif kind == "doi":
        doi = info["doi"]
        pdf_url = resolve_unpaywall(doi)
        if not pdf_url:
            pdf_url = resolve_semantic_scholar(doi)
        if not pdf_url:
            pdf_url = resolve_europe_pmc(doi)
        if not pdf_url:
            pdf_url = resolve_doi_page(doi)

    elif kind == "direct_pdf":
        pdf_url = info["url"]

    elif kind == "url":
        # For general URLs: sniff page, then try Semantic Scholar by URL
        pdf_url = sniff_page_for_pdf(info["url"])
        if not pdf_url:
            pdf_url = resolve_semantic_scholar(info["url"])
        # If the URL contains a DOI, try DOI resolvers too
        if not pdf_url:
            doi_match = DOI_RE.search(info["url"])
            if doi_match:
                doi = doi_match.group(1)
                pdf_url = resolve_unpaywall(doi)
                if not pdf_url:
                    pdf_url = resolve_europe_pmc(doi)

    else:
        return False, f"could not classify: {entry}"

    if not pdf_url:
        return False, f"no PDF found: {entry}"

    # Use id if provided, otherwise use a default naming scheme
    filename = f"{pdf_id}.pdf" if pdf_id else "untitled.pdf"
    dest = out_dir / filename
    ok = download_pdf(pdf_url, dest)
    if ok:
        return True, f"saved: {dest.name}"
    else:
        if dest.exists():
            dest.unlink()
        return False, f"download failed: {entry}"


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Download PDFs from URLs or DOIs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "inputs", nargs="+",
        help="DOIs, URLs, arXiv IDs, or a .txt file (one per line)"
    )
    parser.add_argument(
        "--out", "-o", default="./downloaded_papers",
        help="Output directory (default: ./downloaded_papers)"
    )
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="Seconds to wait between requests (default: 1.0)"
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    for inp in args.inputs:
        p = Path(inp)
        if p.exists() and p.suffix in (".txt", ".csv", ""):
            entries += [l.strip() for l in p.read_text().splitlines() if l.strip()]
        else:
            entries.append(inp)

    for i, entry in enumerate(entries):
        if i > 0:
            time.sleep(args.delay)
        fetch_entry(entry, out_dir, idx=i)

    print("finished")


if __name__ == "__main__":
    main()