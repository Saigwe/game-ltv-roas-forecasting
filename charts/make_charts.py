"""README charts from results/results.md (written by `make all`).
Usage: python charts/make_charts.py [results/results.md]"""
import re
import sys
from pathlib import Path

import style as st

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results" / "results.md"
OUT = ROOT / "docs" / "charts"


def tables(md: str) -> dict:
    """Markdown tables keyed by the nearest heading above them."""
    out, head, rows = {}, None, []
    for line in md.splitlines() + [""]:
        if line.startswith("#"):
            head = line.lstrip("# ").strip()
        elif line.startswith("|"):
            cells = [c.strip().strip("*") for c in line.strip().strip("|").split("|")]
            if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                rows.append(cells)
        elif rows:
            out[head] = [dict(zip(rows[0], r)) for r in rows[1:]]
            rows = []
    return out


def num(s: str) -> float:
    return float(s.replace("%", "").replace("+", "").replace("$", "").replace(",", ""))


t = tables(SRC.read_text(encoding="utf-8"))
rec = next(v for k, v in t.items() if k.startswith("Recommendation from day 30"))
f, ax = st.fig(8, 3.5)
x = range(len(rec))
b1 = ax.bar([i - 0.27 for i in x], [num(r["D7 ROAS"]) for r in rec], 0.26, color=st.MUTED, label="Day-7 ROAS")
lo = [num(r["90% range"].split(" to ")[0]) for r in rec]
hi = [num(r["90% range"].split(" to ")[1]) for r in rec]
fc = [num(r["D180 ROAS forecast"]) for r in rec]
b2 = ax.bar(list(x), fc, 0.26, color=st.S[0], label="Day-180 forecast from day 30, with 90% range",
            yerr=[[f - l for f, l in zip(fc, lo)], [h - f for f, h in zip(fc, hi)]], error_kw={"ecolor": st.TEXT, "capsize": 3, "lw": 1})
b3 = ax.bar([i + 0.27 for i in x], [num(r["Actual D180 ROAS"]) for r in rec], 0.26, color=st.S[2], label="Actual day-180 ROAS (generated truth)")
for b in (b1, b3):
    st.vbar_labels(ax, b, lambda v: f"{v:.2f}")
ax.axhline(1.0, color=st.CRITICAL, lw=1, ls="--", label="Payback (ROAS 1.0)")
ax.set_xticks(list(x), [f"{r['Channel'].replace('_', ' ')}: {r['Decision']}" for r in rec])
ax.set_ylim(0, max(hi) * 1.15)
best7 = max(rec, key=lambda r: num(r["D7 ROAS"]))["Channel"].replace("_", " ")
st.head(ax, f"The best day-7 channel ({best7}) is the worst investment by day 180",
        "ROAS by acquisition channel; the decision scales a channel only when the low end of its range pays back", legend=True, ncol=2)
st.save(f, OUT / "roas_trap.png")

bt = next(v for k, v in t.items() if k.startswith("Backtest"))
chans = list(dict.fromkeys(r["Channel"] for r in bt))
ks = list(dict.fromkeys(r["k"] for r in bt))
f, ax = st.fig(8, 3.2)
w = 0.8 / len(ks)
for j, k in enumerate(ks):
    vals = [num(next(r["Multiplier MAPE"] for r in bt if r["Channel"] == c and r["k"] == k)) / 100 for c in chans]
    bars = ax.bar([i - 0.4 + w * (j + 0.5) for i in range(len(chans))], vals, w * 0.92, color=st.SEQ[1 + j] if hasattr(st, "SEQ") else st.S[j],
                  label=f"Forecast from day {k}")
    st.vbar_labels(ax, bars, lambda v: f"{v:.0%}")
ax.set_xticks(range(len(chans)), [c.replace("_", " ") for c in chans])
st.fmt(ax, "y", "pct")
curve = max(num(r["Curve-fit MAPE"]) for r in bt)
st.head(ax, f"By day {ks[-1]}, forecast error is at its lowest in every channel",
        f"Backtest mean absolute % error of the multiplier method on day-180 revenue per install (curve fitting was up to {curve:.0f}%)",
        legend=True)
st.save(f, OUT / "backtest_error.png")
print(f"wrote charts to {OUT}")
