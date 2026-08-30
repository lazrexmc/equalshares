// rollcall.js - page logic for The Roll Call (EqualShares slice v0; Part 1 and
// Part 1.1 of the 2026-08-29 spec: rows are vote lots, no headline rests on
// managementRecommendation, every count says what it counts).
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
let totalRecords = null;         // from meta.totals.records, for "row N of TOTAL"
let recVerdict = null;           // from meta.mgmt_rec_semantics.verdict
let totalProposals = null;       // from meta.totals.proposals
let focusProposal = null;        // proposal_no the "one proposal only" filter shows
let multiCatProposals = null;    // from meta.totals.proposals_in_multiple_categories
let rollupBySlug = new Map();    // slug -> category row, for deep links from the semantics line

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
  const filerLine = $('filer-line');
  const series = textOr(meta.filing.series_name, '');
  filerLine.textContent =
    (series ? 'Fund: ' + series + ', a series of ' : 'Registrant: ') +
    meta.filer.name + ' (CIK ' + meta.filer.cik + ')' +
    ' | Form ' + textOr(meta.filing.form, ABSENT) +
    ' | proxy year ending ' + textOr(meta.filing.period_of_report, ABSENT);
  show(filerLine);

  // Round two (league): a stranger would take the headline numbers as the
  // registrant's. Say whose they are, on the line under the name.
  const subject = $('subject-line');
  if (series) {
    subject.textContent =
      'Every number on this page is ' + series + '\'s, not ' + meta.filer.name + '\'s: ' +
      'the registrant files, the series votes.';
    show(subject);
  }

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

  const indexUrl = filingIndexUrl(meta);
  if (indexUrl) {
    provenanceRow(dl, 'Filing page', link('filing index at SEC EDGAR', indexUrl),
      'where the receipt URLs below were read from at ingest time');
  }

  const tableUrl = filingVoteTableUrl(meta);
  if (tableUrl) {
    provenanceRow(dl, 'Readable table',
      link('EDGAR\'s rendered vote table (search it by issuer or CUSIP)', tableUrl),
      'the one receipt every row points at');
  }

  if (typeof filing.raw_sha256 === 'string' && filing.raw_sha256) {
    const sha = el('code', 'hash', filing.raw_sha256);
    provenanceRow(dl, 'Raw SHA-256', sha,
      'hash of the extracted vote-document bytes as stored; recompute it over the ' +
      'document to confirm this page read the same bytes');
  }

  // Engine run: id, formula, and both inputs visible (round two: "a promise
  // with nothing on the page I can check it against").
  const er = meta.engine_run || {};
  if (typeof er.engine_run_id === 'string' && er.engine_run_id) {
    const wrap = el('span');
    wrap.appendChild(el('code', null, er.engine_run_id));
    if (er.code_fingerprint && er.config_hash) {
      wrap.appendChild(el('span', 'def-note',
        '= sha256(code_fingerprint + "|" + config_hash)[0:16]'));
      const c1 = el('code', 'hash', 'code_fingerprint ' + er.code_fingerprint);
      const c2 = el('code', 'hash', 'config_hash ' + er.config_hash);
      wrap.appendChild(el('br'));
      wrap.appendChild(c1);
      wrap.appendChild(el('br'));
      wrap.appendChild(c2);
    }
    provenanceRow(dl, 'Engine run', wrap,
      'a fingerprint of the code and configuration that computed every number here; it ' +
      'changes whenever either changes, and two runs with the same id computed the same way');
  }

  // Configuration: the typed constants, named (round two, R6).
  const cfg = meta.config;
  if (cfg && typeof cfg === 'object') {
    const parts = Object.keys(cfg).sort().map((k) => k + ' = ' + String(cfg[k]));
    provenanceRow(dl, 'Configuration', el('code', null, parts.join(', ')),
      'the only typed numbers that shape this page: cells with fewer lots that voted shares ' +
      'than thin_n are marked thin; the recommendation test below needs at least thin_n ' +
      'self-contradicting proposals before it rules. Part of the engine fingerprint.');
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
        fmtInt(t.zero_lot_rows) + ' proposal filed with no lots) | ' +
        fmtInt(t.proposals) + ' proposals (' + fmtInt(t.proposals_in_multiple_categories) +
        ' of them have lots in more than one category and so appear ' +
        fmtInt(t.extra_category_entries) + ' extra times in the table below) | ' +
        fmtInt(t.issuers) + ' companies by CUSIP | ' +
        fmtInt(t.categories) + ' categories | ' +
        fmtInt(t.unparseable_how_voted) + ' unparseable how-voted values | ' +
        fmtInt(t.absent_how_voted) + ' absent in source | ' +
        fmtInt(t.zero_share_lots) + ' lots of 0 shares (' + fmtInt(t.zero_share_lots_readable) +
        ' with a readable vote, shown in the table\'s brackets; ' +
        fmtInt(t.zero_share_lots_unreadable) + ' without)'
      ),
      'each of these counts is a list: open a category and use "Show"'
    );
  }

  // The spellings finding (round two, league): the most legible evidence on
  // the page that the filing needs reading help. Computed, prominent.
  const sp = $('spellings-line');
  if (typeof t.issuers === 'number' && typeof t.issuer_name_spellings === 'number' &&
      t.issuer_name_spellings > t.issuers) {
    sp.textContent =
      'The filing names its ' + fmtInt(t.issuers) + ' companies (by CUSIP) in ' +
      fmtInt(t.issuer_name_spellings) + ' different spellings (' +
      fmtInt(t.issuers_with_multiple_spellings) + ' companies have more than one). This page ' +
      'groups proposals after ignoring letter case, spacing and trailing punctuation, and shows ' +
      'every name as filed.';
    show(sp);
    wireSpellings();
  } else {
    hide(sp);
  }

  const multiNote = $('note-multicat');
  if (multiNote && typeof t.multi_category_records === 'number' && t.multi_category_records > 0) {
    multiNote.textContent =
      'Separately, ' + fmtInt(t.multi_category_records) + ' of the ' + fmtInt(t.records) +
      ' records carry two category tags on the same lot in the filing; such a lot is listed ' +
      'under its first tag only.';
    multiNote.hidden = false;
  }

  // The managementRecommendation test - COMPUTED by the exporter, stated in
  // reader's words with the evidence and one example a reader can open.
  const sem = meta.mgmt_rec_semantics;
  const semLine = $('semantics-line');
  clear(semLine);
  if (sem && typeof sem.verdict === 'string') {
    recVerdict = sem.verdict;
    let text =
      'Test on the filing\'s managementRecommendation field: a board recommends once per item, ' +
      'so the field should carry one value across all the lots of a proposal. In this filing ' +
      fmtInt(sem.proposals_with_mixed_recommendation) + ' of ' +
      fmtInt(sem.proposals_with_recommendation) +
      ' proposals with a recommendation (' + fmtInt(sem.proposals_without_recommendation) +
      ' proposals have none) carry more than one value across their own lots';
    const ex = sem.example_mixed_proposal;
    if (ex && typeof ex === 'object') {
      text += ' (for example ' + textOr(ex.issuer_name, ABSENT) + ', ' +
        textOr(ex.meeting_date, ABSENT) + ', "' + textOr(ex.vote_description, ABSENT) + '": ' +
        fmtInt(ex.lots) + ' lots carrying ' + (Array.isArray(ex.recommendations) ? ex.recommendations.join(' and ') : ABSENT);
      semLine.appendChild(el('span', null, text + '; '));
      const cat = rollupBySlug.get(ex.category_slug);
      if (cat) {
        const a = el('a', null, 'open its ' + fmtInt(ex.lots) + ' lots');
        a.href = '#category-detail';
        a.addEventListener('click', (ev) => {
          ev.preventDefault();
          focusProposal = ex.proposal_no;
          openCategory(cat, 'proposal');
        });
        semLine.appendChild(a);
      }
      semLine.appendChild(el('span', null, ')'));
      text = '';
    }
    let tail = '';
    if (sem.verdict === 'not-board-view') {
      tail = '. So in this filing the field is not a board\'s recommendation: on shareholder ' +
        'items it agrees with the fund\'s own vote in ' + textOr(sem.agreement, ABSENT) +
        ' lots, and on management items it matches the vote almost everywhere. It is shown as ' +
        'filed on each lot, and no headline on this page is computed from it. ';
    } else if (sem.verdict === 'board-view') {
      tail = '. That is below the configured floor, so the field is treated as the board\'s ' +
        'recommendation in this filing.';
    } else {
      tail = '. Too few lots carry a recommendation to judge; the field is shown as filed and ' +
        'nothing rests on it.';
    }
    semLine.appendChild(el('span', null, text + tail));
    if (sem.verdict === 'not-board-view') {
      semLine.appendChild(el('span', null, 'The full vote-by-recommendation counts are in '));
      semLine.appendChild(link('the page\'s data file (meta.json)', PATHS.meta));
      semLine.appendChild(el('span', null, '; every category\'s "Show" has "proposals whose lots carry more than one recommendation value".'));
    }
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
  // "% FOR" with numerator and denominator beside it, and the zero-share lots
  // that were left out of the denominator named (round two, R4).
  const td = el('td', 'num');
  if (!cell || typeof cell !== 'object' || cell.for_pct === null || cell.for_pct === undefined) {
    td.textContent = ABSENT;
    td.title = 'No lot in this cell voted shares' +
      (cell && cell.zero_share_lots ? ' (' + fmtInt(cell.zero_share_lots) + ' lots of 0 shares)' : '') + '.';
    return td;
  }
  // Round three (league): a percentage of one lot invites a screenshot. Thin
  // cells show their counts and no percentage.
  let denom = fmtInt(cell.for_lots) + ' of ' + fmtInt(cell.n_voted);
  if (cell.zero_share_lots) {
    denom += '; ' + fmtInt(cell.zero_share_lots) + ' of 0 shares left out' +
      (cell.for_zero_share_lots ? ' (' + fmtInt(cell.for_zero_share_lots) + ' of them FOR)' : '');
  }
  if (cell.thin) {
    td.appendChild(el('span', null, denom));
    const flag = el('span', 'thin-flag', thinLabelText());
    flag.title =
      'Fewer than ' + (typeof thinN === 'number' ? thinN : 'the threshold') +
      ' lots that voted shares: too few for a percentage.';
    td.appendChild(flag);
    return td;
  }
  td.appendChild(el('span', null, cell.for_pct + '%'));
  td.appendChild(el('span', 'denom', ' (' + denom + ')'));
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
  rollupBySlug = new Map(sorted.map((c) => [c.slug, c]));

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

  // Round two (LinkedUmp): the Proposals column sums above the distinct total
  // because a proposal is counted in each category its lots fall in. Say so
  // with the numbers, computed.
  const propSum = sorted.reduce((s, c) => s + (typeof c.n_proposals === 'number' ? c.n_proposals : 0), 0);
  const noteP = $('note-proposals');
  if (typeof totalProposals === 'number') {
    noteP.textContent =
      'The Proposals column sums to ' + fmtInt(propSum) + ', which is ' +
      fmtInt(propSum - totalProposals) + ' more than the ' + fmtInt(totalProposals) +
      ' distinct proposals, because a proposal whose lots were filed under more than one ' +
      'category is counted in each (' + fmtInt(multiCatProposals) + ' such proposals, ' +
      'some in three or four categories). Lots are never counted twice: each lot sits under ' +
      'one category, so the Lots column sums exactly to the lot total. ' +
      'Use "Show: proposals with lots in another category" inside any category to see them.';
  } else {
    noteP.textContent =
      'The Proposals column sums to ' + fmtInt(propSum) + '; a proposal whose lots were filed ' +
      'under more than one category is counted in each.';
  }

  const tbody = $('category-tbody');
  clear(tbody);

  for (const cat of sorted) {
    const tr = el('tr', 'category-row');
    tr.tabIndex = 0;
    tr.setAttribute('role', 'button');
    tr.setAttribute(
      'aria-label',
      'Show every lot for ' + cat.category + ' (' + fmtInt(cat.n_lots) + ' lots)'
    );

    const nameCell = el('th', null, cat.category);
    nameCell.setAttribute('scope', 'row');
    tr.appendChild(nameCell);

    const v = cat.votes || {};
    const props = el('td', 'num', fmtInt(cat.n_proposals));
    if (cat.n_proposals_shared) {
      props.title = fmtInt(cat.n_proposals_shared) + ' of these also have lots in another category.';
    }
    tr.appendChild(props);
    const lots = el('td', 'num');
    lots.appendChild(el('span', null, fmtInt(cat.n_lots)));
    if (cat.n_zero_share_lots) {
      lots.appendChild(el('span', 'denom', ' (' + fmtInt(cat.n_zero_share_lots) + ' of 0 shares)'));
      lots.title = fmtInt(cat.n_zero_share_lots) + ' of these lots voted 0 shares.';
    }
    tr.appendChild(lots);
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
  management: (r) => typeof r.vote_source === 'string' && r.vote_source.trim().toUpperCase() === 'ISSUER',
  shareholder: (r) => typeof r.vote_source === 'string' && r.vote_source.trim().toUpperCase() === 'SECURITY HOLDER',
  split: (r) => typeof r.lots_in_proposal === 'number' && r.lots_in_proposal > 1,
  elsewhere: (r) => Array.isArray(r.other_categories) && r.other_categories.length > 0,
  mixed: (r) => r.mixed_recommendation === true,
  proposal: (r) => focusProposal !== null && r.proposal_no === focusProposal,
  zero: (r) => r.shares_voted === 0 && typeof r.lot_index === 'number' && r.lot_index >= 1,
  unparseable: (r) => r.how_voted_raw !== null && r.how_voted_raw !== undefined && !r.how_voted,
  absent: (r) => r.how_voted_raw === null || r.how_voted_raw === undefined,
};

const FILTER_LABEL = {
  all: 'all lots',
  management: 'management items',
  shareholder: 'shareholder items',
  split: 'split proposals',
  elsewhere: 'proposals with lots in another category',
  mixed: 'proposals whose lots carry more than one recommendation value',
  proposal: 'one proposal only',
  zero: 'zero-share lots',
  unparseable: 'unparseable how-voted',
  absent: 'absent in source',
};

async function openCategory(cat, initialFilter) {
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
    if (seq !== openSeq) return;
    heading.textContent = cat.category;
    clear(errBox);
    errBox.appendChild(el('strong', null, 'Could not load the records for this category.'));
    errBox.appendChild(el('p', null, describeError(err)));
    show(errBox);
    return;
  }

  if (seq !== openSeq) return;

  const filterName = initialFilter && FILTERS[initialFilter] ? initialFilter : 'all';
  const sel = $('state-filter');
  const one = sel.querySelector('option[value="proposal"]');
  if (one) one.hidden = filterName !== 'proposal';
  sel.value = filterName;
  detailState = {
    category: textOr(data.category, cat.category),
    cat: cat,
    records: data.records,
    view: data.records,
    page: 0,
    filter: 'all',
  };
  // The mgmt rec column header carries this filing's verdict (round two, R7).
  const th = $('mgmt-rec-th');
  clear(th);
  th.appendChild(el('span', null, 'Mgmt rec '));
  th.appendChild(el('span', 'th-note',
    recVerdict === 'not-board-view' ? '(as filed; not a board\'s view here)'
      : recVerdict === 'board-view' ? '(as filed; a board\'s view here)'
      : '(as filed)'));

  applyFilter(filterName);
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

function updateHeading() {
  // Round two (Glizzness): the heading and the pager must not disagree under
  // a filter. The heading follows the filter.
  const { cat, category, records, view, filter } = detailState;
  let text = category + ': ' + fmtInt(cat.n_lots) + ' vote lots in ' +
    fmtInt(cat.n_proposals) + ' proposals by this page\'s rule (' + fmtInt(cat.n) + ' records)';
  if (filter !== 'all') {
    text += ' - showing ' + fmtInt(view.length) + ' of ' + fmtInt(records.length) +
      ' records: ' + (FILTER_LABEL[filter] || filter) +
      (filter === 'proposal' && focusProposal !== null ? ' #' + fmtInt(focusProposal) : '');
  }
  $('detail-heading').textContent = text;
}

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

  const src2 = el('td', 'nowrap');
  if (typeof r.vote_source === 'string' && r.vote_source.length > 0) {
    src2.textContent = r.vote_source;
  } else {
    src2.textContent = ABSENT;
    src2.className = 'nowrap absent';
    src2.title = 'Absent in the source filing.';
  }
  tr.appendChild(src2);

  // Lot: "2 of 7", and where the other lots are when they were filed under
  // another category (round two: "2 of 3" with no "1 of 3" read as data loss).
  const lot = el('td', 'nowrap lot');
  if (typeof r.lot_index === 'number' && typeof r.lots_in_proposal === 'number') {
    lot.appendChild(el('span', null, r.lot_index >= 1
      ? 'lot ' + r.lot_index + ' of ' + r.lots_in_proposal
      : 'no lots'));
    if (Array.isArray(r.other_categories) && r.other_categories.length > 0) {
      const note = el('span', 'finder', 'others under: ' + r.other_categories.join('; '));
      lot.appendChild(note);
      lot.title = 'This proposal\'s other lots were filed under: ' + r.other_categories.join(', ') + '.';
    } else {
      lot.title = r.lot_index >= 1
        ? 'Lot ' + r.lot_index + ' of ' + r.lots_in_proposal + ' the fund reported for this proposal.'
        : 'The filing lists this proposal with no vote lots.';
    }
  } else {
    lot.textContent = ABSENT;
  }
  tr.appendChild(lot);

  tr.appendChild(voteCell(r.how_voted, r.how_voted_raw));
  const rec = voteCell(r.mgmt_rec, r.mgmt_rec_raw);
  if (recVerdict === 'not-board-view') {
    rec.title = 'As filed. In this filing this field is not the board\'s recommendation ' +
      '(see "Where these numbers come from"); it is shown because the filing carries it.';
  }
  tr.appendChild(rec);
  tr.appendChild(el('td', 'num', fmtShares(r.shares_voted)));

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

  updateHeading();
  updatePagers();
  updateScrollHint();
}

// A clipped table throws no console error (PLAYBOOK_DELTA Lesson 8). When the
// table is still wider than its container - phones, narrow windows - say so in
// words above it, because overlay scrollbars are invisible until touched.
function updateScrollHint() {
  for (const [scSel, hintId] of [
    ['#categories .table-scroll', 'scroll-hint-cats'],
    ['#detail-body .table-scroll', 'scroll-hint'],
  ]) {
    const sc = document.querySelector(scSel);
    const hint = $(hintId);
    if (!sc || !hint) continue;
    hint.hidden = !(sc.scrollWidth > sc.clientWidth + 1);
  }
}

// The spellings list (round three: "622 different spellings - I wanted to see
// them"). Loaded on demand from issuers.json, rendered as text only.
let spellingsLoaded = false;
function wireSpellings() {
  const det = $('spellings-details');
  if (!det) return;
  show(det);
  det.addEventListener('toggle', async () => {
    if (!det.open || spellingsLoaded) return;
    const status = $('spellings-status');
    status.textContent = 'Loading /data/issuers.json ...';
    try {
      const data = await fetchJson('/data/issuers.json');
      const list = $('spellings-list');
      clear(list);
      const multi = (data.issuers || []).filter((i) => Array.isArray(i.spellings) && i.spellings.length > 1);
      for (const i of multi) {
        const li = el('li');
        li.appendChild(el('code', null, i.cusip));
        li.appendChild(el('span', null, ': ' + i.spellings.map((s) => s.name + ' (' + fmtInt(s.lots) + ')').join(' | ')));
        list.appendChild(li);
      }
      status.textContent = fmtInt(multi.length) + ' companies with more than one spelling; ' +
        'each name as filed, with the number of records carrying it.';
      spellingsLoaded = true;
    } catch (err) {
      status.textContent = describeError(err);
    }
  });
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
    const tt = meta.totals || {};
    totalProposals = typeof tt.proposals === 'number' ? tt.proposals : null;
    multiCatProposals = typeof tt.proposals_in_multiple_categories === 'number' ? tt.proposals_in_multiple_categories : null;
    recVerdict = meta.mgmt_rec_semantics && typeof meta.mgmt_rec_semantics.verdict === 'string'
      ? meta.mgmt_rec_semantics.verdict : null;

    renderHeader(meta);
    renderRollup(rollup);      // before provenance: the semantics line links into a category
    renderProvenance(meta);
    updateScrollHint();
  } catch (err) {
    renderFatal(err);
  }
}

main();
