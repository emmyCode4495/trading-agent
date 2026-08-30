"""
Backtesting / calibration layer — the most important component per the
design brief. Every LONG/SHORT recommendation gets checked continuously
against real price movement, so you can measure whether confidence scores
are calibrated, what the win rate is, and which market regimes the system
handles well.

`evaluate_open_positions()` is event-driven and meant to run frequently
(every couple of minutes, alongside but independent of the much heavier
full market scan) — it looks at every still-OPEN recommendation, checks the
*current* price, and resolves it to "win" the moment price actually reaches
the target, or "loss" the moment it hits the invalidation level. This is
what makes the win rate genuinely real-time instead of only settling at
fixed 1h/6h/24h checkpoints: a trade that hits its target in 12 minutes
shows as a win in 12 minutes, not after an hour-long wait.

Positions open longer than `settings.position_expiry_hours` without
resolving either way are marked "expired" — tracked separately, and not
counted in win_rate_pct, since neither outcome was actually confirmed.

`calibration_report()` aggregates everything resolved so far into the
summary stats described in the brief: win/loss ratio, calibration of
confidence, performance by regime.
"""
from datetime import datetime, timedelta

from app.config import settings
from app.data import get_adapter
from app.formatting import round_price
from app.models import Recommendation, get_session, init_db


def evaluate_open_positions() -> dict:
    """
    Checks every OPEN (unresolved) LONG/SHORT recommendation against the
    current price and resolves it immediately if target or invalidation has
    been reached, or expires it if it's been open too long. Returns a
    summary of what changed this pass — call this often (every few minutes)
    for the win rate to feel truly live.
    """
    init_db()
    session = get_session()
    adapter = get_adapter()
    resolved_wins, resolved_losses, expired = 0, 0, 0

    try:
        now = datetime.utcnow()
        open_positions = session.query(Recommendation).filter(Recommendation.status == "open").all()

        for rec in open_positions:
            try:
                price_now = adapter.get_latest_price(rec.symbol)
            except Exception:
                continue  # transient data-source error — leave it open, try again next pass

            hit_target = False
            hit_invalidation = False
            if rec.direction == "LONG":
                hit_target = rec.target_price is not None and price_now >= rec.target_price
                hit_invalidation = rec.invalidation_price is not None and price_now <= rec.invalidation_price
            elif rec.direction == "SHORT":
                hit_target = rec.target_price is not None and price_now <= rec.target_price
                hit_invalidation = rec.invalidation_price is not None and price_now >= rec.invalidation_price

            if hit_target or hit_invalidation:
                # If both somehow read true on the same check (shouldn't
                # normally happen), treat invalidation as the binding one —
                # conservative default, never over-count wins.
                won = hit_target and not hit_invalidation
                raw_pct_move = (price_now - rec.entry_price) / rec.entry_price * 100
                pnl_pct = raw_pct_move if rec.direction == "LONG" else -raw_pct_move

                rec.status = "win" if won else "loss"
                rec.resolved_at = now
                rec.exit_price = round_price(price_now)
                rec.pnl_pct = round(pnl_pct, 3)
                resolved_wins += int(won)
                resolved_losses += int(not won)
                continue

            if now > rec.created_at + timedelta(hours=settings.position_expiry_hours):
                raw_pct_move = (price_now - rec.entry_price) / rec.entry_price * 100
                pnl_pct = raw_pct_move if rec.direction == "LONG" else -raw_pct_move

                rec.status = "expired"
                rec.resolved_at = now
                rec.exit_price = round_price(price_now)
                rec.pnl_pct = round(pnl_pct, 3)
                expired += 1

        session.commit()
        return {"checked": len(open_positions), "wins": resolved_wins, "losses": resolved_losses, "expired": expired}
    finally:
        session.close()


def open_positions_summary(limit: int = 50) -> list[dict]:
    """Currently-open LONG/SHORT recommendations, most recent first — for a 'live positions' dashboard panel."""
    session = get_session()
    try:
        rows = (
            session.query(Recommendation)
            .filter(Recommendation.status == "open")
            .order_by(Recommendation.created_at.desc())
            .limit(limit)
            .all()
        )
        return [_position_dict(r) for r in rows]
    finally:
        session.close()


def recent_resolved_summary(limit: int = 30) -> list[dict]:
    """Most recently resolved (win/loss/expired) recommendations — for a live 'results feed'."""
    session = get_session()
    try:
        rows = (
            session.query(Recommendation)
            .filter(Recommendation.status.in_(["win", "loss", "expired"]))
            .order_by(Recommendation.resolved_at.desc())
            .limit(limit)
            .all()
        )
        return [_position_dict(r) for r in rows]
    finally:
        session.close()


def _position_dict(r: Recommendation) -> dict:
    return {
        "id": r.id,
        "symbol": r.symbol,
        "direction": r.direction,
        "bias": r.bias,
        "confidence": r.confidence,
        "created_at": r.created_at.isoformat(),
        "entry_price": r.entry_price,
        "invalidation_price": r.invalidation_price,
        "target_price": r.target_price,
        "status": r.status,
        "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
        "exit_price": r.exit_price,
        "pnl_pct": r.pnl_pct,
    }


def calibration_report() -> dict:
    init_db()
    session = get_session()
    try:
        recs = session.query(Recommendation).filter(Recommendation.direction != "WAIT").all()

        by_regime: dict[str, dict] = {}
        confidence_buckets: dict[str, dict] = {}
        wins, losses, expired_count, open_count = 0, 0, 0, 0

        for rec in recs:
            regime = rec.market_regime or "unknown"
            by_regime.setdefault(regime, {"count": 0, "wins": 0, "losses": 0})

            bucket = f"{(rec.confidence // 10) * 10}-{(rec.confidence // 10) * 10 + 9}"
            confidence_buckets.setdefault(bucket, {"count": 0, "wins": 0, "losses": 0})

            if rec.status == "open":
                open_count += 1
                continue
            if rec.status == "expired":
                expired_count += 1
                continue

            by_regime[regime]["count"] += 1
            confidence_buckets[bucket]["count"] += 1

            if rec.status == "win":
                wins += 1
                by_regime[regime]["wins"] += 1
                confidence_buckets[bucket]["wins"] += 1
            elif rec.status == "loss":
                losses += 1
                by_regime[regime]["losses"] += 1
                confidence_buckets[bucket]["losses"] += 1

        total_resolved = wins + losses
        win_rate = round(wins / total_resolved * 100, 1) if total_resolved else None
        avg_win_pct = None
        avg_loss_pct = None
        resolved_with_pnl = [r for r in recs if r.status in ("win", "loss") and r.pnl_pct is not None]
        wins_pnl = [r.pnl_pct for r in resolved_with_pnl if r.status == "win"]
        losses_pnl = [r.pnl_pct for r in resolved_with_pnl if r.status == "loss"]
        if wins_pnl:
            avg_win_pct = round(sum(wins_pnl) / len(wins_pnl), 2)
        if losses_pnl:
            avg_loss_pct = round(sum(losses_pnl) / len(losses_pnl), 2)

        return {
            "total_recommendations": len(recs),
            "open_positions": open_count,
            "expired_positions": expired_count,
            "total_resolved": total_resolved,
            "wins": wins,
            "losses": losses,
            "win_rate_pct": win_rate,
            "avg_win_pct": avg_win_pct,
            "avg_loss_pct": avg_loss_pct,
            "performance_by_regime": by_regime,
            "calibration_by_confidence_bucket": confidence_buckets,
            "note": "Resolution is continuous/real-time: a position resolves the moment price actually "
                    "reaches its target or invalidation level, not on a fixed schedule. Positions open "
                    f"longer than {settings.position_expiry_hours}h without resolving are marked 'expired' "
                    "and excluded from win_rate_pct. With mock data, any 'edge' measured here is illustrative "
                    "only, not real market skill.",
        }
    finally:
        session.close()
