# Database Query Skill

Run SQL queries against the Argus Neon PostgreSQL database.

## Usage

```
/db <query or command>
```

## Examples

- `/db show partitions` - List all news_items partitions
- `/db SELECT * FROM runs ORDER BY id DESC LIMIT 5`
- `/db news stats` - Show news item counts and date ranges

## Quick Commands

Use the helper script for common queries:

```bash
source /opt/argus/.venv/bin/activate
python3 scripts/dbquery.py --stats        # News stats
python3 scripts/dbquery.py --partitions   # List partitions
python3 scripts/dbquery.py --runs 10      # Recent runs
python3 scripts/dbquery.py --fingerprints # Fingerprint stats
python3 scripts/dbquery.py "SELECT ..."   # Custom SQL
```

## Connection Details

The database is Neon PostgreSQL. Connection reads from DATABASE_URL in .env file.

For ad-hoc Python queries:

```python
source /opt/argus/.venv/bin/activate && python3 << 'EOF'
import sys
sys.path.insert(0, 'scripts')
from dbquery import get_connection

conn = get_connection()
with conn.cursor() as cur:
    cur.execute("SELECT 1")
    print(cur.fetchall())
conn.close()
EOF
```

## Common Queries

### Show all partitions
```sql
SELECT tablename FROM pg_tables WHERE tablename LIKE 'news_items%' ORDER BY tablename;
```

### News stats per stream
```sql
SELECT
    'us_markets' as stream,
    MIN(ingested_at) as earliest,
    MAX(ingested_at) as latest,
    COUNT(*) as total
FROM news_items_us_markets
UNION ALL
SELECT
    'crypto' as stream,
    MIN(ingested_at) as earliest,
    MAX(ingested_at) as latest,
    COUNT(*) as total
FROM news_items_crypto;
```

### Recent runs
```sql
SELECT id, stream_name, run_mode, status, started_at
FROM runs
ORDER BY id DESC
LIMIT 10;
```

### Check fingerprints
```sql
SELECT COUNT(*), MIN(last_seen_at), MAX(last_seen_at) FROM news_fingerprints;
```

## Important Notes

1. Always use `scripts/dbquery.py` for queries - it handles .env parsing correctly
2. The .env file has Windows line endings - don't `source` it directly in bash
3. The venv is at `/opt/argus/.venv/bin/activate`
4. Tables: `news_items`, `news_items_us_markets`, `news_items_crypto`, `news_fingerprints`, `runs`
5. Partitions are named like `news_items_us_markets_2026_01_22`
6. Retention is set to 60 days for news_items (config.yaml)
