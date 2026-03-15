from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from app.config import settings


LLM_INSTRUCTION = """You are a crypto trading advisor analyzing market data for BTC/USDT.

Current market state:
- Price: {current_price}
- EMA-9 (fast): {features[ema_fast]}
- EMA-21 (slow): {features[ema_slow]}
- RSI-14: {features[rsi]}
- ATR-14: {features[atr]}

Strategy signal: {signal[direction]} (confidence: {signal[confidence]})
Reason: {signal[reason]}

Provide a brief JSON analysis with:
1. "agree": true/false - whether you agree with the signal
2. "confidence": 0.0-1.0 - your confidence level
3. "reasoning": brief explanation (2-3 sentences max)
4. "recommendation": "BUY", "SELL", or "HOLD"

Respond ONLY with valid JSON. You are advisory only - execution is deterministic."""


def create_llm_reasoner() -> Agent:
    return Agent(
        name="llm_reasoner",
        model=LiteLlm(model=settings.llm_model),
        instruction=LLM_INSTRUCTION,
        description="LLM advisor that reasons about trading signals",
        output_key="llm_reasoning",
        include_contents="none",
    )
