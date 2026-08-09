# ⚡ Botiquant

**The analytical power of StrategyQuant, redesigned for simplicity.**

Botiquant is a quantitative strategy builder: compose trading strategies from
indicator blocks, generate and evolve them algorithmically, validate them with Monte Carlo
and walk-forward analysis, and combine them into portfolios — with zero AI and zero
external APIs. Every computation is deterministic Python.

It runs two ways from the same codebase. **Cloned and run locally** it needs no accounts
and no network: that is the default and nothing below changes. **Served to other people**
it grows a Google sign-in and requires an account — set the variables in `.env.example`
and the gate turns itself on. Absent those variables there is no login at all, which is
what keeps the local install exactly as simple as it was.

---

## Quick start

```bash
cd Botiquant
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt      # Windows
.venv\Scripts\python run.py
```

Open **http://127.0.0.1:8765**. Three deterministic sample datasets are seeded on first
run, so everything works immediately — no data required.

Run the tests:

```bash
.venv\Scripts\python -m pytest tests -q
```

## What it does

| Page | What you get |
|---|---|
| **Data** | Import CSVs (generic, MetaTrader, TradingView, Binance kline) with auto-detected delimiters/columns/epochs; resample to higher timeframes; create seeded synthetic OHLCV |
| **Builder** | Visual rule blocks: `EMA(50) crosses above EMA(200)`, `RSI < 30`, `Close > VWAP`… plus ATR/percent stops & targets, risk-based position sizing, session/day time filters. Advanced settings stay collapsed |
| **Generator** | Deterministically enumerates entry-driver × filter combinations, backtests every candidate and ranks by a robustness-aware fitness score |
| **Evolution** | Seeded genetic algorithm (tournament selection, uniform crossover, gaussian gene mutation, elitism). Same seed → identical evolution, always |
| **Optimizer** | Auto-discovers every tunable number in a strategy. Quick = random search, Balanced = random + hill-climb, Exhaustive = budget-capped grid |
| **Validation** | Monte Carlo trade-sequence bootstrap (equity fan, confidence intervals, risk of ruin, drawdown distribution) and walk-forward analysis with per-fold re-optimization and an honest robust/acceptable/overfitted verdict |
| **Portfolio** | Blend saved results: combined equity, daily-return correlation matrix, drawdown, and per-strategy risk contribution |
| **Reports** | One-click standalone HTML report (print to PDF from the browser), multi-sheet Excel workbook, trades/metrics CSV |

## Engine guarantees

- **No lookahead.** Signals are computed on bar close; fills happen at the next bar's open.
  Donchian channels exclude the current bar; Ichimoku senkou lines are properly displaced.
- **Conservative intrabar fills.** If a stop and a target could both fill in one bar, the
  stop fills first. Slippage moves fills against you; commission is charged per side.
- **Determinism everywhere.** Sample data is seeded by symbol; the GA, optimizer and
  Monte Carlo take explicit seeds. Any run can be reproduced exactly.
- **NaN-safe rules.** Indicator warm-up periods can never produce a signal.

## Architecture

```
botiquant/
  core/          domain models (dataclass specs), thread job manager
  data/          format-tolerant CSV loader, resampling, seeded sample generator, store
  indicators/    15 built-in indicators + @register decorator for custom ones
  strategies/    vectorised rule evaluation (numpy boolean algebra)
  backtesting/   event-accurate engine over vectorised signals + full metrics suite
  generator/     rule templates (drivers/filters) + combinatorial generation
  genetic/       deterministic GA evolution
  optimizer/     quick / balanced / exhaustive parameter search
  analysis/      Monte Carlo bootstrap, walk-forward analysis
  portfolio/     multi-strategy combination, correlation, risk contribution
  reports/       standalone HTML, Excel, CSV exports
  database/      SQLite persistence (datasets, strategies, results)
  api/           FastAPI app: JSON API + background jobs + static UI
ui/              dependency-free SPA: custom SVG chart library, dark theme
tests/           46 tests: indicators, engine fills, determinism, search, API
```

Strategies serialize to plain JSON, so they can be stored, diffed and shared as text.

### Adding a custom indicator

```python
from botiquant.indicators.base import Indicator, ParamDef, register

@register
class HullMA(Indicator):
    name = "HullMA"
    label = "Hull Moving Average"
    category = "trend"
    params = (ParamDef("period", 20, 2, 200, 1),)

    @classmethod
    def compute(cls, df, **p):
        n = int(p["period"])
        wma = lambda s, k: s.rolling(k).apply(
            lambda x: (x * range(1, k + 1)).sum() / (k * (k + 1) / 2), raw=True)
        hull = wma(2 * wma(df["close"], n // 2) - wma(df["close"], n), int(n ** 0.5))
        return {"value": hull.to_numpy()}
```

It appears in the Builder's indicator list on the next restart — no other wiring needed.

## Design notes

- **Why no vectorbt/numba?** They don't support the newest CPython and would add compiled
  dependencies. The engine computes signals fully vectorised in numpy and walks bars once
  in a tight loop — ~70 ms for 8,000 bars, ~15–20 s for a 72-candidate generation run on
  26,000 bars. Offline installs stay trivial.
- **Why fitness ≠ net profit?** The default *composite* fitness rewards profit factor and
  trade count while penalising drawdown, which suppresses one-lucky-trade strategies.
  Net profit / profit factor / Sharpe modes are one dropdown away.
- **PDF reports** are produced by printing the standalone HTML report from the browser —
  it has a dedicated print stylesheet — keeping the app free of PDF toolchain dependencies.
