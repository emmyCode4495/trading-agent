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


def _score_hypotheses(
    trend: dict, momentum: dict, structure: dict, news: dict,
    volume_profile: dict | None = None,
) -> list[Hypothesis]:
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

    # --- Volume profile evidence (symmetric) ---
    # Breaking outside the value area (where most volume actually
    # transacted) is a sharper "the market has repriced" signal than a
    # swing-point breakout alone — but it's a smaller, corroborating weight,
    # not a primary driver, since it can lag on fast moves.
    if volume_profile and volume_profile.get("price_vs_poc") == "above_value_area":
        uptrend.score += 0.75
        uptrend.supporting.append(
            f"Volume profile agent: price {volume_profile['last_close']} trading above the value area "
            f"high ({volume_profile['value_area_high']}) — outside where most recent volume transacted"
        )
    elif volume_profile and volume_profile.get("price_vs_poc") == "below_value_area":
        downtrend.score += 0.75
        downtrend.supporting.append(
            f"Volume profile agent: price {volume_profile['last_close']} trading below the value area "
            f"low ({volume_profile['value_area_low']}) — outside where most recent volume transacted"
        )

    return [uptrend, downtrend, reversal_caution, range_bound]


def _confidence_from_scores(hypotheses: list[Hypothesis]) -> tuple[Hypothesis, int, bool]:
    ranked = sorted(hypotheses, key=lambda h: h.score, reverse=True)
    winner = ranked[0]
    runner_up = ranked[1]
    total = sum(max(h.score, 0) for h in hypotheses) or 1
    raw_conf = (max(winner.score, 0) / total) * 100
    # Compress toward the middle a bit — never claim near-100% certainty from
    # a handful of technical signals.
    confidence = int(round(35 + raw_conf * 0.55))
    # Conflicted: the top two hypotheses are close enough (runner-up within
    # 85% of the winner's score, and the winner has some real support) that
    # picking one and discarding the other throws away real information —
    # this is exactly the kind of setup likely to whipsaw.
    conflicted = winner.score > 0 and runner_up.score >= winner.score * 0.85
    return winner, max(0, min(confidence, 95)), conflicted


# Reward:risk floor a target is allowed to settle for. The evidence-scaled
# projection below is designed to always clear this by construction; a
# structure-level or volume-profile target is only used as a substitute when
# it also clears it — otherwise a real level sitting close to entry would
# quietly turn a decent setup into one that risks more than it can gain.
MIN_ACCEPTABLE_RR = 1.2

# A "next structure level" more than this many multiples of the risk
# distance away is treated as aspirational rather than a realistic
# single-cycle target (e.g. the next swing high sitting far outside the
# recent range) — the evidence-scaled projection is used instead.
MAX_STRUCTURE_EXTENSION_MULT = 4.0

# The R-multiple fallback target scales with how strong the winning
# hypothesis's case actually is, instead of applying one flat multiplier to
# every setup regardless of conviction. A marginal, barely-cleared-the-bar
# call gets a conservative target near the floor; a high-agreement,
# multi-signal-confirmed call gets a more ambitious one.
MIN_EVIDENCE_MULT = 1.3
MAX_EVIDENCE_MULT = 2.5


def _evidence_scaled_multiplier(confidence: int) -> float:
    """
    Maps confidence (35-95 after _confidence_from_scores' compression) onto
    a 1.3x-2.5x reward multiplier for the fallback R-multiple target.
    """
    conf_norm = max(0.0, min((confidence - 35) / (95 - 35), 1.0))
    return MIN_EVIDENCE_MULT + conf_norm * (MAX_EVIDENCE_MULT - MIN_EVIDENCE_MULT)


def _select_target(
    is_long: bool, last_close: float, risk_distance: float,
    next_level: float | None, vp_level: float | None, evidence_multiplier: float,
) -> tuple[float, str]:
    """
    Picks the target price, preferring (in this order):
      1. A real further-out structure level (the next swing high/low beyond
         the immediate resistance/support) — if one exists, sits on the
         correct side of entry, clears MIN_ACCEPTABLE_RR, and isn't an
         unrealistic reach (MAX_STRUCTURE_EXTENSION_MULT).
      2. An evidence-scaled R-multiple projection, when no such level
         exists or it fails those checks — this always clears the RR floor
         by construction, since it's derived directly from risk_distance.
    A volume-profile value-area edge can then pull the chosen target CLOSER
    to entry (never further out) if a real high-volume zone sits in the
    way — the market has a genuine reason to pause there — as long as doing
    so still clears MIN_ACCEPTABLE_RR.
    """
    sign = 1 if is_long else -1
    risk_distance = max(risk_distance, last_close * 1e-6)  # guard against a degenerate zero/negative distance

    target = last_close + sign * risk_distance * evidence_multiplier
    source = "evidence-scaled projection"

    if next_level is not None:
        next_reward = sign * (next_level - last_close)
        next_rr = next_reward / risk_distance
        on_correct_side = next_reward > 0
        realistic = next_reward <= risk_distance * MAX_STRUCTURE_EXTENSION_MULT
        if on_correct_side and next_rr >= MIN_ACCEPTABLE_RR and realistic:
            target = next_level
            source = "next structure level"

    if vp_level is not None:
        vp_reward = sign * (vp_level - last_close)
        vp_rr = vp_reward / risk_distance
        on_correct_side = vp_reward > 0
        nearer_than_current_target = sign * (target - vp_level) > 0
        if on_correct_side and nearer_than_current_target and vp_rr >= MIN_ACCEPTABLE_RR:
            target = vp_level
            source = "volume profile value area"

    return target, source


def build_report(
    symbol: str, trend: dict, momentum: dict, structure: dict, risk: dict, news: dict,
    correlation: dict | None = None, volume_profile: dict | None = None,
) -> dict:
    hypotheses = _score_hypotheses(trend, momentum, structure, news, volume_profile)
    winner, confidence, conflicted = _confidence_from_scores(hypotheses)

    last_close = structure["last_close"]

    # Direction and bias are fixed by the winning hypothesis; confidence
    # still gets adjusted below (correlation discount, conflict cap) BEFORE
    # target selection, so a discounted/conflicted setup also gets a more
    # conservative evidence-scaled target, not just a lower confidence number
    # sitting next to an unchanged price.
    if winner.name == "A":
        bias, direction = ("Bullish" if confidence >= 60 else "Moderately bullish"), "LONG"
    elif winner.name == "D":
        bias, direction = ("Bearish" if confidence >= 60 else "Moderately bearish"), "SHORT"
    elif winner.name == "B":
        bias, direction = "Cautious / choppy", "WAIT"
    else:
        bias, direction = "Neutral / range-bound", "WAIT"

    # Correlation agent: doesn't veto (that's Risk's job), but discounts
    # confidence when this symbol's technical story is more likely BTC beta
    # riding a directionless BTC than a real symbol-specific edge.
    correlation_note = ""
    if correlation and correlation.get("discount_confidence") and direction != "WAIT":
        confidence = int(round(confidence * 0.75))
        correlation_note = (
            f" (Confidence discounted: {correlation['btc_correlation']*100:.0f}% correlated to BTC, "
            "which itself is directionless right now.)"
        )

    # Conflicted read: the runner-up hypothesis was nearly as well supported
    # as the winner — flag it rather than silently presenting false
    # certainty, and cap confidence accordingly.
    if conflicted and direction != "WAIT":
        confidence = min(confidence, 55)
        bias += " (conflicted read)"

    if winner.name == "A":  # uptrend
        invalidation = structure["support"]
        risk_distance = last_close - invalidation
        evidence_multiplier = _evidence_scaled_multiplier(confidence)
        vp_level = volume_profile.get("value_area_high") if volume_profile else None
        target, target_source = _select_target(
            True, last_close, risk_distance, structure.get("next_resistance"), vp_level, evidence_multiplier
        )
        do_nothing_if = "Price falls back below the invalidation level, or volume collapses on the next bar." + correlation_note
    elif winner.name == "D":  # downtrend
        invalidation = structure["resistance"]
        risk_distance = invalidation - last_close
        evidence_multiplier = _evidence_scaled_multiplier(confidence)
        vp_level = volume_profile.get("value_area_low") if volume_profile else None
        target, target_source = _select_target(
            False, last_close, risk_distance, structure.get("next_support"), vp_level, evidence_multiplier
        )
        do_nothing_if = "Price reclaims back above the invalidation level, or volume collapses on the next bar." + correlation_note
    elif winner.name == "B":  # reversal caution
        invalidation = structure["resistance"]
        target = structure["support"]
        target_source = "mean reversion (no R:RR target — this hypothesis expects a bounce, not a sized trade)"
        do_nothing_if = "No confirmation within the next 1-2 bars — this hypothesis expects mean reversion, not continuation."
    else:  # range bound
        invalidation = None
        target = None
        target_source = None
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

    # Reward:Risk — computed from the FINAL entry/invalidation/target after
    # every adjustment above (correlation discount and conflict-capping
    # already shaped the evidence multiplier that set target; the risk veto
    # zeroes the trade out by forcing WAIT). Only meaningful for an actual
    # directional call with both levels set — the reversal-caution
    # hypothesis targets mean reversion, not a sized R:RR trade.
    risk_reward_ratio = None
    if direction in ("LONG", "SHORT") and invalidation is not None and target is not None:
        risk_amount = abs(last_close - invalidation)
        reward_amount = abs(target - last_close)
        if risk_amount > 0:
            risk_reward_ratio = round(reward_amount / risk_amount, 2)

    what_changed = winner.supporting[0] if winner.supporting else "No single dominant signal this cycle."

    now = datetime.utcnow()
    next_review = now + timedelta(hours=1)

    evidence = winner.supporting + [f"(against) {c}" for c in winner.contradicting]
    if conflicted:
        runner_up = sorted(hypotheses, key=lambda h: h.score, reverse=True)[1]
        evidence.append(
            f"(conflict) '{runner_up.label}' scored nearly as well ({runner_up.score:.2f} vs "
            f"{winner.score:.2f}) — treat this call with extra caution"
        )

    return {
        "symbol": symbol,
        "timestamp": now.isoformat(),
        "next_review": next_review.isoformat(),
        "bias": bias,
        "confidence": confidence,
        "conflicted_signal": conflicted,
        "market_regime": market_regime,
        "what_changed": what_changed,
        "evidence": evidence,
        "direction": direction,
        "entry_price": round_price(last_close),
        "invalidation_price": round_price(invalidation),
        "target_price": round_price(target),
        "risk_reward_ratio": risk_reward_ratio,
        "risk_level": risk["risk_level"],
        "do_nothing_if": do_nothing_if,
        "hypotheses_considered": [
            {"name": h.name, "label": h.label, "score": round(h.score, 2)} for h in hypotheses
        ],
        "agent_outputs": {
            "trend": trend, "momentum": momentum, "structure": structure,
            "risk": risk, "news_sentiment": news,
            "correlation": correlation, "volume_profile": volume_profile,
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
    if report["risk_reward_ratio"] is not None:
        lines.append(f"Risk:Reward: {report['risk_reward_ratio']}:1")
    lines.append(f"Risk: {report['risk_level'].capitalize()}")
    lines.append(f"Do nothing if: {report['do_nothing_if']}")
    lines.append(f"Next review: {datetime.fromisoformat(report['next_review']).strftime('%I:%M %p').lstrip('0')}")
    return "\n".join(lines)