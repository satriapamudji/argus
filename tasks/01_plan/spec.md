# Argus — US Close Market Update Bot (spec.md)

> Telegram bot that ingests news + prices, scores and curates items, generates a WhatsApp/Telegram-style “Market Update” after US close, and publishes on a schedule (SGT + NY DST-safe). Designed to support multiple streams later.

---

## 1) Overview

**Argus** produces three run types for the initial stream (`us_close_basic`):

- **Mon–Fri 06:00 SGT**: Daily “US Close” update
- **Sat 10:00 SGT**: Weekend Wrap (weekly recap + next week catalysts)
- **Sun 18:10 America/New_York**: Conditional “Monday Preview” (only if major risk week)

Argus uses:
- A DB (Postgres) to store news metadata/content, scoring, and run artifacts (facts bundles + published messages)
- A scoring service (heuristics + lightweight LLM triage) to rank/filter news
- A generator LLM to format the final post **strictly from a JSON facts bundle**
- A validator to prevent hallucinations and enforce formatting

---

## 2) Goals & Non-goals

### Goals
- Consistent, skimmable market updates in a strict format contract.
- DST-safe scheduling by using `America/New_York` for NY-timed triggers.
- Ingest continuously; do **not** stop ingestion for runs.
- Strong dedupe (URL hash + near-duplicate similarity) and topic diversity.
- Store everything needed for replay: selected inputs, facts bundle, generated message, send status.
- Future multi-stream expansion with shared ingestion/scoring core.

### Non-goals (v1)
- Personalized portfolios per user.
- Intraday alerts (later as additional streams).
- Deep historical semantic retrieval (optional later).

### Implementation defaults (v0)
- Language/runtime: Python (>=3.12) for the initial build (simple to run under cron on a VM).
- Deployment: VM-first (system cron + systemd); Docker is optional for local testing/dev.
- Telegram formatting: publish with `parse_mode=MarkdownV2` and a single shared escaping/validation layer.
- Full-text storage: default `allow_full_text_storage: false` until an explicit license exists.
- Market calendar: use the NYSE trading calendar for US holidays + half-days.

---

## 3) Key Design Principles

1) **Facts Bundle is the Source of Truth**
   - Generator LLM may only reference facts inside `facts_bundle.json`.
   - If a detail is missing, omit it (never guess).

2) **Ingestion ≠ Enrichment**
   - Ingestion stores *metadata + snippet* for everything.
   - Full-article content fetching is a separate **enrichment step** applied only to shortlisted items.

3) **Retention without pain**
   - Use **partitioned tables** for high-churn data and drop partitions (TTL).
   - Keep long-lived **fingerprints** (hashes/signatures) so duplicates stay blocked even after old content is deleted.

4) **Two-stage LLM use**
   - Lightweight LLM: labeling + “why it matters” for shortlisted items.
   - Main LLM: final narrative + formatting only.

---

## 4) Scheduling & Timezones (DST-safe)

### Timezones
- Primary user timezone: `Asia/Singapore`
- Market reference timezone: `America/New_York` (must handle DST)

### Jobs
1) **Daily US Close Update**
- Schedule: Mon–Fri **06:00 SGT**
- Window: prior US cash session close (plus last ~18h of relevant news, configurable)

2) **Weekend Wrap**
- Schedule: Sat **10:00 SGT**
- Window: Monday open → Friday close (NY time) + weekend pre-read catalysts

3) **Monday Preview (conditional)**
- Trigger: Sun **18:10 America/New_York** (10 min buffer after futures open at 18:00 NY)
- Publish only if `risk_score >= threshold` (default 60)

### `risk_score` definition (Monday Preview)
`risk_score` is a 0–100 composite used **only** to decide whether to publish the Sunday `monday_preview` run.

Inputs (best-effort; missing inputs contribute 0):
- Calendar events for the next 7 days (macro / central bank / earnings / political).
- Market stress metrics when available (VIX, S&P 500 5-trading-day return, US10Y 5-trading-day bps move).
- High-impact news flags from the last 72 hours.

Computation (cap each component):
1) `calendar_score` (0–60)
   - Central bank decision/press conference: +25
   - CPI/PCE: +20
   - Jobs (NFP/unemployment): +15
   - GDP/ISM/PMI: +10
   - Treasury refunding/auction week: +8
   - Mega-cap earnings (config list): +8 each (cap 24)
   - High-impact political/geopolitical event: +15
2) `market_score` (0–30)
   - VIX: >=20 +10; >=25 +20; >=30 +30
   - S&P 500 5D return: <= -3% +10; <= -5% +20
   - US10Y 5D abs move: >=20 bps +8; >=30 bps +12
3) `headline_score` (0–30)
   - Each news item in last 72h with `impact >= 80` and topic in `{geopolitics, systemic, policy, credit}` adds +10 (cap 30)

Total:
`risk_score = min(100, calendar_score + market_score + headline_score)`

Defaults:
- `threshold=60`
- 5D / 72h windows are based on `America/New_York` time (use the most recent US cash close as the anchor on Sundays).

Persist the breakdown (`calendar_score`, `market_score`, `headline_score`) on the run record and allow config overrides:
- `force_publish` (always publish)
- `force_skip` (never publish)

### Cron examples (timezone-aware)
```cron
CRON_TZ=Asia/Singapore
0 6 * * 1-5 /app/bin/argus run --stream us_close_basic --mode us_close
0 10 * * 6 /app/bin/argus run --stream us_close_basic --mode weekend_wrap

CRON_TZ=America/New_York
10 18 * * 0 /app/bin/argus run --stream us_close_basic --mode monday_preview --conditional true
```

### US Holidays & Half-days
Configurable per stream:
- Source of truth: NYSE trading calendar in `America/New_York` (includes half-days/early closes).
- `holiday_behavior`: `skip` (default) | `publish_closed_note`
- `half_day_behavior`: `label_half_day` (default) | `skip`

---

## 5) Output Format Contract (Telegram-ready)

### Telegram formatting
- Target parse mode: `MarkdownV2`.
- The publisher must escape all MarkdownV2-reserved characters in generated text before sending.
- Links must use `[title](url)` and the `title` must also be MarkdownV2-escaped.

### Required sections & formatting
1) Title line: `*Market Update*`
2) Date line: `*<D Mon YYYY>*` (SG local date label)
3) Index snapshot (3 lines; **US cash close; 1D change vs prior close**):
   - `S&P 500 – <close> (1D <chg_pct>%, <chg_pts> pts)`
   - `Dow Jones – <close> (1D <chg_pct>%, <chg_pts> pts)`
   - `Nasdaq – <close> (1D <chg_pct>%, <chg_pts> pts)`

Optional (workflow-configurable):
- Add a single YTD summary line if provided in the facts bundle:
  - `2026 YTD: S&P <ytd>%, Nasdaq <ytd>%, Dow <ytd>%`

4) Narrative: 2–6 short paragraphs:
   - what happened (risk-on/off, breadth, rotation)
   - key drivers (2–4 only)
   - cross-asset confirmation (rates, USD, oil, gold) when available

5) Separator then takeaways:
   - `----`
   - `*Investor Key Takeaways*`
   - 3–5 bullets max

6) Watch next:
   - `*What to Watch Next*`
   - 3 bullets max

7) Optional spotlight (config-driven):
   - `---`
   - `💡 *Fund Spotlight – <name>*`
   - 2–5 sentences + config disclaimer (compliance-safe)

### Canonical section order (v0; matches `tasks/01_plan/telegram_message.example.md`)
The generator must follow this order (and include `*Key Dates (UTC)*` + `*Sources*` like the example):
1) `*Market Update*`
2) `*<D Mon YYYY>*`
3) Index snapshot (S&P 500 / Dow / Nasdaq)
4) Narrative paragraphs
5) `----`
6) `*Investor Key Takeaways*`
7) `*Key Dates (UTC)*`
8) `*What to Watch Next*`
9) (Optional) fund spotlight block
10) `*Sources*`

### Style rules
- Neutral tone, no hype.
- No invented facts, quotes, or numbers.
- No tickers/events not present in the facts bundle.
- Avoid long blocks: max words per run type are configurable.
- Bullets should be short, one per line (prefer a single bullet prefix like `›` or `•` consistently).

---

## 6) Data Requirements

### Required (daily)
- News citations: each selected news item must have enough metadata to appear under `*Sources*` (source name + URL at minimum).
- Calendar formatting: each catalyst must include a timestamp + timezone label (UTC) for `*Key Dates (UTC)*`.
- Indices: S&P 500, Dow, Nasdaq (level, % chg, point chg)
- News: 2–6 selected items with source + timestamp + URL + summary/why-it-matters
- Calendar: next 3–7 catalysts (macro/earnings/events)

### Optional (recommended)
- Cross-asset: US10Y bps, DXY %, WTI %, Gold %, Silver %
- VIX level/%
- Sector/breadth: best/worst sectors or adv/dec (only from reliable provider)

---

## 7) News Content Strategy (metadata vs full text)

Argus should support **two modes** per source:

### A) Licensed/full-text sources
If your news feed/provider contract permits storing full text:
- Ingest: metadata + snippet
- Enrich: fetch full text for shortlisted items (store clean text)

### B) Non-licensed / restricted sources
If full-text storage is not permitted (or paywalled/scrape-restricted):
- Ingest: metadata + allowed snippet
- Enrich: store only:
  - short excerpt (e.g., first 500–1500 chars) OR provider summary
  - URL for reference
  - structured labels from lightweight LLM

> **Implementation rule:** The system must not depend on full text always being available. It should degrade gracefully with snippet-only analysis.

### When to fetch full content (recommended)
Do **not** fetch full content for all 100–200 items/day unless you have an explicit license and cost is acceptable.

Instead:
1) Ingest all items (metadata/snippet).
2) Run dedupe + initial scoring.
3) Select top `K_enrich` items (e.g., 10–25) for enrichment.
4) Fetch content for those items only.
5) Run lightweight LLM triage using enriched content when available.
6) Build facts bundle from the best 2–6 items.

This avoids rate limits, reduces cost, and keeps the system fast.

---

## 8) Architecture

### Components
1) **Ingestion Workers**
- Pull from sources (RSS/API/manual) on cadence (5–15 min)
- Normalize to `news_items`
- Dedupe by URL hash + similarity signature
- Store to DB (partitioned)

2) **Scoring Service**
- Heuristics scoring + optional lightweight LLM triage
- Outputs `news_scores` (impact, quality, confidence, topic, flags, reasons)

3) **Enrichment Service (content fetcher)**
- Fetches full text for top `K_enrich` items per run window
- Stores `content_status` and `content_hash`
- Retries with backoff; respects robots/ToS and provider limits

4) **Facts Bundle Builder**
- Deterministically selects items with diversity constraints
- Fetches market snapshot + calendar
- Emits `facts_bundle_json` stored on `runs`

5) **Generator LLM**
- Takes facts bundle only
- Outputs final formatted message

6) **Validator**
- Required sections present
- Hallucination guard (no numbers/entities outside bundle)
- Retry once; fallback minimal message if still invalid

7) **Publisher**
- Sends to Telegram
- Stores message content + Telegram message id

8) **Run Orchestrator**
- Coordinates end-to-end run execution
- Writes status, timings, artifacts

---

## 9) Database & Retention Strategy (Postgres)

### Scale note
100–200 news/day is small for Postgres. The bigger reasons for TTL are cleanliness and legal/compliance.

### Recommended retention defaults
- Keep `news_items` partitions for **60 days** (configurable)
- Keep `news_fingerprints` for **1–10 years** (or forever)
- Keep `runs` + `messages` for **1–2 years+** for audit/replay

### Partitioning
Partition `news_items` by day on `ingested_at`.
- Retention job drops old partitions: `DROP TABLE news_items_YYYY_MM_DD;`

### Dedupe & “too similar” prevention (3 layers)
1) **Exact URL hash**
   - `hash_url = sha256(normalized_url)`
   - Unique index on `hash_url`

2) **Exact text/title hash**
   - `hash_text = sha256(normalized_title + normalized_snippet)`

3) **Near-duplicate similarity signature**
   Use at least one:
   - **SimHash** (recommended): store 64-bit signature; treat as duplicate if Hamming distance ≤ 4 (configurable)
   - **pg_trgm title similarity**: simple “too similar title” check

Long-lived fingerprints let you delete daily content while still blocking repeats.

---

## 16) Secrets & Configuration

### 16.1 `.env` (required)
Store secrets and deployment-specific IDs here (never commit to git):

```dotenv
# Telegram
TELEGRAM_BOT_TOKEN=xxxx
TELEGRAM_CHAT_ID=xxxx              # default chat for this stream
TELEGRAM_PARSE_MODE=MarkdownV2     # recommended default

# Database
DATABASE_URL=postgresql://user:pass@host:5432/argus

# Optional
LOG_LEVEL=INFO
```

Notes:
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` must be read from environment at runtime.
- If you later support multiple streams/chats, allow `TELEGRAM_CHAT_ID` to be overridden per-stream in `config.yaml` (still permitted to be an env var reference).

### 16.2 `config.yaml`
`config.yaml` contains **non-secret** stream settings, including the RSS allowlist file(s) that live under the `rss/` folder so feeds are easily extensible.

```yaml
stream:
  name: us_close_basic
  enabled: true

telegram:
  # Prefer env vars; allow optional override per stream
  bot_token_env: TELEGRAM_BOT_TOKEN
  chat_id_env: TELEGRAM_CHAT_ID
  parse_mode_env: TELEGRAM_PARSE_MODE

schedule:
  daily_us_close_sgt: "06:00"
  weekend_wrap_sgt: "10:00"
  monday_preview_ny: "SUN 18:10"

monday_preview:
  conditional: true
  risk_threshold: 60
  force_publish: false
  force_skip: false

retention:
  news_items_days: 60
  fingerprints_days: 3650
  runs_days: 3650

dedupe:
  url_hash: true
  text_hash: true
  simhash:
    enabled: true
    hamming_threshold: 4
    window_days: 14
  title_trigram:
    enabled: true
    similarity_threshold: 0.85

enrichment:
  enabled: true
  max_enrich_per_run: 25
  allow_full_text_storage: false
  snippet_chars: 1200

rss:
  # Whitelisted RSS feeds are defined in files under ./rss so adding feeds is a file edit, not a code change.
  # Each line: URL (optionally "#" comments). Blank lines ignored.
  allowlist_files:
    - "rss/us_close_basic.txt"
  poll_interval_minutes: 10

constraints:
  max_words_daily: 420
  max_words_weekend: 520
  max_words_preview: 320
  max_takeaway_bullets: 5
  max_watch_bullets: 3

spotlight:
  enabled: true
  title: "Lionglobal Singapore Physical Gold Fund"
  body: |
    <config-provided educational copy>
  disclaimer: |
    This material is for information only and does not constitute investment advice.
```

### 16.3 RSS folder layout (extensible)
Recommended repository layout:

```
rss/
  us_close_basic.txt
  # later: crypto_close.txt, asia_open.txt, etc.
```
