"""
Decision Engine.

Deliberately NOT "ask an LLM if we should buy." It:
  1. Collects structured output from every agent (already computed).
  2. Scores FOUR competing hypotheses against that evidence: uptrend (LONG),
     downtrend (SHORT), reversal caution (WAIT — false breakout/breakdown),
     and range-bound (WAIT — no edge). Uptrend and downtrend are scored
     symmetrically from the same evidence, so the system can surface short
     opportunities as readily as long ones — it does not have a built-in
     long bias. (In practice, crypto's historical long-side drift means you
     may *observe* more LONG calls than SHORT ones over time, but that comes
     from the market data, not from the scoring logic favoring one side.)
  3. Picks the best-supported hypothesis and assigns a confidence score.
  4. Applies the Risk Agent's veto (never overridable).
  5. Formats the final report in the "BTC — 10:00 PM" style from the brief,
     with every evidence line traceable back to a specific agent output.

This module is pure Python — no LLM call required. An optional LLM
"narrative" pass can be layered in `app/notifiers` or `app/api.py` to turn the
structured report into more natural prose, but the decision itself is
auditable and deterministic.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.formatting import format_price, round_price


@dataclass
class Hypothesis:
    name: str
    label: str
    score: float = 0.0
    supporting: list = field(default_factory=list)
    contradicting: list = field(default_factory=list)


def _score_hypotheses(trend: dict, momentum: dict, structure: dict, news: dict) -> list[Hypothesis]:
    uptrend = Hypothesis("A", "Market is beginning/continuing an uptrend")
    downtrend = Hypothesis("D", "Market is beginning/continuing a downtrend")
    reversal_caution = Hypothesis("B", "Exhaustion / false breakout-or-breakdown — caution")
    range_bound = Hypothesis("C", "Market is range-bound, no clear edge")

    # --- Trend evidence (symmetric) ---
    if trend["overall"] in ("bullish", "mildly bullish"):
        uptrend.score += 2 * trend["agreement_score"]
        uptrend.supporting.append(f"Trend agent: {trend['overall']} across timeframes (agreement {trend['agreement_score']*100:.0f}%)")
        downtrend.contradicting.append(f"Trend agent: {trend['overall']}, working against a downtrend read")
    elif trend["overall"] in ("bearish", "mildly bearish"):
        downtrend.score += 2 * trend["agreement_score"]
        downtrend.supporting.append(f"Trend agent: {trend['overall']} across timeframes (agreement {trend['agreement_score']*100:.0f}%)")
        uptrend.contradicting.append(f"Trend agent: {trend['overall']}, working against an uptrend read")
    else:
        range_bound.score += 1
        range_bound.supporting.append("Trend agent: sideways, no clear multi-timeframe direction")

    # --- Momentum evidence (symmetric) ---
    if momentum["label"] == "positive":
        uptrend.score += 1.5
        uptrend.supporting.append(f"Momentum agent: positive (RSI {momentum['rsi']}, MACD histogram rising)")
        if momentum["volume_increasing"]:
            uptrend.supporting.append(f"Momentum agent: volume {momentum['volume_ratio_vs_20bar_avg']}x the 20-bar average")
        else:
            uptrend.contradicting.append("Volume below average, weakens the move's conviction")
    elif momentum["label"] == "negative":
        downtrend.score += 1.5
        downtrend.supporting.append(f"Momentum agent: negative (RSI {momentum['rsi']}, MACD histogram falling)")
        if momentum["volume_increasing"]:
            downtrend.supporting.append(f"Momentum agent: volume {momentum['volume_ratio_vs_20bar_avg']}x the 20-bar average")
        else:
            downtrend.contradicting.append("Volume below average, weakens the move's conviction")
    else:
        range_bound.score += 0.5
        range_bound.supporting.append("Momentum agent: mixed signal")

    if momentum["rsi_state"] == "overbought":
        reversal_caution.score += 1
        reversal_caution.supporting.append(f"Momentum agent: RSI overbought ({momentum['rsi']}) — stretched, reversal-prone conditions")
        uptrend.contradicting.append("RSI overbought, raises false-breakout risk")
    elif momentum["rsi_state"] == "oversold":
        reversal_caution.score += 1
        reversal_caution.supporting.append(f"Momentum agent: RSI oversold ({momentum['rsi']}) — stretched, bounce-prone conditions")
        downtrend.contradicting.append("RSI oversold, raises false-breakdown risk")

    # --- Structure evidence (symmetric) ---
    if structure["event"] == "breakout_above_resistance":
        if structure["volume_confirmed"]:
            uptrend.score += 2
            uptrend.supporting.append(f"Structure agent: broke resistance at {structure['resistance']} with volume confirmation")
        else:
            reversal_caution.score += 1.5
            reversal_caution.supporting.append(f"Structure agent: broke resistance at {structure['resistance']} WITHOUT volume confirmation")
    elif structure["event"] == "breakdown_below_support":
        if structure["volume_confirmed"]:
            downtrend.score += 2
            downtrend.supporting.append(f"Structure agent: broke support at {structure['support']} with volume confirmation")
        else:
            reversal_caution.score += 1.5
            reversal_caution.supporting.append(f"Structure agent: broke support at {structure['support']} WITHOUT volume confirmation")
    else:
        range_bound.score += 1.5
        range_bound.supporting.append(f"Structure agent: still inside range [{structure['support']}, {structure['resistance']}]")

    if structure["higher_highs_higher_lows"]:
        uptrend.score += 1
        downtrend.contradicting.append("Structure agent: higher-highs / higher-lows pattern — works against a downtrend read")
        uptrend.supporting.append("Structure agent: higher-highs / higher-lows pattern intact")
    if structure["lower_highs_lower_lows"]:
        downtrend.score += 1
        uptrend.contradicting.append("Structure agent: lower-highs / lower-lows pattern — structurally weak")
        downtrend.supporting.append("Structure agent: lower-highs / lower-lows pattern intact")

    # --- News/sentiment evidence (symmetric) ---
    if news["label"] == "bullish":
        uptrend.score += 1
        uptrend.supporting.append(f"News/sentiment agent: bullish — {news['headline_summary']}")
        downtrend.contradicting.append("News/sentiment agent flags a bullish catalyst")
    elif news["label"] == "bearish":
        downtrend.score += 1
        downtrend.supporting.append(f"News/sentiment agent: bearish — {news['headline_summary']}")
        uptrend.contradicting.append("News/sentiment agent flags a bearish catalyst")

    return [uptrend, downtrend, reversal_caution, range_bound]


def _confidence_from_scores(hypotheses: list[Hypothesis]) -> tuple[Hypothesis, int]:
    winner = max(hypotheses, key=lambda h: h.score)
    total = sum(max(h.score, 0) for h in hypotheses) or 1
    raw_conf = (max(winner.score, 0) / total) * 100
    # Compress toward the middle a bit — never claim near-100% certainty from
    # a handful of technical signals.
    confidence = int(round(35 + raw_conf * 0.55))
    return winner, max(0, min(confidence, 95))


def build_report(symbol: str, trend: dict, momentum: dict, structure: dict, risk: dict, news: dict) -> dict:
    hypotheses = _score_hypotheses(trend, momentum, structure, news)
    winner, confidence = _confidence_from_scores(hypotheses)

    last_close = structure["last_close"]

    if winner.name == "A":  # uptrend
        bias = "Bullish" if confidence >= 60 else "Moderately bullish"
        direction = "LONG"
        invalidation = structure["support"]
        target = last_close + (last_close - structure["support"]) * 1.5
        do_nothing_if = "Price falls back below the invalidation level, or volume collapses on the next bar."
    elif winner.name == "D":  # downtrend
        bias = "Bearish" if confidence >= 60 else "Moderately bearish"
        direction = "SHORT"
        invalidation = structure["resistance"]
        target = last_close - (structure["resistance"] - last_close) * 1.5
        do_nothing_if = "Price reclaims back above the invalidation level, or volume collapses on the next bar."
    elif winner.name == "B":  # reversal caution
        bias = "Cautious / choppy"
        direction = "WAIT"
        invalidation = structure["resistance"]
        target = structure["support"]
        do_nothing_if = "No confirmation within the next 1-2 bars — this hypothesis expects mean reversion, not continuation."
    else:  # range bound
        bias = "Neutral / range-bound"
        direction = "WAIT"
        invalidation = None
        target = None
        do_nothing_if = "Price stays inside the current range with no volume expansion."

    # Risk agent has veto power over direction, never over reporting.
    if risk["veto_directional_trade"] and direction != "WAIT":
        direction = "WAIT"
        do_nothing_if = f"Risk agent vetoed directional trades — abnormal volatility ({risk['max_abs_move_pct_recent']}% move detected)."
        confidence = min(confidence, 40)

    market_regime = {
        "A": "Uptrend" if not risk["abnormal_volatility"] else "Uptrend (elevated volatility)",
        "D": "Downtrend" if not risk["abnormal_volatility"] else "Downtrend (elevated volatility)",
        "B": "Volatile / indecisive",
        "C": "Range-bound",
    }[winner.name]

    what_changed = winner.supporting[0] if winner.supporting else "No single dominant signal this cycle."

    now = datetime.utcnow()
    next_review = now + timedelta(hours=1)

    return {
        "symbol": symbol,
        "timestamp": now.isoformat(),
        "next_review": next_review.isoformat(),
        "bias": bias,
        "confidence": confidence,
        "market_regime": market_regime,
        "what_changed": what_changed,
        "evidence": winner.supporting + [f"(against) {c}" for c in winner.contradicting],
        "direction": direction,
        "entry_price": round_price(last_close),
        "invalidation_price": round_price(invalidation),
        "target_price": round_price(target),
        "risk_level": risk["risk_level"],
        "do_nothing_if": do_nothing_if,
        "hypotheses_considered": [
            {"name": h.name, "label": h.label, "score": round(h.score, 2)} for h in hypotheses
        ],
        "agent_outputs": {
            "trend": trend, "momentum": momentum, "structure": structure,
            "risk": risk, "news_sentiment": news,
        },
    }


def format_report_text(report: dict) -> str:
    """Renders the exact "BTC — 10:00 PM" style block from the design brief."""
    ts = datetime.fromisoformat(report["timestamp"]).strftime("%I:%M %p").lstrip("0")
    lines = [
        f"{report['symbol']} — {ts}",
        f"Bias: {report['bias']}",
        f"Confidence: {report['confidence']}/100",
        f"Market regime: {report['market_regime']}",
        f"What changed: {report['what_changed']}",
        "Evidence:",
    ]
    lines += [f"• {e}" for e in report["evidence"]]
    lines.append(f"Suggested direction: {report['direction']}")
    if report["invalidation_price"] is not None:
        lines.append(f"Invalidation: {format_price(report['invalidation_price'])}")
    if report["target_price"] is not None:
        lines.append(f"Target: {format_price(report['entry_price'])} → {format_price(report['target_price'])}")
    lines.append(f"Risk: {report['risk_level'].capitalize()}")
    lines.append(f"Do nothing if: {report['do_nothing_if']}")
    lines.append(f"Next review: {datetime.fromisoformat(report['next_review']).strftime('%I:%M %p').lstrip('0')}")
    return "\n".join(lines)
