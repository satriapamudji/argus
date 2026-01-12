# Task 26: Neon CU Optimization — Reduce Database Compute Usage

## Goal

Reduce Neon Compute Unit (CU) consumption from ~15 CUs in 2 days to a sustainable level for the free/hobby tier. Target: **<5 CUs per day** under normal operation.

## Current Status (2026-01-10)

- **Investigation phase** — CU consumption analysis complete
- Current usage: ~7.5 CUs/day (15 CUs in 2 days)
- Neon free tier: 191.9 CU-hours/month ≈ **6.4 CU-hours/day**
- At current rate: **will exhaust monthly quota in ~25 days**

## Background

### What is a Neon Compute Unit?

Neon CU measures CPU and memory consumption:
- 1 CU = 1 vCPU + 4GB RAM for 1 hour
- Charged per second of active compute
- Auto-suspend after 5 minutes of inactivity (free tier)

### Where CUs Are Consumed

| Activity | Frequency | Est. CU Share |
|----------|-----------|---------------|
| Ingestion (RSS/API fetch + insert) | Every 10 min | 25-35% |
| SimHash near-duplicate detection | Per ingested entry | 20-30% |
| Scoring worker queries | Per orchestration run | 10-15% |
| Connection overhead | Every DB operation | 10-15% |
| Retention/partition cleanup | Daily | 5-10% |
| Ad-hoc queries (health checks) | Every 10 min | 2-5% |

### Root Cause Analysis

**RANK 1 - 🔴 CRITICAL: SimHash Near-Duplicate Detection**
- **Location:** `src/argus/db/repository.py:437-470`
- **Pattern:** Fetches ALL fingerprints in 14-day window, computes Hamming distance in Python
- **Impact:** 1000s of extra rows transferred per day
- **Example:** 1000 fingerprints × 100 entries/day = 100,000 row reads

**RANK 2 - 🔴 CRITICAL: Per-Entry Transaction Overhead**
- **Location:** `src/argus/ingestion/rss_worker.py:131-140`
- **Pattern:** 3-4 queries + 3-4 commits per entry (N+1 anti-pattern)
- **Impact:** 144 ingest runs × 50+ entries = 7000+ commits/day
- **Example:** 100 entries = 400 individual queries instead of 4 batched queries

**RANK 3 - 🔴 CRITICAL: Missing Composite Indexes**
- **Location:** `src/argus/db/migrations/001_initial_schema.sql`
- **Pattern:** Key lookups don't use optimal indexes
- **Missing:**
  - `(stream_name, hash_text)` — used in text hash dedupe
  - `(stream_name, first_seen_at)` — used in near-dup queries
  - `last_seen_at` on fingerprints — used in cleanup

**RANK 4 - 🟡 HIGH: No Connection Pooling**
- **Location:** `src/argus/db/connection.py`
- **Pattern:** Fresh `psycopg2.connect()` per operation
- **Impact:** Connection setup overhead (5-50ms) × 100s of operations/day

**RANK 5 - 🟡 HIGH: Ingestion Frequency**
- **Current:** Every 10 minutes (144 runs/day)
- **Each run:** ~50 entries × 4 queries = 200 queries
- **Daily:** 28,800 queries just for ingestion

## Scope

### Phase 1: Quick Wins (P0) — Est. 40-50% CU Reduction

| Change | File(s) | Est. Savings |
|--------|---------|--------------|
| Reduce ingestion frequency to 20 min | `config.yaml` | 10-15% |
| Add missing indexes | New migration | 10-15% |
| Batch ingestion inserts | `rss_worker.py`, `repository.py` | 15-20% |
| UPSERT fingerprints | `repository.py` | 5-10% |

### Phase 2: Medium Effort (P1) — Est. 20-30% Additional CU Reduction

| Change | File(s) | Est. Savings |
|--------|---------|--------------|
| Disable/optimize SimHash near-dup | `config.yaml`, `repository.py` | 20-30% |
| Connection pooling | `connection.py` | 10-15% |

### Phase 3: Longer Term (P2) — Est. 10-15% Additional CU Reduction

| Change | File(s) | Est. Savings |
|--------|---------|--------------|
| Server-side Hamming distance (PG14+) | `repository.py` | 10-15% |
| Transaction batching refactor | `rss_worker.py`, `scoring/worker.py` | 5-10% |

## Implementation Details

### 1. Reduce Ingestion Frequency (P0)

**File:** `config.yaml`

```yaml
# Before
schedule:
  ingest_interval_minutes: 10

# After
schedule:
  ingest_interval_minutes: 20  # 72 runs/day instead of 144
```

**Trade-off:** News items may be up to 20 minutes stale instead of 10 minutes. Acceptable for daily recap use case.

### 2. Add Missing Indexes (P0)

**File:** `src/argus/db/migrations/006_cu_optimization_indexes.sql`

```sql
BEGIN;

-- Index for text hash lookup (used in check_duplicate_by_text)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fingerprints_stream_hash_text
ON news_fingerprints(stream_name, hash_text)
WHERE hash_text IS NOT NULL;

-- Index for near-duplicate query (used in check_near_duplicate)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fingerprints_stream_first_seen
ON news_fingerprints(stream_name, first_seen_at)
WHERE simhash IS NOT NULL;

-- Index for fingerprint cleanup (used in drop_old_fingerprints)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_fingerprints_last_seen
ON news_fingerprints(last_seen_at);

-- Record migration
INSERT INTO schema_migrations (version) VALUES ('006_cu_optimization_indexes');

COMMIT;
```

### 3. Batch Ingestion Inserts (P0)

**File:** `src/argus/db/repository.py`

```python
# Before: Individual inserts per entry
def insert_news_item(conn, item: NewsItemInsert) -> int:
    cur = conn.cursor()
    cur.execute("INSERT INTO news_items (...) VALUES (%s, %s, ...) RETURNING id", ...)
    conn.commit()
    return cur.fetchone()[0]

# After: Batch insert with executemany or VALUES list
def insert_news_items_batch(conn, items: list[NewsItemInsert]) -> list[int]:
    """Insert multiple news items in a single query."""
    if not items:
        return []

    cur = conn.cursor()
    values = [(item.stream_name, item.fingerprint_id, ...) for item in items]

    # Use execute_values from psycopg2.extras for efficient bulk insert
    from psycopg2.extras import execute_values

    query = """
        INSERT INTO news_items (stream_name, fingerprint_id, source_name, source_url,
                                title, snippet, author, published_at, raw_metadata)
        VALUES %s
        RETURNING id
    """
    result = execute_values(cur, query, values, fetch=True)
    conn.commit()
    return [row[0] for row in result]
```

**File:** `src/argus/ingestion/rss_worker.py`

```python
# Before: Process entries one at a time
for entry in entries:
    check_duplicate_by_url(self.conn, url)
    fp_id = get_or_create_fingerprint(self.conn, ...)
    insert_news_item(self.conn, ...)

# After: Batch processing with pre-check
def ingest_batch(self, entries: list[FeedEntry]) -> IngestionStats:
    # 1. Batch check for existing URLs
    urls = [e.url for e in entries]
    existing_urls = get_existing_urls_batch(self.conn, urls, self.stream_name)

    # 2. Filter to new entries only
    new_entries = [e for e in entries if e.url not in existing_urls]

    # 3. Batch create fingerprints
    fingerprints = create_fingerprints_batch(self.conn, new_entries, self.stream_name)

    # 4. Batch insert news items
    items = [to_news_item_insert(e, fp_id) for e, fp_id in zip(new_entries, fingerprints)]
    insert_news_items_batch(self.conn, items)

    return IngestionStats(new=len(new_entries), duplicates=len(existing_urls))
```

### 4. UPSERT Fingerprints (P0)

**File:** `src/argus/db/repository.py`

```python
# Before: SELECT then conditional INSERT
def get_or_create_fingerprint(conn, stream_name, hash_url, hash_text, ...) -> int:
    cur = conn.cursor()
    cur.execute("SELECT id FROM news_fingerprints WHERE stream_name = %s AND hash_url = %s", ...)
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("INSERT INTO news_fingerprints (...) VALUES (...) RETURNING id", ...)
    conn.commit()
    return cur.fetchone()[0]

# After: Single UPSERT
def get_or_create_fingerprint(conn, stream_name, hash_url, hash_text, ...) -> int:
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO news_fingerprints (stream_name, hash_url, hash_text, simhash, first_seen_at, last_seen_at)
        VALUES (%s, %s, %s, %s, NOW(), NOW())
        ON CONFLICT (stream_name, hash_url)
        DO UPDATE SET last_seen_at = NOW()
        RETURNING id
    """, (stream_name, hash_url, hash_text, simhash))
    conn.commit()
    return cur.fetchone()[0]
```

### 5. Disable/Optimize SimHash Near-Duplicate (P1)

**Option A: Disable entirely (simplest)**

**File:** `config.yaml`

```yaml
deduplication:
  near_duplicate:
    enabled: false  # Was: true
    # simhash_threshold: 4
    # window_days: 14
```

**Option B: Reduce window and threshold**

```yaml
deduplication:
  near_duplicate:
    enabled: true
    simhash_threshold: 3  # Stricter (was 4)
    window_days: 3        # Shorter window (was 14)
```

**Option C: Server-side Hamming (requires PostgreSQL 14+)**

**File:** `src/argus/db/repository.py`

```python
# Check if Neon supports bit_count (PG 14+)
def check_near_duplicate_server_side(conn, stream_name: str, simhash: int, threshold: int, window_days: int) -> bool:
    """Use server-side bit_count for Hamming distance."""
    cur = conn.cursor()
    cur.execute("""
        SELECT 1 FROM news_fingerprints
        WHERE stream_name = %s
          AND first_seen_at >= NOW() - INTERVAL '%s days'
          AND simhash IS NOT NULL
          AND bit_count(simhash::bit(64) # %s::bit(64)) <= %s
        LIMIT 1
    """, (stream_name, window_days, simhash, threshold))
    return cur.fetchone() is not None
```

### 6. Connection Pooling (P1)

**Option A: Use psycopg3 with built-in pooling**

**File:** `src/argus/db/connection.py`

```python
# Before: psycopg2 with fresh connections
import psycopg2

def get_connection():
    return psycopg2.connect(os.environ["DATABASE_URL"])

# After: psycopg3 connection pool
from psycopg_pool import ConnectionPool

_pool: Optional[ConnectionPool] = None

def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            os.environ["DATABASE_URL"],
            min_size=1,
            max_size=5,
            timeout=30,
        )
    return _pool

@contextmanager
def get_connection():
    pool = get_pool()
    with pool.connection() as conn:
        yield conn
```

**Option B: Use PgBouncer (external)**

- Neon supports PgBouncer via connection string parameter
- Add `?pgbouncer=true` to DATABASE_URL
- No code changes needed

### 7. Reduce Health Check Frequency (P0)

**File:** `src/argus/daemon/scheduler.py`

```python
# Before: Health ping every 10 minutes
scheduler.add_job(health_ping, CronTrigger(minute="*/10"))

# After: Health ping every 30 minutes (or disable)
scheduler.add_job(health_ping, CronTrigger(minute="*/30"))
```

## Acceptance Criteria

### Functional

| ID | Criterion | Verification |
|----|-----------|--------------|
| AC-1 | Ingestion runs every 20 minutes | Check scheduler logs |
| AC-2 | Missing indexes created | `\di` in psql shows new indexes |
| AC-3 | Batch insert reduces query count | Verify 1 INSERT per batch, not per entry |
| AC-4 | UPSERT replaces SELECT+INSERT pattern | Code review |
| AC-5 | Near-duplicate check optimized or disabled | Config review |

### Performance

| ID | Criterion | Verification |
|----|-----------|--------------|
| PC-1 | CU usage < 5/day after Phase 1 | Monitor Neon dashboard |
| PC-2 | Ingestion batch processes 50 entries in < 2s | Benchmark |
| PC-3 | No increase in duplicate news items | Compare dedup stats before/after |

### Quality Gates

- [ ] All existing tests pass
- [ ] No regression in news coverage
- [ ] Neon dashboard shows CU reduction
- [ ] No increase in error rates

## Monitoring & Measurement

### Before/After Metrics to Track

| Metric | Before | Target After |
|--------|--------|--------------|
| CU per day | ~7.5 | < 5 |
| Queries per ingest run | ~200 | < 20 |
| Commits per ingest run | ~100 | < 5 |
| Avg query latency | TBD | -50% |

### How to Monitor Neon CU

1. **Neon Dashboard:** Project → Usage → Compute
2. **SQL:** `SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 20;`
3. **Enable pg_stat_statements:** Already available on Neon

## Rollback Plan

Each optimization can be rolled back independently:

| Change | Rollback |
|--------|----------|
| Ingestion frequency | Change config back to 10 min |
| Indexes | `DROP INDEX CONCURRENTLY idx_name` |
| Batch inserts | Revert code, use old per-entry inserts |
| UPSERT | Revert to SELECT+INSERT pattern |
| SimHash disable | Re-enable in config |
| Connection pooling | Revert to psycopg2 direct connections |

## Risks / Notes

### Neon-Specific Considerations

- **Auto-suspend:** Free tier suspends after 5 min inactivity; wake-up takes ~500ms
- **Connection limits:** Free tier = 100 connections; pooling helps
- **Branching:** Can test changes on a branch before main

### Trade-offs

| Optimization | Trade-off |
|--------------|-----------|
| 20-min ingest interval | News up to 20 min stale |
| Disable SimHash | May see more near-duplicate entries |
| Shorter SimHash window | Reduced dedup effectiveness |
| Batch inserts | Slightly more complex error handling |

### PostgreSQL Version Check

```sql
SELECT version();
-- Neon typically runs PG 15+, so bit_count() should be available
```

## Dependencies

- None (standalone optimization task)

## Estimated Effort

| Phase | Component | Estimate |
|-------|-----------|----------|
| P0 | Config changes (interval, SimHash) | 15 min |
| P0 | Migration for indexes | 30 min |
| P0 | Batch inserts + UPSERT | 2-3 hours |
| P1 | Connection pooling | 2 hours |
| P1 | Server-side Hamming (if needed) | 1 hour |
| Testing | Verify CU reduction | 1-2 days monitoring |

**Total: ~6-8 hours implementation + monitoring**

## Recommended Execution Order

1. **Immediate (today):**
   - Change ingestion interval to 20 min
   - Reduce health check frequency
   - Consider disabling SimHash temporarily

2. **This week:**
   - Add missing indexes (migration)
   - Implement batch inserts
   - Implement UPSERT for fingerprints

3. **Next week:**
   - Monitor CU usage
   - Add connection pooling if still high
   - Re-enable SimHash with server-side Hamming if needed
