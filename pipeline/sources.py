"""EqualShares "The Roll Call" - source registry and extraction config.

DATA, not logic (ingestion-pipeline module section 5: "the source registry is
data"). Adding a source is a config line here plus, at most, one adapter.

Two hashes live here conceptually:
  - config_hash() covers CONFIG and is half of the extractor's provenance
    fingerprint (extractor-provenance module). Changing any CONFIG value
    changes engine_run_id, which is the point.
  - The base URLs are deliberately NOT in CONFIG: run_ingest.py overrides them
    for the outage gate, and pointing at a test host must never look like a
    different extractor.
"""

import hashlib
import json
import os

# Every EDGAR request must carry a declared User-Agent (name + contact email).
# Anonymous fetchers get HTTP 403 - verified live 2026-08-28 (DRYRUN_001 Part 2, B4).
EDGAR_UA = "EqualShares/0.1 (lancemccarter1316@hotmail.com)"

# Default EDGAR hosts. run_ingest.py accepts --base-url-data / --base-url-archives
# overrides (the test seam for the outage gate: point both at an unreachable host
# and the runner MUST exit 2).
DEFAULT_BASE_URL_DATA = "https://data.sec.gov"
DEFAULT_BASE_URL_ARCHIVES = "https://www.sec.gov"

# One dict per source, never a branch in code. id is "type:name" and is stable
# forever. enabled: False pauses a source without deleting it.
# Part 2 (spec section 5, 2026-08-30): one registrant files one N-PX per fund
# series (VANGUARD INDEX FUNDS: 108 in one window) or MANY series in one N-PX
# (iShares Trust 29, SPDR SERIES TRUST 45), so "the newest filing" is an
# unstable pointer (README deferred finding 2). series_id pins a source to ONE
# series by the id EDGAR's filing index page carries (S000...; names change
# year to year, ids do not); the adapter walks the registrant's N-PX filings
# newest-first, reads each index page's series rows, and keeps the first
# max_filings that carry the id (series_match, a name fragment, is the
# fallback when no id is given). Extraction is scoped to that series; the raw
# file keeps every series. No match = the source FAILS. It never falls back
# to "newest". The Big Three, each through its S&P 500 index fund, so the
# compare view compares like with like. Registrants verified on EDGAR
# 2026-08-29/30 (iShares Trust 7 N-PX filed 2026-08-28, 180 MB for 29 series;
# SPDR SERIES TRUST 8 filed 2026-08-14; SPDR S&P 500 ETF Trust is a UIT whose
# last N-PX is 2004 and is NOT the State Street source).
SOURCES = [
    {
        "id": "npx:vanguard-index-funds",
        "type": "edgar-npx",
        "enabled": True,
        "cik": "0000036405",              # VANGUARD INDEX FUNDS - an RMIC fund-voting registrant
        "name": "VANGUARD INDEX FUNDS",
        "registrant_type": "RMIC",
        "form": "N-PX",
        "max_filings": 1,
        "series_id": "S000002839",          # Vanguard 500 Index Fund
        "series_match": "Vanguard 500 Index Fund",
    },
    {
        "id": "npx:ishares-trust",
        "type": "edgar-npx",
        "enabled": True,
        "cik": "0001100663",              # iSHARES TRUST (BlackRock)
        "name": "iSHARES TRUST",
        "registrant_type": "RMIC",
        "form": "N-PX",
        "max_filings": 1,
        "series_id": "S000004310",          # iShares Core S&P 500 ETF; 29 series in one N-PX
        "series_match": "iShares Core S&P 500 ETF",
    },
    {
        "id": "npx:spdr-series-trust",
        "type": "edgar-npx",
        "enabled": True,
        "cik": "0001064642",              # SPDR SERIES TRUST (State Street)
        "name": "SPDR SERIES TRUST",
        "registrant_type": "RMIC",
        "form": "N-PX",
        "max_filings": 1,
        "series_id": "S000006983",          # State Street(R) SPDR(R) Portfolio S&P 500(R) ETF; 45 series in one N-PX
        "series_match": "Portfolio S&P 500",
    },
    # The contrast set (DRYRUN_001 decision 3), 2026-08-30. Series ids from the
    # SEC's own ticker file (https://www.sec.gov/files/company_tickers_mf.json:
    # FXAIX, PREIX, SWPPX, AGTHX); registrant names from each CIK's submissions
    # JSON, which the identity check compares against. Three more S&P 500 index
    # funds (like with like) and one active large-cap fund from Capital Group
    # (the contrast). A public pension is NOT here: pensions do not file N-PX
    # vote records (institutional managers file say-on-pay votes only), so that
    # part of decision 3 has no N-PX source - recorded, not built.
    {
        "id": "npx:fidelity-concord-street-trust",
        "type": "edgar-npx",
        "enabled": True,
        "cik": "0000819118",
        "name": "FIDELITY CONCORD STREET TRUST",
        "registrant_type": "RMIC",
        "form": "N-PX",
        "max_filings": 1,
        "series_id": "S000006027",          # Fidelity 500 Index Fund (FXAIX)
        "series_match": "Fidelity 500 Index",
    },
    {
        "id": "npx:t-rowe-price-index-trust",
        "type": "edgar-npx",
        "enabled": True,
        "cik": "0000858581",
        "name": "T. Rowe Price Index Trust, Inc.",
        "registrant_type": "RMIC",
        "form": "N-PX",
        "max_filings": 1,
        "series_id": "S000002089",          # T. Rowe Price Equity Index 500 Fund (PREIX)
        "series_match": "Equity Index 500",
    },
    {
        "id": "npx:schwab-capital-trust",
        "type": "edgar-npx",
        "enabled": True,
        "cik": "0000904333",
        "name": "SCHWAB CAPITAL TRUST",
        "registrant_type": "RMIC",
        "form": "N-PX",
        "max_filings": 1,
        "series_id": "S000005911",          # Schwab S&P 500 Index Fund (SWPPX)
        "series_match": "S&P 500 Index",
    },
    {
        "id": "npx:growth-fund-of-america",
        "type": "edgar-npx",
        "enabled": True,
        "cik": "0000044201",
        "name": "GROWTH FUND OF AMERICA",
        "registrant_type": "RMIC",
        "form": "N-PX",
        "max_filings": 1,
        "series_id": "S000009228",          # The Growth Fund of America (AGTHX), Capital Group; active
        "series_match": "Growth Fund of America",
    },
]

CONFIG = {
    # Normalization enum is exactly {FOR, AGAINST, ABSTAIN, WITHHOLD}:
    # case-insensitive exact match after strip. Anything else - including the
    # known-dirty numeric "1.0"/"2.0"/"3.0" say-on-pay frequency values -
    # normalizes to NULL with the RAW ALWAYS KEPT (tri-valued field state).
    "vote_normalization": {
        "FOR": "FOR",
        "AGAINST": "AGAINST",
        "ABSTAIN": "ABSTAIN",
        "WITHHOLD": "WITHHOLD",
    },
    # managementRecommendation values beyond the vote enum that are still
    # EXTRACTED values (not absent, not unparseable). NONE = "no recommendation"
    # as filed. Cold-read round one, 2026-08-29.
    "mgmt_rec_extra_values": {
        "NONE": "NONE",
    },
    # Fewer than 5 lots that voted shares in a cell is "thin" (VisibleGov
    # precedent). export_site.py reads this; it is part of the behaviour
    # fingerprint because it changes what gets published as a headline. It is
    # also the floor for the managementRecommendation semantics check: a
    # filing whose field carries more than one value on the lots of a single
    # proposal at least thin_n times is not publishing a board's view (a board
    # recommends once per item). The 50% agreement threshold that used to sit
    # here was a typed assumption; the self-contradiction count needs none
    # (cold-read round two, 2026-08-30).
    "thin_n": 5,
    # EDGAR politeness floor: >= 0.5s between requests.
    "request_delay_seconds": 0.5,
    # In-run retries with linear backoff sleep(2 * attempt).
    "retry_attempts": 3,
    # Failed ingest runs before an accession retires to the terminal table
    # (always with a written reason - an empty reason is a ValueError).
    "max_skip_count": 3,
    # The complete submission bundle can be ~20MB; the server ignores Range.
    "http_timeout_seconds": 180,
}


def config_hash():
    """sha256 of the canonical JSON (sorted keys) of CONFIG.

    EXTRACT_CONFIG_PERTURB=1 adds {"_perturb": 1} before hashing - the test
    seam for provenance gate G6: with the env var set the engine_run_id must
    change; with it unset the id must return to the original value.
    """
    cfg = dict(CONFIG)
    if os.environ.get("EXTRACT_CONFIG_PERTURB") == "1":
        cfg["_perturb"] = 1
    canonical = json.dumps(cfg, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    # Handy for the provenance gates: print the current config hash without
    # running an extraction. EXTRACT_CONFIG_PERTURB=1 must change this output.
    print(f"config_hash: {config_hash()}")
    print(f"user_agent:  {EDGAR_UA}")
    print(f"sources:     {len(SOURCES)} ({sum(1 for s in SOURCES if s.get('enabled'))} enabled)")
