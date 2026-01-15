# Task 28: Crypto Stream — Experimental Multi-Source Data Integration

## Goal

Create an experimental `crypto` stream for daily cryptocurrency market updates, integrating multiple data sources for:
1. **Price & Market Data** — Top coins, market cap, volume, dominance
2. **On-Chain Metrics** — TVL, exchange flows, whale movements
3. **Sentiment & Derivatives** — Fear/Greed Index, funding rates, open interest
4. **News** — Crypto-specific RSS feeds and news APIs

This is an **experimental stream** to validate data source reliability, API costs, and user engagement before scaling.

## Current Status (2026-01-10)

- **Planning phase** — Data source research complete
- No crypto-specific infrastructure exists yet
- Existing `us_markets` stream architecture can be extended
- Multi-stream support already implemented (Task 21)

## Decisions / Requirements (2026-01-13)

- Recap schedule: run **daily at 00:00 UTC**.
- Trading day definition: **close-to-close by UTC date** (use the day that just ended; `trading_date = (now_utc.date() - 1 day)`).
- Top N: **dynamic top 10 by market cap**, always include **BTC/ETH**, exclude stablecoins (**USDT/USDC/DAI**).
- News ingestion: **RSS only** for the crypto stream (v1).
- Derivatives: **Binance-only** (funding + open interest + long/short ratio).
- DeFi TVL: include (DeFiLlama).
- ChartInspect: use for **daily OHLCV** (close-to-close) and optional BTC on-chain metrics; env `CHARTINSPECT_API`.
- Tests: prefer **live API calls** (no mocked data).

## Background

### Why a Crypto Stream?

| Factor | Opportunity |
|--------|-------------|
| **24/7 Markets** | No market close; daily recap at fixed time (e.g., 00:00 UTC) |
| **High Volatility** | More frequent significant moves to report |
| **On-Chain Transparency** | Unique data not available in traditional markets |
| **Engaged Audience** | Crypto users actively seek daily updates |

### Data Categories Required

| Category | Purpose | Priority |
|----------|---------|----------|
| Price/Market Data | BTC, ETH, top alts price, volume, dominance | P0 (Essential) |
| Fear & Greed Index | Market sentiment gauge | P0 (Essential) |
| CEX Funding Rates | Derivatives sentiment (long/short bias) | P0 (Essential) |
| CEX Open Interest | Leverage in the system | P1 (Important) |
| CEX Exchange Reserves | BTC/ETH held on exchanges | P2 (Future) |
| News | Crypto-specific headlines | P0 (Essential) |
| DeFi TVL | Ecosystem health indicator | P1 (Include in v1) |

**Note:** Whale tracking on DEXes is de-prioritized. For v1 we focus on **Binance-only** derivatives (funding, open interest, long/short ratio) + broader market context (CoinGecko + ChartInspect).

## Data Source Analysis

### 0. Unified API Option - ChartInspect

ChartInspect provides a single REST API that covers **crypto OHLCV**, **Bitcoin on-chain metrics**, and **derivatives** (funding + open interest) under one auth model.

- Base URL: `https://chartinspect.com/api/v1`
- Auth (recommended): `X-API-Key: <key>`
- Auth (alternative): `Authorization: Bearer <key>`
- Env var: `CHARTINSPECT_API` (API key)

Key endpoints (from docs):

```
# Prices
GET /crypto/prices/{symbol}?days=N      # e.g. BTC, ETH, SOL
GET /crypto/prices/list                # Symbols available (does NOT include market cap / rank)

# On-chain
GET /onchain/status
GET /onchain/{metric}?days=N           # e.g. mvrv-data, sopr

# Derivatives
# NOTE: Pro subscription required (free tier returns 403).
GET /derivatives/futures_funding_rates
GET /derivatives/futures_open_interest

# Market indicators
# NOTE: Pro subscription required (free tier returns 403).
GET /market-indicators/{indicator}     # e.g. altcoin-season-index-90d-top-50

# Exchange / ETF
# NOTE: Pro subscription required (free tier returns 403).
GET /exchange-etf/exchange-balances
GET /exchange-etf/etf-balances
```

Example response shapes (docs examples):
- `/crypto/prices/BTC?days=30` returns `{ date, open, high, low, close, volume }[]` + `metadata`.
- `/onchain/mvrv-data?days=90` returns `{ date, mvrv, marketCap, realizedCap }[]` + `metadata`.

How this fits Task 28:
- Can supply **daily OHLCV** aligned to UTC close-to-close recaps.
- Can supply **Bitcoin on-chain metrics** (e.g., MVRV, SOPR) on the free tier.
- Derivatives/indicators/exchange+ETF endpoints require Pro; for v1 (free tier) we use **Binance** for funding + open interest + long/short ratio.
- `crypto/prices/list` is symbols-only, so we still need **CoinGecko** (or equivalent) for **dynamic top N by market cap**.

### 1. Price & Market Data

| Provider | Free Tier | Rate Limit | Coverage | Recommendation |
|----------|-----------|------------|----------|----------------|
| **CoinGecko** | Yes | 30 req/min, 10K/month | 15,000+ coins | ✅ Primary |
| **CoinMarketCap** | Yes | 333 req/day (10K/mo) | 10,000+ coins | Backup |
| **CoinPaprika** | Yes | 250K lifetime | 2,000 top coins | Alternative |
| **Messari** | Yes (limited) | Rate limited | 500+ assets | Research data |
| **ChartInspect** | Free plan (API key) | TBD | OHLCV for major crypto symbols | Candidate (unified stack) |

**CoinGecko Recommended Endpoints:**

```
GET /api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true
GET /api/v3/global  # Market cap, BTC dominance, volume
GET /api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=20
```

**Data Points to Capture:**

| Metric | Description | Update Frequency |
|--------|-------------|------------------|
| BTC Price | Bitcoin USD price | Real-time |
| ETH Price | Ethereum USD price | Real-time |
| BTC Dominance | % of total market cap | Daily |
| Total Market Cap | Aggregate crypto market cap | Daily |
| 24h Volume | Total trading volume | Daily |
| Top 10 Movers | Biggest gainers/losers in top 100 | Daily |

### 2. Fear & Greed Index

| Provider | Free Tier | Update Freq | API |
|----------|-----------|-------------|-----|
| **Alternative.me** | ✅ Free | Daily | `https://api.alternative.me/fng/` |
| **CFGI.io** | ✅ Free (limited) | 15 min | REST API |
| **CoinMarketCap** | ✅ Free tier | Daily | CMC API |

**Alternative.me API (Recommended):**

```python
# Simple, free, no API key required
import requests

def get_fear_greed_index() -> dict:
    """Fetch current Fear & Greed Index."""
    response = requests.get("https://api.alternative.me/fng/")
    data = response.json()["data"][0]
    return {
        "value": int(data["value"]),  # 0-100
        "classification": data["value_classification"],  # "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"
        "timestamp": data["timestamp"],
    }
```

**Index Interpretation:**

| Range | Classification | Market Implication |
|-------|----------------|-------------------|
| 0-24 | Extreme Fear | Potential buying opportunity |
| 25-49 | Fear | Bearish sentiment |
| 50-50 | Neutral | Balanced market |
| 51-74 | Greed | Bullish sentiment |
| 75-100 | Extreme Greed | Potential correction ahead |

### 3. DeFi TVL (Total Value Locked)

| Provider | Free Tier | Coverage | API |
|----------|-----------|----------|-----|
| **DeFiLlama** | ✅ Completely free | 2,000+ protocols | `https://api.llama.fi/` |

**DeFiLlama Endpoints:**

```
GET https://api.llama.fi/protocols  # All protocols with TVL
GET https://api.llama.fi/charts     # Historical total TVL
GET https://api.llama.fi/tvl/{protocol}  # Specific protocol TVL
GET https://api.llama.fi/chains     # TVL by chain
```

**Key Metrics:**

| Metric | Description |
|--------|-------------|
| Total DeFi TVL | Sum of all protocol TVL |
| Top 5 Protocols | Lido, AAVE, MakerDAO, etc. |
| Chain Breakdown | Ethereum, Solana, BSC, Arbitrum |
| 24h TVL Change | Inflow/outflow indicator |

### 4. Funding Rates (Derivatives)

| Provider | Free Tier | Coverage | API |
|----------|-----------|----------|-----|
| **ChartInspect** | Pro required | Funding + open interest | REST API |
| **Binance API** | ✅ Free | Binance Futures only | Direct API |

**Binance Funding Rate Endpoint:**

```
GET https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=1
```

**Binance Open Interest Endpoint:**

```
GET https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT
```

**Binance Long/Short Ratio Endpoint:**

```
GET https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=BTCUSDT&period=1d&limit=2
```

**What Funding Rates Tell Us:**

| Rate | Interpretation |
|------|----------------|
| > 0.01% (positive) | Longs pay shorts; bullish sentiment |
| < -0.01% (negative) | Shorts pay longs; bearish sentiment |
| Near 0% | Neutral/balanced positioning |
| > 0.1% (extreme) | Overleveraged longs; correction risk |

### 5. CEX Exchange Reserves & Open Interest

**Focus on CEX-derived data rather than DEX whale tracking** — more reliable signal for institutional flow.

| Provider | Free Tier | Data Type | Coverage |
|----------|-----------|-----------|----------|
| **ChartInspect** | Pro required | Exchange balances, ETF balances, OI, funding | Multi-source |
| **CryptoQuant** | ✅ Limited | Exchange Reserves, Flows | BTC, ETH on CEXes |
| **Coinalyze** | ✅ Free | OI, Funding, Long/Short | Major pairs |
| **Binance API** | ✅ Free | Own exchange data | Binance only |

**Binance Futures (v1 implementation target):**

```
# Open interest (Binance only)
GET https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT

# Funding rate (Binance only)
GET https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=1

# Long/short ratio (Binance only)
GET https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=BTCUSDT&period=1d&limit=2
```

**CryptoQuant Data (Exchange Reserves):**

```
# BTC Exchange Reserve (how much BTC held on all CEXes)
# Decreasing = bullish (coins moving to cold storage)
# Increasing = bearish (coins moving to exchanges for selling)
```

**Key CEX Metrics:**

| Metric | What It Tells Us | Bullish/Bearish |
|--------|------------------|-----------------|
| **Open Interest** | Total $ in open futures positions | Rising OI + rising price = bullish |
| **Funding Rate** | Cost to hold longs vs shorts | High positive = overleveraged longs |
| **Long/Short Ratio** | Retail sentiment on CEXes | Extreme readings = contrarian signal |
| **Exchange Reserves** | BTC/ETH held on exchanges | Decreasing = accumulation |
| **Liquidations** | Forced position closes | High = volatility, potential reversal |

**Why CEX Data > DEX Whale Tracking:**

- CEX data reflects actual leveraged positioning
- Exchange reserves track real accumulation/distribution
- Funding rates show cost of leverage (market structure)
- DEX whale moves often just internal transfers or MEV

### 6. Crypto News Sources

#### RSS Feeds (Free)

| Source | Feed URL | Focus |
|--------|----------|-------|
| **Cointelegraph** | `https://cointelegraph.com/rss` | General crypto |
| **CoinDesk** | `https://www.coindesk.com/arc/outboundfeeds/rss/` | Institutional focus |
| **The Block** | `https://www.theblock.co/rss.xml` | Research/analysis |
| **Decrypt** | `https://decrypt.co/feed` | Consumer crypto |
| **Bitcoin Magazine** | `https://bitcoinmagazine.com/feed` | BTC-focused |
| **DeFi Pulse** | N/A | DeFi-specific |

#### News APIs (P2 / Future)

v1 is **RSS-only** for crypto news ingestion. Keep this section as research for later if RSS quality/coverage is insufficient.

| Provider | Free Tier | Crypto Coverage |
|----------|-----------|-----------------|
| **TheNewsAPI** | 100 req/day | Crypto category filter |
| **CryptoNews-API** | Limited | Crypto-native |
| **NewsData.io** | 200 req/day | Crypto category |

**Recommended RSS Config (`rss/crypto.txt`):**

```
# Tier 1 - Primary Sources
https://cointelegraph.com/rss
https://www.coindesk.com/arc/outboundfeeds/rss/
https://www.theblock.co/rss.xml
https://decrypt.co/feed

# Tier 2 - Specialized
https://bitcoinmagazine.com/feed
https://defillama.com/rss  # If available
```

## Implementation Details

### 1. Stream Configuration

**File:** `config.yaml`

```yaml
streams:
  us_markets:
    enabled: true
    # ... existing us_markets config ...

  crypto:
    enabled: true
    rss:
      allowlist_files:
        - "rss/crypto.txt"
    schedule:
      daily_crypto_utc: "00:00"  # Recap the day that just ended (UTC)

    # New Task 28 config block (to implement)
    crypto:
      top_n_market_cap: 10
      always_include_symbols: ["BTC", "ETH"]
      exclude_symbols: ["USDT", "USDC", "DAI"]

      # Source routing
      market_cap_provider: "coingecko"      # Dynamic top N by market cap
      ohlcv_provider: "chartinspect"        # Daily candles (UTC close-to-close)
      derivatives_provider: "binance"       # Funding + open interest + long/short ratio (Binance-only)
      fear_greed_provider: "alternative_me"
      defi_tvl_provider: "defillama"
```

### 2. New Data Adapters

#### CoinGecko Adapter

**File:** `src/argus/adapters/coingecko.py`

```python
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
import httpx

COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"

@dataclass(frozen=True)
class CryptoAsset:
    id: str                    # "bitcoin"
    symbol: str                # "BTC"
    name: str                  # "Bitcoin"
    price_usd: Decimal
    price_change_24h_pct: Decimal
    price_change_7d_pct: Optional[Decimal]
    market_cap_usd: Decimal
    volume_24h_usd: Decimal
    market_cap_rank: int

@dataclass(frozen=True)
class CryptoMarketSnapshot:
    timestamp: datetime
    total_market_cap_usd: Decimal
    total_volume_24h_usd: Decimal
    btc_dominance_pct: Decimal
    eth_dominance_pct: Decimal
    active_cryptocurrencies: int
    assets: list[CryptoAsset]

class CoinGeckoClient:
    """Client for CoinGecko API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key  # Optional Pro API key
        self.base_url = COINGECKO_BASE_URL

    async def get_market_snapshot(self, asset_ids: list[str]) -> CryptoMarketSnapshot:
        """Fetch current market data for specified assets."""
        async with httpx.AsyncClient() as client:
            # Global market data
            global_resp = await client.get(f"{self.base_url}/global")
            global_data = global_resp.json()["data"]

            # Asset prices
            markets_resp = await client.get(
                f"{self.base_url}/coins/markets",
                params={
                    "vs_currency": "usd",
                    "ids": ",".join(asset_ids),
                    "order": "market_cap_desc",
                    "sparkline": "false",
                    "price_change_percentage": "24h,7d",
                }
            )
            markets_data = markets_resp.json()

            assets = [
                CryptoAsset(
                    id=coin["id"],
                    symbol=coin["symbol"].upper(),
                    name=coin["name"],
                    price_usd=Decimal(str(coin["current_price"])),
                    price_change_24h_pct=Decimal(str(coin["price_change_percentage_24h"] or 0)),
                    price_change_7d_pct=Decimal(str(coin.get("price_change_percentage_7d_in_currency") or 0)),
                    market_cap_usd=Decimal(str(coin["market_cap"])),
                    volume_24h_usd=Decimal(str(coin["total_volume"])),
                    market_cap_rank=coin["market_cap_rank"],
                )
                for coin in markets_data
            ]

            return CryptoMarketSnapshot(
                timestamp=datetime.utcnow(),
                total_market_cap_usd=Decimal(str(global_data["total_market_cap"]["usd"])),
                total_volume_24h_usd=Decimal(str(global_data["total_volume"]["usd"])),
                btc_dominance_pct=Decimal(str(global_data["market_cap_percentage"]["btc"])),
                eth_dominance_pct=Decimal(str(global_data["market_cap_percentage"]["eth"])),
                active_cryptocurrencies=global_data["active_cryptocurrencies"],
                assets=assets,
            )
```

#### Fear & Greed Adapter

**File:** `src/argus/adapters/fear_greed.py`

```python
@dataclass(frozen=True)
class FearGreedIndex:
    value: int                 # 0-100
    classification: str        # "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"
    timestamp: datetime
    previous_value: Optional[int] = None
    previous_classification: Optional[str] = None

async def get_fear_greed_index() -> FearGreedIndex:
    """Fetch current Fear & Greed Index from Alternative.me."""
    async with httpx.AsyncClient() as client:
        resp = await client.get("https://api.alternative.me/fng/?limit=2")
        data = resp.json()["data"]

        current = data[0]
        previous = data[1] if len(data) > 1 else None

        return FearGreedIndex(
            value=int(current["value"]),
            classification=current["value_classification"],
            timestamp=datetime.fromtimestamp(int(current["timestamp"])),
            previous_value=int(previous["value"]) if previous else None,
            previous_classification=previous["value_classification"] if previous else None,
        )
```

#### DeFi TVL Adapter

**File:** `src/argus/adapters/defillama.py`

```python
@dataclass(frozen=True)
class DeFiTVLSnapshot:
    timestamp: datetime
    total_tvl_usd: Decimal
    tvl_change_24h_pct: Decimal
    top_protocols: list[tuple[str, Decimal]]  # (name, tvl)
    chain_breakdown: dict[str, Decimal]        # {chain: tvl}

async def get_defi_tvl() -> DeFiTVLSnapshot:
    """Fetch DeFi TVL data from DeFiLlama."""
    async with httpx.AsyncClient() as client:
        # Get protocol TVLs
        protocols_resp = await client.get("https://api.llama.fi/protocols")
        protocols = protocols_resp.json()

        # Sort by TVL, get top 5
        sorted_protocols = sorted(protocols, key=lambda x: x.get("tvl", 0), reverse=True)[:5]
        top_protocols = [(p["name"], Decimal(str(p["tvl"]))) for p in sorted_protocols]

        # Get chain breakdown
        chains_resp = await client.get("https://api.llama.fi/chains")
        chains = chains_resp.json()
        chain_breakdown = {c["name"]: Decimal(str(c["tvl"])) for c in chains[:10]}

        total_tvl = sum(Decimal(str(p.get("tvl", 0))) for p in protocols)

        return DeFiTVLSnapshot(
            timestamp=datetime.utcnow(),
            total_tvl_usd=total_tvl,
            tvl_change_24h_pct=Decimal("0"),  # Calculate from historical
            top_protocols=top_protocols,
            chain_breakdown=chain_breakdown,
        )
```

#### Binance Derivatives Adapter (Funding + Open Interest + Long/Short)

**File:** `src/argus/adapters/binance_derivatives.py`

```python
@dataclass(frozen=True)
class FundingRate:
    symbol: str          # "BTCUSDT"
    rate: Decimal        # e.g., 0.0001 = 0.01%
    next_funding_time: datetime
    interpretation: str  # "Bullish", "Bearish", "Neutral"

@dataclass(frozen=True)
class OpenInterest:
    symbol: str          # "BTCUSDT"
    open_interest: Decimal  # contract units (as returned by Binance)

@dataclass(frozen=True)
class LongShortRatio:
    symbol: str
    long_short_ratio: Decimal
    long_account_pct: Decimal
    short_account_pct: Decimal
    timestamp: datetime

@dataclass(frozen=True)
class BinanceDerivativesSnapshot:
    timestamp: datetime
    funding_rates: list[FundingRate]
    open_interest: list[OpenInterest]
    long_short_ratios: list[LongShortRatio]

async def get_funding_rates(symbols: list[str] = ["BTCUSDT", "ETHUSDT"]) -> list[FundingRate]:
    """Fetch funding rates from Binance USDⓈ-M Futures."""
    async with httpx.AsyncClient() as client:
        rates = []
        for symbol in symbols:
            resp = await client.get(
                "https://fapi.binance.com/fapi/v1/fundingRate",
                params={"symbol": symbol, "limit": 1}
            )
            data = resp.json()[0]

            rate = Decimal(data["fundingRate"])
            interpretation = (
                "Bullish" if rate > Decimal("0.0001") else
                "Bearish" if rate < Decimal("-0.0001") else
                "Neutral"
            )

            rates.append(FundingRate(
                symbol=symbol,
                rate=rate,
                next_funding_time=datetime.fromtimestamp(data["fundingTime"] / 1000),
                interpretation=interpretation,
            ))

        return rates

async def get_open_interest(symbol: str) -> OpenInterest:
    """Fetch open interest (Binance USDⓈ-M)."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://fapi.binance.com/fapi/v1/openInterest",
            params={"symbol": symbol},
        )
        data = resp.json()
        return OpenInterest(symbol=symbol, open_interest=Decimal(data["openInterest"]))

async def get_long_short_ratio(symbol: str, *, period: str = "1d") -> LongShortRatio:
    """Fetch global long/short account ratio (Binance Futures)."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://fapi.binance.com/futures/data/globalLongShortAccountRatio",
            params={"symbol": symbol, "period": period, "limit": 1},
        )
        data = resp.json()[0]
        return LongShortRatio(
            symbol=symbol,
            long_short_ratio=Decimal(data["longShortRatio"]),
            long_account_pct=Decimal(data["longAccount"]),
            short_account_pct=Decimal(data["shortAccount"]),
            timestamp=datetime.fromtimestamp(int(data["timestamp"]) / 1000),
        )
```

### 3. Crypto Facts Bundle

**File:** `src/argus/facts_bundle/types.py` (extend)

```python
@dataclass(frozen=True)
class CryptoFactsBundle:
    """Facts bundle for crypto stream."""
    stream_name: str
    generated_at: datetime

    # Market Data
    market_snapshot: CryptoMarketSnapshot

    # Sentiment
    fear_greed: FearGreedIndex

    # DeFi (optional)
    defi_tvl: Optional[DeFiTVLSnapshot] = None

    # Derivatives (optional)
    derivatives: Optional["BinanceDerivativesSnapshot"] = None

    # News
    news_items: list[NewsItemBundle] = field(default_factory=list)

    # Calendar (crypto events - optional)
    upcoming_events: list[str] = field(default_factory=list)
```

### 4. Crypto-Specific Prompts

**File:** `src/argus/generator/prompts_crypto.py`

```python
SYSTEM_PROMPT_CRYPTO_DAILY = """
You are a senior crypto analyst writing the daily market recap for institutional and retail investors.

Your report should cover:

1. **Market Overview**
   - Total crypto market cap and 24h change
   - BTC and ETH price action with % changes
   - BTC dominance trend (rising = risk-off, falling = alt season)

2. **Sentiment Check**
   - Fear & Greed Index value and classification
   - Compare to previous day (improving/worsening)
   - What this suggests for positioning

3. **Key Movers**
   - Notable gainers/losers in top 20
   - Any catalysts from the news [#CITEKEY]

4. **On-Chain Insights** (if data available)
    - DeFi TVL trend
    - Funding rates + open interest + long/short ratio (Binance-only)

5. **What to Watch**
   - Upcoming events (unlocks, upgrades, regulatory)
   - Key support/resistance levels
   - Risk factors

CONSTRAINTS:
- Maximum {max_words} words
- Use ONLY facts provided in the bundle
- Reference news with EXACT citation keys [#A1B2C3D4]
- Professional but accessible tone (not overly technical)
- Include specific numbers: prices, percentages, TVL figures

OUTPUT FORMAT:
{{
  "narrative": "2-4 paragraphs with citations",
  "market_scorecard": {{
    "btc": "$XX,XXX (+X.X%)",
    "eth": "$X,XXX (+X.X%)",
    "total_mcap": "$X.XT",
    "fear_greed": "XX (Classification)"
  }},
  "key_movers": ["BTC +X%", "ETH +X%", "SOL +X%"],
  "watch_next": ["item1", "item2", "item3"]
}}
"""
```

### 5. Crypto Message Renderer

**File:** `src/argus/generator/renderer_crypto.py`

```python
def render_crypto_message(bundle: CryptoFactsBundle, news_contexts: list) -> str:
    """Render crypto daily update message."""
    sections = []

    # Header
    sections.append("*Crypto Daily Recap*")
    sections.append(f"*{bundle.generated_at.strftime('%d %b %Y')}*")
    sections.append("")

    # Market Snapshot
    snapshot = bundle.market_snapshot
    btc = next((a for a in snapshot.assets if a.symbol == "BTC"), None)
    eth = next((a for a in snapshot.assets if a.symbol == "ETH"), None)

    if btc:
        sections.append(f"BTC – ${btc.price_usd:,.0f} ({_format_pct(btc.price_change_24h_pct)})")
    if eth:
        sections.append(f"ETH – ${eth.price_usd:,.0f} ({_format_pct(eth.price_change_24h_pct)})")

    sections.append(f"Total Market Cap: ${snapshot.total_market_cap_usd / 1e12:.2f}T")
    sections.append(f"BTC Dominance: {snapshot.btc_dominance_pct:.1f}%")
    sections.append("")

    # Fear & Greed
    fg = bundle.fear_greed
    emoji = _fear_greed_emoji(fg.value)
    sections.append(f"{emoji} Fear & Greed: {fg.value} ({fg.classification})")
    sections.append("")

    # Narrative (from LLM)
    sections.append(bundle.narrative)
    sections.append("")
    sections.append("—————")

    # ... rest of sections (takeaways, sources, etc.)

    return "\n".join(sections)

def _fear_greed_emoji(value: int) -> str:
    if value <= 24:
        return "😱"  # Extreme Fear
    elif value <= 49:
        return "😰"  # Fear
    elif value <= 54:
        return "😐"  # Neutral
    elif value <= 74:
        return "😀"  # Greed
    else:
        return "🤑"  # Extreme Greed
```

## New Files to Create

| File | Purpose |
|------|---------|
| `src/argus/adapters/chartinspect.py` | ChartInspect unified market data client |
| `src/argus/adapters/coingecko.py` | CoinGecko API client |
| `src/argus/adapters/fear_greed.py` | Fear & Greed Index client |
| `src/argus/adapters/defillama.py` | DeFiLlama TVL client |
| `src/argus/adapters/binance_derivatives.py` | Binance USDⓈ-M derivatives client (funding, OI, long/short) |
| `src/argus/generator/prompts_crypto.py` | Crypto-specific LLM prompts |
| `src/argus/generator/renderer_crypto.py` | Crypto message formatter |
| `src/argus/facts_bundle/crypto_builder.py` | Crypto facts bundle builder |
| `rss/crypto.txt` | Crypto RSS feed allowlist |
| `tests/test_coingecko.py` | CoinGecko adapter tests |
| `tests/test_crypto_stream.py` | Integration tests |

## Files to Modify

| File | Changes |
|------|---------|
| `config.yaml` | Add `crypto` stream configuration |
| `src/argus/config.py` | Add `CryptoStreamConfig` dataclass |
| `src/argus/orchestrator/orchestrator.py` | Add crypto run mode |
| `src/argus/daemon/scheduler.py` | Add crypto daily job |
| `src/argus/facts_bundle/types.py` | Add `CryptoFactsBundle` |
| `src/argus/pipeline/registry.py` | Register crypto providers |

## API Cost Analysis

### Free Tier Limits (Daily)

| Provider | Free Limit | Crypto Stream Usage | Margin |
|----------|------------|---------------------|--------|
| CoinGecko | 10K calls/month (~333/day) | ~10 calls/day | ✅ Plenty |
| Alternative.me | Unlimited | ~2 calls/day | ✅ Free |
| DeFiLlama | Unlimited | ~5 calls/day | ✅ Free |
| Binance | 1200 req/min | ~5 calls/day | ✅ Plenty |

**Total Estimated API Calls:** ~25 calls/day = well within free tiers

### Fallback Strategy

| Primary | Fallback | Trigger |
|---------|----------|---------|
| CoinGecko | CoinMarketCap | Rate limit hit |
| Alternative.me | CoinMarketCap F&G | API down |
| DeFiLlama | Skip section | API down |
| Binance derivatives | Skip derivatives section | API error / schema change |

## Acceptance Criteria

### Functional

| ID | Criterion | Verification |
|----|-----------|--------------|
| AC-1 | Top 10 selection is dynamic by market cap; BTC/ETH always included; stablecoins excluded | Unit test |
| AC-2 | ChartInspect OHLCV fetched for selected symbols; close-to-close % computed by UTC date | Integration test |
| AC-3 | Binance derivatives fetched (funding + open interest + long/short ratio) | Integration test |
| AC-4 | Fear & Greed Index fetched and parsed | Unit test |
| AC-5 | DeFi TVL from DeFiLlama | Unit test |
| AC-6 | Crypto RSS feeds ingested | Integration test |
| AC-7 | Crypto daily message generated | End-to-end test |
| AC-8 | Message published to Telegram only for subscribers | Manual test |

### Data Quality

| ID | Criterion | Verification |
|----|-----------|--------------|
| DQ-1 | BTC price within 1% of actual | Compare to exchange |
| DQ-2 | Fear & Greed matches Alternative.me | Manual check |
| DQ-3 | Recap uses the completed UTC day (no partial-day candles) | Timestamp validation |

### Quality Gates

- [ ] All new adapters have unit tests
- [ ] Integration test for full crypto pipeline
- [ ] API rate limits not exceeded in testing
- [ ] Message fits within 4096 char limit
- [ ] Type checking passes
- [ ] Linting passes

## Out of Scope (v1)

- Real-time price alerts (beyond daily recap)
- Portfolio tracking
- Trading signals/recommendations
- NFT market data
- Layer 2 specific metrics
- DEX volume tracking
- Liquidation data
- Social sentiment analysis (Twitter/Discord)

## Risks / Notes

### API Reliability

| Risk | Mitigation |
|------|------------|
| CoinGecko rate limits | Cache responses, use fallback |
| Alternative.me downtime | Cache last known value |
| DeFiLlama data lag | Accept 1-hour staleness |
| Binance API changes | Monitor, have fallback |

### Data Accuracy

- Crypto prices vary by exchange (use aggregated data)
- TVL calculations differ by methodology
- Fear & Greed is subjective/proprietary

### Regulatory Considerations

- Avoid specific investment advice
- Include disclaimer in messages
- No price predictions

### 24/7 Nature

- No "market close" — pick arbitrary daily time (00:00 UTC)
- Weekend data still relevant (unlike US markets)
- Consider multiple daily updates later

## Dependencies

- Task 21 (Multi-Stream Schema) — ✅ Complete
- Task 25 (Weekly Statistics) — Independent (can enhance later)
- Task 27 (Message Interactivity) — Independent (apply to crypto too)

## Estimated Effort

| Component | Estimate |
|-----------|----------|
| CoinGecko adapter | 2 hours |
| ChartInspect adapter | 2 hours |
| Fear & Greed adapter | 1 hour |
| DeFiLlama adapter | 1.5 hours |
| Binance derivatives adapter | 2 hours |
| RSS feed curation | 1 hour |
| Crypto facts bundle | 2 hours |
| Crypto prompts | 2 hours |
| Crypto renderer | 2 hours |
| Config & orchestrator | 2 hours |
| Unit tests | 3 hours |
| Integration testing | 2 hours |

**Total: ~20 hours**

## Phased Rollout

### Phase 1: MVP (Week 1)
- Dynamic top 10 by market cap (CoinGecko), always include BTC/ETH, exclude stablecoins
- Daily OHLCV and close-to-close % changes (ChartInspect primary)
- Fear & Greed Index
- Binance-only derivatives (funding + open interest + long/short ratio)
- DeFi TVL (DeFiLlama)
- Crypto RSS feeds (Cointelegraph, CoinDesk, The Block)
- Basic daily message

### Phase 2: CEX Data Integration (Week 2)
- Improve derivatives narrative (trend vs 7d average, extremes)
- Improved prompts with derivatives context

### Phase 3: Advanced CEX Metrics (Week 3+)
- Exchange reserves (CryptoQuant if free tier sufficient)
- Liquidation data (24h liquidations)
- Interactive message buttons (from Task 27)
- Optional BTC on-chain metrics (ChartInspect free tier: MVRV/SOPR) if useful

## Example Output Message

```
*Crypto Daily Recap*
*10 Jan 2026*

BTC – $97,234 (+2.1%)
ETH – $3,456 (+3.4%)
Total Market Cap: $3.42T
BTC Dominance: 54.2%

😀 Fear & Greed: 68 (Greed)

📊 CEX Derivatives:
• Open Interest: $58.2B (+4.2%)
• Funding Rate: 0.015% (Bullish bias)
• 24h Liquidations: $124M (68% shorts)

Bitcoin pushed above $97K overnight as spot ETF inflows
continued for the 8th consecutive day [1]. Ethereum outperformed
with a 3.4% gain ahead of the Pectra upgrade narrative [2].

Open interest climbed 4.2% to $58.2B while funding rates remain
elevated at 0.015%, suggesting leveraged longs are confident but
potentially overextended. Yesterday's $124M in liquidations were
predominantly shorts (68%), indicating bears capitulating.

—————

__Key Takeaways__
• BTC ETF inflows remain strong ($340M yesterday)
• OI rising with price = healthy trend continuation
• Elevated funding rates signal caution for leveraged longs
• Short liquidations accelerating — potential local top forming

__What to Watch__
• SOL unlock event (Jan 12) — 1.2M tokens
• CPI data (Jan 15) — macro catalyst for risk assets
• BTC $100K psychological resistance

__Sources__
[1] [Bitcoin ETF Inflows Continue](https://coindesk.com/...)
[2] [Ethereum Pectra Upgrade Timeline](https://theblock.co/...)
```

## References

- [ChartInspect API Documentation](https://chartinspect.com/api-docs)
- [CoinGecko API Documentation](https://www.coingecko.com/api/documentation)
- [Alternative.me Fear & Greed API](https://alternative.me/crypto/fear-and-greed-index/)
- [DeFiLlama API](https://defillama.com/docs/api)
- [Binance Futures API](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data)
- [Top Crypto RSS Feeds](https://rss.feedspot.com/cryptocurrency_rss_feeds/)
