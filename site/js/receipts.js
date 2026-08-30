// receipts.js - the receipts contract (static-publication-site module §5.3).
//
// Every function here returns a URL that was ALREADY STORED with the row or
// filing at ingest time, verbatim, or null. This module never constructs,
// completes, reformats, or guesses a URL - a null means "render nothing",
// and rendering nothing is correct: a guessed receipt would be worse than
// the ambiguity it replaces.

function storedUrl(value) {
  return typeof value === 'string' && value.length > 0 ? value : null;
}

// Per-record receipt: record.source_url is stamped on every vote_record at
// ingest time (the filing's EDGAR index page - a reader can open it and
// reach the voting record). Verbatim or null.
export function receiptUrl(record) {
  if (!record || typeof record !== 'object') return null;
  return storedUrl(record.source_url);
}

// Filing-level receipt: the human-navigable EDGAR filing index page,
// stored verbatim at ingest time in filings.index_url.
export function filingIndexUrl(meta) {
  if (!meta || typeof meta !== 'object' || !meta.filing) return null;
  return storedUrl(meta.filing.index_url);
}

// Filing-level receipt: EDGAR's own rendered, human-readable vote table for
// this filing (the xsl view listed on the filing index page), stored
// verbatim at ingest time in filings.vote_doc_view_url. Null when EDGAR
// listed none.
export function filingVoteTableUrl(meta) {
  if (!meta || typeof meta !== 'object' || !meta.filing) return null;
  return storedUrl(meta.filing.vote_doc_view_url);
}

// Filing-level receipt: the URL that was actually fetched and parsed (the
// sibling vote XML when one existed, else the complete-submission .txt
// bundle), stored verbatim at ingest time in filings.vote_doc_url.
export function filingVoteDocUrl(meta) {
  if (!meta || typeof meta !== 'object' || !meta.filing) return null;
  return storedUrl(meta.filing.vote_doc_url);
}
