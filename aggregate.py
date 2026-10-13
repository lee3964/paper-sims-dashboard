#!/usr/bin/env python3
"""Aggregate three paper-sim ledgers into one normalized snapshot."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Singapore")

ROOT = Path("/workspace")
FOMO_BOAN = ROOT / "fomo-sim-0xboan"
FOMO_TENZO = ROOT / "fomo-sim"
SAVIPWW = ROOT / "paper-trading"
SAVIPWW_DATA = SAVIPWW / "data"
SAVIPWW_CFG = SAVIPWW / "config.yaml"

EVENT_TYPES = {"hire", "fire", "open", "close", "skip", "rules_update", "system_init"}


def _now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if limit is not None and len(rows) > limit:
        return rows[-limit:]
    return rows


def _normalize_event(ev: dict[str, Any], bot_id: str) -> dict[str, Any] | None:
    et = ev.get("type") or ev.get("event")
    if not et:
        return None
    # Map journal-style fill events → open/close
    if et == "fill_buy" or et == "fill_alpaca_paper":
        et = "open"
    elif et == "fill_sell":
        et = "close"

    keep = {"hire", "fire", "open", "close", "skip", "rules_update"}
    if et not in keep:
        return None

    pnl = ev.get("pnl")
    if pnl is None:
        pnl = ev.get("realized_pnl")
    if pnl is None and isinstance(ev.get("closed"), dict):
        pnl = ev["closed"].get("realized_pnl")
    if pnl is None and isinstance(ev.get("meta"), dict):
        pnl = ev["meta"].get("realized_pnl")

    handle = ev.get("handle")
    symbol = ev.get("symbol")
    msg = ev.get("msg") or ev.get("reason") or ev.get("note") or ""
    summary = msg
    if handle and not summary:
        summary = f"@{handle}"
    if symbol and et in ("open", "close", "skip"):
        summary = f"{symbol}" + (f" · {msg}" if msg else "")

    return {
        "ts": ev.get("ts") or ev.get("timestamp") or "",
        "type": et,
        "bot_id": bot_id,
        "handle": handle,
        "symbol": symbol,
        "pnl": pnl,
        "msg": summary[:200] if summary else "",
    }


def _recent_events(path: Path, bot_id: str, n: int = 20) -> list[dict[str, Any]]:
    raw = _read_jsonl(path)
    out: list[dict[str, Any]] = []
    for ev in raw:
        norm = _normalize_event(ev, bot_id)
        if norm and norm["type"] in ("hire", "fire", "open", "close", "skip", "rules_update"):
            out.append(norm)
    return out[-n:]


def _fomo_sizing_note(cfg: dict[str, Any]) -> str:
    ratio = cfg.get("copy_ratio") or cfg.get("copy_size_mult") or 0.25
    frac = (
        cfg.get("equity_fraction_fallback")
        or cfg.get("equity_pct_fallback")
        or 0.05
    )
    cap = cfg.get("max_equity_fraction") or cfg.get("max_position_pct_equity") or 0.25
    return f"对方下单×{ratio:g}；未知则权益×{frac:g}；单笔上限权益×{cap:g}"


def aggregate_fomo(bot_id: str, name: str, root: Path) -> dict[str, Any]:
    ledger = _read_json(root / "ledger.json")
    cfg = _read_json(root / "config.json")
    events_path = root / "events.jsonl"
    start = float(cfg.get("start_cash") or ledger.get("start_cash") or 1000.0)
    cash = float(ledger.get("cash") or 0)
    equity = float(ledger.get("equity") or cash)
    trader = ledger.get("current_trader")
    trader_handle = None
    if isinstance(trader, dict):
        trader_handle = trader.get("handle")
    elif isinstance(trader, str):
        trader_handle = trader
    open_pos = ledger.get("open_positions") or []
    open_count = len(open_pos) if isinstance(open_pos, list) else len(open_pos)

    return {
        "id": bot_id,
        "name": name,
        "strategy": "FOMO 周榜跟单 · 两连亏换人",
        "start_cash": start,
        "cash": round(cash, 4),
        "equity": round(equity, 4),
        "realized_pnl": round(float(ledger.get("realized_pnl") or 0), 4),
        "trade_count": int(ledger.get("trade_count") or 0),
        "win_count": int(ledger.get("win_count") or 0),
        "loss_count": int(ledger.get("loss_count") or 0),
        "open_positions_count": open_count,
        "current_trader": trader_handle,
        "consecutive_losses": int(
            ledger.get("consecutive_losses_current_trader")
            or ledger.get("consecutive_losses")
            or 0
        ),
        "sizing_note": _fomo_sizing_note(cfg),
        "updated_at": ledger.get("updated_at") or cfg.get("updated_at") or _now_iso(),
        "recent_events": _recent_events(events_path, bot_id),
        "source_path": str(root),
    }


def _parse_yaml_simple_start_cash(path: Path) -> float:
    """Minimal YAML peek for meme starting_cash_usd without PyYAML dependency."""
    if not path.exists():
        return 100.0
    text = path.read_text(encoding="utf-8")
    in_meme = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("meme:"):
            in_meme = True
            continue
        if in_meme and stripped.startswith("starting_cash_usd:"):
            try:
                return float(stripped.split(":", 1)[1].strip().split()[0])
            except ValueError:
                return 100.0
        if in_meme and stripped and not stripped.startswith("#") and not line.startswith(" ") and not line.startswith("\t"):
            # left meme block
            if not line.startswith(" ") and not line.startswith("\t"):
                in_meme = False
        if in_meme and stripped.startswith("alpaca:"):
            in_meme = False
    return 100.0


def aggregate_savipww() -> dict[str, Any]:
    state = _read_json(SAVIPWW_DATA / "ledger_state.json")
    start = float(state.get("starting_cash") or _parse_yaml_simple_start_cash(SAVIPWW_CFG))
    cash = float(state.get("cash") or 0)
    positions = state.get("positions") or {}
    mark_sum = 0.0
    if isinstance(positions, dict):
        for pos in positions.values():
            if not isinstance(pos, dict):
                continue
            if "mark_usd" in pos:
                mark_sum += float(pos["mark_usd"])
            elif "mark_value" in pos:
                mark_sum += float(pos["mark_value"])
            elif "qty" in pos and "mark_price" in pos:
                mark_sum += float(pos["qty"]) * float(pos["mark_price"])
            elif "entry_cost_usd" in pos:
                mark_sum += float(pos["entry_cost_usd"])
            elif "notional_usd" in pos:
                mark_sum += float(pos["notional_usd"])
        open_count = len(positions)
    else:
        open_count = len(positions)

    equity = cash + mark_sum
    closed = state.get("closed") or []
    wins = losses = 0
    realized = 0.0
    for c in closed:
        if not isinstance(c, dict):
            continue
        pnl = float(c.get("realized_pnl") or 0)
        realized += pnl
        if pnl > 0:
            wins += 1
        elif pnl < 0:
            losses += 1

    # Prefer events.jsonl; fall back to journal mapped types
    events_path = SAVIPWW_DATA / "events.jsonl"
    recent = _recent_events(events_path, "savipww")
    if len(recent) < 3:
        journal = SAVIPWW_DATA / "journal.jsonl"
        recent = _recent_events(journal, "savipww")

    kelly = 6.0
    if SAVIPWW_CFG.exists():
        for line in SAVIPWW_CFG.read_text(encoding="utf-8").splitlines():
            if "kelly_cap_pct_of_bank" in line:
                try:
                    kelly = float(line.split(":", 1)[1].strip().split()[0])
                except ValueError:
                    pass
                break

    return {
        "id": "savipww",
        "name": "模拟盘savipww",
        "strategy": "八席纸面台 QUANT→SCAN→JUDGE→SIZE→FILL · RISK",
        "start_cash": start,
        "cash": round(cash, 4),
        "equity": round(equity, 4),
        "realized_pnl": round(realized, 4),
        "trade_count": len(closed),
        "win_count": wins,
        "loss_count": losses,
        "open_positions_count": open_count,
        "current_trader": None,
        "consecutive_losses": None,
        "sizing_note": f"Kelly×自由现金，meme 封顶约 {kelly:g}% · QUANT 拨盘",
        "updated_at": state.get("saved_at") or _now_iso(),
        "recent_events": recent,
        "source_path": str(SAVIPWW_DATA),
        "seats": ["CHIEF", "QUANT", "SCAN", "JUDGE", "STOCKS", "SIZE", "FILL", "RISK"],
    }


def aggregate() -> dict[str, Any]:
    bots = [
        aggregate_fomo("0xboan", "模拟盘0xboan", FOMO_BOAN),
        aggregate_fomo("0xTenzo", "模拟盘0xTenzo", FOMO_TENZO),
        aggregate_savipww(),
    ]
    # Merge recent events across bots for the dashboard table
    all_events: list[dict[str, Any]] = []
    for b in bots:
        for ev in b.get("recent_events") or []:
            all_events.append({**ev, "bot_name": b["name"]})
    all_events.sort(key=lambda e: e.get("ts") or "", reverse=True)

    return {
        "generated_at": _now_iso(),
        "timezone": "Asia/Singapore",
        "bots": bots,
        "recent_events": all_events[:40],
        "note": "纸面模拟 · 非实盘 · Paper only",
    }


if __name__ == "__main__":
    print(json.dumps(aggregate(), ensure_ascii=False, indent=2))
