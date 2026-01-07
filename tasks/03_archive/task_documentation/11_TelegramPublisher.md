# Task 11: Telegram Publisher + Persistence

## Summary
Implemented a Telegram publisher module for sending generated messages via Bot API with retry logic, automatic truncation, and database integration.

## What Was Before
- No publishing capability - messages could be generated and validated but not sent
- No mechanism to track publish status in the database
- No CLI command for publishing

## What Changed

### 1. Publisher Types (`src/argus/publisher/types.py`)

| Type | Purpose |
|------|---------|
| `PublishResult` | Dataclass with: success, telegram_message_id, published_at, error, dry_run, payload, retries, was_truncated, original_length |
| `PublishError` | Exception with metadata: retries, last_status_code, last_response |

### 2. Telegram Publisher (`src/argus/publisher/telegram.py`)

Core class `TelegramPublisher`:

| Method | Purpose |
|--------|---------|
| `publish()` | Send message via Telegram Bot API with retry logic |
| `publish_dry_run()` | Return payload without sending (for testing) |

Key features:
- **Retry strategy**: 3 attempts with exponential backoff (1s, 2s, 4s) on transient errors
- **Transient errors**: 429 (rate limit), 5xx (server), network errors
- **No retry on**: 400 (bad request), 401/403 (auth failures)
- **Truncation**: Messages over 4096 chars truncated with `... [message truncated]` suffix
- **Link preview**: Disabled by default (`disable_web_page_preview=True`)
- **Silent mode**: Optional `disable_notification=True`

Helper functions:

| Function | Purpose |
|----------|---------|
| `run_publish()` | Fetch message from DB, publish, update DB status |
| `publish_content()` | Convenience function for ad-hoc publishing without DB |

### 3. Module Exports (`src/argus/publisher/__init__.py`)

Exports: `TelegramPublisher`, `PublishResult`, `PublishError`, `run_publish`, `publish_content`

### 4. Repository Extensions (`src/argus/db/repository.py`)

Added functions for message retrieval:

| Function | Purpose |
|----------|---------|
| `get_message_by_id(conn, id)` | Fetch single message by ID |
| `get_messages_by_run_id(conn, run_id)` | Fetch all messages for a run |
| `get_pending_messages(conn, limit)` | Fetch messages with `publish_status='pending'` |

### 5. CLI Command (`src/argus/cli.py`)

Added `argus publish` command:

```bash
# Publish from database
argus publish --message-id 123

# Publish from file (testing)
argus publish --file message.txt

# Dry-run mode (show payload without sending)
argus publish --message-id 123 --dry-run

# Silent mode (no notification sound)
argus publish --message-id 123 --silent
```

### 6. Tests (`tests/test_publisher.py`)

21 unit tests covering:
- Publisher initialization
- Context manager usage
- Dry-run mode
- Message truncation (short, long, preserves newlines)
- Successful publishing (mocked httpx)
- API error handling
- Retry on 429 and network errors
- Failure after max retries
- No retry on 400 errors
- Validation (missing token/chat_id)
- PublishResult and PublishError types

## API Design

### TelegramPublisher

```python
from argus.publisher import TelegramPublisher
from argus.config import TelegramConfig

config = TelegramConfig(bot_token="...", chat_id="...")

# Using context manager
with TelegramPublisher(config) as publisher:
    result = publisher.publish("Hello, world!")
    if result.success:
        print(f"Sent! Message ID: {result.telegram_message_id}")
    else:
        print(f"Failed: {result.error}")

# Dry-run
result = publisher.publish_dry_run("Test message", silent=True)
print(result.payload)  # Shows what would be sent
```

### run_publish (with DB)

```python
from argus.publisher import run_publish
from argus.config import TelegramConfig, load_config

config = load_config()
with get_connection() as conn:
    result = run_publish(
        conn=conn,
        message_id=123,
        config=config.telegram,
        dry_run=False,
        silent=False
    )
```

## Database Flow

1. `run_publish()` fetches message by ID
2. Validates message is in publishable state (`validation_status` in ['valid', 'fallback'])
3. Publishes via `TelegramPublisher`
4. Updates `messages` table:
   - `publish_status` → 'published' or 'failed'
   - `published_at` → timestamp (on success)
   - `telegram_message_id` → from API response (on success)

## Files Changed

| File | Change |
|------|--------|
| `src/argus/publisher/types.py` | **NEW** - Type definitions |
| `src/argus/publisher/telegram.py` | **NEW** - Main publisher implementation |
| `src/argus/publisher/__init__.py` | **NEW** - Module exports |
| `src/argus/db/repository.py` | **MODIFIED** - Added message retrieval functions |
| `src/argus/cli.py` | **MODIFIED** - Added `publish` command |
| `tests/test_publisher.py` | **NEW** - Unit tests |

## Testing

```bash
# Run publisher tests
pytest tests/test_publisher.py -v

# Run all tests
pytest
```

## Integration with Task 12 (Orchestrator)

The `run_publish()` function is designed for Task 12 integration:

```python
# In orchestrator pipeline
for message in get_pending_messages(conn, limit=10):
    result = run_publish(conn, message.id, config.telegram)
    if not result.success:
        log.error(f"Publish failed: {result.error}")
```
