#!/usr/bin/env python3
"""Write docs/data/latest.json, per-bot detail JSON, and a history copy."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aggregate import snapshots

ROOT = Path(__file__).resolve().parent
DOCS_DATA = ROOT / "docs" / "data"
HISTORY = DOCS_DATA / "history"
BOTS = DOCS_DATA / "bots"
TZ = ZoneInfo("Asia/Singapore")


def _dump(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    HISTORY.mkdir(parents=True, exist_ok=True)
    BOTS.mkdir(parents=True, exist_ok=True)
    snap, details = snapshots()
    latest = DOCS_DATA / "latest.json"
    _dump(latest, snap)
    stamp = datetime.now(TZ).strftime("%Y%m%d-%H%M%S")
    hist = HISTORY / f"{stamp}.json"
    _dump(hist, snap)
    print(f"wrote {latest}")
    print(f"wrote {hist}")
    for bot_id, payload in details.items():
        path = BOTS / f"{bot_id}.json"
        _dump(path, payload)
        bot = payload["bot"]
        events = bot.get("events") or []
        archived = sum(1 for ev in events if ev.get("archived"))
        print(f"wrote {path} events={len(events)} archived={archived} open={len(bot.get('open_positions') or [])}")
    for b in snap["bots"]:
        pnl_pct = (b["equity"] - b["start_cash"]) / b["start_cash"] * 100 if b["start_cash"] else 0
        print(
            f"  {b['id']}: equity={b['equity']} cash={b['cash']} "
            f"pnl%={pnl_pct:.2f} trades={b['trade_count']} "
            f"W/L={b['win_count']}/{b['loss_count']} "
            f"trader={b.get('current_trader')} open={b['open_positions_count']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
