/* 0xTenzo HD desk. No-ops unless html.skin-tenzo / data-bot=0xTenzo. */
(function () {
  var root = document.documentElement;
  var on = root.classList.contains("skin-tenzo") || root.getAttribute("data-bot") === "0xTenzo";
  if (!on) {
    window.TenzoDesk = {
      paintStats: function () {},
      paintContext: function () {},
      paintChrome: function () {},
      paintFooter: function () {},
      filterRows: function (rows) { return rows; },
      setLive: function () {},
    };
    return;
  }
  if (!root.classList.contains("skin-tenzo")) root.classList.add("skin-tenzo");
  root.setAttribute("data-bot", "0xTenzo");

  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var prev = {};
  var CN = { "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10 };
  var EXTRA = {
    rules_set: "规则设定",
    system_init: "初始化",
    source_watch_enabled: "盯梢",
    copy_skip: "跳过",
  };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function money(n) {
    var x = Number(n);
    if (!isFinite(x)) return "—";
    var abs = Math.abs(x);
    var body = abs >= 1000
      ? abs.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      : abs.toFixed(2);
    return (x < 0 ? "-" : "") + "$" + body;
  }
  function signedMoney(n) {
    var x = Number(n);
    if (!isFinite(x)) return "—";
    if (x > 0) return "+" + money(x);
    return money(x);
  }
  function pctSigned(n) {
    var x = Number(n);
    if (!isFinite(x)) return "—";
    if (x > 0) return "+" + x.toFixed(2) + "%";
    if (x < 0) return x.toFixed(2) + "%";
    return "+0.00%";
  }
  function pnlClass(n) {
    var x = Number(n);
    if (!isFinite(x) || Math.abs(x) < 0.0001) return "flat";
    return x > 0 ? "up" : "down";
  }
  function tickTo(id, target, format) {
    var el = document.getElementById(id);
    if (!el) return;
    var end = Number(target);
    if (!isFinite(end)) {
      el.textContent = "—";
      return;
    }
    var start = prev[id];
    var known = start != null && isFinite(start);
    start = known ? start : (reduce ? end : 0);
    prev[id] = end;
    if (reduce || Math.abs(end - start) < 1e-9) {
      el.textContent = format(end);
      return;
    }
    el.classList.remove("tick-flash");
    void el.offsetWidth;
    el.classList.add("tick-flash");
    var t0 = performance.now();
    function frame(now) {
      var p = Math.min(1, (now - t0) / 700);
      var v = start + (end - start) * (1 - Math.pow(1 - p, 3));
      el.textContent = format(p < 1 ? v : end);
      if (p < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }
  function fireAfter(b) {
    if (b.fire_after != null && b.fire_after !== "") return Number(b.fire_after);
    if (b.fire_after_consecutive_losses != null && b.fire_after_consecutive_losses !== "") {
      return Number(b.fire_after_consecutive_losses);
    }
    var m = String(b.strategy || "").match(/([一二两三四五六七八九十]|\d+)\s*连亏/);
    if (!m) return null;
    if (CN[m[1]] != null) return CN[m[1]];
    var n = Number(m[1]);
    return isFinite(n) ? n : null;
  }
  function traderInfo(b) {
    var detail = b.current_trader_detail && typeof b.current_trader_detail === "object" ? b.current_trader_detail : {};
    var raw = typeof b.current_trader === "string"
      ? b.current_trader
      : (b.current_trader && typeof b.current_trader === "object" ? (b.current_trader.handle || "") : "");
    var handle = String(raw || detail.handle || "").replace(/^@/, "");
    var out = {};
    var k;
    for (k in detail) out[k] = detail[k];
    if (b.current_trader && typeof b.current_trader === "object") {
      for (k in b.current_trader) out[k] = b.current_trader[k];
    }
    out.handle = handle;
    return out;
  }

  function paintStats(b) {
    var equity = Number(b.equity);
    var start = Number(b.start_cash);
    var pnl = b.total_pnl != null && b.total_pnl !== "" ? Number(b.total_pnl) : (equity - start);
    var pnlP = b.total_pnl_pct != null && b.total_pnl_pct !== ""
      ? Number(b.total_pnl_pct)
      : (start ? (pnl / start) * 100 : 0);
    var hasStreak = b.consecutive_losses != null && b.consecutive_losses !== "";
    var streak = hasStreak ? Number(b.consecutive_losses) || 0 : 0;
    var fire = hasStreak ? fireAfter(b) : null;
    var streakText = "—";
    var streakCls = "flat";
    var streakSub = "";
    var meter = "";
    if (hasStreak) {
      streakText = fire != null && isFinite(fire) ? (streak + " / " + fire) : String(streak);
      streakCls = fire != null && streak >= fire ? "down" : streak > 0 ? "warn" : "flat";
      streakSub = fire != null ? "达到阈值解雇" : "当前交易员连亏";
      if (fire != null && isFinite(fire) && fire > 0) {
        var bars = Math.max(1, Math.min(fire, 8));
        var i;
        for (i = 0; i < bars; i++) meter += '<span class="' + (i < streak ? "on" : "") + '"></span>';
      }
    } else {
      var posN = b.open_positions_count != null ? b.open_positions_count : (b.open_positions || []).length;
      streakText = String(posN);
      streakSub = (b.seats && b.seats.length) ? (b.seats.length + " 席在岗") : "当前未平";
    }
    var label6 = hasStreak ? "连亏 · 解雇线" : "持仓";
    var fired = b.fired_traders_count;
    var tradeSub = "共 " + (b.trade_count == null ? 0 : b.trade_count) + " 笔" + (fired != null && fired !== "" ? " · 已解雇 " + fired + " 人" : "");
    var box = document.getElementById("stats");
    box.innerHTML =
      '<div class="stat accent"><div class="k">权益 Equity</div><div class="v" id="t-equity">—</div><div class="hint ' + pnlClass(pnl) + '" id="t-equity-sub"></div></div>' +
      '<div class="stat"><div class="k">现金 Cash</div><div class="v" id="t-cash">—</div><div class="hint">起步 ' + esc(money(b.start_cash)) + "</div></div>" +
      '<div class="stat"><div class="k">已实现盈亏</div><div class="v ' + pnlClass(b.realized_pnl) + '" id="t-realized">—</div><div class="hint">Realized PnL</div></div>' +
      '<div class="stat"><div class="k">总收益率</div><div class="v ' + pnlClass(pnlP) + '" id="t-pnl">—</div><div class="hint ' + pnlClass(pnl) + '">绝对 ' + esc(signedMoney(pnl)) + "</div></div>" +
      '<div class="stat"><div class="k">胜 / 负</div><div class="v"><span class="up">' + esc(b.win_count == null ? 0 : b.win_count) + '</span> <span class="flat">/</span> <span class="down">' + esc(b.loss_count == null ? 0 : b.loss_count) + '</span></div><div class="hint">' + esc(tradeSub) + "</div></div>" +
      '<div class="stat"><div class="k">' + esc(label6) + '</div><div class="v ' + streakCls + '">' + esc(streakText) + '</div><div class="hint">' + esc(streakSub) + '</div><div class="streak-meter">' + meter + "</div></div>";
    var sub = document.getElementById("t-equity-sub");
    if (sub) sub.textContent = signedMoney(pnl) + " (" + pctSigned(pnlP) + ")";
    tickTo("t-equity", b.equity, money);
    tickTo("t-cash", b.cash, money);
    tickTo("t-realized", b.realized_pnl, signedMoney);
    tickTo("t-pnl", pnlP, pctSigned);
  }

  function paintSizing(b) {
    var host = document.getElementById("tenzo-sizing");
    if (!host) return;
    var sz = b.sizing && typeof b.sizing === "object" ? b.sizing : null;
    var note = b.sizing_note || "";
    var dynamic = (sz && sz.mode === "dynamic") || /动态|0\.25|kelly/i.test(note);
    var chips = [];
    if (sz) {
      if (sz.chip || note) chips.push(["accent", sz.chip || note]);
      if (sz.next_size_if_unknown != null) chips.push(["hot", "下次未知对手额 ≈ " + money(sz.next_size_if_unknown)]);
      if (sz.mode) chips.push(["", "mode · " + sz.mode]);
      var parts = [];
      if (sz.copy_size_mult != null) parts.push(sz.copy_size_mult + "×");
      if (sz.equity_pct_fallback != null) parts.push("回退 " + Math.round(sz.equity_pct_fallback * 100) + "%");
      if (sz.max_position_pct_equity != null) parts.push("封顶 " + Math.round(sz.max_position_pct_equity * 100) + "%");
      if (sz.min_copy_size != null) parts.push("下限 $" + sz.min_copy_size);
      if (parts.length) chips.push(["", parts.join(" · ")]);
    } else if (note) {
      note.split(/[·;；|]/).forEach(function (part, i) {
        part = part.trim();
        if (part) chips.push([i === 0 ? "accent" : "", part]);
      });
    } else {
      chips.push(["", "未标注仓位"]);
    }
    host.innerHTML = '<span class="strip-tag">' + (dynamic ? "动态仓位" : "仓位") + "</span><div class=\"chips-row\">" +
      chips.map(function (c) { return '<span class="tchip ' + c[0] + '">' + esc(c[1]) + "</span>"; }).join("") +
      "</div>";
  }

  function paintContext(b) {
    paintSizing(b);
    var el = document.getElementById("context");
    if (!el) return;
    el.classList.add("tenzo-split");
    var info = traderInfo(b);
    var trader;
    if (info.handle) {
      var pnl7 = info.pnl7d != null ? money(info.pnl7d) : "";
      var chips = "";
      if (info.rank != null) chips += '<span class="tchip accent">周榜 #' + esc(info.rank) + "</span>";
      if (pnl7) chips += '<span class="tchip">7日盈亏 <span class="' + pnlClass(info.pnl7d) + '">' + esc(pnl7) + "</span></span>";
      if (b.consecutive_losses != null && b.consecutive_losses !== "") chips += '<span class="tchip">连亏 ' + esc(b.consecutive_losses) + "</span>";
      trader =
        '<div class="trader-head"><div class="avatar">' + esc(info.handle.slice(0, 2).toUpperCase()) + "</div><div>" +
        '<div class="trader-handle"><a href="https://x.com/' + esc(info.handle) + '" target="_blank" rel="noopener">@' + esc(info.handle) + "</a></div>" +
        '<div class="role">当前席位 · 一人跟单</div></div></div>' +
        (chips ? '<div class="tchips">' + chips + "</div>" : "") +
        (info.note ? '<div class="tnote">' + esc(info.note) + "</div>" : "");
    } else {
      trader = '<div class="empty">当前无跟单员</div>';
    }
    var rules = Array.isArray(b.rules) ? b.rules : [];
    var ruleHtml;
    var ruleTitle = "规则摘要";
    if (rules.length) {
      ruleHtml = '<ul class="tenzo-rules">' + rules.slice(0, 12).map(function (r) {
        var text = typeof r === "string" ? r : (r && (r.msg || r.text)) || "";
        return "<li>" + esc(text) + "</li>";
      }).join("") + "</ul>";
    } else {
      ruleTitle = "台面说明";
      var lines = [b.strategy, b.sizing_note].filter(Boolean);
      ruleHtml = '<ul class="tenzo-rules">' + (lines.length ? lines : ["暂无规则摘要"]).map(function (r) {
        return "<li>" + esc(r) + "</li>";
      }).join("") + "</ul>";
    }
    var hint = b.source_twitter ? esc(b.source_twitter) : (info.handle ? "@" + esc(info.handle) : "");
    el.innerHTML =
      '<article class="glass-card"><h2>当前跟单员 <span class="en">Trader</span></h2>' + trader + "</article>" +
      '<article class="glass-card"><h2>' + ruleTitle + ' <span class="en">' + hint + "</span></h2>" + ruleHtml + "</article>";
  }

  function paintChrome(b, whenText) {
    var badge = document.getElementById("badge");
    if (badge) badge.textContent = "模拟盘 · 非实盘";
    var status = document.getElementById("tenzo-status");
    if (status) {
      if (b.status) {
        status.hidden = false;
        status.textContent = b.status;
        status.classList.toggle("fired", /fire|halt|stop/i.test(String(b.status)));
      } else {
        status.hidden = true;
        status.textContent = "";
      }
    }
    var meta = document.getElementById("meta");
    if (meta) {
      meta.innerHTML = '<div>' + esc(whenText) + '</div><div id="tenzo-clock"></div>';
    }
    tickClock();
    setLive(true);
  }

  function paintFooter(b, data) {
    var el = document.getElementById("footer");
    if (!el) return;
    var handle = String((b && b.source_twitter) || "@0xTenzo").replace(/^@/, "");
    var parts = String((b && b.source_path) || "").split("/").filter(Boolean).slice(-2).join("/");
    el.innerHTML = '源策略 <a href="https://x.com/' + esc(handle) + '" target="_blank" rel="noopener">@' + esc(handle) + "</a> · 模拟盘 · 非实盘" +
      (parts ? " · " + esc(parts) : "") +
      (data && data.note ? " · " + esc(data.note) : "");
  }

  function filterRows(base, events) {
    var rows = base.slice();
    var seen = {};
    rows.forEach(function (row) { seen[row[0]] = true; });
    (events || []).forEach(function (e) {
      var t = e && e.type;
      if (t && !seen[t]) {
        seen[t] = true;
        rows.push([t, EXTRA[t] || t]);
      }
    });
    return rows;
  }

  function setLive(on) {
    var pill = document.getElementById("tenzo-live");
    if (!pill) return;
    pill.classList.toggle("off", !on);
    var label = pill.querySelector(".live-label");
    if (label) label.textContent = on ? "LIVE" : "OFFLINE";
  }

  function tickClock() {
    var el = document.getElementById("tenzo-clock");
    if (!el) return;
    var s = new Date().toLocaleString("zh-CN", {
      timeZone: "Asia/Singapore",
      hour12: false,
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    el.textContent = s + " SGT";
  }
  setInterval(tickClock, 1000);

  window.TenzoDesk = {
    paintStats: paintStats,
    paintContext: paintContext,
    paintChrome: paintChrome,
    paintFooter: paintFooter,
    filterRows: filterRows,
    setLive: setLive,
  };
})();
