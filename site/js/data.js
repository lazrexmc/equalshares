// data.js — the fetch layer for The Roll Call.
//
// One property here is load-bearing (static-publication-site module, trap 6.1,
// found live in VisibleGov): a failed fetch THROWS a typed error. It never
// resolves to anything a caller could mistake for an empty result. A Postgres
// timeout once rendered as an honest-looking "no results" page because a fetch
// primitive fell through to an empty array — this file exists so that can
// never happen here.
//
// Same-origin static JSON only; there is no API key and no config to blank.
// A missing or unparseable file is a loud FetchError naming the path.

export class FetchError extends Error {
  constructor(path, status, detail) {
    super('fetch of ' + path + ' failed: ' + detail);
    this.name = 'FetchError';
    this.path = path;      // the path that failed — callers name it in the error box
    this.status = status;  // HTTP status, or null when the request never completed
    this.detail = detail;  // human-readable cause
  }
}

// Thrown by callers when a file fetched and parsed fine but does not have the
// shape the exporter contract promises. Kept here so every typed data-layer
// error lives in one module.
export class DataShapeError extends Error {
  constructor(message) {
    super(message);
    this.name = 'DataShapeError';
  }
}

// fetchJson(path) -> parsed JSON, or throws FetchError.
// cache: 'no-cache' — the browser must revalidate with the server instead of
// serving a stale cached copy after a re-export (no caching surprises).
export async function fetchJson(path) {
  let resp;
  try {
    resp = await fetch(path, { cache: 'no-cache' });
  } catch (err) {
    throw new FetchError(
      path,
      null,
      'network error (' + (err && err.message ? err.message : String(err)) + ')'
    );
  }

  if (!resp.ok) {
    throw new FetchError(
      path,
      resp.status,
      'HTTP ' + resp.status + (resp.statusText ? ' ' + resp.statusText : '')
    );
  }

  let data;
  try {
    data = await resp.json();
  } catch (err) {
    throw new FetchError(
      path,
      resp.status,
      'response is not valid JSON (' + (err && err.message ? err.message : String(err)) + ')'
    );
  }

  return data;
}
