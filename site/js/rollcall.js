// rollcall.js - page logic for The Roll Call (EqualShares slice v0, Part 1 of the
// 2026-08-29 spec: rows are vote lots, no headline rests on managementRecommendation).
//
// Load-bearing properties, from the static-publication-site module:
//   - meta.json and rollup.json load in parallel; ANY fetch or parse failure
//     renders a visible error box naming the file that failed - never an
//     empty table (trap 6.1: failure must be distinguishable from emptiness).
//   - All data-derived text lands in textContent / element properties, never
//     innerHTML. No markup is ever built from data.
//   - Slugs come from rollup.json verbatim; this page never derives them.
//   - Receipt URLs come from receipts.js verbatim, or render nothing.
//   - NO blended cross-category number exists anywhere on this page. The
//     anti-blend note is COMPUTED from rollup.json at render time.
//   - Tri-valued fields render honestly: normalized value, or the raw value
//     with a visible mark when normalization failed, or a plain mark when the
//     field is absent in the source. Nothing is invented.

import { fetchJson, FetchError, DataShapeError } from './data.js';
import { receiptUrl, filingIndexUrl, filingVoteDocUrl, filingVoteTableUrl } from './receipts.js';

const PATHS = {
  meta: '/data/meta.json',
  rollup: '/data/rollup.json',
  category: (slug) => '/data/category/' + encodeURIComponent(slug) + '.json',
};

const PAGE_SIZE = 100;
const ABSENT = '-';

const categoryCache = new Map(); // slug -> parsed category JSON (successes only)
let detailState = null;          // { category, cat, records, view, page, filter }
let thinN = null;                // from meta.thin_n, used in the thin-sample label
let totalRecords = null;         // from meta.totals.records, for "record N of TOTAL"

// ---------- tiny DOM helpers (textContent only - never innerHTML) ----------

function $(id) {
  return document.getElementById(id);
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function show(node) { node.hidden = false; }
function hide(node) { node.hidden = true; }

function clear(node) { node.textContent = ''; }

// ---------- formatting ----------

function fmtInt(v) {
  return typeof v === 'number' && isFinite(v) ? v.toLocaleString('en-US') : ABSENT;
}

function fmtShares(v) {
  return typeof v === 'number' && isFinite(v)
    ? v.toLocaleString('en-US', { maximumFractionDigits: 2 })
    : ABSENT;
}

function fmtBytes(n) {
  if (typeof n !== 'number' || !isFinite(n)) return '';
  if (n >= 1048576) return (n / 1048576).toFixed(1) + ' MB';
  if (n >= 1024) return (n / 1024).toFixed(1) + ' KB';
  return n + ' bytes';
}

function textOr(value, fallback) {
  return typeof value === 'string' && value.length > 0 ? value : fallback;
}

// ---------- error rendering: loud, named, never an empty table ----------

function describeError(err) {
  if (err instanceof FetchError) {
    return (
      'Failed to load ' + err.path + ': ' + err.detail +
      '. Nothing on this page is rendered from a failed fetch.'
    );
  }
  if (err instanceof DataShapeError) {
    return err.message;
  }
  return err && err.message ? err.message : String(err);
}

function renderFatal(err) {
  const box = $('error-box');
  clear(box);
  box.appendChild(el('strong', null, 'This page could not load its data.'));
  box.appendChild(el('p', null, describeError(err)));
  show(box);
}

// ---------- header ----------

function renderHeader(meta) {
  // A meta.json missing filer.name once rendered the literal header
  // "undefined (CIK undefined)". Require the actual strings, loudly.
  for (const [label, v] of [
    ['filer.name', meta.filer.name],
    ['filer.cik', meta.filer.cik],
    ['filing.accession', meta.filing.accession],
  ]) {
    if (typeof v !== 'string' || v.length === 0) {
      throw new DataShapeError(
        '/data/meta.json is missing ' + label + ' - refusing to render a ' +
        'header with invented placeholders.');
    }
  }
  // Cold-read round one: the trust name in the banner and the series name in a
  // box below read as a contradiction. Lead with the fund; name the registrant
  // as what it is.
  const filerLine = $('filer-line');
  const series = textOr(meta.filing.series_name, '');
  filerLine.textContent =
    (series ? 'Fund: ' + series + ', a series of ' : 'Registrant: ') +
    meta.filer.name + ' (CIK ' + meta.filer.cik + ')' +
    ' | Form ' + textOr(meta.filing.form, ABSENT) +
    ' | proxy year ending ' + textOr(meta.filing.period_of_report, ABSENT);
  show(filerLine);

  const fresh = $('freshness-line');
  fresh.textContent =
    'Filed ' + textOr(meta.filing.filed_at, ABSENT) + ' (SEC)' +
    ' | fetched ' + textOr(meta.filing.fetched_at, ABSENT) +
    ' | page generated ' + textOr(meta.generated_at, ABSENT);
  show(fresh);
}

// ---------- provenance box ----------

function provenanceRow(dl, label, valueNode, note) {
  dl.appendChild(el('dt', null, label));
  const dd = el('dd');
  dd.appendChild(valueNode);
  if (note) dd.appendChild(el('span', 'def-note', note));
  dl.appendChild(dd);
}

function link(text, url) {
  const a = el('a', null, text);
  a.href = url;
  a.rel = 'noopener';
  a.target = '_blank';
  return a;
}

function renderProvenance(meta) {
  const dl = $('provenance-list');
  clear(dl);
  const filing = meta.filing;

  provenanceRow(dl, 'Accession', el('code', null, filing.accession),
    'the SEC\'s identifier for this filing');

  if (typeof filing.series_name === 'string' && filing.series_name) {
    const s = el('span', null, filing.series_name +
      (typeof filing.series_id === 'string' && filing.series_id ? ' (' + filing.series_id + ')' : ''));
    provenanceRow(dl, 'Fund series', s, 'the one series this filing covers');
  }

  // The vote document: name linked to the URL that was actually fetched and
  // parsed, labelled with its stored size. URL comes from receipts.js
  // verbatim; if it is null the name renders as plain text and no link is
  // constructed.
  const voteName = textOr(filing.vote_doc_name, '');
  const voteUrl = filingVoteDocUrl(meta);
  if (voteName || voteUrl) {
    const size = fmtBytes(filing.raw_bytes);
    const urlBase = voteUrl ? voteUrl.split('/').pop() : '';
    const isBundle = Boolean(voteUrl) && voteName && urlBase !== voteName;
    const label = isBundle
      ? 'complete submission, containing ' + voteName +
        (size ? ' (' + size + ' extracted)' : '')
      : (voteName || 'vote document') + (size ? ' (' + size + ')' : '');
    let node;
    if (voteUrl) {
      node = link(label, voteUrl);
    } else {
      node = el('span', null, label);
    }
    if (typeof filing.raw_bytes === 'number' && isFinite(filing.raw_bytes)) {
      node.title =
        filing.raw_bytes.toLocaleString('en-US') +
        ' bytes of extracted vote-document XML as stored (the SHA-256 below ' +
        'is of this extracted section, not of the bundle)' +
        (filing.vote_doc_type ? ' | type: ' + filing.vote_doc_type : '');
    }
    provenanceRow(dl, 'Vote document', node);
  }

  // The filing's own EDGAR index page - verbatim from meta, or nothing.
  const indexUrl = filingIndexUrl(meta);
  if (indexUrl) {
    provenanceRow(dl, 'Filing page', link('filing index at SEC EDGAR', indexUrl),
      'where the receipt URLs below were read from at ingest time');
  }

  // Dogfood finding 2 (2026-08-28): the filing index page is a document
  // list, not a place a reader can find a vote. EDGAR renders the proxy
  // table as a searchable HTML page - link it when it was listed.
  const tableUrl = filingVoteTableUrl(meta);
  if (tableUrl) {
    provenanceRow(dl, 'Readable table',
      link('EDGAR\'s rendered vote table (search it by issuer or CUSIP)', tableUrl),
      'the one receipt every row points at');
  }

  // Cold-read round one: a truncated hash is unverifiable as shown. Full value.
  if (typeof filing.raw_sha256 === 'string' && filing.raw_sha256) {
    const sha = el('code', 'hash', filing.raw_sha256);
    provenanceRow(dl, 'Raw SHA-256', sha,
      'hash of the extracted vote-document bytes as stored; recompute it over the ' +
      'document to confirm this page read the same bytes');
  }

  const er = meta.engine_run || {};
  if (typeof er.engine_run_id === 'string' && er.engine_run_id) {
    const run = el('code', null, er.engine_run_id);
    const bits = [];
    if (er.engine_version) bits.push('version ' + er.engine_version);
    if (er.code_fingerprint) bits.push('code ' + er.code_fingerprint);
    if (er.config_hash) bits.push('config ' + er.config_hash);
    if (bits.length) run.title = bits.join(' | ');
    provenanceRow(dl, 'Engine run', run,
      'a fingerprint of the code and configuration that computed every number here; ' +
      'two runs with the same id computed the same way');
  }

  const t = meta.totals || {};
  if (typeof t.records === 'number') {
    totalRecords = t.records;
    provenanceRow(
      dl,
      'Totals',
      el(
        'span',
        null,
        fmtInt(t.records) + ' records (' + fmtInt(t.lots) + ' vote lots + ' +
        fmtInt(t.zero_lot_rows) + ' zero-lot rows) | ' +
        fmtInt(t.proposals) + ' proposals | ' +
        fmtInt(t.categories) + ' categories | ' +
        fmtInt(t.unparseable_how_voted) + ' unparseable how-voted values | ' +
        fmtInt(t.absent_how_voted) + ' absent in source | ' +
        fmtInt(t.zero_share_lots) + ' zero-share lots'
      ),
      'each of these counts is a list: open a category and use "Show"'
    );
  }

  // Multi-category disclosure - COMPUTED from meta, never asserted.
  const multiNote = $('note-multicat');
  if (multiNote && typeof t.multi_category_records === 'number') {
    if (t.multi_category_records > 0) {
      multiNote.textContent =
        fmtInt(t.multi_category_records) + ' of ' + fmtInt(t.records) +
        ' records carry more than one category in the filing. Each is counted ' +
        'under its first-listed category only, so category counts sum exactly ' +
        'to the record total and nothing is counted twice.';
    } else {
      multiNote.hidden = true;
    }
  } else if (multiNote) {
    multiNote.hidden = true;
  }

  // The managementRecommendation semantics check - COMPUTED by the exporter,
  // stated here so a reader knows why no concordance headline exists (or, for
  // a filer whose field is the board's view, that it passed).
  const sem = meta.mgmt_rec_semantics;
  const semLine = $('semantics-line');
  if (sem && typeof sem.verdict === 'string') {
    let text =
      'Check on the filing\'s managementRecommendation field: on shareholder items it agrees ' +
      'with the fund\'s own vote in ' + textOr(sem.agreement, ABSENT) + ' lots';
    if (typeof sem.agreement_pct === 'number') text += ' (' + sem.agreement_pct + '%)';
    text += '; ' + fmtInt(sem.shareholder_lots) + ' shareholder lots in all, ' +
      fmtInt(sem.shareholder_lots_with_recommendation) + ' with a FOR/AGAINST/ABSTAIN/WITHHOLD recommendation. ';
    if (sem.verdict === 'tracks-lot') {
      text += 'A field carrying the board\'s view would agree at least ' +
        fmtInt(sem.min_board_view_pct) + '% of the time, so in this filing the field tracks ' +
        'something else (it varies lot by lot within one proposal). It is shown as filed on each ' +
        'lot, and no headline on this page is computed from it.';
    } else if (sem.verdict === 'board-view') {
      text += 'That meets the threshold of ' + fmtInt(sem.min_board_view_pct) +
        '% for treating the field as the board\'s recommendation.';
    } else {
      text += 'Too few lots to judge (fewer than ' + fmtInt(thinN) + '); the field is shown as ' +
        'filed and nothing rests on it.';
    }
    semLine.textContent = text;
    show(semLine);
  } else {
    hide(semLine);
  }

  show($('provenance'));
}

// ---------- category rollup table + anti-blend note ----------

function thinLabelText() {
  return 'thin' + (typeof thinN === 'number' ? ' (n<' + thinN + ')' : '');
}

function pctCell(cell) {
  // "% FOR" with its numerator and denominator beside it (RapidForge review
  // note 1: the denominator is the first thing a reader asks for).
  const td = el('td', 'num');
  if (!cell || typeof cell !== 'object' || cell.for_pct === null || cell.for_pct === undefined) {
    td.textContent = ABSENT;
    td.title = 'No voted lots in this cell.';
    return td;
  }
  td.appendChild(el('span', null, cell.for_pct + '%'));
  td.appendChild(el('span', 'denom', ' (' + fmtInt(cell.for_lots) + ' of ' + fmtInt(cell.n_voted) + ')'));
  if (cell.thin) {
    const flag = el('span', 'thin-flag', thinLabelText());
    flag.title =
      'Fewer than ' + (typeof thinN === 'number' ? thinN : 'the threshold') +
      ' voted lots: too few to treat as a headline.';
    td.appendChild(flag);
  }
  return td;
}

function renderRollup(rollup) {
  const cats = rollup && Array.isArray(rollup.categories) ? rollup.categories : null;
  if (!cats) {
    throw new DataShapeError(
      PATHS.rollup + ' has no categories array - the export step did not ' +
      'produce a usable rollup.json.'
    );
  }
  if (cats.length === 0) {
    throw new DataShapeError(
      PATHS.rollup + ' contains zero categories. A filing with no categorised ' +
      'records is almost certainly an extraction failure, so this page refuses ' +
      'to render an empty table for it.'
    );
  }

  const sorted = cats.slice().sort((a, b) => (b.n || 0) - (a.n || 0));

  // Anti-blend note - COMPUTED from rollup.json at render time, never typed.
  const total = sorted.reduce((sum, c) => sum + (typeof c.n === 'number' ? c.n : 0), 0);
  const largest = sorted[0];
  if (total > 0 && largest && typeof largest.n === 'number') {
    const pct = Math.round((100 * largest.n) / total);
    const note = $('anti-blend');
    note.textContent =
      pct + '% of this filing\'s records are ' + largest.category +
      '. A single blended number would mostly measure that category, so none is shown.';
    show(note);
  }

  const tbody = $('category-tbody');
  clear(tbody);

  for (const cat of sorted) {
    const tr = el('tr', 'category-row');
    tr.tabIndex = 0;
    tr.setAttribute('role', 'button');
    tr.setAttribute(
      'aria-label',
      'Show all ' + fmtInt(cat.n) + ' records for ' + cat.category
    );

    const nameCell = el('th', null, cat.category);
    nameCell.setAttribute('scope', 'row');
    tr.appendChild(nameCell);

    const v = cat.votes || {};
    tr.appendChild(el('td', 'num', fmtInt(cat.n_proposals)));
    tr.appendChild(el('td', 'num', fmtInt(cat.n_lots)));
    tr.appendChild(el('td', 'num', fmtInt(v.FOR)));
    tr.appendChild(el('td', 'num', fmtInt(v.AGAINST)));
    tr.appendChild(el('td', 'num', fmtInt(v.ABSTAIN)));
    tr.appendChild(el('td', 'num', fmtInt(v.WITHHOLD)));
    tr.appendChild(el('td', 'num', fmtInt(v.UNPARSEABLE)));
    tr.appendChild(el('td', 'num', fmtInt(v.ABSENT)));
    const bs = cat.by_source || {};
    tr.appendChild(pctCell(bs['ISSUER']));
    tr.appendChild(pctCell(bs['SECURITY HOLDER']));

    tr.addEventListener('click', () => openCategory(cat));
    tr.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter' || ev.key === ' ') {
        ev.preventDefault();
        openCategory(cat);
      }
    });

    tbody.appendChild(tr);
  }

  show($('categories'));
}

// ---------- category detail: fetch, filter, page, render ----------

let openSeq = 0; // last click must win

const FILTERS = {
  all: () => true,
  unparseable: (r) => r.how_voted_raw !== null && r.how_voted_raw !== undefined && !r.how_voted,
  absent: (r) => r.how_voted_raw === null || r.how_voted_raw === undefined,
  zero: (r) => r.shares_voted === 0 && typeof r.lot_index === 'number' && r.lot_index >= 1,
  split: (r) => typeof r.lots_in_proposal === 'number' && r.lots_in_proposal > 1,
};

async function openCategory(cat) {
  const seq = ++openSeq;
  const detail = $('category-detail');
  const heading = $('detail-heading');
  const errBox = $('detail-error');
  const body = $('detail-body');

  hide(errBox);
  hide(body);
  heading.textContent = cat.category + ': loading...';
  show(detail);

  if (typeof cat.slug !== 'string' || cat.slug.length === 0) {
    heading.textContent = cat.category;
    clear(errBox);
    errBox.appendChild(el('strong', null, 'Could not load the records for this category.'));
    errBox.appendChild(el('p', null,
      'rollup.json carries no slug for "' + cat.category + '". ' +
      'This page never derives slugs itself, so these records cannot be fetched. ' +
      'Re-run the export step.'));
    show(errBox);
    return;
  }

  const path = PATHS.category(cat.slug);
  let data;
  try {
    if (categoryCache.has(cat.slug)) {
      data = categoryCache.get(cat.slug);
    } else {
      data = await fetchJson(path);
      if (!data || !Array.isArray(data.records)) {
        throw new DataShapeError(path + ' has no records array - the export step did not produce a usable category file.');
      }
      if (data.records.length === 0) {
        throw new DataShapeError(
          path + ' contains zero records for a category rollup.json says has ' +
          fmtInt(cat.n) + ' - refusing to render an empty table for a broken export.'
        );
      }
      if (data.n !== cat.n || data.records.length !== cat.n) {
        throw new DataShapeError(
          path + ' disagrees with rollup.json: file n=' + fmtInt(data.n) +
          ', records=' + fmtInt(data.records.length) + ', rollup n=' +
          fmtInt(cat.n) + ' - mixed export versions; re-run export_site.py.');
      }
      categoryCache.set(cat.slug, data); // cache successes only
    }
  } catch (err) {
    if (seq !== openSeq) return; // a later click superseded this one
    heading.textContent = cat.category;
    clear(errBox);
    errBox.appendChild(el('strong', null, 'Could not load the records for this category.'));
    errBox.appendChild(el('p', null, describeError(err)));
    show(errBox);
    return;
  }

  if (seq !== openSeq) return; // a later click superseded this fetch

  const filterSel = $('state-filter');
  filterSel.value = 'all';
  detailState = {
    category: textOr(data.category, cat.category),
    cat: cat,
    records: data.records,
    view: data.records,
    page: 0,
    filter: 'all',
  };

  heading.textContent =
    detailState.category + ': ' + fmtInt(cat.n_lots) + ' vote lots in ' +
    fmtInt(cat.n_proposals) + ' proposals (' + fmtInt(cat.n) + ' records)';
  renderDetailPage();
  show(body);
  detail.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function applyFilter(name) {
  if (!detailState) return;
  const fn = FILTERS[name] || FILTERS.all;
  detailState.filter = name;
  detailState.view = detailState.records.filter(fn);
  detailState.page = 0;
  renderDetailPage();
}

// One cell for a tri-valued vote field: normalized value, or the raw value
// with a visible mark when normalization failed, or a plain mark when the
// field is absent in the source filing.
function voteCell(normalized, raw) {
  const td = el('td');
  if (typeof normalized === 'string' && normalized.length > 0) {
    td.textContent = normalized;
  } else if (raw !== null && raw !== undefined && String(raw).length > 0) {
    td.appendChild(el('span', 'raw-value', String(raw)));
    const mark = el('span', 'raw-mark', 'raw');
    mark.title =
      'This value could not be normalized to FOR/AGAINST/ABSTAIN/WITHHOLD; ' +
      'the filing\'s raw value is shown verbatim.';
    td.appendChild(mark);
  } else {
    td.textContent = ABSENT;
    td.className = 'absent';
    td.title = 'Absent in the source filing.';
  }
  return td;
}

function recordRow(r, prev) {
  const tr = el('tr');
  // First lot of a proposal on this page gets a visible top rule, so the lots
  // of one proposal read as a group (cold-read round one, F3).
  if (!prev || prev.proposal_no !== r.proposal_no) tr.className = 'proposal-first';

  tr.appendChild(el('td', 'nowrap', textOr(r.meeting_date, ABSENT)));
  tr.appendChild(el('td', null, textOr(r.issuer_name, ABSENT)));

  // Proposal text WRAPS (Lance, 2026-08-30 00:2x CDT: at laptop width the
  // nine-column row clipped at "Mgmt rec" with no visible scrollbar), and the
  // finder sits under it in the same cell so the row fits without a scroll.
  const desc = el('td', 'desc');
  if (typeof r.vote_description === 'string' && r.vote_description.length > 0) {
    desc.appendChild(el('span', null, r.vote_description));
  } else {
    desc.appendChild(el('span', null, ABSENT));
  }
  // Where to find it (cold-read round one, F6; round two: say whose numbers
  // these are): this page's row and proposal numbers, then what to search for
  // in EDGAR's rendered table. Never a claim about EDGAR's own numbering.
  const finder = [];
  if (typeof r.seq === 'number') {
    finder.push('row ' + fmtInt(r.seq) + (totalRecords ? ' of ' + fmtInt(totalRecords) : '') + ' on this page');
  }
  if (typeof r.proposal_no === 'number') finder.push('this page\'s proposal #' + fmtInt(r.proposal_no));
  const search = [
    r.issuer_name ? r.issuer_name : null,
    r.cusip ? 'CUSIP ' + r.cusip : null,
    r.meeting_date ? r.meeting_date : null,
  ].filter(Boolean).join(', ');
  if (search) finder.push('find it in the filing by: ' + search);
  desc.appendChild(el('span', 'finder', finder.join(' | ')));
  tr.appendChild(desc);

  // Proposed by: the filing's voteSource, verbatim (ISSUER / SECURITY HOLDER).
  const src2 = el('td', 'nowrap');
  if (typeof r.vote_source === 'string' && r.vote_source.length > 0) {
    src2.textContent = r.vote_source;
  } else {
    src2.textContent = ABSENT;
    src2.className = 'nowrap absent';
    src2.title = 'Absent in the source filing.';
  }
  tr.appendChild(src2);

  // Lot: "2 of 4" - which block of shares this row is, of how many the fund
  // reported for this proposal. 0 = the proposal was filed with no lots.
  const lot = el('td', 'nowrap lot');
  if (typeof r.lot_index === 'number' && typeof r.lots_in_proposal === 'number') {
    lot.textContent = r.lot_index >= 1
      ? r.lot_index + ' of ' + r.lots_in_proposal
      : 'no lots';
    lot.title = r.lot_index >= 1
      ? 'Lot ' + r.lot_index + ' of ' + r.lots_in_proposal + ' the fund reported for this proposal.'
      : 'The filing lists this proposal with no vote lots.';
  } else {
    lot.textContent = ABSENT;
  }
  tr.appendChild(lot);

  tr.appendChild(voteCell(r.how_voted, r.how_voted_raw));
  tr.appendChild(voteCell(r.mgmt_rec, r.mgmt_rec_raw));
  tr.appendChild(el('td', 'num', fmtShares(r.shares_voted)));

  // Receipt: the verbatim stored URL via receipts.js, or nothing at all.
  const where = el('td', 'nowrap');
  const url = receiptUrl(r);
  if (url) {
    const a = link('source', url);
    a.title = 'Opens EDGAR\'s rendered vote table for this filing (one receipt per filing); ' +
      'search it by the issuer, CUSIP or meeting date shown under the proposal.';
    where.appendChild(a);
  } else {
    where.textContent = ABSENT;
  }
  tr.appendChild(where);

  return tr;
}

function renderDetailPage() {
  const { view, page } = detailState;
  const start = page * PAGE_SIZE;
  const slice = view.slice(start, start + PAGE_SIZE);

  const tbody = $('detail-tbody');
  clear(tbody);
  let prev = null;
  for (const r of slice) {
    tbody.appendChild(recordRow(r, prev));
    prev = r;
  }
  if (slice.length === 0) {
    const tr = el('tr');
    const td = el('td', 'empty-note', 'No records match this filter in ' + detailState.category + '.');
    td.colSpan = 9;
    tr.appendChild(td);
    tbody.appendChild(tr);
  }

  const fs = $('filter-status');
  fs.textContent = detailState.filter === 'all'
    ? ''
    : fmtInt(view.length) + ' of ' + fmtInt(detailState.records.length) + ' records match';

  updatePagers();
  updateScrollHint();
}

// A clipped table throws no console error (PLAYBOOK_DELTA Lesson 8). When the
// table is still wider than its container - phones, narrow windows - say so in
// words above it, because overlay scrollbars are invisible until touched.
function updateScrollHint() {
  const sc = document.querySelector('#detail-body .table-scroll');
  const hint = $('scroll-hint');
  if (!sc || !hint) return;
  hint.hidden = !(sc.scrollWidth > sc.clientWidth + 1);
}

function updatePagers() {
  const { view, page } = detailState;
  const pages = Math.max(1, Math.ceil(view.length / PAGE_SIZE));
  const first = view.length === 0 ? 0 : page * PAGE_SIZE + 1;
  const last = Math.min(view.length, (page + 1) * PAGE_SIZE);
  const status =
    'Page ' + (page + 1) + ' of ' + pages +
    ' | records ' + fmtInt(first) + ' to ' + fmtInt(last) +
    ' of ' + fmtInt(view.length);

  document.querySelectorAll('.pager').forEach((nav) => { nav.hidden = pages <= 1; });
  document.querySelectorAll('.pager .pager-status').forEach((s) => { s.textContent = status; });
  document.querySelectorAll('.pager-prev').forEach((b) => { b.disabled = page <= 0; });
  document.querySelectorAll('.pager-next').forEach((b) => { b.disabled = page >= pages - 1; });
}

function turnPage(delta) {
  if (!detailState) return;
  const pages = Math.max(1, Math.ceil(detailState.view.length / PAGE_SIZE));
  const next = Math.min(pages - 1, Math.max(0, detailState.page + delta));
  if (next === detailState.page) return;
  detailState.page = next;
  renderDetailPage();
  $('detail-heading').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function wirePagers() {
  document.querySelectorAll('.pager-prev').forEach((b) =>
    b.addEventListener('click', () => turnPage(-1))
  );
  document.querySelectorAll('.pager-next').forEach((b) =>
    b.addEventListener('click', () => turnPage(1))
  );
  $('state-filter').addEventListener('change', (ev) => applyFilter(ev.target.value));
  window.addEventListener('resize', updateScrollHint);
}

// ---------- boot ----------

async function main() {
  wirePagers();

  let meta;
  let rollup;
  try {
    [meta, rollup] = await Promise.all([
      fetchJson(PATHS.meta),
      fetchJson(PATHS.rollup),
    ]);
  } catch (err) {
    renderFatal(err);
    return;
  }

  try {
    if (!meta || typeof meta !== 'object' || !meta.filer || !meta.filing) {
      throw new DataShapeError(
        PATHS.meta + ' is missing required fields (filer, filing) - the ' +
        'export step did not produce a usable meta.json.'
      );
    }
    thinN = typeof meta.thin_n === 'number' ? meta.thin_n : null;

    renderHeader(meta);
    renderProvenance(meta);
    renderRollup(rollup);
  } catch (err) {
    renderFatal(err);
  }
}

main();
