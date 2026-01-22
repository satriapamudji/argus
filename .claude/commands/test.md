# Test Skill

Run tests for the Argus codebase.

## Usage

```
/test [filter]
```

## Examples

- `/test` - Run all tests
- `/test crypto` - Run crypto-related tests
- `/test validator` - Run validator tests

## Running Tests

The test environment requires the venv at `/opt/argus/.venv`:

```bash
source /opt/argus/.venv/bin/activate
cd /opt/argus/app
python -m pytest tests/ -v --tb=short
```

## Specific Test Files

### Crypto tests
```bash
source /opt/argus/.venv/bin/activate
python -m pytest tests/test_bundle_selector_crypto.py tests/test_scoring_crypto.py -v --tb=short
```

### Validator tests
```bash
source /opt/argus/.venv/bin/activate
python -m pytest tests/test_validator.py -v --tb=short
```

### Schema tests
```bash
source /opt/argus/.venv/bin/activate
python -m pytest tests/test_bundle_schema.py -v --tb=short
```

### Daemon tests
```bash
source /opt/argus/.venv/bin/activate
python -m pytest tests/test_daemon.py -v --tb=short
```

## Quick Validation Test

Test a specific fix without full pytest:

```bash
source /opt/argus/.venv/bin/activate && python3 -c "
from decimal import Decimal
import re

# Test decimal formatting
val = Decimal('-6.6E-7')
formatted = format(val, 'f')
pattern = r'^-?\d+(\.\d+)?$'
matches = bool(re.match(pattern, formatted))
print(f'Value: {formatted}, Matches schema: {matches}')
"
```

## Test Database

Tests use the same Neon database. Some tests are marked `xfail` for rate limit resilience.

## Important Notes

1. Always activate venv first: `source /opt/argus/.venv/bin/activate`
2. Run from `/opt/argus/app` directory
3. Some adapter tests hit live APIs (CoinGecko, Binance) - may be rate limited
4. Total test count: ~591 tests
