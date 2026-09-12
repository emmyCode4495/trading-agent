# Market Intelligence Agent

An autonomous, multi-agent market-intelligence system. It doesn't wait to be
told what to look at: it **discovers** every tradable pair on the exchange,
**screens** them down to the ones with enough liquidity to matter, runs
several independent analyses (trend, momentum, structure, risk,
news/sentiment) on each survivor, combines them into competing hypotheses,
and **ranks** the results into a shortlist of opportunities — with a bias, a
confidence score, and evidence behind each one. Never a bare "BUY". "Do
nothing" is always a valid output, for the market as a whole as much as for
any one symbol.

**This is a decision-support prototype, not a trading bot, and nothing it
outputs is financial advice.** It ships with synthetic (mock) market data —
including a synthetic *exchange universe* to scan — so you can run the
entire discover-through-rank pipeline right now with zero API keys, then
swap in real data when you're ready.

## Recent fixes

- **Price precision.** Prices are now rounded to a sensible number of
  decimals for their magnitude (`app/formatting.py`) — e.g. 2 decimals for
  a >$1,000 asset, more for sub-cent tokens — instead of a fixed decimal
  count that produced garbled-looking numbers for some assets. The root
  cause (the mock data generator using Python's non-deterministic built-in
  `hash()` for base prices) is also fixed; mock prices now land in a
  realistic ballpark per asset.
- **Real-time win/loss tracking.** Every LONG/SHORT recommendation now
  resolves continuously: the moment its target or invalidation price is
  actually reached, it's marked "win" or "loss" with a live P&L% — not on a
  fixed hourly/daily checkpoint. See `GET /api/positions` and the
  dashboard's "Live positions" panel. (Positions open longer than
  `POSITION_EXPIRY_HOURS` without resolving are marked "expired" and
  excluded from the win rate.) Getting this right also required fixing the
  mock data adapter so prices actually evolve over real wall-clock time
  and every timeframe is derived from one coherent price path — see the
  comments at the top of `app/data/mock_adapter.py` for the full story.
- **Continuous scanning, both directions, and a live indicator.** The
  decision engine now scores a symmetric downtrend/SHORT hypothesis
  alongside the uptrend/LONG one (it previously could only ever output
  LONG or WAIT) — see `app/decision.py`. And the API process itself now
  runs a background scan loop (`app/scheduler.py` + `app/scan_state.py`),
  so simply running `uvicorn app.api:app` gives continuous real-time
  scanning with a live status the dashboard polls (`GET /api/status`) —
  no separate process required.

## Quick start (mock data, ~2 minutes)

```bash
python -m venv venv && source venv/bin/activate      # or your preferred env tool
pip install -r requirements.txt
cp .env.example .env

# One-off scan: discovers the mock universe, screens by liquidity, analyzes
# the survivors, prints ranked opportunities:
python -m scripts.run_scan

# Or launch the full web dashboard + API:
uvicorn app.api:app --reload --port 8000
# then open http://localhost:8000
```

The dashboard's primary view is the **scanner**: how many markets were
discovered and screened, a ranked opportunities table, and a "RUN SCAN"
button to trigger a fresh cycle on demand. Clicking any opportunity (or
typing a symbol into the "Manual lookup" box — an optional, secondary
drill-down for checking one specific pair regardless of what the scanner
surfaced) shows the full report: confidence gauge, evidence trail,
entry/invalidation/target, and that symbol's recommendation history. A
backtest/calibration panel (win rate, etc.) populates once recommendations
have had time to be checked against real price movement.

To also get hourly scans without keeping the dashboard open:

```bash
python -m app.scheduler
```

This runs a full scan every `RUN_INTERVAL_MINUTES` (default 60) and, if
you've filled in `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` in `.env`, pushes
a summary of the top opportunities to Telegram too.

Already know the one symbol you want checked, regardless of whether it'd
survive the liquidity screen? `python -m scripts.run_once` runs the
manual-watchlist path (`SYMBOLS` in `.env`) directly, bypassing discovery
and screening entirely — the same path the dashboard's "Manual lookup" box
uses.

## Architecture

```
                    ┌─── SCANNER (app/scanner.py) ───┐
Exchange            │                                 │
  │  1. DISCOVER     every tradable {quote}-asset pair │
  │  2. SCREEN        by 24h liquidity  → shortlist    │
  └─────────────────►│  3. ANALYZE  (per shortlisted symbol) ─┐
                     │                                 │       │
                     │  4. RANK    by confidence,       │       ▼
                     │             WAIT calls excluded  │  [Trend | Momentum | Structure
                     └────────────────┬────────────────┘   | Risk | News/Sentiment] agents
                                      │                     → Hypothesis scoring (3 hypotheses)
                                      ▼                     → Decision engine (+ Risk veto)
                          Ranked opportunities                     │
                          → Dashboard / Telegram ◄─────────────────┘
                          → (later) Backtest evaluator checks each call
                                     against real price

A manual watchlist symbol (SYMBOLS in .env) skips discovery/screening
entirely and feeds step 3 directly — an optional, secondary path for
checking one specific pair (scripts/run_once.py, the dashboard's "Manual
lookup" box, GET /api/report/latest?symbol=...).
```

| Piece | File(s) | Notes |
|---|---|---|
| Data adapters | `app/data/` | `MockAdapter` generates synthetic OHLCV *and* a synthetic exchange universe (`list_markets`) so everything, including the scanner, runs offline — but its prices are illustrative estimates, not live data, and **will drift from reality over time**; don't expect them to match real markets. `BinanceAdapter`, `BybitAdapter`, and `MexcAdapter` implement the same interface against real exchanges. `FailoverAdapter` (`DATA_SOURCE=auto`) tries them in priority order so one being unreachable doesn't stop the scanner. |
| **Scanner** | `app/scanner.py` | **Discover → screen → analyze → rank.** `discover_markets` asks the adapter for every tradable pair; `screen_by_liquidity` drops thin markets by 24h quote volume before any agent runs; `run_scan` orchestrates the full cycle and persists a `ScanRun` summary. This is the autonomous entry point — not a fixed symbol list. |
| Trend agent | `app/agents/trend.py` | EMA slope + multi-timeframe (15m/1h/4h/1d) agreement. Pure pandas, no LLM. |
| Momentum agent | `app/agents/momentum.py` | RSI, MACD histogram, volume-vs-average. Pure pandas, no LLM. |
| Structure agent | `app/agents/structure.py` | Swing-point support/resistance, breakout/breakdown detection. Pure pandas, no LLM. |
| Risk agent | `app/agents/risk.py` | Volatility check with **veto power** — the decision engine cannot override it. Regime-adaptive: thresholds are computed per-symbol from that symbol's own recent volatility distribution (90-bar p90), not one flat global number. |
| News/Sentiment agent | `app/agents/news_sentiment.py` | The one agent that legitimately needs an LLM (it interprets language, not numbers). Off by default (`ENABLE_LLM_AGENTS=false`); uses the Anthropic API + web search when enabled. |
| Correlation agent | `app/agents/correlation.py` | Measures the symbol's return correlation to BTC/USDT and BTC's own trend. Doesn't veto — discounts confidence when a symbol is highly BTC-correlated *and* BTC itself is directionless, since that combination means the symbol's own technical story is more likely BTC beta than a real edge. |
| Volume profile agent | `app/agents/volume_profile.py` | Builds a volume-at-price histogram from recent bars and derives the Point of Control and a 70% value area — sharper, volume-backed levels than swing-point S/R alone. Feeds both hypothesis scoring and target-price selection. |
| Decision engine | `app/decision.py` | Scores 4 competing hypotheses (uptrend / downtrend / reversal caution / range-bound) against the evidence, picks the best-supported one, formats the final report. Flags a `conflicted_signal` when the runner-up hypothesis scored nearly as well as the winner, and caps confidence accordingly rather than presenting false certainty. |
| Pipeline | `app/pipeline.py` | `run_cycle(symbol)` runs one full cycle for a single symbol (all 7 agents → decision engine) and persists it — called once per shortlisted symbol by the scanner, and directly by the manual watchlist path. Symbol-agnostic; doesn't know or care whether the scanner or a person chose the symbol. |
| Backtest/calibration | `app/backtest.py` | Re-checks past recommendations continuously against real price; aggregates win rate, calibration by confidence bucket, performance by regime. **This is the layer that tells you whether the system is actually any good — trust it over the confidence score itself.** `agent_accuracy_report()` breaks this down further: of the trades where a given agent's own directional read agreed with the direction taken, what fraction won — the real feedback loop for eventually tuning `_score_hypotheses`' hand-picked weights. |
| Scheduler | `app/scheduler.py` | Hourly automation via APScheduler — runs a full scan, not a fixed watchlist. |
| API + Dashboard | `app/api.py`, `app/static/dashboard.html` | FastAPI serving JSON + a terminal-style dashboard (vanilla HTML/JS, no build step). `/api/scan/*` and `/api/markets` are the scanner surface; `/api/report/latest` is the manual drill-down. |

## Going live: real exchange data

**If you're seeing prices that don't match reality (e.g. an entry price
nowhere near the actual market), you're still on `DATA_SOURCE=mock`.** That
mode exists for zero-setup offline testing — its "anchor prices" are
illustrative estimates hardcoded at build time, not live data, and they
*will* drift from the real market over time. There's no way to keep mock
prices accurate; the fix is switching to a real data source, not tuning the
mock numbers.

Three exchanges are implemented, all calling public REST endpoints that need
**no API key** for market data:

| Exchange | Adapter | Notes |
|---|---|---|
| Bybit | `app/data/bybit_adapter.py` | v5 public API. Not named in Nigeria's 2024 NCC exchange-block directive. |
| MEXC | `app/data/mexc_adapter.py` | v3 public API (Binance-compatible). Also not named in that directive; actively used by Nigerians via its P2P product with no VPN workaround mentioned anywhere — a strong signal it's normally reachable. |
| Binance | `app/data/binance_adapter.py` | v3 public API. Blocked at the ISP level in some regions (Nigeria's NCC directive named Binance, Coinbase, and Kraken specifically in Feb 2024) — a VPN may be required there. |

```bash
# in .env — pick ONE:

# Option A: a specific exchange
DATA_SOURCE=bybit          # or mexc, or binance
SCAN_QUOTE_ASSET=USDT      # the scanner discovers every USDT pair on that exchange itself

# Option B (RECOMMENDED): try multiple in order, fail over automatically
DATA_SOURCE=auto
DATA_SOURCE_PRIORITY=bybit,mexc,binance   # order matters; first reachable one wins per call
```

With `DATA_SOURCE=auto`, every call (fetching a candle, a price, or the
market list) tries each exchange in `DATA_SOURCE_PRIORITY` order and uses
whichever one actually responds — so if Binance is geo-blocked where you're
running this, it just quietly uses Bybit or MEXC instead, no manual
switching required. It also remembers which exchange last worked for a
given symbol (for 5 minutes) so it's not re-trying a dead one on every
single call, while still periodically re-checking in case a block was
temporary.

That's the whole switch either way — agents, decision engine, backtester,
scanner, and dashboard all talk to the `DataAdapter` interface, not to any
specific exchange, so nothing else changes. `SYMBOLS` is no longer required
at all once you're scanning; it's only read by the manual watchlist path.

Notes on the implementation:
- **Discovery**: `list_markets()` on each adapter combines that exchange's
  symbol-list endpoint with its 24h ticker endpoint (2-3 calls total,
  cached, regardless of how many symbols come back). All three exclude
  leveraged tokens and stablecoin-vs-stablecoin pairs, since neither has
  real directional signal to analyze.
- **Exchange-specific quirks handled**: Bybit returns klines *newest-first*
  (reversed here to the chronological order every other adapter uses) and
  reports 24h price change as a fraction rather than a percent (converted).
  MEXC has no native `1h` kline interval (mapped to its `60m` instead) and
  uses different tradability status values across its API surface (checked
  defensively rather than pinned to one exact string). Binance's exact
  behavior is covered in its own module docstring.
- **Caching**: OHLCV responses are cached ~30s and the latest price ~5s per
  adapter; each exchange's symbol-list/24h-ticker endpoints are cached
  longer (minutes) — so a scan across dozens of symbols, each pulling
  multiple agents × multiple timeframes, doesn't hammer any one API or trip
  rate limits.
- **Errors**: each adapter raises its own clear error type
  (`BinanceError`/`BybitError`/`MexcError`) on network failures, non-2xx
  responses, or logical errors the exchange reports with an HTTP 200 (both
  Bybit and MEXC do this — the real error is in the response body, not the
  status code, and each adapter checks for it explicitly). `run_scan()`
  catches per-symbol analysis errors so one bad symbol doesn't sink the
  whole cycle.
- **Testing**: this sandbox's network is restricted to package registries,
  so none of `api.binance.com`, `api.bybit.com`, or `api.mexc.com` could be
  reached from inside this conversation. Instead, each adapter has an
  offline test suite that mocks the HTTP layer with response shapes copied
  from that exchange's own API docs — including the trickier real-world
  details like Bybit's reversed kline order and MEXC's interval naming —
  and verifies that the full agent pipeline runs against it with zero code
  changes. Run them with:
  ```bash
  python -m scripts.test_binance_adapter
  python -m scripts.test_bybit_adapter
  python -m scripts.test_mexc_adapter
  python -m scripts.test_failover_adapter
  ```
  Do one real-network smoke test yourself once you know which exchange(s)
  your network can actually reach (`python -m scripts.run_scan` with the
  matching `DATA_SOURCE`) before relying on it for real prices.
- **Other exchanges**: implement the same `DataAdapter` interface
  (`get_ohlcv`, `get_latest_price`, `list_markets`) for Coinbase, Kraken, a
  stock API, etc., then add it to the registry in `app/data/__init__.py` —
  same drop-in pattern, and it becomes available for `DATA_SOURCE_PRIORITY`
  automatically.

## Execution & payments (Hyperliquid + Tempo) — OFF by default

Two additive layers sit on top of the pipeline above without changing any
agent, the decision engine, or the scanner. Both are disabled by default
(`EXECUTION_ENABLED=false`, `PAYMENTS_ENABLED=false`) — the system behaves
exactly as described above until you opt in.

| Piece | File(s) | Notes |
|---|---|---|
| Position sizing | `app/execution/sizing.py` | Fixed-fractional risk sizing (risk a fixed % of equity on the distance to invalidation), not Kelly — see the module docstring for why. Capped by `MAX_POSITION_PCT_OF_EQUITY` so a tight stop can't produce an oversized position. |
| Hyperliquid adapter | `app/execution/hyperliquid_adapter.py` | Thin wrapper around `hyperliquid-python-sdk`. Every order carries `HYPERLIQUID_BUILDER_ADDRESS` as a builder code, so fills route back a fee share automatically — no token stake required. |
| Executor | `app/execution/executor.py` | The seam: consumes the same report dict `pipeline.run_cycle()` already produces. Gates on `direction != WAIT`, `confidence >= MIN_CONFIDENCE_TO_ACT`, and no same-direction position already open (flips opposite positions, skips pyramiding). Every attempt — including skips — is persisted to the `executions` table (`GET /api/executions`) for a full audit trail. |
| Tempo adapter | `app/payments/tempo_adapter.py` | Standard web3.py against Tempo's EVM RPC. TIP-20 (Tempo's stablecoin standard) exposes an ERC-20-compatible interface, so no special SDK is needed for transfers/balances. |
| Subscriptions | `app/payments/subscriptions.py` | `POST /api/subscribe` verifies a claimed payment on-chain (via `tempo_adapter.verify_incoming_payment`) before activating — never trusts the claim alone. |

**Setup, testnet-first:**
1. Hyperliquid: generate an API wallet at https://app.hyperliquid-testnet.xyz/API, set `HYPERLIQUID_PRIVATE_KEY`/`HYPERLIQUID_ACCOUNT_ADDRESS`/`HYPERLIQUID_BUILDER_ADDRESS` in `.env`, then call `hyperliquid_adapter.ensure_builder_fee_approved()` once.
2. Tempo: get a wallet + free testnet pathUSD from the faucet at https://tempo.xyz/developers/docs/quickstart/faucet, set `TEMPO_OPERATOR_PRIVATE_KEY`/`TEMPO_OPERATOR_ADDRESS`.
3. Set `EXECUTION_ENABLED=true` / `PAYMENTS_ENABLED=true` only once both are funded on testnet.

**Known gap, real-money blocker:** order sizes aren't yet rounded to each
asset's `szDecimals` (Hyperliquid rejects orders with too much size
precision) — this needs a real testnet call to `Info.meta()` to fetch per-
asset precision, which this sandbox's network couldn't reach while building
this (see the "Testing" note above — same restriction applies here). Confirm
this against a real testnet order before going further.

**Privacy upgrade path (not built yet):** Tempo's [Zones](https://tempo.xyz/blog/introducing-tempo-zones/)
feature — private, permissioned parallel chains with selective disclosure —
is the natural next step for the subscription flow, so a subscriber's
payment amount/identity isn't publicly visible, only to the operator and any
auditor holding a viewing key. Slots into `subscriptions.py` without
changing its interface.

## Before you trust this with real money

- **Let the backtest layer run for a while first.** Hundreds of logged
  recommendations, not a handful, is what makes the win-rate/calibration
  numbers meaningful. With mock data, any "edge" you see is an artifact of
  the synthetic random walk, not real market skill.
- **The confidence score is a relative ranking of hypotheses, not a
  calibrated probability**, until the backtest layer has enough history to
  actually check that calibration.
- **The Risk agent's veto is intentionally not LLM-controlled** — keep it
  that way if you extend the system. Circuit breakers should stay
  deterministic.
- Consider starting with `ENABLE_LLM_AGENTS=false` (recommendation-only,
  numeric agents only) until you've validated the technical layer, then add
  news/sentiment as a refinement rather than a foundation.

## Roadmap ideas

- ~~Per-agent accuracy tracking in the backtest report~~ — done, see
  `backtest.agent_accuracy_report()` / `GET /api/calibration/agent-accuracy`.
  Still to do: actually feed this back into `_score_hypotheses`' weights
  (currently hand-picked constants) once there's enough resolved-trade volume.
- ~~Multi-asset correlation agent~~ — done, see `app/agents/correlation.py`.
  Currently only checks correlation to BTC/USDT; extending to an ETH/BTC
  ratio or a broader dominance index is a natural next step.
- Walk-forward validation for `backtest.py` (train/tune on one window, test
  on the next, roll forward) rather than one static historical check, so
  weight/threshold tuning doesn't overfit to whichever period it was tuned on
- Position sizing suggestions in the risk agent (e.g. Kelly-fraction-style,
  capped)
- Swap the vanilla dashboard JS for a small React app if you want richer
  interactivity (charts, filters) — the API is already decoupled from the
  frontend so this is a drop-in replacement.
