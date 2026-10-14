#!/usr/bin/env python3
"""Pipeline checks for per-bot detail snapshots. Stdlib only."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import aggregate


class NormalizeTests(unittest.TestCase):
    def test_fomo_hire_and_position(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config.json").write_text(
                json.dumps({"start_cash": 1000, "copy_ratio": 0.25, "equity_fraction_fallback": 0.05, "max_equity_fraction": 0.25}),
                encoding="utf-8",
            )
            (root / "ledger.json").write_text(
                json.dumps(
                    {
                        "cash": 900,
                        "equity": 1012.5,
                        "start_cash": 1000,
                        "realized_pnl": 12.5,
                        "trade_count": 1,
                        "win_count": 1,
                        "loss_count": 0,
                        "current_trader": {"handle": "healthysmilee"},
                        "consecutive_losses": 0,
                        "updated_at": "2026-10-14T08:00:00+08:00",
                        "open_positions": [
                            {
                                "symbol": "BONK",
                                "qty": 1000,
                                "entry_price": 0.00001,
                                "notional_usd": 10,
                                "unrealized_pnl": 1.25,
                                "opened_at": "2026-10-14T08:00:00+08:00",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (root / "events.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps({"ts": "2026-10-14T07:14:04+08:00", "type": "hire", "handle": "healthysmilee", "msg": "雇佣交易员 @healthysmilee"}),
                        json.dumps({"ts": "2026-10-14T08:00:00+08:00", "type": "open", "symbol": "BONK", "qty": 1000, "price": 0.00001, "notional_usd": 10, "msg": "copy"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            bot = aggregate.aggregate_fomo("0xboan", "模拟盘0xboan", root, include_archives=False)
        self.assertEqual(bot["current_trader"], "healthysmilee")
        self.assertEqual(bot["equity"], 1012.5)
        self.assertEqual(len(bot["open_positions"]), 1)
        self.assertEqual(bot["open_positions"][0]["symbol"], "BONK")
        self.assertEqual(bot["events"][-1]["type"], "open")
        self.assertEqual(bot["events"][-1]["qty"], 1000)
        self.assertFalse(bot["events"][-1]["archived"])

    def test_savipww_merges_archives_and_keeps_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            data.mkdir()
            (data / "ledger_state.json").write_text(
                json.dumps(
                    {
                        "starting_cash": 1000,
                        "cash": 1000,
                        "positions": {},
                        "closed": [],
                        "saved_at": "2026-10-14T07:35:13+08:00",
                        "paper_only": True,
                    }
                ),
                encoding="utf-8",
            )
            (data / "events.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps({"ts": "2026-10-14T07:35:15+08:00", "type": "skip", "reason": "judge_no_pick", "sleeve": "meme"}),
                        json.dumps({"ts": "2026-10-14T07:36:06+08:00", "type": "rules_update", "msg": "本金改为 $1000", "sleeve": "meme"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (data / "journal.jsonl").write_text(
                json.dumps({"ts": "2026-10-14T07:35:15+08:00", "event": "skip", "reason": "judge_no_pick", "sleeve": "meme"}) + "\n",
                encoding="utf-8",
            )
            (data / "journal.bak.20261014_073511.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps({"ts": "2026-10-14T07:18:01+08:00", "event": "reset", "note": "paper ledger reset"}),
                        json.dumps(
                            {
                                "ts": "2026-10-14T07:18:09+08:00",
                                "event": "fill_buy",
                                "side": "buy",
                                "symbol": "DEMO1",
                                "qty": 44091.7,
                                "price": 0.00012096,
                                "notional_usd": 5.333333,
                                "fee_usd": 0.95,
                                "reason": "SCAN→JUDGE→SIZE",
                                "meta": {"sleeve": "meme"},
                            }
                        ),
                        json.dumps(
                            {
                                "ts": "2026-10-14T07:18:13+08:00",
                                "event": "fill_alpaca_paper",
                                "symbol": "NVDA",
                                "requested": 1250,
                                "filled": 1250,
                                "fill_price": None,
                                "sleeve": "STOCKS",
                                "reason": "fill_alpaca_paper",
                            }
                        ),
                        json.dumps(
                            {
                                "ts": "2026-10-14T07:18:54+08:00",
                                "event": "fill_sell",
                                "side": "sell",
                                "symbol": "DEMO1",
                                "qty": 44091.7,
                                "price": 0.000154752,
                                "notional_usd": 6.82,
                                "fee_usd": 0.95,
                                "reason": "volume_momentum_collapse",
                                "meta": {"realized_pnl": -0.410053, "pnl_pct": -6.526, "sleeve": "meme"},
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (data / "events.bak.20261014_073511.jsonl").write_text(
                json.dumps({"ts": "2026-10-14T07:18:09+08:00", "type": "open", "symbol": "DEMO1", "reason": "SCAN→JUDGE→SIZE", "sleeve": "meme"})
                + "\n",
                encoding="utf-8",
            )
            bot = aggregate.aggregate_savipww(root, include_archives=True)

        self.assertEqual(bot["equity"], 1000.0)
        self.assertEqual(bot["cash"], 1000.0)
        self.assertEqual(bot["trade_count"], 0)
        types = [(e["ts"], e["type"], e["symbol"], e["archived"]) for e in bot["events"]]
        self.assertIn(("2026-10-14T07:18:09+08:00", "open", "DEMO1", True), types)
        self.assertIn(("2026-10-14T07:36:06+08:00", "rules_update", None, False), types)
        # journal skip and events skip are one row
        skips = [e for e in bot["events"] if e["type"] == "skip" and e["ts"] == "2026-10-14T07:35:15+08:00"]
        self.assertEqual(len(skips), 1)
        demo = next(e for e in bot["events"] if e["symbol"] == "DEMO1" and e["type"] == "open")
        self.assertEqual(demo["qty"], 44091.7)
        self.assertAlmostEqual(demo["price"], 0.00012096)
        nvda = next(e for e in bot["events"] if e["symbol"] == "NVDA")
        self.assertIsNone(nvda["qty"])
        self.assertEqual(nvda["notional_usd"], 1250)
        close = next(e for e in bot["events"] if e["type"] == "close")
        self.assertAlmostEqual(close["pnl"], -0.410053)
        # homepage list is the live book, not the archive
        self.assertTrue(all(not e["archived"] for e in bot["recent_events"]))
        self.assertGreater(len(bot["events"]), len(bot["recent_events"]))


if __name__ == "__main__":
    unittest.main()
