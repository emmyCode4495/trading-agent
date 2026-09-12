"""
Central configuration. Everything is read from environment variables so the
same code runs locally, in a container, or on a server without edits.

Copy .env.example to .env and fill in real values when you're ready to move
off mock data.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

# Load a .env file if python-dotenv is installed and one exists. Optional
# dependency: falls back silently if not present.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    # --- Manual watchlist: an OPTIONAL secondary drill-down, not the input to
    # the autonomous scanner. Used only as the default symbol for
    # GET /api/report/latest when no ?symbol= is given and no scan has run
    # yet. The scanner (app/scanner.py) discovers its own universe instead
    # of reading this. ---
    symbols: list = field(default_factory=lambda: os.getenv("SYMBOLS", "BTC/USDT").split(","))

    # --- Data source: "mock" works with zero setup, for testing without any
    # network access. For real prices, use "binance", "bybit", or "mexc"
    # directly, or "auto" to try multiple exchanges in priority order (see
    # data_source_priority below) and fail over automatically if one is
    # unreachable — e.g. geo-blocked in your region. "auto" is the
    # recommended setting once you're past initial testing. ---
    data_source: str = os.getenv("DATA_SOURCE", "mock")
    # Order to try exchanges in when data_source is "auto". Bybit and MEXC
    # are listed first because, as of this writing, neither is among the
    # exchanges named in Nigeria's 2024 NCC directive (Binance, Coinbase,
    # Kraken specifically) — so they're more likely reachable without a VPN
    # in affected regions. Adjust the order/list for your own situation.
    data_source_priority: str = os.getenv("DATA_SOURCE_PRIORITY", "bybit,mexc,binance")

    # --- Autonomous scanner: discover -> screen -> analyze -> rank ---
    # Quote asset that defines "the market" to scan (USDT pairs, by far
    # Binance's deepest and most numerous, is the sane default universe).
    scan_quote_asset: str = os.getenv("SCAN_QUOTE_ASSET", "USDT")
    # Liquidity floor in quote-asset terms (24h volume). Symbols below this
    # are discarded before any agent ever looks at them — thin markets
    # produce noisy technicals and are hard to actually trade anyway.
    scan_min_quote_volume_24h: float = float(os.getenv("SCAN_MIN_QUOTE_VOLUME_24H", "5000000"))
    # The full 5-agent pipeline is the expensive step (multiple timeframes x
    # multiple agents x network calls), so liquidity screening narrows a
    # universe of hundreds down to this many candidates before it runs.
    scan_max_symbols_to_analyze: int = int(os.getenv("SCAN_MAX_SYMBOLS_TO_ANALYZE", "15"))
    # How many of the analyzed symbols get surfaced as "opportunities"
    # (ranked by confidence, WAIT calls excluded).
    scan_top_n_opportunities: int = int(os.getenv("SCAN_TOP_N_OPPORTUNITIES", "5"))

    # --- Storage ---
    # SQLite by default (zero setup). Swap to a Postgres/Timescale URL in
    # production, e.g. postgresql+psycopg2://user:pass@host:5432/trading_agent
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/trading_agent.db")

    # --- LLM (used only by the news/sentiment agents and the narrative
    # write-up step; all the numeric agents are pure Python/pandas) ---
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    enable_llm_agents: bool = os.getenv("ENABLE_LLM_AGENTS", "false").lower() == "true"

    # --- Notifications ---
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # --- Scheduling ---
    # Full market scan (discover -> screen -> analyze -> rank): the expensive
    # cycle, since it runs the whole 5-agent pipeline per candidate symbol.
    run_interval_minutes: int = int(os.getenv("RUN_INTERVAL_MINUTES", "15"))
    # Position monitoring (checking OPEN recommendations' current price
    # against target/invalidation): cheap — one price lookup per open
    # position — so this runs much more often, which is what makes the
    # win rate feel live instead of only updating once an hour.
    position_check_interval_minutes: int = int(os.getenv("POSITION_CHECK_INTERVAL_MINUTES", "2"))
    # A position that never reaches its target or invalidation within this
    # many hours is marked "expired" rather than sitting open forever.
    position_expiry_hours: int = int(os.getenv("POSITION_EXPIRY_HOURS", "48"))

    # --- Risk thresholds ---
    max_volatility_pct: float = float(os.getenv("MAX_VOLATILITY_PCT", "6.0"))  # 1h % move considered "abnormal"
    min_confidence_to_act: int = int(os.getenv("MIN_CONFIDENCE_TO_ACT", "60"))

    # --- Web server ---
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))

    # --- Execution (Hyperliquid): OFF by default. The scanner/agents/
    # decision engine above are unaffected either way — this only controls
    # whether a qualifying report also gets sent to Hyperliquid as an order.
    execution_enabled: bool = os.getenv("EXECUTION_ENABLED", "false").lower() == "true"
    hyperliquid_env: str = os.getenv("HYPERLIQUID_ENV", "testnet")  # "testnet" or "mainnet" — start on testnet
    # Private key of the API wallet (NOT your main wallet) generated at
    # https://app.hyperliquid.xyz/API (or the testnet equivalent). This wallet
    # can only trade on your behalf, never withdraw.
    hyperliquid_private_key: str = os.getenv("HYPERLIQUID_PRIVATE_KEY", "")
    # Main wallet address the API wallet trades on behalf of. Required
    # whenever the API wallet differs from the main account (the normal case).
    hyperliquid_account_address: str = os.getenv("HYPERLIQUID_ACCOUNT_ADDRESS", "")
    # Your builder address — every order this system places attributes its
    # fee share here. Same address as hyperliquid_account_address is fine to
    # start; a dedicated builder wallet is cleaner once this is a real product.
    hyperliquid_builder_address: str = os.getenv("HYPERLIQUID_BUILDER_ADDRESS", "")
    # Fee rate as a string percentage, e.g. "0.01%" — passed to
    # approve_builder_fee once. Must be a ceiling the user approves; you can
    # charge up to this, not more.
    hyperliquid_builder_max_fee_rate: str = os.getenv("HYPERLIQUID_BUILDER_MAX_FEE_RATE", "0.05%")
    # Actual per-order fee in tenths of a basis point (Hyperliquid's native
    # unit for the `f` field) — 10 = 1bp = 0.01%. Must be <= the approved max.
    hyperliquid_builder_fee_tenths_bps: int = int(os.getenv("HYPERLIQUID_BUILDER_FEE_TENTHS_BPS", "5"))
    hyperliquid_max_slippage_pct: float = float(os.getenv("HYPERLIQUID_MAX_SLIPPAGE_PCT", "0.02"))  # 2%

    # --- Position sizing (fixed-fractional risk sizing, not Kelly — see
    # app/execution/sizing.py for why). Applied only when execution_enabled. ---
    risk_per_trade_pct: float = float(os.getenv("RISK_PER_TRADE_PCT", "1.0"))       # % of equity risked per trade
    max_position_pct_of_equity: float = float(os.getenv("MAX_POSITION_PCT_OF_EQUITY", "20.0"))

    # --- Payments (Tempo): OFF by default, independent of execution. ---
    payments_enabled: bool = os.getenv("PAYMENTS_ENABLED", "false").lower() == "true"
    tempo_env: str = os.getenv("TEMPO_ENV", "testnet")  # "testnet" (Moderato) or "mainnet"
    tempo_rpc_url_testnet: str = os.getenv("TEMPO_RPC_URL_TESTNET", "https://rpc.moderato.tempo.xyz")
    tempo_rpc_url_mainnet: str = os.getenv("TEMPO_RPC_URL_MAINNET", "https://rpc.tempo.xyz")
    # Wallet that receives subscription payments / sends payouts. Private key
    # only needed for the payout side (sending); receiving needs just the address.
    tempo_operator_private_key: str = os.getenv("TEMPO_OPERATOR_PRIVATE_KEY", "")
    tempo_operator_address: str = os.getenv("TEMPO_OPERATOR_ADDRESS", "")
    # pathUSD is Tempo's first predeployed stablecoin — same address on
    # mainnet and testnet (Tempo's predeployed contracts use deterministic
    # addresses). Verify on https://explore.testnet.tempo.xyz before relying
    # on this for real funds.
    tempo_stablecoin_address: str = os.getenv("TEMPO_STABLECOIN_ADDRESS", "0x20c0000000000000000000000000000000000000")
    tempo_stablecoin_decimals: int = int(os.getenv("TEMPO_STABLECOIN_DECIMALS", "6"))
    subscription_price_usd: float = float(os.getenv("SUBSCRIPTION_PRICE_USD", "20.0"))
    subscription_period_days: int = int(os.getenv("SUBSCRIPTION_PERIOD_DAYS", "30"))


settings = Settings()
