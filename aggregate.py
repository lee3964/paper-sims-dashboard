#!/usr/bin/env python3
"""Aggregate three paper-sim ledgers into one normalized snapshot.

Compare view (`aggregate`) keeps a short `recent_events` list.
Detail view (`detail_snapshot` / `build_bots`) adds open positions and a
long event timeline, including `*.bak.*.jsonl` archives left by ledger resets.
"""
from __future__ import annotations

import copy
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Singapore")

REPO = Path(__file__).resolve().parent
DOCS_DATA = REPO / "docs" / "data"

KEEP_TYPES = {"hire", "fire", "open", "close", "skip", "rules_update"}
RECENT_LIMIT = 20


def _now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _env_path(name: str) -> Path | None:
    raw = os.environ.get(name)
    if not raw:
        return None
    return Path(raw).expanduser()


def _first_with_marker(candidates: list[Path | None], marker: str) -> Path | None:
    for path in candidates:
        if path is None:
            continue
        if (path / marker).exists():
            return path
    return None


def fomo_root(env_name: str, folder: str) -> Path | None:
    return _first_with_marker(
        [
            _env_path(env_name),
            Path("/workspace") / folder,
            REPO.parent / folder,
            REPO / folder,
        ],
        "ledger.json",
    ) or _first_with_marker(
        [
            _env_path(env_name),
            Path("/workspace") / folder,
            REPO.parent / folder,
            REPO / folder,
        ],
        "events.jsonl",
    )


def savipww_root() -> Path | None:
    """Project root that contains data/ledger_state.json (or the data dir itself)."""
    candidates: list[Path | None] = [
        _env_path("SAVIPWW_ROOT"),
        Path("/workspace/paper-trading"),
        REPO.parent / "paper-trading",
        REPO / "paper-trading",
    ]
    for path in candidates:
        if path is None:
            continue
        if (path / "data" / "ledger_state.json").exists() or (path / "data" / "events.jsonl").exists():
            return path
        if (path / "ledger_state.json").exists() or (path / "events.jsonl").exists():
            # Caller passed the data directory.
            return path.parent if path.name == "data" else path
    return None


def _num(*vals: Any) -> float | None:
    for value in vals:
        if value is None or value is False or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _normalize_event(ev: dict[str, Any], bot_id: str, archived: bool = False) -> dict[str, Any] | None:
    et = ev.get("type") or ev.get("event")
    if not et:
        return None
    if et in ("fill_buy", "fill_alpaca_paper"):
        et = "open"
    elif et == "fill_sell":
        et = "close"
    if et not in KEEP_TYPES:
        return None

    meta = ev.get("meta") if isinstance(ev.get("meta"), dict) else {}
    closed = ev.get("closed") if isinstance(ev.get("closed"), dict) else {}

    pnl = _num(ev.get("pnl"), ev.get("realized_pnl"), closed.get("realized_pnl"), meta.get("realized_pnl"))
    pnl_pct = _num(ev.get("pnl_pct"), meta.get("pnl_pct"), closed.get("pnl_pct"))

    handle = ev.get("handle")
    symbol = ev.get("symbol") or closed.get("symbol")
    msg = ev.get("msg") or ev.get("reason") or ev.get("note") or ""
    summary = str(msg)
    if handle and not summary:
        summary = f"@{handle}"
    if symbol and et in ("open", "close", "skip"):
        summary = f"{symbol}" + (f" · {msg}" if msg else "")

    # Alpaca paper stubs record requested/filled as dollars, not token qty.
    alpaca_dollars = ev.get("event") == "fill_alpaca_paper" or ev.get("venue") == "Alpaca_paper_stub"
    if alpaca_dollars:
        qty = None
        notional = _num(ev.get("notional_usd"), ev.get("notional"), ev.get("filled"), ev.get("requested"))
        price = _num(ev.get("price"), ev.get("fill_price"), ev.get("entry_price"))
    else:
        qty = _num(ev.get("qty"), ev.get("size"), ev.get("amount"), closed.get("qty"))
        notional = _num(ev.get("notional_usd"), ev.get("notional"), closed.get("entry_cost_usd"))
        price = _num(ev.get("price"), ev.get("fill_price"), ev.get("entry_price"), closed.get("exit_price"), closed.get("entry_price"))

    sleeve = ev.get("sleeve") or meta.get("sleeve")
    if sleeve is None and isinstance(closed.get("meta"), dict):
        sleeve = closed["meta"].get("sleeve")
    side = ev.get("side")
    if side is None and et == "open":
        side = "buy"
    elif side is None and et == "close":
        side = "sell"

    return {
        "ts": ev.get("ts") or ev.get("timestamp") or "",
        "type": et,
        "bot_id": bot_id,
        "handle": handle,
        "symbol": symbol,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "qty": qty,
        "price": price,
        "notional_usd": notional,
        "fee_usd": _num(ev.get("fee_usd"), ev.get("fee")),
        "sleeve": sleeve,
        "side": side,
        "msg": summary[:240] if summary else "",
        "archived": archived,
    }


def _richness(ev: dict[str, Any]) -> int:
    score = 0
    for key in ("qty", "price", "notional_usd", "pnl", "pnl_pct", "fee_usd", "sleeve", "side", "handle", "msg"):
        if ev.get(key) not in (None, "", False):
            score += 1
    if not ev.get("archived"):
        score += 1
    return score


def _dedupe(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse journal + shared-event mirrors of the same action."""
    best: dict[tuple, dict[str, Any]] = {}
    order: list[tuple] = []
    for ev in events:
        key = (ev.get("ts") or "", ev.get("type") or "", ev.get("symbol") or "", ev.get("handle") or "")
        prev = best.get(key)
        if prev is None:
            best[key] = ev
            order.append(key)
            continue
        if _richness(ev) >= _richness(prev):
            best[key] = ev
    return [best[k] for k in order]


def _jsonl_sources(directory: Path, filename: str, include_archives: bool) -> list[tuple[Path, bool]]:
    if not directory.exists():
        return []
    out: list[tuple[Path, bool]] = []
    current = directory / filename
    if current.exists():
        out.append((current, False))
    if include_archives:
        stem = filename[: -len(".jsonl")] if filename.endswith(".jsonl") else filename
        for path in sorted(directory.glob(f"{stem}.bak.*.jsonl")):
            out.append((path, True))
    return out


def _collect_events(
    directories: list[Path],
    filenames: list[str],
    bot_id: str,
    *,
    include_archives: bool,
) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen_files: set[Path] = set()
    for directory in directories:
        for filename in filenames:
            for path, archived in _jsonl_sources(directory, filename, include_archives):
                resolved = path.resolve()
                if resolved in seen_files:
                    continue
                seen_files.add(resolved)
                for raw in _read_jsonl(path):
                    norm = _normalize_event(raw, bot_id, archived=archived)
                    if norm:
                        found.append(norm)
    events = _dedupe(found)
    events.sort(key=lambda e: e.get("ts") or "")
    return events


def _normalize_position(pos: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(pos, dict):
        return None
    symbol = pos.get("symbol") or pos.get("token") or pos.get("mint")
    if not symbol and not pos.get("qty") and not pos.get("size"):
        return None
    meta = pos.get("meta") if isinstance(pos.get("meta"), dict) else {}
    return {
        "symbol": symbol,
        "qty": _num(pos.get("qty"), pos.get("size"), pos.get("amount")),
        "entry_price": _num(pos.get("entry_price"), pos.get("avg_price"), pos.get("price")),
        "notional_usd": _num(pos.get("entry_cost_usd"), pos.get("notional_usd"), pos.get("notional"), pos.get("mark_usd"), pos.get("mark_value")),
        "mark_price": _num(pos.get("mark_price"), pos.get("mark")),
        "unrealized_pnl": _num(pos.get("unrealized_pnl"), pos.get("upnl"), pos.get("pnl")),
        "opened_at": pos.get("opened_at") or pos.get("ts") or "",
        "side": pos.get("side") or "long",
        "sleeve": pos.get("sleeve") or meta.get("sleeve"),
    }


def _positions_from(raw: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        items = list(raw.values())
    elif isinstance(raw, list):
        items = raw
    else:
        return rows
    for item in items:
        norm = _normalize_position(item)
        if norm:
            rows.append(norm)
    return rows


def _previous_bots() -> dict[str, dict[str, Any]]:
    latest = _read_json(DOCS_DATA / "latest.json")
    out: dict[str, dict[str, Any]] = {}
    for bot in latest.get("bots") or []:
        if isinstance(bot, dict) and bot.get("id"):
            out[str(bot["id"])] = bot
    detail_dir = DOCS_DATA / "bots"
    if detail_dir.exists():
        for path in detail_dir.glob("*.json"):
            bot = _read_json(path).get("bot")
            if not isinstance(bot, dict) or not bot.get("id"):
                continue
            bot_id = str(bot["id"])
            base = dict(out.get(bot_id) or {})
            # Summary numbers stay with latest.json when present; keep the long timeline.
            if base:
                base["events"] = bot.get("events") or base.get("events") or base.get("recent_events") or []
                base["open_positions"] = bot.get("open_positions") or base.get("open_positions") or []
                # Detail files may carry desk fields the compare snapshot lacks.
                for key in ("meme_dial", "meme_dial_source", "kelly_cap_pct"):
                    if base.get(key) is None and bot.get(key) is not None:
                        base[key] = bot[key]
                out[bot_id] = base
            else:
                out[bot_id] = bot
    return out


def _fill_event_defaults(ev: dict[str, Any]) -> dict[str, Any]:
    base = {
        "ts": "",
        "type": "",
        "bot_id": "",
        "handle": None,
        "symbol": None,
        "pnl": None,
        "pnl_pct": None,
        "qty": None,
        "price": None,
        "notional_usd": None,
        "fee_usd": None,
        "sleeve": None,
        "side": None,
        "msg": "",
        "archived": False,
    }
    base.update(ev)
    return base


def _from_previous(bot_id: str) -> dict[str, Any] | None:
    prev = _previous_bots().get(bot_id)
    if not prev:
        return None
    bot = copy.deepcopy(prev)
    bot.setdefault("open_positions", [])
    events = bot.get("events") or bot.get("recent_events") or []
    bot["events"] = [_fill_event_defaults(e) for e in events if isinstance(e, dict)]
    recent = bot.get("recent_events") or bot["events"]
    bot["recent_events"] = [_fill_event_defaults(e) for e in recent if isinstance(e, dict)]
    return bot


def _finalize(bot: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    bot["events"] = events
    bot["recent_events"] = events[-RECENT_LIMIT:] if events else []
    # Homepage should reflect the live book, not every reset archive.
    current = [e for e in events if not e.get("archived")]
    if current:
        bot["recent_events"] = current[-RECENT_LIMIT:]
    bot["open_positions_count"] = len(bot.get("open_positions") or [])
    return bot


def _fomo_sizing_note(cfg: dict[str, Any]) -> str:
    ratio = cfg.get("copy_ratio") or cfg.get("copy_size_mult") or 0.25
    frac = cfg.get("equity_fraction_fallback") or cfg.get("equity_pct_fallback") or 0.05
    cap = cfg.get("max_equity_fraction") or cfg.get("max_position_pct_equity") or 0.25
    return f"对方下单×{float(ratio):g}；未知则权益×{float(frac):g}；单笔上限权益×{float(cap):g}"


def aggregate_fomo(bot_id: str, name: str, root: Path | None, *, include_archives: bool = True) -> dict[str, Any]:
    if root is None or not root.exists():
        prev = _from_previous(bot_id)
        if prev:
            return prev
        root = Path("/workspace") / bot_id

    ledger = _read_json(root / "ledger.json")
    cfg = _read_json(root / "config.json")
    if not ledger and not cfg and not (root / "events.jsonl").exists():
        prev = _from_previous(bot_id)
        if prev:
            return prev

    start = float(cfg.get("start_cash") or ledger.get("start_cash") or 1000.0)
    cash = float(ledger.get("cash") or 0)
    equity = float(ledger.get("equity") or cash)
    trader = ledger.get("current_trader")
    trader_handle = None
    if isinstance(trader, dict):
        trader_handle = trader.get("handle")
    elif isinstance(trader, str):
        trader_handle = trader

    positions = _positions_from(ledger.get("open_positions") or ledger.get("positions") or [])
    events = _collect_events([root], ["events.jsonl"], bot_id, include_archives=include_archives)

    bot = {
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
        "open_positions_count": len(positions),
        "open_positions": positions,
        "current_trader": trader_handle,
        "consecutive_losses": int(
            ledger.get("consecutive_losses_current_trader")
            or ledger.get("consecutive_losses")
            or 0
        ),
        "sizing_note": _fomo_sizing_note(cfg) if cfg else "对方下单×0.25；未知则权益×0.05；单笔上限权益×0.25",
        "updated_at": ledger.get("updated_at") or cfg.get("updated_at") or _now_iso(),
        "source_path": str(root),
    }
    return _finalize(bot, events)


def _parse_yaml_simple_start_cash(path: Path) -> float:
    """Minimal YAML peek for meme starting_cash_usd without PyYAML."""
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
        if in_meme and stripped and not stripped.startswith("#") and not line.startswith((" ", "\t")):
            in_meme = False
        if in_meme and stripped.startswith("alpaca:"):
            in_meme = False
    return 100.0


def _as_percent(value: float | None, *, unit_interval_is_fraction: bool) -> float | None:
    """Kelly caps in config are already percent. A ledger dial may be 0.06 or 6."""
    if value is None:
        return None
    if unit_interval_is_fraction and abs(value) <= 1:
        return value * 100
    return value


def _savipww_dial(state: dict[str, Any], kelly: float) -> tuple[float, str]:
    raw = state.get("meme_dial")
    if raw is None and isinstance(state.get("quant"), dict):
        raw = state["quant"].get("meme_dial")
    if raw is None and isinstance(state.get("dials"), dict):
        raw = state["dials"].get("meme")
    dial = _as_percent(_num(raw), unit_interval_is_fraction=True)
    if dial is None:
        return round(float(kelly), 4), "kelly_cap"
    return round(dial, 4), "ledger"


def _savipww_data_dir(root: Path) -> Path:
    if (root / "ledger_state.json").exists() or (root / "events.jsonl").exists() or (root / "journal.jsonl").exists():
        return root
    return root / "data"


def aggregate_savipww(root: Path | None = None, *, include_archives: bool = True) -> dict[str, Any]:
    if root is None:
        root = savipww_root()
    if root is None or not root.exists():
        prev = _from_previous("savipww")
        if prev:
            return prev
        root = Path("/workspace/paper-trading")

    data_dir = _savipww_data_dir(root)
    state = _read_json(data_dir / "ledger_state.json")
    cfg_path = root / "config.yaml"
    if not cfg_path.exists():
        cfg_path = data_dir.parent / "config.yaml"

    if not state and not (data_dir / "events.jsonl").exists() and not (data_dir / "journal.jsonl").exists():
        prev = _from_previous("savipww")
        if prev:
            return prev

    start = float(state.get("starting_cash") or _parse_yaml_simple_start_cash(cfg_path))
    cash = float(state.get("cash") or 0)
    positions_raw = state.get("positions") or {}
    positions = _positions_from(positions_raw)
    mark_sum = 0.0
    if isinstance(positions_raw, dict):
        for pos in positions_raw.values():
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
    equity = cash + mark_sum

    closed = state.get("closed") or []
    wins = losses = 0
    realized = 0.0
    for row in closed:
        if not isinstance(row, dict):
            continue
        pnl = float(row.get("realized_pnl") or 0)
        realized += pnl
        if pnl > 0:
            wins += 1
        elif pnl < 0:
            losses += 1

    events = _collect_events(
        [data_dir],
        ["events.jsonl", "journal.jsonl"],
        "savipww",
        include_archives=include_archives,
    )

    kelly = 6.0
    if cfg_path.exists():
        for line in cfg_path.read_text(encoding="utf-8").splitlines():
            if "kelly_cap_pct_of_bank" in line:
                try:
                    kelly = float(line.split(":", 1)[1].strip().split()[0])
                except ValueError:
                    pass
                break

    dial, dial_source = _savipww_dial(state, kelly)

    bot = {
        "id": "savipww",
        "name": "模拟盘savipww",
        "strategy": "八席纸面台 QUANT→SCAN→JUDGE→SIZE→FILL · RISK",
        "start_cash": start,
        "cash": round(cash, 4),
        "equity": round(equity, 4),
        "realized_pnl": round(realized, 4),
        "trade_count": len(closed) if isinstance(closed, list) else 0,
        "win_count": wins,
        "loss_count": losses,
        "open_positions_count": len(positions),
        "open_positions": positions,
        "current_trader": None,
        "consecutive_losses": None,
        "sizing_note": f"Kelly×自由现金，meme 封顶约 {kelly:g}% · QUANT 拨盘",
        "kelly_cap_pct": kelly,
        "meme_dial": dial,
        "meme_dial_source": dial_source,
        "updated_at": state.get("saved_at") or _now_iso(),
        "source_path": str(data_dir),
        "seats": ["CHIEF", "QUANT", "SCAN", "JUDGE", "STOCKS", "SIZE", "FILL", "RISK"],
    }
    return _finalize(bot, events)


def build_bots() -> list[dict[str, Any]]:
    include_archives = os.environ.get("SIM_INCLUDE_ARCHIVES", "1") not in ("0", "false", "False")
    return [
        aggregate_fomo("0xboan", "模拟盘0xboan", fomo_root("FOMO_BOAN_ROOT", "fomo-sim-0xboan"), include_archives=include_archives),
        aggregate_fomo("0xTenzo", "模拟盘0xTenzo", fomo_root("FOMO_TENZO_ROOT", "fomo-sim"), include_archives=include_archives),
        aggregate_savipww(include_archives=include_archives),
    ]


def _envelope(bots: list[dict[str, Any]], *, full_events: bool) -> dict[str, Any]:
    view: list[dict[str, Any]] = []
    all_events: list[dict[str, Any]] = []
    for bot in bots:
        item = dict(bot)
        if not full_events:
            item.pop("events", None)
        view.append(item)
        for ev in bot.get("recent_events") or []:
            all_events.append({**ev, "bot_name": bot["name"]})
    all_events.sort(key=lambda e: e.get("ts") or "", reverse=True)
    return {
        "generated_at": _now_iso(),
        "timezone": "Asia/Singapore",
        "bots": view,
        "recent_events": all_events[:40],
        "note": "纸面模拟 · 非实盘 · Paper only",
    }


def aggregate() -> dict[str, Any]:
    """Homepage snapshot. Per-bot `recent_events` stays short."""
    return _envelope(build_bots(), full_events=False)


def detail_snapshot(bot_id: str) -> dict[str, Any] | None:
    for bot in build_bots():
        if bot.get("id") == bot_id:
            return {
                "generated_at": _now_iso(),
                "timezone": "Asia/Singapore",
                "note": "纸面模拟 · 非实盘 · Paper only",
                "bot": bot,
            }
    return None


def snapshots() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Compare payload plus per-bot detail payloads sharing one timestamp."""
    bots = build_bots()
    compare = _envelope(bots, full_events=False)
    details = {
        bot["id"]: {
            "generated_at": compare["generated_at"],
            "timezone": compare["timezone"],
            "note": compare["note"],
            "bot": bot,
        }
        for bot in bots
    }
    return compare, details


if __name__ == "__main__":
    print(json.dumps(aggregate(), ensure_ascii=False, indent=2))
