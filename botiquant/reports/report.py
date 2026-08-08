"""Report builder.

* ``html_report`` — a fully self-contained HTML file (inline SVG charts, no
  JS, no external assets). Print it to PDF from any browser.
* ``excel_report`` — multi-sheet workbook (Summary, Trades, Monthly, Equity).
* ``trades_csv`` / ``metrics_csv`` — flat CSV exports.
"""

from __future__ import annotations

import io
from html import escape
from typing import Any

import numpy as np
import pandas as pd

_METRIC_LABELS: list[tuple[str, str, str]] = [
    ("net_profit", "Net profit", "$"),
    ("net_profit_pct", "Net profit %", "%"),
    ("cagr_pct", "CAGR", "%"),
    ("profit_factor", "Profit factor", ""),
    ("sharpe", "Sharpe ratio", ""),
    ("sortino", "Sortino ratio", ""),
    ("max_drawdown_pct", "Max drawdown", "%"),
    ("recovery_factor", "Recovery factor", ""),
    ("win_rate_pct", "Win rate", "%"),
    ("trades", "Trades", ""),
    ("avg_trade", "Average trade", "$"),
    ("expectancy_r", "Expectancy (R)", ""),
]


def _fmt(v: Any, unit: str) -> str:
    if isinstance(v, (int, np.integer)):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:,.2f}{'%' if unit == '%' else ''}"
    return str(v)


def _svg_equity(equity: list[float], width: int = 900, height: int = 260) -> str:
    if len(equity) < 2:
        return ""
    a = np.asarray(equity, dtype=np.float64)
    lo, hi = float(a.min()), float(a.max())
    span = (hi - lo) or 1.0
    pad = 10
    xs = np.linspace(pad, width - pad, len(a))
    ys = height - pad - (a - lo) / span * (height - 2 * pad)
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    base = a[0]
    base_y = height - pad - (base - lo) / span * (height - 2 * pad)
    return (
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;height:auto;background:#11141b;border-radius:12px">'
        f'<line x1="{pad}" y1="{base_y:.1f}" x2="{width - pad}" y2="{base_y:.1f}" '
        f'stroke="#39415a" stroke-dasharray="4 4" stroke-width="1"/>'
        f'<polyline points="{pts}" fill="none" stroke="#6d8dff" stroke-width="2"/>'
        f"</svg>"
    )


def _monthly_table(monthly: list[dict[str, Any]]) -> str:
    if not monthly:
        return "<p>No monthly data.</p>"
    years = sorted({m["year"] for m in monthly})
    grid = {(m["year"], m["month"]): m["return_pct"] for m in monthly}
    head = "".join(f"<th>{mn}</th>" for mn in
                   ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Year"])
    rows = []
    for y in years:
        cells = []
        yr_total = 1.0
        for mo in range(1, 13):
            v = grid.get((y, mo))
            if v is None:
                cells.append("<td>–</td>")
            else:
                yr_total *= 1.0 + v / 100.0
                cls = "pos" if v >= 0 else "neg"
                cells.append(f'<td class="{cls}">{v:.1f}</td>')
        tot = (yr_total - 1.0) * 100.0
        cells.append(f'<td class="{"pos" if tot >= 0 else "neg"}"><b>{tot:.1f}</b></td>')
        rows.append(f"<tr><th>{y}</th>{''.join(cells)}</tr>")
    return (f'<table class="monthly"><thead><tr><th></th>{head}</tr></thead>'
            f"<tbody>{''.join(rows)}</tbody></table>")


def html_report(result: dict[str, Any], title: str, dataset_name: str) -> str:
    """Render one backtest payload as a standalone HTML document."""
    metrics = result.get("metrics", {})
    trades = result.get("trades", [])
    strategy = result.get("strategy", {})

    metric_rows = "".join(
        f"<div class='metric'><span>{label}</span><b>{_fmt(metrics.get(key, 0), unit)}</b></div>"
        for key, label, unit in _METRIC_LABELS
    )
    rules = []
    for group, gl in (("entry_long", "Long entry"), ("entry_short", "Short entry"),
                      ("exit_long", "Long exit"), ("exit_short", "Short exit")):
        conds = strategy.get(group) or []
        if conds:
            from botiquant.core.models import Condition
            labels = " AND ".join(escape(Condition.from_dict(c).label()) for c in conds)
            rules.append(f"<p><b>{gl}:</b> {labels}</p>")

    trade_rows = "".join(
        f"<tr><td>{escape(str(t['entry_time']))}</td><td>{escape(str(t['exit_time']))}</td>"
        f"<td>{t['direction']}</td><td>{t['entry_price']}</td><td>{t['exit_price']}</td>"
        f"<td class='{'pos' if t['pnl'] >= 0 else 'neg'}'>{t['pnl']:,.2f}</td>"
        f"<td>{t['exit_reason']}</td></tr>"
        for t in trades[:500]
    )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{escape(title)} — Botiquant report</title>
<style>
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0b0d12;color:#e6e9f2;
     margin:0;padding:40px;max-width:1000px;margin-inline:auto}}
h1{{font-weight:600;font-size:26px}} h2{{font-weight:600;font-size:18px;margin-top:36px}}
.sub{{color:#8b93a8}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin:20px 0}}
.metric{{background:#161a24;border:1px solid #232a3b;border-radius:12px;padding:14px 16px}}
.metric span{{display:block;color:#8b93a8;font-size:12px;margin-bottom:4px}}
.metric b{{font-size:18px}}
table{{border-collapse:collapse;width:100%;font-size:13px;margin-top:12px}}
th,td{{padding:6px 10px;text-align:right;border-bottom:1px solid #232a3b}}
th:first-child,td:first-child{{text-align:left}}
.pos{{color:#4ade80}} .neg{{color:#f87171}}
.monthly td,.monthly th{{text-align:center}}
@media print{{body{{background:#fff;color:#111}} .metric{{border-color:#ddd;background:#fafafa}}
th,td{{border-color:#ddd}}}}
</style></head><body>
<h1>{escape(title)}</h1>
<p class="sub">Dataset: {escape(dataset_name)} · Generated by Botiquant (offline, deterministic)</p>
{''.join(rules)}
<h2>Performance</h2>
<div class="grid">{metric_rows}</div>
<h2>Equity curve</h2>
{_svg_equity(result.get('equity', []))}
<h2>Monthly returns (%)</h2>
{_monthly_table(result.get('monthly_returns', []))}
<h2>Trades (first 500)</h2>
<table><thead><tr><th>Entry</th><th>Exit</th><th>Dir</th><th>Entry px</th>
<th>Exit px</th><th>P&amp;L</th><th>Reason</th></tr></thead>
<tbody>{trade_rows}</tbody></table>
</body></html>"""


def trades_csv(result: dict[str, Any]) -> str:
    trades = result.get("trades", [])
    if not trades:
        return "entry_time,exit_time,direction,entry_price,exit_price,units,pnl,pnl_pct,bars,exit_reason\n"
    df = pd.DataFrame(trades)
    return df.to_csv(index=False)


def metrics_csv(result: dict[str, Any]) -> str:
    m = result.get("metrics", {})
    df = pd.DataFrame([m])
    return df.to_csv(index=False)


def excel_report(result: dict[str, Any], title: str) -> bytes:
    """Multi-sheet Excel workbook for one backtest payload."""
    buf = io.BytesIO()
    metrics = result.get("metrics", {})
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        pd.DataFrame({"Metric": [lbl for _, lbl, _ in _METRIC_LABELS],
                      "Value": [metrics.get(k, "") for k, _, _ in _METRIC_LABELS]}) \
            .to_excel(xw, sheet_name="Summary", index=False)
        trades = result.get("trades", [])
        (pd.DataFrame(trades) if trades else pd.DataFrame()) \
            .to_excel(xw, sheet_name="Trades", index=False)
        monthly = result.get("monthly_returns", [])
        (pd.DataFrame(monthly) if monthly else pd.DataFrame()) \
            .to_excel(xw, sheet_name="Monthly", index=False)
        eq = result.get("equity", [])
        ts = result.get("timestamps", [])
        pd.DataFrame({"time": ts[:len(eq)], "equity": eq}) \
            .to_excel(xw, sheet_name="Equity", index=False)
    return buf.getvalue()
