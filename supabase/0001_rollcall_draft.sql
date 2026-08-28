-- ============================================================================
-- 0001_rollcall_draft.sql
-- DRAFT - NOT APPLIED. Blocked on the owner decision recorded in README
-- (a 4th Supabase project costs $10/mo; alternatives listed).
-- Draft-then-apply: Lance applies.
--
-- EqualShares "The Roll Call" - Postgres mirror of the SQLite pipeline store
-- (data/rollcall.db) plus the supabase-rls-wall module applied in full
-- (F:/RapidForge/modules/supabase-rls-wall.md). Written for a DEDICATED NEW
-- Supabase project (owner option A in README). If option B
-- (schema-in-existing) is chosen, the ALTER DEFAULT PRIVILEGES block below
-- MUST NOT run as-is - see the trap 6.3 note at that block.
--
-- Re-runnable: create table if not exists; drop view if exists then create;
-- the seed uses on conflict do nothing.
--
-- Type mapping from the SQLite contract: TEXT -> text, REAL -> numeric,
-- INTEGER counts/bytes -> bigint, AUTOINCREMENT PK -> bigint generated always
-- as identity, pipeline-owned timestamps -> timestamptz. Source-supplied date
-- strings (period_of_report, filed_at, meeting_date) stay text: the pipeline
-- owns their normalization and the tri-valued rule forbids the database
-- coercing raw values. Tightening to date is a candidate at apply time.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. START FROM DENY - "revoke is the wall; RLS is the door".
-- Supabase auto-grants new public-schema tables to anon AND authenticated,
-- including FUTURE tables (rls-wall trap 6.2). Reset the baseline, then grant
-- back explicitly per surface. Functions and sequences are revoked separately
-- (trap 6.9: revoke on tables does not touch functions).
--
-- Trap 6.3 (do not bundle the repo-wide default-privileges change with
-- targeted revokes) DOES NOT APPLY HERE, deliberately: that caveat protects
-- LIVE projects whose existing public surface depends on anon grants. This is
-- a dedicated new project whose entire posture is set from empty in this one
-- reviewed file, which is exactly the new-build case the module says the
-- default-privileges reset is correct for.
-- ----------------------------------------------------------------------------
alter default privileges in schema public revoke all on tables from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;
alter default privileges in schema public revoke all on functions from anon, authenticated;
revoke all on all tables in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
revoke all on all functions in schema public from anon, authenticated;

-- ----------------------------------------------------------------------------
-- 2. TABLES - mirror of the SQLite contract. Lowercase snake_case throughout.
-- ----------------------------------------------------------------------------
create table if not exists filers (
  cik text primary key,
  name text not null,
  registrant_type text,
  added_at timestamptz not null
);

create table if not exists filings (
  accession text primary key,
  cik text not null references filers(cik),
  form text not null,
  period_of_report text,
  filed_at text,
  series_name text,
  primary_doc text,
  vote_doc_name text,
  vote_doc_type text,
  vote_doc_url text,
  index_url text,
  raw_path text not null,
  raw_sha256 text not null,
  raw_bytes bigint not null,
  fetched_at timestamptz not null
);

create table if not exists engine_runs (
  engine_run_id text primary key,
  engine_version text not null,
  code_fingerprint text not null,
  config_hash text not null,
  created_at timestamptz not null,
  git_commit text  -- trace only, NEVER part of the id (extractor-provenance trap 6.2)
);

create table if not exists vote_records (
  id bigint generated always as identity primary key,
  accession text not null references filings(accession),
  seq bigint not null,
  issuer_name text,
  cusip text,
  isin text,
  meeting_date text,
  category_type text,
  vote_description text,
  shares_voted numeric,
  shares_on_loan numeric,
  how_voted_raw text,
  -- Normalization enum is exactly this set; anything else stays raw-only
  -- (tri-valued rule: unparseable = raw kept, normalized NULL).
  how_voted text check (how_voted is null or how_voted in ('FOR','AGAINST','ABSTAIN','WITHHOLD')),
  mgmt_rec_raw text,
  mgmt_rec text check (mgmt_rec is null or mgmt_rec in ('FOR','AGAINST','ABSTAIN','WITHHOLD')),
  vote_series text,
  source_url text not null,
  -- FK added beyond the SQLite DDL: it makes extractor-provenance acceptance
  -- 7.1 (no orphan engine ids) mechanical. Safe because the pipeline inserts
  -- the engine_runs row before any vote_record (contract order).
  engine_run_id text not null references engine_runs(engine_run_id),
  extracted_at timestamptz not null,
  -- The UPSERT target for re-parse (gate G5). Its leading column also serves
  -- as the vote_records.accession FK index.
  unique (accession, seq)
);

create table if not exists skip (
  accession text primary key,
  attempt_count bigint not null,
  last_attempt timestamptz,
  last_error text
);

create table if not exists terminal (
  accession text primary key,
  reason text not null check (reason <> ''),  -- retired without a reason = retired without being understood
  retired_at timestamptz not null
);

create table if not exists ingest_runs (
  run_id bigint generated always as identity primary key,
  started_at timestamptz,
  finished_at timestamptz,
  exit_status bigint,
  sources_total bigint,
  sources_ok bigint,
  sources_failed bigint,
  notes text
);

create table if not exists publication_config (
  key text primary key,
  value text
);

-- on conflict do nothing ON PURPOSE: config is operator-owned, so a re-run of
-- this file must not clobber an edited value. (This is not the trap-6.5 case -
-- that trap is about re-parse corrections, and vote_records upserts.)
insert into publication_config (key, value) values ('thin_n', '5')
on conflict (key) do nothing;

-- ----------------------------------------------------------------------------
-- 3. FK AND QUERY INDEXES - Postgres does not index FK columns automatically.
-- vote_records.accession is already covered by unique(accession, seq).
-- ----------------------------------------------------------------------------
create index if not exists filings_cik_idx on filings (cik);
create index if not exists vote_records_engine_run_id_idx on vote_records (engine_run_id);
create index if not exists vote_records_category_type_idx on vote_records (category_type);

-- ----------------------------------------------------------------------------
-- 4. RLS EVERYWHERE. Base tables are PRIVATE/internal: no grants, no policies
-- (the sealed posture). Zero policies is deliberate - the wall is the revoke
-- in section 1; the pipeline writes via the service role, which bypasses RLS.
-- No policy here calls an auth function; if one is ever added it MUST wrap the
-- call as (select auth.uid()) - the bare per-row form is 100x slower at scale
-- (supabase-postgres-best-practices, security-rls-performance).
-- ----------------------------------------------------------------------------
alter table filers enable row level security;
alter table filings enable row level security;
alter table engine_runs enable row level security;
alter table vote_records enable row level security;
alter table skip enable row level security;
alter table terminal enable row level security;
alter table ingest_runs enable row level security;
alter table publication_config enable row level security;

-- ----------------------------------------------------------------------------
-- 5. PUBLIC READ VIEWS - the only anon surface.
-- security_invoker = off ON PURPOSE. Trap 6.10 says views do not inherit
-- base-table RLS; here that is the mechanism, not the bug: the definer view IS
-- the wall's one door, and the base tables stay unreadable. The Supabase
-- advisor will flag definer views - this is the deliberate exception, and the
-- probe must therefore check ROWS, not just columns (trap 6.4).
-- public_votes bakes in no ORDER BY: PostgREST callers must pass a
-- deterministic order (static-publication-site 5.1.3) or Range paging drops
-- and duplicates rows across page boundaries.
-- ----------------------------------------------------------------------------
drop view if exists public_votes;
create view public_votes with (security_invoker = off) as
select v.accession, v.seq, v.issuer_name, v.cusip, v.isin, v.meeting_date,
       v.category_type, v.vote_description, v.shares_voted, v.shares_on_loan,
       v.how_voted, v.how_voted_raw, v.mgmt_rec, v.mgmt_rec_raw, v.vote_series,
       v.source_url, v.engine_run_id
from vote_records v;

-- ANTI-BLEND (locked decision): per-category rows ONLY. No ALL row, no grand
-- total, ever - the real filing is ~73% director elections, so a blended
-- number measures nothing. thin_n comes from publication_config, never
-- hardcoded. Column names votes_for etc. because for/against collide with SQL
-- keywords; the JSON export names (FOR/AGAINST/...) are the site's contract,
-- this view is its own surface.
drop view if exists public_category_rollup;
create view public_category_rollup with (security_invoker = off) as
with cfg as (
  select coalesce((select nullif(value, '')::bigint
                     from publication_config where key = 'thin_n'), 5) as thin_n
), per_cat as (
  select category_type as category,
         count(*) as n,
         count(*) filter (where how_voted = 'FOR')      as votes_for,
         count(*) filter (where how_voted = 'AGAINST')  as votes_against,
         count(*) filter (where how_voted = 'ABSTAIN')  as votes_abstain,
         count(*) filter (where how_voted = 'WITHHOLD') as votes_withhold,
         count(*) filter (where how_voted is null)      as votes_other,
         sum(shares_voted) as shares_voted_total,
         count(*) filter (where how_voted is not null and mgmt_rec is not null) as n_comparable,
         count(*) filter (where how_voted is not null and mgmt_rec is not null
                            and how_voted = mgmt_rec) as with_mgmt
  from vote_records
  group by category_type
)
select p.category,
       nullif(trim(both '-' from regexp_replace(lower(coalesce(p.category, '')),
                                                '[^a-z0-9]+', '-', 'g')), '') as slug,
       p.n, p.votes_for, p.votes_against, p.votes_abstain, p.votes_withhold,
       p.votes_other, p.shares_voted_total, p.n_comparable, p.with_mgmt,
       case when p.n_comparable = 0 then null
            else round(100.0 * p.with_mgmt / p.n_comparable, 1) end as with_mgmt_pct,
       (p.n_comparable < c.thin_n) as thin
from per_cat p cross join cfg c
order by p.n desc;

-- Receipt fields, verbatim from ingest time. The site renders these exactly
-- and never constructs a URL.
drop view if exists public_filing;
create view public_filing with (security_invoker = off) as
select f.accession, f.cik, fl.name as filer_name, f.form, f.filed_at,
       f.period_of_report, f.series_name, f.vote_doc_name, f.vote_doc_type,
       f.vote_doc_url, f.index_url, f.raw_sha256, f.raw_bytes, f.fetched_at
from filings f
join filers fl on fl.cik = f.cik;

-- Filed / fetched / extracted times + the engine that produced the extraction
-- (latest extraction per filing, via lateral - deterministic tiebreak on id).
drop view if exists public_freshness;
create view public_freshness with (security_invoker = off) as
select f.accession, f.cik, f.filed_at, f.fetched_at,
       vr.extracted_at, vr.engine_run_id
from filings f
left join lateral (
  select v.extracted_at, v.engine_run_id
  from vote_records v
  where v.accession = f.accession
  order by v.extracted_at desc, v.id desc
  limit 1
) vr on true;

grant select on public_votes, public_category_rollup, public_filing, public_freshness
  to anon, authenticated;

-- ----------------------------------------------------------------------------
-- 6. SELF-TEST (LinkedUmp 99_verify style). Must print OK; any assert aborts
-- the transaction, so a partially-applied wall cannot pass silently.
-- ----------------------------------------------------------------------------
do $$
declare
  t text;
  v text;
  r text;
  p text;
begin
  for t in select c.relname from pg_class c
             join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = 'public' and c.relkind = 'r'
  loop
    assert (select c2.relrowsecurity from pg_class c2
              join pg_namespace n2 on n2.oid = c2.relnamespace
             where n2.nspname = 'public' and c2.relname = t),
      format('RLS off: %s', t);
    foreach r in array array['anon', 'authenticated'] loop
      foreach p in array array['select', 'insert', 'update', 'delete'] loop
        assert not has_table_privilege(r, format('public.%I', t), p),
          format('%s holds %s on base table %s - the wall is missing', r, p, t);
      end loop;
    end loop;
  end loop;
  assert (select count(*) from pg_policies where schemaname = 'public') = 0,
    'expected zero policies: base tables are sealed and the wall is the revoke';
  foreach v in array array['public_votes', 'public_category_rollup',
                           'public_filing', 'public_freshness'] loop
    assert has_table_privilege('anon', format('public.%I', v), 'select'),
      format('anon missing select on %s - the front door is bricked (check 7.3)', v);
  end loop;
  assert (select value from publication_config where key = 'thin_n') is not null,
    'thin_n not seeded in publication_config';
  raise notice '0001_rollcall_draft OK - now run the curl probes in the footer comment';
end $$;

-- ----------------------------------------------------------------------------
-- 7. VERIFY FROM OUTSIDE (after apply; substitute PROJECT and ANON).
--
-- Base tables: require HTTP 401 (PostgREST code 42501) on EVERY one.
-- 200 [] is a FAIL - it means anon still holds select and RLS is merely
-- returning no rows (rls-wall traps 6.1 and 6.8; the probe that accepted
-- 200 [] reported green for weeks on a live defect).
--
--   for t in filers filings vote_records engine_runs skip terminal ingest_runs publication_config; do
--     curl -s -o /dev/null -w "$t %{http_code}" "https://PROJECT.supabase.co/rest/v1/$t?select=*&limit=1" -H "apikey: ANON" -H "Authorization: Bearer ANON"; echo
--   done
--
-- Views: require 200 (with rows once data is loaded) under the same anon key.
--
--   for v in public_votes public_category_rollup public_filing public_freshness; do
--     curl -s -o /dev/null -w "$v %{http_code}" "https://PROJECT.supabase.co/rest/v1/$v?select=*&limit=1" -H "apikey: ANON" -H "Authorization: Bearer ANON"; echo
--   done
--
-- Negative test (rls-wall 7.5, scratch project only): alter table filers
-- disable row level security; re-run the base-table loop - it must STILL be
-- 401, proving the revoke holds the door and not the policy. Re-enable after.
-- ----------------------------------------------------------------------------
