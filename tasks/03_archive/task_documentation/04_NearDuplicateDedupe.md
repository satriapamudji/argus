# Task 04: Near-Duplicate Dedupe + Diversity Helpers

## Summary
Implemented SimHash-based near-duplicate detection and topic diversity helpers to prevent near-duplicates and support topic diversity constraints in facts bundle selection.

## Implementation Details

### New Module: `src/argus/dedupe/`

| File | Purpose |
|------|---------|
| `__init__.py` | Module exports |
| `simhash.py` | SimHash computation and Hamming distance |
| `near_duplicate.py` | Database-integrated near-duplicate detection |
| `topics.py` | Heuristic-based topic labeling (10 topics) |
| `diversity.py` | Topic diversity enforcement for selection |

### SimHash Implementation (`simhash.py`)

**Key Functions:**
- `tokenize(text, ngram_size=3)` - Character n-gram tokenization
- `compute_simhash(text)` - Compute 64-bit SimHash signature
- `hamming_distance(hash1, hash2)` - Count differing bits
- `is_near_duplicate(hash1, hash2, threshold=4)` - Check if near-duplicate

**Algorithm:**
1. Tokenize text into character trigrams
2. Hash each token to 64-bit value via MD5
3. For each bit position, sum +1 (bit=1) or -1 (bit=0) across all tokens
4. Final hash: bit i = 1 if sum[i] > 0, else 0

### Near-Duplicate Detection (`near_duplicate.py`)

**Key Functions:**
- `check_near_duplicate(conn, simhash, threshold, window_days)` - Find matching fingerprint
- `find_near_duplicates(conn, simhash, threshold, window_days, limit)` - Find all matches
- `check_title_trigram_similarity(conn, title, similarity_threshold, window_days)` - pg_trgm check

**Database Integration:**
- Queries `news_fingerprints` table for SimHash values
- Respects `window_days` configuration (default 14 days)
- Supports `hamming_threshold` configuration (default 4)

### Topic Labeling (`topics.py`)

**TopicLabel Enum:**
- `MACRO` - Fed, ECB, inflation, GDP, jobs
- `EARNINGS` - Company earnings, guidance
- `GEOPOLITICS` - War, sanctions, trade
- `POLICY` - Regulation, legislation
- `CREDIT` - Credit markets, defaults
- `EQUITIES` - Stock movements, sectors
- `COMMODITIES` - Oil, gold, metals
- `CRYPTO` - Bitcoin, Ethereum
- `TECH` - Technology sector
- `OTHER` - Uncategorized

**Functions:**
- `label_topic(title, snippet, source_name)` - Assign topic via regex keywords
- `get_topic_priority()` - Priority ordering for selection tiebreakers

### Diversity Helpers (`diversity.py`)

**DiversityChecker Class:**
```python
checker = DiversityChecker(max_per_topic=1)
checker.can_add(item)  # Check if violates constraint
checker.add(item)      # Add and track topic count
checker.reset()        # Clear state for new selection round
```

**Selection Functions:**
- `enforce_topic_diversity(items, max_items, max_per_topic)` - Select with constraints
- `select_diverse_items_with_fallback(items, max_items, max_per_topic, fallback)` - Relax if needed
- `compute_diversity_score(items)` - Score 0-1 based on unique topics
- `rank_by_topic_priority(items)` - Secondary ranking by topic importance

### Repository Integration (`repository.py`)

**New Functions:**
- `check_near_duplicate_by_simhash(conn, simhash, threshold, window_days)` - Wrapper
- `get_or_create_fingerprint_with_dedupe(conn, url, source_name, title, snippet, ...)` - Full dedupe flow

**Dedupe Flow:**
1. Check exact URL hash match
2. Compute SimHash if enabled
3. Check for near-duplicates within window
4. Create fingerprint with computed SimHash
5. Return (fingerprint, was_created, near_duplicate_id)

## Configuration

From `config.yaml`:
```yaml
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
```

Already defined in `src/argus/config.py`:
- `SimHashConfig` dataclass
- `TitleTrigramConfig` dataclass
- `DedupeConfig` dataclass

## Test Coverage

**Test File:** `tests/test_dedupe.py`

| Test Class | Tests | Coverage |
|------------|-------|----------|
| TestTokenize | 7 | Basic, short, empty, whitespace, punctuation, case |
| TestComputeSimhash | 5 | Basic, empty, similar, different, deterministic |
| TestHammingDistance | 4 | Identical, one-bit, all-bits, known distance |
| TestIsNearDuplicate | 4 | Identical, within, at, above threshold |
| TestLabelTopic | 12 | All 10 topics + snippet + unknown |
| TestGetTopicPriority | 3 | Dict, highest, lowest |
| TestDiversityChecker | 8 | Add, reject, reset, counts |
| TestEnforceTopicDiversity | 4 | Ranking, diversity, filter, limit |
| TestSelectDiverseWithFallback | 2 | Strict, fallback |
| TestComputeDiversityScore | 4 | Empty, perfect, none, partial |
| TestRankByTopicPriority | 2 | Ranking, preservation |

**Total:** 55 tests (all passing)

## Files Modified/Created

| File | Status |
|------|--------|
| `src/argus/dedupe/__init__.py` | Created |
| `src/argus/dedupe/simhash.py` | Created |
| `src/argus/dedupe/near_duplicate.py` | Created |
| `src/argus/dedupe/topics.py` | Created |
| `src/argus/dedupe/diversity.py` | Created |
| `src/argus/db/repository.py` | Modified |
| `tests/test_dedupe.py` | Created |

## Usage Examples

### Check Near-Duplicate on Ingestion
```python
from argus.dedupe import compute_simhash
from argus.db.repository import get_or_create_fingerprint_with_dedupe

# Compute and check
fingerprint, created, near_dup_id = get_or_create_fingerprint_with_dedupe(
    conn=conn,
    url="https://example.com/article",
    source_name="Example News",
    title="Fed raises rates",
    snippet="The Federal Reserve raised...",
    simhash_enabled=True,
    simhash_threshold=4,
    simhash_window_days=14,
)

if near_dup_id:
    print(f"Near-duplicate of fingerprint {near_dup_id}")
```

### Select Diverse Items
```python
from argus.dedupe import (
    label_topic,
    enforce_topic_diversity,
    NewsItemForDiversity,
)

# Label topics
items = []
for news in candidates:
    topic = label_topic(news.title, news.snippet)
    items.append(NewsItemForDiversity(
        id=news.id,
        topic=topic,
        score=news.impact_score,
    ))

# Select with diversity
selected = enforce_topic_diversity(items, max_items=6, max_per_topic=1)
```

## Verification Results

- **Tests:** 180 passed, 1 skipped
- **Ruff:** All checks passed
- **Mypy:** Success (no issues in dedupe module)

## Dependencies

No new dependencies added. Uses only standard library:
- `hashlib` for MD5 hashing
- `re` for regex patterns
- `enum` for TopicLabel
- `collections.Counter` for topic counting
