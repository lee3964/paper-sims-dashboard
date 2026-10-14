/* Eight-seat paper desk. Only runs when bot.html?id=savipww. No invented fills. */
(function () {
  const SEAT_ZH = {
    CHIEF: "主控", QUANT: "量化", SCAN: "扫描", JUDGE: "裁决",
    STOCKS: "股票", SIZE: "仓位", FILL: "成交", RISK: "风控",
  };
  const SEAT_ROLE = {
    CHIEF: "编排", QUANT: "拨盘", SCAN: "选池", JUDGE: "取舍",
    STOCKS: "股票组", SIZE: "Kelly", FILL: "纸面", RISK: "限额",
  };
  const DEFAULT_SEATS = ["CHIEF", "QUANT", "SCAN", "JUDGE", "STOCKS", "SIZE", "FILL", "RISK"];
  const CX = 120, CY = 120, R = 78, START = 135, SWEEP = 270;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const state = {
    bot: null,
    hooks: null,
    equity: null,
    dialKey: "",
    dialAngle: START,
    dialT: 0,
    anim: 0,
    eqAnim: 0,
    ready: false,
  };

  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }
  function money(n) {
    if (n == null || n === "" || Number.isNaN(Number(n))) return "—";
    const x = Number(n);
    const body = Math.abs(x).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return (x < 0 ? "-$" : "$") + body;
  }
  function signedMoney(n) {
    if (n == null || n === "" || Number.isNaN(Number(n))) return "—";
    const x = Number(n);
    const body = Math.abs(x).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (x > 0.0001) return "+$" + body;
    if (x < -0.0001) return "-$" + body;
    return "$" + body;
  }
  function pct(n) {
    const sign = n > 0 ? "+" : "";
    return sign + Number(n).toFixed(2) + "%";
  }
  function pnlClass(n) {
    if (n > 0.0001) return "up";
    if (n < -0.0001) return "down";
    return "flat";
  }
  function trimNum(n) {
    if (n == null || !Number.isFinite(Number(n))) return "—";
    return Number(n).toFixed(2).replace(/\.?0+$/, "");
  }

  function readDial(b) {
    if (b.meme_dial != null && b.meme_dial !== "" && Number.isFinite(Number(b.meme_dial))) {
      return { value: Number(b.meme_dial), source: b.meme_dial_source || "ledger" };
    }
    const note = String(b.sizing_note || "");
    const labeled = note.match(/封顶约\s*([0-9]+(?:\.[0-9]+)?)\s*%/);
    if (labeled) return { value: Number(labeled[1]), source: "kelly_cap" };
    if (b.kelly_cap_pct != null && Number.isFinite(Number(b.kelly_cap_pct))) {
      return { value: Number(b.kelly_cap_pct), source: "kelly_cap" };
    }
    return { value: null, source: "none" };
  }
  function dialScale(value) {
    const v = Math.abs(Number(value) || 0);
    if (v <= 15) return 15;
    if (v <= 30) return 30;
    if (v <= 50) return 50;
    if (v <= 100) return 100;
    return Math.ceil(v / 10) * 10;
  }
  function sourceLabel(source) {
    if (source === "ledger") return "读自账本 meme_dial · 只读";
    if (source === "kelly_cap") return "读自 Kelly 封顶 · 账本没有单独的拨盘读数";
    return "账本未提供拨盘";
  }
  function arcPath(cx, cy, r, startDeg, endDeg) {
    const s = (startDeg * Math.PI) / 180;
    const e = (endDeg * Math.PI) / 180;
    const x1 = cx + r * Math.cos(s);
    const y1 = cy + r * Math.sin(s);
    const x2 = cx + r * Math.cos(e);
    const y2 = cy + r * Math.sin(e);
    const large = endDeg - startDeg > 180 ? 1 : 0;
    return `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
  }
  function polar(frac, radius) {
    const ang = ((START + SWEEP * frac) * Math.PI) / 180;
    return [CX + radius * Math.cos(ang), CY + radius * Math.sin(ang)];
  }
  function msgOf(e) {
    return String((e && e.msg) || "").toLowerCase();
  }
  function eventMatchesSeat(e, seat) {
    const m = msgOf(e);
    const sleeve = String(e.sleeve || "").toUpperCase();
    if (seat === "CHIEF") return e.type === "rules_update";
    if (seat === "QUANT") return e.type === "rules_update" || m.includes("kelly") || m.includes("拨盘") || m.includes("封顶");
    if (seat === "SCAN") return m.includes("scan");
    if (seat === "JUDGE") return m.includes("judge");
    if (seat === "STOCKS") return sleeve === "STOCKS";
    if (seat === "SIZE") return m.includes("size") || m.includes("kelly");
    if (seat === "FILL") return e.type === "open" || e.type === "close";
    if (seat === "RISK") {
      return e.type === "skip" || m.includes("risk") || m.includes("collapse") || (e.type === "close" && Number(e.pnl) < 0);
    }
    return false;
  }
  function seatModel(b) {
    const dial = readDial(b);
    const events = b.events || b.recent_events || [];
    const live = events.filter((e) => !e.archived);
    const positions = b.open_positions || [];
    const any = (list, pred) => list.some(pred);
    const stockPos = positions.filter((p) => String(p.sleeve || "").toUpperCase() === "STOCKS");
    const scannedLive = any(live, (e) => msgOf(e).includes("scan"));
    const scanned = scannedLive || any(events, (e) => msgOf(e).includes("scan"));
    const judgeEv = [...live].reverse().find((e) => msgOf(e).includes("judge"));
    const fillsLive = any(live, (e) => e.type === "open" || e.type === "close");
    const stockArch = any(events, (e) => String(e.sleeve || "").toUpperCase() === "STOCKS");
    const rules = any(live, (e) => e.type === "rules_update");
    const riskLive = Number(b.realized_pnl) < 0 || any(live, (e) => e.type === "close" && Number(e.pnl) < 0);
    const dialText = dial.value == null ? "无读数" : "拨盘 " + trimNum(dial.value) + "%";
    let judgeLevel = "dim";
    let judgeStatus = "待命";
    if (judgeEv) {
      judgeLevel = "hot";
      judgeStatus = msgOf(judgeEv).includes("no_pick") || msgOf(judgeEv).includes("未选") ? "未选标的" : "已裁决";
    }
    const byId = {
      CHIEF: { level: rules ? "hot" : "on", status: rules ? "规则已更新" : "在岗" },
      QUANT: { level: dial.value == null ? "dim" : "hot", status: dialText },
      SCAN: { level: scannedLive ? "hot" : scanned ? "on" : "dim", status: scannedLive ? "本轮有扫描" : scanned ? "归档有扫描" : "待命" },
      JUDGE: { level: judgeLevel, status: judgeStatus },
      STOCKS: {
        level: stockPos.length ? "hot" : stockArch ? "on" : "dim",
        status: stockPos.length ? "持仓 " + stockPos.length : stockArch ? "空仓" : "待命",
      },
      SIZE: { level: dial.value == null ? "dim" : "on", status: dial.value == null ? "无封顶" : "封顶 " + trimNum(dial.value) + "%" },
      FILL: { level: fillsLive ? "hot" : "dim", status: fillsLive ? "纸面成交" : "无新成交" },
      RISK: { level: riskLive ? "alert" : "dim", status: riskLive ? "账上亏损" : "观察" },
    };
    const ids = (b.seats && b.seats.length ? b.seats : DEFAULT_SEATS).map(String);
    return ids.map((id) => ({
      id,
      zh: SEAT_ZH[id] || id,
      role: SEAT_ROLE[id] || "席位",
      ...(byId[id] || { level: "dim", status: "待命" }),
    }));
  }

  function setNeedle(ang) {
    const node = document.getElementById("dial-needle");
    if (node) node.setAttribute("transform", `rotate(${(ang - 270).toFixed(2)} 120 120)`);
    state.dialAngle = ang;
  }
  function setDash(t) {
    const value = document.getElementById("dial-value");
    const glow = document.getElementById("dial-glow");
    if (!value) return;
    const len = value.getTotalLength() || 1;
    const dash = `${(len * t).toFixed(2)} ${len.toFixed(2)}`;
    value.style.strokeDasharray = dash;
    if (glow) glow.style.strokeDasharray = dash;
    state.dialT = t;
  }
  function paintTicks(scale) {
    const g = document.getElementById("dial-ticks");
    if (!g) return;
    const parts = [];
    for (let i = 0; i <= 4; i++) {
      const frac = i / 4;
      const [x1, y1] = polar(frac, 86);
      const [x2, y2] = polar(frac, i % 2 === 0 ? 98 : 94);
      parts.push(`<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="rgba(239,230,255,0.55)" stroke-width="${i % 2 === 0 ? 1.6 : 1}"/>`);
    }
    const [lx, ly] = polar(0, 112);
    const [rx, ry] = polar(1, 112);
    parts.push(`<text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" fill="#b7adc9" font-size="11" font-family="JetBrains Mono, monospace" text-anchor="middle">0</text>`);
    parts.push(`<text x="${rx.toFixed(1)}" y="${ry.toFixed(1)}" fill="#b7adc9" font-size="11" font-family="JetBrains Mono, monospace" text-anchor="middle">${scale}</text>`);
    g.innerHTML = parts.join("");
  }
  function animateDial(toT, toAng) {
    const fromT = state.dialT;
    const fromAng = state.dialAngle;
    if (reduceMotion) {
      setDash(toT);
      setNeedle(toAng);
      return;
    }
    const token = ++state.anim;
    const t0 = performance.now();
    function frame(now) {
      if (token !== state.anim) return;
      const k = Math.min(1, (now - t0) / 900);
      const e = 1 - Math.pow(1 - k, 3);
      setDash(fromT + (toT - fromT) * e);
      setNeedle(fromAng + (toAng - fromAng) * e);
      if (k < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }
  function animateEquity(el, from, to) {
    el.setAttribute("aria-label", money(to));
    if (reduceMotion || from === to) {
      el.textContent = money(to);
      return;
    }
    const token = ++state.eqAnim;
    const t0 = performance.now();
    function frame(now) {
      if (token !== state.eqAnim) return;
      const k = Math.min(1, (now - t0) / 850);
      const e = 1 - Math.pow(1 - k, 3);
      el.textContent = money(from + (to - from) * e);
      if (k < 1) requestAnimationFrame(frame);
      else el.textContent = money(to);
    }
    requestAnimationFrame(frame);
  }

  function selectedSeat() {
    return state.hooks && state.hooks.getState ? state.hooks.getState().seat : null;
  }

  function renderSeats() {
    const rail = document.getElementById("seat-rail");
    const note = document.getElementById("seat-note");
    if (!rail || !state.bot) return;
    const seat = selectedSeat();
    rail.innerHTML = seatModel(state.bot).map((s) => `
      <button type="button" class="seat is-${esc(s.level)}${seat === s.id ? " is-selected" : ""}" data-seat="${esc(s.id)}" aria-pressed="${seat === s.id ? "true" : "false"}">
        <span class="seat-top"><span class="seat-en">${esc(s.id)}</span><span class="lamp" aria-hidden="true"></span></span>
        <span class="seat-zh">${esc(s.zh)}</span>
        <span class="seat-role">${esc(s.role)}</span>
        <span class="seat-st">${esc(s.status)}</span>
      </button>`).join("");
    if (!note) return;
    if (seat) note.textContent = "正在看「" + (SEAT_ZH[seat] || seat) + "」在流水里的记录。再点一次取消。";
    else note.textContent = "主控、量化、扫描、裁决、股票、仓位、成交、风控。点一席，只看它在流水里留下的记录。灯是账本状态，不是新的成交。";
  }

  function updateEquity(b) {
    const target = Number(b.equity);
    const startCash = Number(b.start_cash);
    const pnl = (Number.isFinite(target) ? target : 0) - (Number.isFinite(startCash) ? startCash : 0);
    const pnlP = startCash ? (pnl / startCash) * 100 : 0;
    const el = document.getElementById("equity-num");
    if (el && state.equity !== target) {
      const from = state.equity == null ? 0 : state.equity;
      state.equity = target;
      animateEquity(el, from, Number.isFinite(target) ? target : 0);
    }
    const pnlEl = document.getElementById("equity-pnl");
    if (pnlEl) {
      pnlEl.className = "equity-pnl mono " + pnlClass(pnl);
      pnlEl.textContent = signedMoney(pnl) + " · " + pct(Number.isFinite(pnlP) ? pnlP : 0);
    }
    const mix = b.equity ? Math.max(0, Math.min(100, (Number(b.cash) / Number(b.equity)) * 100)) : 0;
    const mixEl = document.getElementById("cash-mix");
    const bar = document.getElementById("cash-bar");
    if (mixEl) mixEl.textContent = trimNum(mix) + "%";
    if (bar) bar.style.width = mix + "%";
  }

  function updateDial(b) {
    const dial = readDial(b);
    const scale = dialScale(dial.value == null ? 0 : dial.value);
    const t = dial.value == null ? 0 : Math.max(0, Math.min(1, dial.value / scale));
    const ang = START + SWEEP * t;
    const key = (dial.value == null ? "x" : dial.value) + "@" + scale;
    const val = document.getElementById("dial-val");
    const cap = document.getElementById("dial-cap");
    const scaleEl = document.getElementById("dial-scale");
    const src = document.getElementById("dial-src");
    if (val) val.textContent = dial.value == null ? "—" : trimNum(dial.value);
    if (cap) cap.textContent = dial.value == null ? "无拨盘读数" : "meme 拨盘 " + trimNum(dial.value) + "%";
    if (scaleEl) scaleEl.textContent = "刻度 0–" + scale + "%";
    if (src) src.textContent = sourceLabel(dial.source);
    if (state.dialKey !== key) {
      paintTicks(scale);
      state.dialKey = key;
      animateDial(t, ang);
    }
  }

  function updateBook(b) {
    const book = document.getElementById("book");
    if (!book) return;
    const pnl = Number(b.realized_pnl);
    const rows = [
      ["现金", money(b.cash), ""],
      ["起始", money(b.start_cash), ""],
      ["已实现", signedMoney(b.realized_pnl), pnlClass(pnl)],
      ["胜 / 负", `${b.win_count ?? 0} / ${b.loss_count ?? 0}`, ""],
      ["成交", String(b.trade_count ?? 0), ""],
      ["持仓", String(b.open_positions_count ?? (b.open_positions || []).length), ""],
    ];
    book.innerHTML = rows.map(([k, v, cls]) => `<dt>${k}</dt><dd class="${cls}">${v}</dd>`).join("");
    const sizing = document.getElementById("sizing-copy");
    if (sizing) sizing.textContent = b.sizing_note || "账本没有仓位说明";
  }

  function initDial() {
    if (state.ready) return;
    const track = document.getElementById("dial-track");
    if (!track) return;
    const d = arcPath(CX, CY, R, START, START + SWEEP);
    track.setAttribute("d", d);
    const glow = document.getElementById("dial-glow");
    const value = document.getElementById("dial-value");
    if (glow) glow.setAttribute("d", d);
    if (value) value.setAttribute("d", d);
    setNeedle(START);
    setDash(0);
    state.ready = true;
  }

  function install(hooks) {
    state.hooks = hooks || null;
    initDial();
    const rail = document.getElementById("seat-rail");
    if (rail && !rail.dataset.bound) {
      rail.dataset.bound = "1";
      rail.addEventListener("click", (ev) => {
        const btn = ev.target.closest(".seat");
        if (!btn || !state.hooks || !state.hooks.getState) return;
        const seat = btn.dataset.seat;
        const st = state.hooks.getState();
        st.seat = st.seat === seat ? null : seat;
        renderSeats();
        if (state.hooks.rerender) state.hooks.rerender();
      });
    }
    const tick = () => {
      const el = document.getElementById("desk-clock");
      if (!el) return;
      el.textContent = new Intl.DateTimeFormat("zh-CN", {
        timeZone: "Asia/Singapore",
        hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
      }).format(new Date());
    };
    tick();
    setInterval(tick, 1000);
  }

  function update(bot) {
    state.bot = bot || {};
    initDial();
    updateEquity(state.bot);
    updateDial(state.bot);
    updateBook(state.bot);
    renderSeats();
  }

  window.SavipwwDesk = {
    install,
    update,
    refreshSeats: renderSeats,
    eventMatchesSeat,
    seatLabel(id) { return SEAT_ZH[id] || id; },
    readDial,
  };
})();
