"""EDGAR N-PX adapter: submissions JSON -> pick N-PX filings (newest first,
respecting max_filings) -> filing index.json -> select the vote-bearing
document -> return filing metadata + raw XML bytes.

FETCH ONLY - no vote parsing here. extract.py owns parsing, network-free.

Trap 6.8 (ingestion-pipeline module, found live 2026-08-28): the votes are NOT
in primary_doc.xml - that is ~7KB of cover page and signatures which fetches
and parses cleanly with zero vote records, indistinguishable from "this fund
cast no votes." Verified live against the target accession: index.json exposes
ONLY primary_doc.xml plus the complete submission <accession>.txt - no sibling
proxytable.xml even though the SGML header says PUBLIC DOCUMENT COUNT: 2.
So this adapter does BOTH paths:

  (1) enumerate index.json; if a non-primary vote-bearing XML sibling exists
      (some filers expose proxytable*.xml), fetch that;
  (2) OTHERWISE fetch <accession>.txt (the SGML bundle; the server IGNORES
      Range headers - full download, streamed to a temp file, expect up to
      ~20MB), split it on <DOCUMENT>...</DOCUMENT> sections, read each
      section's <TYPE> and <FILENAME> lines, select the section whose TYPE
      identifies the proxy voting record (or whose filename matches
      proxytable*.xml), and extract the XML payload between its <TEXT> and
      </TEXT> markers. Exactly ONE candidate section is required; zero
      candidates raises 'no-vote-document'.

The extracted XML bytes are what gets stored as the raw file - raw_path /
raw_sha256 / raw_bytes all refer to IT, so a re-parse never re-downloads 20MB.

Every request carries the declared User-Agent (anonymous fetchers get HTTP
403) and is followed by a polite delay of >= 0.5s. Raises on HTTP >= 400
(surfacing the error body - urllib discards it otherwise, trap 6.3), on an
empty body, and on zero parsed documents from a non-empty body (trap 6.1: a
dead source must never read as a quiet day).
"""

import gzip
import json
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

_PIPELINE_DIR = Path(__file__).resolve().parent
if str(_PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_DIR))

from sources import CONFIG, EDGAR_UA


class AdapterError(Exception):
    """Any condition that must fail this fetch loudly (never silently empty)."""


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _polite_delay():
    time.sleep(CONFIG["request_delay_seconds"])


def _request(url):
    return urllib.request.Request(url, headers={
        "User-Agent": EDGAR_UA,
        "Accept-Encoding": "gzip",
    })


def _open(url):
    """urlopen with the declared UA. Raises AdapterError on HTTP >= 400 with the
    error body surfaced, and on an unreachable host."""
    try:
        return urllib.request.urlopen(
            _request(url), timeout=CONFIG["http_timeout_seconds"])
    except urllib.error.HTTPError as e:
        body = b""
        try:
            body = e.read()
        except Exception:
            pass
        raise AdapterError(
            f"HTTP {e.code} for {url}: "
            f"{body[:300].decode('utf-8', 'replace')}") from e
    except urllib.error.URLError as e:
        raise AdapterError(f"unreachable: {url} ({e.reason})") from e


def _http_get(url):
    """GET url -> bytes (gzip-decoded if the server compressed). Raises on
    HTTP >= 400 and on an empty body. Polite delay after every request."""
    resp = _open(url)
    with resp:
        if resp.status >= 400:  # belt: urlopen already raises HTTPError for these
            raise AdapterError(f"HTTP {resp.status} for {url}")
        data = resp.read()
        if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
            data = gzip.decompress(data)
    if not data:
        raise AdapterError(f"empty body from {url}")
    _polite_delay()
    return data


def _http_get_to_file(url, dest_path):
    """GET url streamed to dest_path in 1MB chunks - the complete submission can
    be ~20MB and the server ignores Range headers, so never hold it in the HTTP
    response. Returns total bytes written; raises on an empty body."""
    resp = _open(url)
    total = 0
    with resp:
        if resp.status >= 400:
            raise AdapterError(f"HTTP {resp.status} for {url}")
        stream = resp
        if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
            stream = gzip.GzipFile(fileobj=resp)
        with open(dest_path, "wb") as fh:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                total += len(chunk)
    if total == 0:
        raise AdapterError(f"empty body from {url}")
    _polite_delay()
    return total


def list_filings(source, base_url_data):
    """Submissions JSON -> the newest max_filings filings of source['form'].

    Returns {"entity_name": str, "filings": [{accession, form, filed_at,
    period_of_report, primary_doc}, ...]} newest-first.

    Raises AdapterError when the entity has ZERO filings of the requested form:
    a fund-voting registrant with no N-PX is a wrong source or a dead feed, not
    a quiet day (trap 6.1 / 6.6).
    """
    cik10 = source["cik"].zfill(10)
    url = f"{base_url_data}/submissions/CIK{cik10}.json"
    log(f"fetching submissions index: {url}")
    body = _http_get(url)
    try:
        sub = json.loads(body)
    except json.JSONDecodeError as e:
        raise AdapterError(f"submissions JSON did not parse for {url}: {e}") from e

    entity_name = (sub.get("name") or "").strip()
    recent = (sub.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    accessions = recent.get("accessionNumber") or []
    filing_dates = recent.get("filingDate") or []
    report_dates = recent.get("reportDate") or []
    primary_docs = recent.get("primaryDocument") or []

    found = []
    for i, form in enumerate(forms):
        # Review finding (2026-08-28): accept amendments too. An N-PX/A is the
        # filer's own CORRECTION of its voting record; filtering it out is trap
        # 6.5 (corrections silently discarded) operating at the source layer.
        # Newest-first sort below means an amendment naturally supersedes its
        # original under max_filings.
        if form not in (source["form"], source["form"] + "/A"):
            continue
        found.append({
            "accession": accessions[i],
            "form": form,
            "filed_at": filing_dates[i] if i < len(filing_dates) else None,
            "period_of_report": report_dates[i] if i < len(report_dates) else None,
            "primary_doc": primary_docs[i] if i < len(primary_docs) else None,
        })
    if not found:
        raise AdapterError(
            f"zero {source['form']} filings in submissions JSON for CIK "
            f"{source['cik']} ({entity_name or 'unnamed entity'}) - wrong "
            f"source, wrong form, or a dried-up feed; never a quiet day")

    found.sort(key=lambda f: (f["filed_at"] or "", f["accession"]), reverse=True)
    max_filings = int(source.get("max_filings", 1))
    return {"entity_name": entity_name, "filings": found[:max_filings]}


def fetch_filing(source, filing, base_url_archives):
    """One filing -> its metadata plus the raw vote-document XML bytes.

    Returns a dict with: accession, form, filed_at, period_of_report,
    series_name, primary_doc, vote_doc_name, vote_doc_type, vote_doc_url,
    index_url, raw (bytes). vote_doc_url is the URL actually fetched and
    parsed; index_url is the human-navigable filing page (the reader-facing
    receipt) - both stored verbatim at ingest time, never reconstructed later.
    """
    accession = filing["accession"]
    acc_nodash = accession.replace("-", "")
    cik_int = int(source["cik"])
    dir_url = f"{base_url_archives}/Archives/edgar/data/{cik_int}/{acc_nodash}"
    index_url = f"{dir_url}/{accession}-index.html"

    idx_json_url = f"{dir_url}/index.json"
    log(f"enumerating filing documents: {idx_json_url}")
    body = _http_get(idx_json_url)
    try:
        idx = json.loads(body)
    except json.JSONDecodeError as e:
        raise AdapterError(f"index.json did not parse for {idx_json_url}: {e}") from e
    items = ((idx.get("directory") or {}).get("item")) or []
    if not items:
        raise AdapterError(f"zero documents listed in {idx_json_url}")

    primary_doc_lower = (filing.get("primary_doc") or "").lower()

    # Path 1: a non-primary vote-bearing XML sibling (some filers expose
    # proxytable*.xml directly). primary_doc.xml is the cover page: REJECT.
    siblings = []
    for item in items:
        name = (item.get("name") or "").strip()
        low = name.lower()
        if not low or low == primary_doc_lower:
            continue
        item_type = (item.get("type") or "").strip()
        if (low.startswith("proxytable") and low.endswith(".xml")) or \
                ("proxy voting" in item_type.lower()):
            siblings.append((name, item_type))

    if len(siblings) > 1:
        names = ", ".join(n for n, _ in siblings)
        raise AdapterError(
            f"{accession}: expected exactly one vote-bearing sibling in "
            f"index.json, found {len(siblings)}: {names}")

    if len(siblings) == 1:
        name, item_type = siblings[0]
        vote_doc_url = f"{dir_url}/{name}"
        log(f"vote-bearing sibling found: {name} - fetching {vote_doc_url}")
        raw = _http_get(vote_doc_url)
        return {
            "accession": accession,
            "form": filing["form"],
            "filed_at": filing.get("filed_at"),
            "period_of_report": filing.get("period_of_report"),
            # No SGML header on this path, so the series name is absent-in-source.
            "series_name": None,
            "primary_doc": filing.get("primary_doc"),
            "vote_doc_name": name,
            "vote_doc_type": item_type or None,
            "vote_doc_url": vote_doc_url,
            "index_url": index_url,
            "raw": raw,
        }

    # Path 2: the complete submission SGML bundle (the verified-live reality
    # for the target accession: no sibling exposed despite DOCUMENT COUNT: 2).
    txt_url = f"{dir_url}/{accession}.txt"
    log(f"no vote-bearing sibling in index.json - fetching complete submission "
        f"{txt_url} (expect up to ~20MB; Range is ignored by the server)")
    tmp = tempfile.NamedTemporaryFile(
        prefix=f"{acc_nodash}_", suffix=".txt", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()
    try:
        total = _http_get_to_file(txt_url, tmp_path)
        log(f"downloaded {total:,} bytes - splitting SGML <DOCUMENT> sections")
        series_name, doc = _select_vote_document(
            tmp_path.read_bytes(), primary_doc_lower, accession)
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass

    log(f"selected section TYPE={doc['type'] or '?'} "
        f"FILENAME={doc['filename'] or '?'} "
        f"({len(doc['payload']):,} bytes of XML)")
    return {
        "accession": accession,
        "form": filing["form"],
        "filed_at": filing.get("filed_at"),
        "period_of_report": filing.get("period_of_report"),
        "series_name": series_name,
        "primary_doc": filing.get("primary_doc"),
        "vote_doc_name": doc["filename"] or "proxy_voting_record.xml",
        "vote_doc_type": doc["type"] or None,
        "vote_doc_url": txt_url,
        "index_url": index_url,
        "raw": doc["payload"],
    }


def _sgml_line_value(data, tag):
    """The value following <TAG> on its own line, or None. First occurrence
    wins (the contract pins SERIES-NAME to the first SERIES-NAME line)."""
    pos = data.find(tag)
    if pos == -1:
        return None
    start = pos + len(tag)
    end = data.find(b"\n", start)
    if end == -1:
        end = len(data)
    value = data[start:end].strip(b"\r \t")
    return value.decode("utf-8", "replace") if value else None


def _select_vote_document(data, primary_doc_lower, accession):
    """Split the SGML bundle into <DOCUMENT> sections and select the ONE section
    carrying the proxy voting record. Returns (series_name, {type, filename,
    payload}) where payload is the XML bytes between <TEXT> and </TEXT>
    (an <XML>...</XML> wrapper, when present, is stripped).
    """
    # The SGML top header carries <SERIES-NAME> - the specific fund.
    series_name = _sgml_line_value(data, b"<SERIES-NAME>")

    sections = []
    pos = 0
    while True:
        s = data.find(b"<DOCUMENT>", pos)
        if s == -1:
            break
        e = data.find(b"</DOCUMENT>", s)
        if e == -1:
            raise AdapterError(
                f"{accession}: unterminated <DOCUMENT> section in SGML bundle")
        sections.append(data[s:e])
        pos = e + len(b"</DOCUMENT>")
    if not sections:
        raise AdapterError(
            f"{accession}: zero <DOCUMENT> sections in a non-empty SGML bundle")

    parsed = []
    for sec in sections:
        text_at = sec.find(b"<TEXT>")
        header = sec[:text_at] if text_at != -1 else sec
        parsed.append({
            "type": _sgml_line_value(header, b"<TYPE>") or "",
            "filename": _sgml_line_value(header, b"<FILENAME>") or "",
            "section": sec,
            "text_at": text_at,
        })

    candidates = []
    for p in parsed:
        flow = p["filename"].lower()
        if flow and flow == primary_doc_lower:
            continue  # the cover page: REJECT, whatever its TYPE says
        if ("PROXY VOTING" in p["type"].upper()) or \
                (flow.startswith("proxytable") and flow.endswith(".xml")):
            candidates.append(p)

    if len(candidates) == 0:
        seen = ", ".join(
            f"{p['type'] or '?'}/{p['filename'] or '?'}" for p in parsed)
        raise AdapterError(
            f"{accession}: no-vote-document - {len(sections)} <DOCUMENT> "
            f"sections, none identifies a proxy voting record "
            f"(TYPE/FILENAME seen: {seen})")
    if len(candidates) > 1:
        names = ", ".join(
            f"{p['type'] or '?'}/{p['filename'] or '?'}" for p in candidates)
        raise AdapterError(
            f"{accession}: expected exactly ONE vote-bearing section, found "
            f"{len(candidates)}: {names}")

    p = candidates[0]
    if p["text_at"] == -1:
        raise AdapterError(
            f"{accession}: vote-bearing section has no <TEXT> marker")
    sec = p["section"]
    t_start = p["text_at"] + len(b"<TEXT>")
    t_end = sec.find(b"</TEXT>", t_start)
    if t_end == -1:
        raise AdapterError(
            f"{accession}: vote-bearing section has no closing </TEXT>")
    payload = sec[t_start:t_end].strip(b"\r\n\t ")
    if payload.startswith(b"<XML>"):
        payload = payload[len(b"<XML>"):]
        stripped = payload.rstrip(b"\r\n\t ")
        if stripped.endswith(b"</XML>"):
            payload = stripped[:-len(b"</XML>")]
        payload = payload.strip(b"\r\n\t ")
    if not payload:
        raise AdapterError(
            f"{accession}: vote-bearing section <TEXT> payload is empty")
    return series_name, {
        "type": p["type"] or None,
        "filename": p["filename"] or None,
        "payload": payload,
    }
