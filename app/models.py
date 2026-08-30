"""
Database schema.

Two tables matter most:
- Recommendation: every report the system ever produced, immutable once written.
- RecommendationOutcome: the follow-up check(s) done later against real price,
  which is what makes the backtesting/calibration layer possible.

Everything else (bars) is just the raw market data cache.
"""
from datetime import datetime

from sqlalchemy import (Column, DateTime, Float, ForeignKey, Integer, String,
                         Text, create_engine)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from app.config import settings

Base = declarative_base()


class Bar(Base):
    """One OHLCV candle for one symbol/timeframe."""
    __tablename__ = "bars"

    id = Column(Integer, primary_key=True)
    symbol = Column(String, index=True, nullable=False)
    timeframe = Column(String, index=True, nullable=False)  # "15m", "1h", "4h", "1d"
    ts = Column(DateTime, index=True, nullable=False)  # candle open time
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)


class Recommendation(Base):
    """
    A single hourly report. `evidence_json` and `agent_outputs_json` store the
    full structured trail from every agent so the reasoning is auditable, not
    just the final bias.

    `status`/`resolved_at`/`exit_price`/`pnl_pct` track the trade's outcome
    continuously and in real time: as soon as a later price check crosses
    the target or invalidation level (not waiting for a fixed 1h/6h/24h
    checkpoint), the recommendation resolves to "win" or "loss" and its
    realized P&L% is recorded — this is what lets the dashboard show a live,
    ever-updating win rate rather than one that only settles hours later.
    """
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    symbol = Column(String, index=True, nullable=False)

    bias = Column(String, nullable=False)          # bullish / bearish / neutral
    direction = Column(String, nullable=False)      # LONG / SHORT / WAIT
    confidence = Column(Integer, nullable=False)    # 0-100
    market_regime = Column(String)                  # uptrend / downtrend / range / volatile
    entry_price = Column(Float)
    invalidation_price = Column(Float)
    target_price = Column(Float)
    risk_level = Column(String)                     # low / medium / high
    summary = Column(Text)                          # "what changed" narrative
    evidence_json = Column(Text)                    # list of evidence bullet strings
    agent_outputs_json = Column(Text)                # raw per-agent structured output

    # --- Real-time outcome tracking ---
    status = Column(String, default="open", index=True)  # open / win / loss / expired (WAIT calls stay "n/a")
    resolved_at = Column(DateTime, nullable=True)
    exit_price = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)  # realized % gain (positive) or loss (negative) at resolution

    outcomes = relationship("RecommendationOutcome", back_populates="recommendation")


class ScanRun(Base):
    """
    One autonomous discover -> screen -> analyze -> rank cycle. The
    per-symbol detail lives in `Recommendation` rows (created the same way a
    manual lookup creates them); this table is just the scan-level summary —
    how big the universe was, how much got screened out, and which symbols
    came out on top — so the dashboard can show scanner history without
    re-running anything.
    """
    __tablename__ = "scan_runs"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    quote_asset = Column(String, nullable=False)
    markets_discovered = Column(Integer, nullable=False)
    markets_screened = Column(Integer, nullable=False)
    symbols_analyzed_json = Column(Text)     # list of symbols the full pipeline ran on
    top_opportunities_json = Column(Text)    # ranked summaries, see scanner._opportunity_summary
    error = Column(Text, nullable=True)      # set if discovery/screening itself failed


class RecommendationOutcome(Base):
    """
    A later re-check of one Recommendation against actual price movement.
    Multiple rows per recommendation (+1h, +6h, +24h) build up the dataset
    the calibration report is computed from.
    """
    __tablename__ = "recommendation_outcomes"

    id = Column(Integer, primary_key=True)
    recommendation_id = Column(Integer, ForeignKey("recommendations.id"), nullable=False)
    checked_at = Column(DateTime, default=datetime.utcnow)
    horizon_label = Column(String)      # "1h", "6h", "24h"
    price_at_check = Column(Float)
    pct_move_since_entry = Column(Float)
    hit_target = Column(Integer, default=0)       # bool as int (sqlite friendly)
    hit_invalidation = Column(Integer, default=0)

    recommendation = relationship("Recommendation", back_populates="outcomes")


engine = create_engine(settings.database_url, connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db():
    Base.metadata.create_all(engine)


def get_session():
    return SessionLocal()
