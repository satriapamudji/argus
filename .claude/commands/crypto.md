# Crypto Stream Skill

Debug and check the crypto daily stream.

## Usage

```
/crypto [command]
```

## Examples

- `/crypto status` - Check latest crypto run status
- `/crypto debug` - Debug why crypto failed
- `/crypto run` - Manually trigger crypto daily

## Quick Status Check

```bash
source /opt/argus/.venv/bin/activate
python3 scripts/dbquery.py "SELECT id, status, started_at, error_message FROM runs WHERE stream_name='crypto' ORDER BY id DESC LIMIT 5"
```

## Check Today's Crypto Logs

```bash
journalctl -u argus --since today 2>/dev/null | grep -iE "crypto|00:00" | tail -30
```

## Manual Run (Dry Run)

```bash
cd /opt/argus/app
source /opt/argus/.venv/bin/activate
python -m argus run --stream crypto --mode crypto_daily --dry-run
```

## Manual Run (Actual)

```bash
cd /opt/argus/app
source /opt/argus/.venv/bin/activate
python -m argus run --stream crypto --mode crypto_daily
```

## Common Issues

### 1. Bundle Validation Failed
- Check schema.py patterns match actual data formats
- Scientific notation in Decimals (e.g., `-6.6E-7`) won't match `^\d+(\.\d+)?$`
- Fix: Use `format(v, 'f')` instead of `str(v)` for Decimal serialization

### 2. LLM Validation Failed After 5 Attempts
- Check `validator.py` regex patterns
- Watch for section boundary issues (regex too greedy)
- Check hallucination detection thresholds

### 3. News Extraction Issues
- `newspaper4k extracted insufficient content` - usually OK, just a warning
- Some sites block scraping or have paywalls

## Key Files

| File | Purpose |
|------|---------|
| `src/argus/facts_bundle/crypto_builder.py` | Bundle builder |
| `src/argus/generator/prompts_crypto.py` | LLM prompts |
| `src/argus/generator/renderer_crypto.py` | Telegram formatting |
| `src/argus/validator/validator.py` | Output validation |
| `src/argus/facts_bundle/schema.py` | JSON schema |
| `config.yaml` (lines 130-240) | Crypto stream config |

## Schedule

- Runs daily at **00:00 UTC**
- Configured in `config.yaml` under `streams.crypto.schedule.daily_crypto_utc`

## Data Sources

| Source | Data |
|--------|------|
| CoinGecko | Prices, market caps, volumes |
| Alternative.me | Fear & Greed Index |
| DeFiLlama | TVL data |
| Binance FAPI | Funding rates, open interest |
| RSS feeds | News from CoinDesk, The Block, etc. |
