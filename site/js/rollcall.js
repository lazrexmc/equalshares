// rollcall.js — page logic for The Roll Call (EqualShares slice v0).
//
// Load-bearing properties, from the static-publication-site module:
//   - meta.json and rollup.json load in parallel; ANY fetch or parse failure
//     renders a visible error box naming the file that failed — never an
//     empty table (trap 6.1: failure must be distinguishable from emptiness).
//   - All data-derived text lands in textContent / element properties, never
//     innerHTML. No markup is ever built from data.
//   - Slugs come from rollup.json verbatim; this page never derives them.
//   - Receipt URLs come from receipts.js verbatim, or render nothing.
//   - NO blended cross-category number exists anywhere on this page. The
//     anti-blend note is COMPUTED from rollup.json at render time.
//   - Tri-valued fields render honestly: normalized value, or the raw value
//     with a visible mark when normalization failed, or an em dash when the
//     field is absent in the source. Nothing is invented.

import { fetchJson, FetchError, DataShapeError } from './data.js';
import { receiptUrl, filingIndexUrl, filingVoteDocUrl, filingVoteTableUrl } from './receipts.js';

const PATHS = {
  meta: '/data/meta.json',
  rollup: '/data/rollup.json',
  category: (slug) => '/data/category/' + encodeURIComponent(slug) + '.json',
};

const PAGE_SIZE = 100;
const EM_DASH = '—';

const categoryCache = new Map(); // slug -> parsed category JSON (successes only)
let detailState = null;          // { category, records, page }
let thinN = null;                // from meta.thin_n, used in the thin-sample label

// ---------- tiny DOM helpers (textContent only — never innerHTML) ----------

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
  return typeof v === 'number' && isFinite(v) ? v.toLocaleString('en-US') : EM_DASH;
}

function fmtShares(v) {
  return typeof v === 'number' && isFinite(v)
    ? v.toLocaleString('en-US', { maximumFractionDigits: 2 })
    : EM_DASH;
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
      'Failed to load ' + err.path + ' — ' + err.detail +
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
  // Review finding (2026-08-28): filer/filing objects existing is not enough -
  // a meta.json missing filer.name rendered the literal header
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
  const filerLine = $('filer-line');
  filerLine.textContent =
    meta.filer.name +
    ' (CIK ' + meta.filer.cik + ')' +
    ' · Form ' + textOr(meta.filing.form, EM_DASH) +
    ' · period ' + textOr(meta.filing.period_of_report, EM_DASH);
  show(filerLine);

  const fresh = $('freshness-line');
  fresh.textContent =
    'Filed ' + textOr(meta.filing.filed_at, EM_DASH) + ' (SEC)' +
    ' · fetched ' + textOr(meta.filing.fetched_at, EM_DASH) +
    ' · page generated ' + textOr(meta.generated_at, EM_DASH);
  show(fresh);
}

// ---------- provenance box ----------

function provenanceRow(dl, label, valueNode) {
  dl.appendChild(el('dt', null, label));
  const dd = el('dd');
  dd.appendChild(valueNode);
  dl.appendChild(dd);
}

function renderProvenance(meta) {
  const dl = $('provenance-list');
  clear(dl);
  const filing = meta.filing;

  provenanceRow(dl, 'Accession', el('code', null, filing.accession));

  if (typeof filing.series_name === 'string' && filing.series_name) {
    provenanceRow(dl, 'Fund series', el('span', null, filing.series_name));
  }

  // The vote document: name linked to the URL that was actually fetched and
  // parsed, labelled with its stored size. URL comes from receipts.js
  // verbatim; if it is null the name renders as plain text and no link is
  // constructed.
  const voteName = textOr(filing.vote_doc_name, '');
  const voteUrl = filingVoteDocUrl(meta);
  if (voteName || voteUrl) {
    const size = fmtBytes(filing.raw_bytes);
    // Review finding (2026-08-28): when the link opens the complete-submission
    // bundle rather than the named section (the live case: proxytable.xml
    // lives INSIDE the ~18MB .txt), say so - a label naming one document while
    // opening another is a receipt that misdescribes itself. raw_bytes (and
    // the SHA-256 row) describe the EXTRACTED section, not the bundle.
    const urlBase = voteUrl ? voteUrl.split('/').pop() : '';
    const isBundle = Boolean(voteUrl) && voteName && urlBase !== voteName;
    const label = isBundle
      ? 'complete submission — contains ' + voteName +
        (size ? ' (' + size + ' extracted)' : '')
      : (voteName || 'vote document') + (size ? ' (' + size + ')' : '');
    let node;
    if (voteUrl) {
      node = el('a', null, label);
      node.href = voteUrl;
      node.rel = 'noopener';
      node.target = '_blank';
    } else {
      node = el('span', null, label);
    }
    if (typeof filing.raw_bytes === 'number' && isFinite(filing.raw_bytes)) {
      node.title =
        filing.raw_bytes.toLocaleString('en-US') +
        ' bytes of extracted vote-document XML as stored (the SHA-256 below ' +
        'is of this extracted section, not of the bundle)' +
        (filing.vote_doc_type ? ' · type: ' + filing.vote_doc_type : '');
    }
    provenanceRow(dl, 'Vote document', node);
  }

  // The filing's own EDGAR index page — verbatim from meta, or nothing.
  const indexUrl = filingIndexUrl(meta);
  if (indexUrl) {
    const a = el('a', null, 'filing index at SEC EDGAR');
    a.href = indexUrl;
    a.rel = 'noopener';
    a.target = '_blank';
    provenanceRow(dl, 'Filing page', a);
  }

  // Dogfood finding 2 (2026-08-28): the filing index page is a document
  // list, not a place a reader can find a vote. EDGAR renders the proxy
  // table as a searchable HTML page - link it when it was listed.
  const tableUrl = filingVoteTableUrl(meta);
  if (tableUrl) {
    const t = el('a', null, 'EDGAR\u2019s rendered vote table (search it by issuer or CUSIP)');
    t.href = tableUrl;
    t.rel = 'noopener';
    t.target = '_blank';
    provenanceRow(dl, 'Readable table', t);
  }

  if (typeof filing.raw_sha256 === 'string' && filing.raw_sha256) {
    const sha = el('code', null, filing.raw_sha256.slice(0, 12) + '…');
    sha.title = filing.raw_sha256;
    provenanceRow(dl, 'Raw SHA-256', sha);
  }

  const er = meta.engine_run || {};
  if (typeof er.engine_run_id === 'string' && er.engine_run_id) {
    const run = el('code', null, er.engine_run_id);
    const bits = [];
    if (er.engine_version) bits.push('version ' + er.engine_version);
    if (er.code_fingerprint) bits.push('code ' + er.code_fingerprint);
    if (er.config_hash) bits.push('config ' + er.config_hash);
    if (bits.length) run.title = bits.join(' · ');
    provenanceRow(dl, 'Engine run', run);
  }

  const t = meta.totals || {};
  if (typeof t.records === 'number') {
    provenanceRow(
      dl,
      'Totals',
      el(
        'span',
        null,
        fmtInt(t.records) + ' vote records · ' +
        fmtInt(t.categories) + ' categories · ' +
        fmtInt(t.comparable_records) + ' comparable · ' +
        fmtInt(t.unparseable_how_voted) + ' unparseable how-voted values'
      )
    );
  }

  // Multi-category disclosure - COMPUTED from meta, never asserted. A record
  // the filer tagged with several categories is counted under its FIRST
  // category only; this states the rule with the real count beside it.
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

  show($('provenance'));
}

// ---------- category rollup table + anti-blend note ----------

function thinLabelText() {
  return 'thin sample' + (typeof thinN === 'number' ? ' (n<' + thinN + ')' : '');
}

function renderRollup(rollup) {
  const cats = rollup && Array.isArray(rollup.categories) ? rollup.categories : null;
  if (!cats) {
    throw new DataShapeError(
      PATHS.rollup + ' has no categories array — the export step did not ' +
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

  // rollup.json is exported sorted n desc; sort defensively so the display
  // honours the contract even if the file was regenerated out of order.
  const sorted = cats.slice().sort((a, b) => (b.n || 0) - (a.n || 0));

  // Anti-blend note — COMPUTED from rollup.json at render time, never typed.
  const total = sorted.reduce((sum, c) => sum + (typeof c.n === 'number' ? c.n : 0), 0);
  const largest = sorted[0];
  if (total > 0 && largest && typeof largest.n === 'number') {
    const pct = Math.round((100 * largest.n) / total);
    const note = $('anti-blend');
    note.textContent =
      pct + '% of this filing’s records are ' + largest.category +
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
    tr.appendChild(el('td', 'num', fmtInt(cat.n)));
    tr.appendChild(el('td', 'num', fmtInt(v.FOR)));
    tr.appendChild(el('td', 'num', fmtInt(v.AGAINST)));
    tr.appendChild(el('td', 'num', fmtInt(v.ABSTAIN)));
    tr.appendChild(el('td', 'num', fmtInt(v.WITHHOLD)));
    // Tri-valued honesty: unparseable (raw kept, normalization failed) and
    // absent-in-source are DIFFERENT states (locked decision 5); the old
    // single OTHER column conflated them and visibly contradicted the totals.
    tr.appendChild(el('td', 'num', fmtInt(v.UNPARSEABLE)));
    tr.appendChild(el('td', 'num', fmtInt(v.ABSENT)));
    tr.appendChild(el('td', 'num', fmtInt(cat.n_comparable)));

    // % voted with management — plain cell text, never headline-styled.
    // thin=true gets a visible label beside the value.
    const pctCell = el('td', 'num');
    if (cat.with_mgmt_pct === null || cat.with_mgmt_pct === undefined) {
      pctCell.textContent = EM_DASH;
      pctCell.title = 'No comparable records (both sides normalized) in this category.';
    } else {
      pctCell.appendChild(el('span', null, cat.with_mgmt_pct + '%'));
      if (cat.thin) {
        const flag = el('span', 'thin-flag', thinLabelText());
        flag.title =
          'Fewer than ' + (typeof thinN === 'number' ? thinN : 'the threshold') +
          ' comparable records — too few to treat as a headline.';
        pctCell.appendChild(flag);
      }
    }
    tr.appendChild(pctCell);

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

// ---------- category detail: fetch, page, render ----------

let openSeq = 0; // review finding (2026-08-28): last click must win

async function openCategory(cat) {
  const seq = ++openSeq;
  const detail = $('category-detail');
  const heading = $('detail-heading');
  const errBox = $('detail-error');
  const body = $('detail-body');

  hide(errBox);
  hide(body);
  heading.textContent = cat.category + ' — loading…';
  show(detail);

  // Slugs come from rollup.json only. If one is missing, that is an export
  // defect and this page says so instead of deriving a slug itself.
  if (typeof cat.slug !== 'string' || cat.slug.length === 0) {
    heading.textContent = cat.category;
    clear(errBox);
    errBox.appendChild(el('strong', null, 'Could not load the records for this category.'));
    errBox.appendChild(el('p', null,
      'rollup.json carries no slug for “' + cat.category + '”. ' +
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
        throw new DataShapeError(path + ' has no records array — the export step did not produce a usable category file.');
      }
      if (data.records.length === 0) {
        throw new DataShapeError(
          path + ' contains zero records for a category rollup.json says has ' +
          fmtInt(cat.n) + ' — refusing to render an empty table for a broken export.'
        );
      }
      // Review finding (2026-08-28): a truncated or mixed-version category
      // file used to render silently under a rollup from a different export.
      // The file must agree with rollup.json's declared count - both its own
      // header n and its actual record count.
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

  detailState = {
    category: textOr(data.category, cat.category),
    records: data.records,
    page: 0,
  };

  heading.textContent =
    detailState.category + ' — ' + fmtInt(detailState.records.length) + ' records';
  renderDetailPage();
  show(body);
  detail.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// One cell for a tri-valued vote field: normalized value, or the raw value
// with a visible mark when normalization failed, or an em dash when the
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
      'the filing’s raw value is shown verbatim.';
    td.appendChild(mark);
  } else {
    td.textContent = EM_DASH;
    td.className = 'absent';
    td.title = 'Absent in the source filing.';
  }
  return td;
}

function recordRow(r) {
  const tr = el('tr');

  tr.appendChild(el('td', 'nowrap', textOr(r.meeting_date, EM_DASH)));
  tr.appendChild(el('td', null, textOr(r.issuer_name, EM_DASH)));

  const desc = el('td', 'desc');
  if (typeof r.vote_description === 'string' && r.vote_description.length > 0) {
    desc.textContent = r.vote_description;      // CSS truncates with ellipsis
    desc.title = r.vote_description;            // full text on hover
  } else {
    desc.textContent = EM_DASH;
  }
  tr.appendChild(desc);

  // Proposed by: the filing's voteSource, verbatim (ISSUER / SECURITY
  // HOLDER). Absent -> em dash. No mapping, no relabelling - the footnote
  // explains the vocabulary instead.
  const src2 = el('td', 'nowrap');
  if (typeof r.vote_source === 'string' && r.vote_source.length > 0) {
    src2.textContent = r.vote_source;
  } else {
    src2.textContent = EM_DASH;
    src2.className = 'nowrap absent';
    src2.title = 'Absent in the source filing.';
  }
  tr.appendChild(src2);

  tr.appendChild(voteCell(r.how_voted, r.how_voted_raw));
  tr.appendChild(voteCell(r.mgmt_rec, r.mgmt_rec_raw));
  tr.appendChild(el('td', 'num', fmtShares(r.shares_voted)));

  // Receipt: verbatim stored URL via receipts.js, or nothing at all.
  const src = el('td');
  const url = receiptUrl(r);
  if (url) {
    const a = el('a', null, 'source');
    a.href = url;
    // Tell the reader how to FIND this row once they land there (dogfood
    // finding 2). Data goes into a title attribute via the property, never
    // markup.
    const finder = [
      r.issuer_name ? 'issuer "' + r.issuer_name + '"' : null,
      r.cusip ? 'CUSIP ' + r.cusip : null,
      r.meeting_date ? 'meeting ' + r.meeting_date : null,
    ].filter(Boolean).join(' \u00b7 ');
    a.title = 'Opens EDGAR\u2019s own page for this filing. Search it for ' +
      (finder || 'this proposal') + '.';
    a.rel = 'noopener';
    a.target = '_blank';
    src.appendChild(a);
  }
  tr.appendChild(src);

  return tr;
}

function renderDetailPage() {
  const { records, page } = detailState;
  const start = page * PAGE_SIZE;
  const slice = records.slice(start, start + PAGE_SIZE);

  const tbody = $('detail-tbody');
  clear(tbody);
  for (const r of slice) {
    tbody.appendChild(recordRow(r));
  }

  updatePagers();
}

function updatePagers() {
  const { records, page } = detailState;
  const pages = Math.max(1, Math.ceil(records.length / PAGE_SIZE));
  const first = records.length === 0 ? 0 : page * PAGE_SIZE + 1;
  const last = Math.min(records.length, (page + 1) * PAGE_SIZE);
  const status =
    'Page ' + (page + 1) + ' of ' + pages +
    ' · records ' + fmtInt(first) + '–' + fmtInt(last) +
    ' of ' + fmtInt(records.length);

  document.querySelectorAll('.pager-status').forEach((s) => { s.textContent = status; });
  document.querySelectorAll('.pager-prev').forEach((b) => { b.disabled = page <= 0; });
  document.querySelectorAll('.pager-next').forEach((b) => { b.disabled = page >= pages - 1; });
}

function turnPage(delta) {
  if (!detailState) return;
  const pages = Math.max(1, Math.ceil(detailState.records.length / PAGE_SIZE));
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
        PATHS.meta + ' is missing required fields (filer, filing) — the ' +
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
