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
SOURCES = [
    {
        "id": "npx:vanguard-index-funds",
        "type": "edgar-npx",
        "enabled": True,
        "cik": "0000036405",              # VANGUARD INDEX FUNDS - an RMIC fund-voting registrant
        "name": "VANGUARD INDEX FUNDS",
        "registrant_type": "RMIC",
        "form": "N-PX",
        "max_filings": 1,                  # slice v0: the single most recent N-PX only
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
    # Semantics check for managementRecommendation, computed per filing by
    # export_site.py and published in meta.mgmt_rec_semantics: on shareholder
    # (SECURITY HOLDER) lots, the share of lots whose vote agrees with the
    # filed recommendation. A field that IS the board's view agrees at least
    # this often (funds side with boards on most shareholder proposals);
    # below it the field tracks something else and no headline may rest on it.
    # The Vanguard filing scores 0 of 1,433.
    "mgmt_rec_board_view_min_pct": 50,
    # Fewer than 5 voted lots in a cell is "thin" (VisibleGov precedent).
    # export_site.py reads this; it is part of the behaviour fingerprint
    # because it changes what gets published as a headline.
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
