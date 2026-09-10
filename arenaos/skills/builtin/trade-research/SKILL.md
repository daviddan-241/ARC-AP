---
name: trade-research
description: Market + strategy research with honest risk framing (freqtrade style).
---

Research markets/strategies with data, not vibes:
1. Get REAL data: http_request to public endpoints (exchange price
   candles, OHLCV) for the assets + timeframe in question.
2. Analyze with the shell tool (python/pandas if needed) — trends,
   volatility, drawdowns. No made-up numbers: compute from the fetched data.
3. For strategy ideas: describe entry/exit rules precisely, then evaluate
   honestly — including fees, slippage, and the risk of ruin.
4. Report: tables of computed stats, the top risks, and what would falsify
   the thesis. Trading involves risk — present it plainly, never hype.
You analyze; the operator decides.
