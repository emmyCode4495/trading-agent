"""
News/Macro + Sentiment Agent — the one agent that legitimately needs an LLM,
because it's interpreting language (headlines, events), not computing numbers.

Disabled by default (ENABLE_LLM_AGENTS=false) so the rest of the pipeline is
fully runnable with zero API keys. Turn it on once you've set
ANTHROPIC_API_KEY in your .env.

Keep the discipline from the source design doc: numeric agents never touch
the LLM, and this agent never invents numbers, it only reasons over
retrieved text.
"""
import json

from app.config import settings

NEUTRAL_STUB = {
    "agent": "news_sentiment",
    "label": "neutral",
    "headline_summary": "LLM agent disabled — set ENABLE_LLM_AGENTS=true and ANTHROPIC_API_KEY to activate.",
    "notable_events": [],
    "sentiment_score": 0,  # -100..100
}


def run(symbol: str) -> dict:
    if not settings.enable_llm_agents or not settings.anthropic_api_key:
        return NEUTRAL_STUB

    try:
        import anthropic
    except ImportError:
        return {**NEUTRAL_STUB, "headline_summary": "anthropic package not installed (`pip install anthropic`)."}

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    system = (
        "You are a market news/sentiment analyst. You will be asked about one asset. "
        "Search for recent news and gauge market sentiment. "
        "Respond with ONLY a JSON object (no prose, no markdown fences) matching this schema: "
        '{"label": "bullish|bearish|neutral", "headline_summary": "<= 2 sentences", '
        '"notable_events": ["short phrase", ...max 3], "sentiment_score": <int -100..100>}'
    )

    try:
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=500,
            system=system,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": f"Recent news and sentiment for {symbol}."}],
        )
        text_parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
        raw = "\n".join(text_parts).strip().strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
        parsed = json.loads(raw)
        return {"agent": "news_sentiment", **parsed}
    except Exception as exc:  # noqa: BLE001 — degrade gracefully, never crash the pipeline
        return {**NEUTRAL_STUB, "headline_summary": f"news_sentiment agent failed: {exc}"}
