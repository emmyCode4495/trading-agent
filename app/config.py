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


settings = Settings()
