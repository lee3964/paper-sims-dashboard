# 模拟盘对比 / Paper Sim Compare

一眼对照三个纸面模拟盘（**非实盘**），方便实盘前复盘。

| 盘 | 策略 | 账本路径 |
|---|---|---|
| 模拟盘0xboan | FOMO 周榜跟单 · 两连亏换人 · 动态 0.25× | `/workspace/fomo-sim-0xboan/` |
| 模拟盘0xTenzo | 同上（跟不同交易员） | `/workspace/fomo-sim/` |
| 模拟盘savipww | 八席 QUANT→SCAN→JUDGE→SIZE→FILL | `/workspace/paper-trading/data/` |

## 本地打开（推荐 · 实时读账本）

```bash
cd /workspace/sim-compare
python3 export_snapshot.py   # 刷新 docs/data/latest.json
python3 server.py            # http://127.0.0.1:8765/
```

- 页面：http://127.0.0.1:8765/
- 实时 API：http://127.0.0.1:8765/api/snapshot.json（每次请求重新聚合账本）
- 静态快照：`docs/data/latest.json`

浏览器打开后约每 30 秒自动刷新。

仅看静态文件也可以：

```bash
cd /workspace/sim-compare/docs && python3 -m http.server 8765
```

## GitHub Pages

把本目录推到仓库后，把 Pages 源设为 `/docs`（或把 `docs/` 内容放到 `gh-pages`）。

页面会拉取 `./data/latest.json`。更新数据：

```bash
python3 export_snapshot.py
git add docs/data && git commit -m "chore: refresh sim snapshot" && git push
```

历史快照会写到 `docs/data/history/YYYYMMDD-HHMMSS.json`。

## 文件

- `aggregate.py` — 归一化三盘快照
- `export_snapshot.py` — 写出 `latest.json` + history
- `server.py` — 静态站 + `/api/snapshot.json`
- `docs/index.html` — 深色对比页（无构建步骤）

## English

Static dashboard comparing three paper sims. Run `python3 server.py` then open http://127.0.0.1:8765/. For GitHub Pages, publish the `docs/` folder; refresh via `export_snapshot.py`. Paper only — no live orders.
