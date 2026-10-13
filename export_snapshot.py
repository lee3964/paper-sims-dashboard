#!/usr/bin/env python3
"""Write docs/data/latest.json and a timestamped history copy."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aggregate import aggregate

ROOT = Path(__file__).resolve().parent
DOCS_DATA = ROOT / "docs" / "data"
HISTORY = DOCS_DATA / "history"
TZ = ZoneInfo("Asia/Singapore")


def main() -> int:
    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    HISTORY.mkdir(parents=True, exist_ok=True)
    snap = aggregate()
    latest = DOCS_DATA / "latest.json"
    latest.write_text(
        json.dumps(snap, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    stamp = datetime.now(TZ).strftime("%Y%m%d-%H%M%S")
    hist = HISTORY / f"{stamp}.json"
    hist.write_text(latest.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"wrote {latest}")
    print(f"wrote {hist}")
    for b in snap["bots"]:
        pnl_pct = (
            (b["equity"] - b["start_cash"]) / b["start_cash"] * 100
            if b["start_cash"]
            else 0
        )
        print(
            f"  {b['id']}: equity={b['equity']} cash={b['cash']} "
            f"pnl%={pnl_pct:.2f} trades={b['trade_count']} "
            f"W/L={b['win_count']}/{b['loss_count']} "
            f"trader={b.get('current_trader')} open={b['open_positions_count']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
