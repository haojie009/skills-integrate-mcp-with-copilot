document.addEventListener("DOMContentLoaded", () => {
  const listEl = document.getElementById("list");
  const listTitle = document.getElementById("list-title");
  const disclaimerEl = document.getElementById("disclaimer");
  const dataSourceEl = document.getElementById("data-source");
  const modal = document.getElementById("modal");
  const modalBody = document.getElementById("modal-body");

  let screenerData = [];
  let currentSort = "score";
  let currentTab = "screener";
  let categoriesLoaded = false;
  let watchSet = new Set();

  // ---- 口袋名單（登入時同步雲端 Supabase，未登入時存本機 localStorage）----
  let cachedWatchlist = [];

  function readLocalWatchlist() {
    try {
      return JSON.parse(localStorage.getItem("watchlist") || "[]");
    } catch (e) {
      return [];
    }
  }
  function writeLocalWatchlist(list) {
    localStorage.setItem("watchlist", JSON.stringify(list));
  }

  function isLoggedIn() {
    return !!(window.SB && window.SB.getUser());
  }

  async function loadWatchlistFromBackend() {
    if (isLoggedIn()) {
      try {
        const cloud = await window.SB.cloudGetWatchlist();
        cachedWatchlist = cloud || [];
        watchSet = new Set(cachedWatchlist);
        return;
      } catch (e) {
        console.warn("讀取雲端口袋名單失敗，改用本機資料", e);
      }
    }
    cachedWatchlist = readLocalWatchlist();
    watchSet = new Set(cachedWatchlist);
  }

  async function persistWatchlist() {
    if (isLoggedIn()) {
      try {
        await window.SB.cloudSetWatchlist(cachedWatchlist);
        return;
      } catch (e) {
        console.warn("寫入雲端失敗，改存本機", e);
      }
    }
    writeLocalWatchlist(cachedWatchlist);
  }

  function getWatchlist() {
    return [...cachedWatchlist];
  }
  function setWatchlistInMemory(list) {
    cachedWatchlist = [...new Set(list)];
    watchSet = new Set(cachedWatchlist);
  }
  function toggleWatch(code) {
    if (watchSet.has(code)) {
      cachedWatchlist = cachedWatchlist.filter((c) => c !== code);
    } else {
      cachedWatchlist = [...cachedWatchlist, code];
    }
    watchSet = new Set(cachedWatchlist);
    persistWatchlist();
    return watchSet.has(code);
  }
  function refreshWatchSet() {
    watchSet = new Set(cachedWatchlist);
  }

  async function migrateLocalToCloud() {
    const local = readLocalWatchlist();
    if (!local.length) return;
    try {
      const cloud = (await window.SB.cloudGetWatchlist()) || [];
      const merged = [...new Set([...cloud, ...local])];
      await window.SB.cloudSetWatchlist(merged);
      localStorage.removeItem("watchlist");
    } catch (e) {
      console.warn("遷移本機口袋名單到雲端失敗", e);
    }
  }

  // ---- 工具函式 -----------------------------------------------------------
  const fmtPrice = (n) => Number(n).toLocaleString("zh-Hant", { minimumFractionDigits: 2 });
  const fmtPct = (n) => (n >= 0 ? "+" : "") + Number(n).toFixed(2) + "%";
  const dirClass = (n) => (n >= 0 ? "up" : "down");
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const esc = (s) =>
    String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

  // 具備逾時與自動重試的 fetch — 用來撐過免費主機的冷啟動等待
  async function fetchJSON(url, options = {}, hooks = {}) {
    const attempts = hooks.attempts || 4;
    const timeoutMs = hooks.timeoutMs || 20000;
    let lastErr;
    for (let i = 1; i <= attempts; i++) {
      if (hooks.onAttempt) hooks.onAttempt(i, attempts);
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), timeoutMs);
      try {
        const res = await fetch(url, { ...options, signal: ctrl.signal });
        clearTimeout(timer);
        if (!res.ok) throw new Error("伺服器回應 HTTP " + res.status);
        return await res.json();
      } catch (err) {
        clearTimeout(timer);
        lastErr = err;
        if (i < attempts) await sleep(2000 * i);
      }
    }
    throw lastErr;
  }

  function actionClass(action) {
    if (action === "強烈買進") return "act-strong";
    if (action === "買進") return "act-buy";
    if (action === "觀望") return "act-hold";
    return "act-avoid";
  }

  function scoreColor(score) {
    if (score >= 72) return "#e23b3b";
    if (score >= 60) return "#c9622f";
    if (score >= 46) return "#7b8da0";
    return "#1aa251";
  }

  function bar(label, score) {
    const color = scoreColor(score);
    return `
      <div class="subscore">
        <div class="lbl"><span>${label}</span><span>${score.toFixed(0)}</span></div>
        <div class="bar"><span style="width:${score}%;background:${color}"></span></div>
      </div>`;
  }

  function signalRow(sig) {
    const isUp = sig.side === "多";
    return `<div class="sig"><span class="tag ${isUp ? "tag-up" : "tag-down"}">${sig.side}</span>${sig.text}</div>`;
  }

  // ---- 選股清單 -----------------------------------------------------------
  const fmtLots = (n) => {
    const v = Math.round(n || 0);
    return (v > 0 ? "+" : "") + v.toLocaleString("zh-Hant");
  };

  function tagClass(tag) {
    if (tag === "弱勢" || tag === "法人賣超") return "tag-down";
    if (
      tag === "小型爆發" ||
      tag === "投信買超" ||
      tag === "飆股訊號" ||
      tag === "突破前高"
    ) {
      return "tag-gold";
    }
    return "tag-up";
  }

  function screenerRowHTML(s, rank) {
    const tags = (s.tags || [])
      .map((t) => `<span class="tag-chip ${tagClass(t)}">${esc(t)}</span>`)
      .join("");
    const inst =
      s.inst_lots === undefined || s.inst_lots === null
        ? ""
        : `<span class="${dirClass(s.inst_lots)}">法人 ${fmtLots(s.inst_lots)} 張</span>`;
    return `
      <div class="srow" data-code="${s.code}" data-name="${esc(s.name)}">
        <span class="srank">${rank}</span>
        <div class="sinfo">
          <div class="sname">${esc(s.name)} <span class="scode">${s.code}</span>${
            s.theme ? ` <span class="theme-tag">${esc(s.theme)}</span>` : ""
          } ${tags}</div>
          <div class="smetrics">
            <span>現價 <b>${fmtPrice(s.close)}</b></span>
            <span class="${dirClass(s.change_pct)}">${fmtPct(s.change_pct)}</span>
            <span>振幅 ${s.amplitude_pct}%</span>
            <span>金額 ${s.turnover_yi} 億</span>
            ${s.vol_ratio ? `<span>量增 ${s.vol_ratio} 倍</span>` : ""}
            ${inst}
          </div>
        </div>
        <div class="sscore">
          <div class="sscore-num" style="color:${scoreColor(s.score)}">${Math.round(s.score)}</div>
          <div class="sscore-lbl">當沖分</div>
        </div>
        <button class="star-btn ${watchSet.has(s.code) ? "on" : ""}" data-code="${s.code}"
          >${watchSet.has(s.code) ? "★" : "☆"}</button>
      </div>`;
  }

  function wireRows(container) {
    container.querySelectorAll(".srow").forEach((row) => {
      row.addEventListener("click", () => openDetail(row.dataset.code, row.dataset.name));
    });
    container.querySelectorAll(".star-btn").forEach((star) => {
      star.addEventListener("click", (e) => {
        e.stopPropagation();
        const added = toggleWatch(star.dataset.code);
        star.textContent = added ? "★" : "☆";
        star.classList.toggle("on", added);
        if (currentTab === "watchlist") renderWatchlist();
      });
    });
  }

  function renderScreener() {
    refreshWatchSet();
    const sorted = [...screenerData]
      .sort((a, b) => (b[currentSort] ?? 0) - (a[currentSort] ?? 0))
      .slice(0, 300);
    listEl.innerHTML = sorted.map((s, i) => screenerRowHTML(s, i + 1)).join("");
    wireRows(listEl);
  }

  function renderWatchlist() {
    refreshWatchSet();
    const listWrap = document.getElementById("watchlist-list");
    const actionsEl = document.getElementById("wl-actions");
    const codes = getWatchlist();
    if (codes.length === 0) {
      listWrap.innerHTML =
        '<p class="loading">口袋名單是空的。<br><small>到「當沖選股」頁點每列右側的 ☆，或在上方輸入代號加入。</small></p>';
      actionsEl.innerHTML = "";
      return;
    }
    const byCode = {};
    screenerData.forEach((s) => {
      byCode[s.code] = s;
    });
    const found = codes.map((c) => byCode[c]).filter(Boolean);
    const missing = codes.filter((c) => !byCode[c]);
    listWrap.innerHTML =
      found.map((s, i) => screenerRowHTML(s, i + 1)).join("") +
      missing
        .map(
          (c) => `
        <div class="srow" data-code="${c}" data-name="">
          <span class="srank">–</span>
          <div class="sinfo"><div class="sname">${c}
            <span class="scode">${screenerData.length ? "查無即時資料" : "資料載入中…"}</span></div></div>
          <button class="star-btn on" data-code="${c}">★</button>
        </div>`
        )
        .join("");
    wireRows(listWrap);
    actionsEl.innerHTML =
      '<button id="wl-to-premarket" class="retry-btn">用口袋名單做盤前簡報</button>';
    document.getElementById("wl-to-premarket").addEventListener("click", () => {
      document.getElementById("pm-holdings").value = codes.join(",");
      document.querySelector('.tab-btn[data-tab="premarket"]').click();
    });
  }

  // ---- 載入選股清單 -------------------------------------------------------
  function renderError(message) {
    disclaimerEl.textContent = "⚠️ 本工具僅供教學研究，非投資建議。";
    listEl.innerHTML = `
      <div class="error-box">
        <p>${message}</p>
        <button id="retry-btn" class="retry-btn">重新載入</button>
      </div>`;
    document.getElementById("retry-btn").addEventListener("click", loadScreener);
  }

  async function loadScreener() {
    listEl.innerHTML =
      '<p class="loading">掃描全市場中…<br><small>首次載入需即時抓取 130+ 檔真實行情，約 30–90 秒，請稍候</small></p>';
    const onAttempt = (i, total) => {
      if (i > 1) {
        listEl.innerHTML = `<p class="loading">仍在抓取真實行情，重試 ${i}/${total}…<br><small>請勿關閉頁面</small></p>`;
      }
    };
    try {
      const data = await fetchJSON(
        "/api/screener?limit=2000",
        {},
        { onAttempt, timeoutMs: 60000, attempts: 5 }
      );
      disclaimerEl.textContent = "⚠️ " + data.disclaimer;
      dataSourceEl.textContent = "資料來源：" + data.data_source;
      screenerData = data.stocks || [];
      const shown = Math.min(screenerData.length, 300);
      listTitle.textContent = `當沖適合度排行（顯示前 ${shown} 檔，掃描 ${data.total} 檔）`;

      const warnEl = document.getElementById("screener-warn");
      if ((data.data_source || "").includes("demo")) {
        const reason = data.live_error
          ? `真實行情抓取失敗：${esc(data.live_error)}`
          : "尚未取得真實行情（證交所資料來源無回應）";
        warnEl.innerHTML =
          `⚠️ 目前顯示「示範資料」（僅 ${screenerData.length} 檔模擬股），<b>非真實行情</b>。<br>${reason}`;
        warnEl.classList.remove("hidden");
      } else {
        warnEl.classList.add("hidden");
      }
      renderScreener();
      if (currentTab === "watchlist") renderWatchlist();
    } catch (err) {
      renderError(
        `掃描失敗：${err.message}。免費主機可能仍在喚醒，請按下方按鈕重試。`
      );
      console.error(err);
    }
  }

  // ---- 個股分類 -----------------------------------------------------------
  function volRowHTML(s) {
    return `
      <div class="srow" data-code="${s.code}" data-name="${esc(s.name)}">
        <span class="srank">${s.rank}</span>
        <div class="sinfo">
          <div class="sname">${esc(s.name)} <span class="scode">${s.code}</span></div>
          <div class="smetrics">
            <span>現價 <b>${fmtPrice(s.close)}</b></span>
            <span class="${dirClass(s.change_pct)}">${fmtPct(s.change_pct)}</span>
          </div>
        </div>
        <div class="sscore">
          <div class="sscore-num" style="font-size:1.05rem">${s.volume_lots.toLocaleString("zh-Hant")}</div>
          <div class="sscore-lbl">張</div>
        </div>
      </div>`;
  }

  function themeCardHTML(t, idx) {
    const members = t.members
      .map(
        (m) => `
        <div class="tmember" data-code="${m.code}" data-name="${esc(m.name)}">
          <span>${esc(m.name)} <span class="scode">${m.code}</span></span>
          <span class="${dirClass(m.change_pct)}">${fmtPct(m.change_pct)}</span>
        </div>`
      )
      .join("");
    return `
      <div class="theme-card">
        <div class="theme-head" data-idx="${idx}">
          <div class="theme-info">
            <div class="theme-name">${esc(t.name)}
              <span class="${dirClass(t.avg_change)}">平均 ${fmtPct(t.avg_change)}</span></div>
            <div class="theme-sub">▲ ${t.up_count}/${t.member_count} 家上漲　·　成交 ${t.turnover_yi} 億　·　領漲 ${esc(t.leader.name)} ${fmtPct(t.leader.change_pct)}</div>
          </div>
          <span class="theme-toggle">▾</span>
        </div>
        <div class="theme-members hidden" id="theme-m-${idx}">${members}</div>
      </div>`;
  }

  async function loadCategories() {
    const volEl = document.getElementById("volume-list");
    const themeEl = document.getElementById("theme-list");
    volEl.innerHTML = '<p class="loading">載入中…</p>';
    themeEl.innerHTML = "";
    try {
      const data = await fetchJSON("/api/categories", {}, { attempts: 3 });
      categoriesLoaded = true;
      volEl.innerHTML = data.volume_ranking.map(volRowHTML).join("");
      volEl.querySelectorAll(".srow").forEach((row) => {
        row.addEventListener("click", () => openDetail(row.dataset.code, row.dataset.name));
      });
      themeEl.innerHTML = data.themes.map((t, i) => themeCardHTML(t, i)).join("");
      themeEl.querySelectorAll(".theme-head").forEach((h) => {
        h.addEventListener("click", () => {
          document.getElementById("theme-m-" + h.dataset.idx).classList.toggle("hidden");
          h.querySelector(".theme-toggle").classList.toggle("open");
        });
      });
      themeEl.querySelectorAll(".tmember").forEach((m) => {
        m.addEventListener("click", () => openDetail(m.dataset.code, m.dataset.name));
      });
    } catch (err) {
      volEl.innerHTML = `<p class="loading">分類載入失敗：${err.message}</p>`;
      console.error(err);
    }
  }

  // ---- 盤前簡報 -----------------------------------------------------------
  function premarketHTML(d) {
    const mkt = (d.markets || [])
      .map((m) => {
        const c = m.change_pct;
        const cls = c == null ? "" : dirClass(c);
        return `<div class="pm-mkt"><span>${esc(m.name)}</span>
          <span><b>${m.price == null ? "—" : m.price}</b>
          <span class="${cls}">${c == null ? "" : fmtPct(c)}</span></span></div>`;
      })
      .join("");

    let briefing;
    if (d.available && d.briefing) {
      const a = d.briefing;
      const block = (t, x) => `<div class="ai-role"><h5>${t}</h5><p>${esc(x)}</p></div>`;
      briefing = `
        <p class="ai-summary">${esc(a.summary)}</p>
        ${block("大盤與國際盤前情緒", a.market_sentiment)}
        ${block("今日重要財經事件", a.key_events)}
        ${block("主要利多", a.bullish_factors)}
        ${block("主要利空", a.bearish_factors)}
        ${block("熱門題材與資金流向", a.sector_rotation)}
        ${block("持股盤前風險檢查", a.holdings_check)}
        ${block("開高／開低／平盤 應對計畫", a.scenario_plan)}
        <div class="ai-role risk"><h5>今日最需避免的交易錯誤</h5><p>${esc(a.avoid_mistakes)}</p></div>
        ${block("風控與交易紀律提醒", a.discipline_note)}
        <p class="ai-model">AI 盤前助理（${esc(d.model || "")}）· 不提供買賣明牌 · 僅供參考</p>`;
    } else {
      briefing = `<div class="ai-unavailable"><p>${esc(d.message || "AI 盤前簡報無法產生")}</p></div>`;
    }

    const levels = (d.holdings || []).concat(d.watch || []);
    let table = "";
    if (levels.length) {
      table =
        '<div class="modal-section"><h4>持股／觀察股 觀察價位</h4><div class="screener-list">' +
        levels
          .map(
            (s) => `
        <div class="srow" data-code="${s.code}" data-name="${esc(s.name)}">
          <div class="sinfo">
            <div class="sname">${esc(s.name)} <span class="scode">${s.code}</span></div>
            <div class="smetrics">
              <span>現價 <b>${fmtPrice(s.last_close)}</b></span>
              <span class="${dirClass(s.change_pct)}">${fmtPct(s.change_pct)}</span>
              <span>壓力 ${s.r1} / ${s.r2}</span>
              <span>支撐 ${s.s1} / ${s.s2}</span>
              <span class="down">停損 ${s.stop}</span>
            </div>
          </div>
        </div>`
          )
          .join("") +
        "</div></div>";
    }

    return `
      <div class="modal-section">
        <h4>國際盤前指標（最近收盤）</h4>
        <div class="pm-markets">${mkt}</div>
      </div>
      <div class="modal-section ai-section">
        <h4>AI 盤前簡報</h4>
        ${briefing}
      </div>
      ${table}
      <p style="font-size:0.76rem;color:var(--muted);margin-top:12px">⚠️ ${esc(d.disclaimer || "")}</p>`;
  }

  // ---- 全球盤勢卡片 -------------------------------------------------------
  function globalBiasHTML(bias, markets) {
    if (!bias) return "";
    const label = bias.label || "中性";
    const score = bias.overall_score;
    const cls =
      label.includes("偏多") ? "bias-up" :
      label.includes("偏空") ? "bias-down" : "bias-mid";
    const signals = (bias.signals || [])
      .map((s) => `<li>${esc(s)}</li>`)
      .join("");
    const groupBias = bias.group_bias || {};
    const groupItems = Object.keys(groupBias)
      .sort((a, b) => groupBias[b] - groupBias[a])
      .map((g) => {
        const v = groupBias[g];
        const c = v > 0.3 ? "up" : v < -0.3 ? "down" : "neu";
        const sign = v >= 0 ? "+" : "";
        return `<span class="gb-tag ${c}">${esc(g)} ${sign}${v.toFixed(1)}</span>`;
      })
      .join("");
    const tickers = (markets || [])
      .map((m) => {
        if (m.change_pct === null || m.change_pct === undefined) {
          return `<div class="ticker"><span class="tn">${esc(m.name)}</span><span class="tv muted">—</span></div>`;
        }
        const c = m.change_pct >= 0 ? "up" : "down";
        return `<div class="ticker"><span class="tn">${esc(m.name)}</span>
          <span class="tv ${c}">${fmtPct(m.change_pct)}</span></div>`;
      })
      .join("");

    return `
      <div class="bias-card ${cls}">
        <div class="bias-head">
          <div class="bias-label">全球盤勢:<b>${esc(label)}</b>
            <span class="bias-score">(${score >= 0 ? "+" : ""}${score})</span></div>
        </div>
        <div class="bias-hint">${esc(bias.action_hint || "")}</div>
        ${signals ? `<ul class="bias-signals">${signals}</ul>` : ""}
        ${groupItems ? `<div class="bias-groups"><span class="bgl">族群方向:</span>${groupItems}</div>` : ""}
        <div class="bias-tickers">${tickers}</div>
      </div>`;
  }

  // 迷你 K 棒圖(近 N 根日 K,純 HTML/CSS)
  function miniKBarHTML(bars) {
    if (!bars || !bars.length) return "";
    const valid = bars.filter((b) => b && b.high && b.low && b.open && b.close);
    if (!valid.length) return "";
    const all = valid.flatMap((b) => [b.high, b.low]);
    const max = Math.max(...all);
    const min = Math.min(...all);
    const range = max - min || 1;
    const H = 50;
    const cells = bars
      .map((b) => {
        if (!b || !b.open || !b.close || !b.high || !b.low) {
          return '<div class="mb-cell"></div>';
        }
        const bull = b.close >= b.open;
        const cls = bull ? "up" : "down";
        const topY = H * (1 - (b.high - min) / range);
        const botY = H * (1 - (b.low - min) / range);
        const bodyTop = H * (1 - (Math.max(b.open, b.close) - min) / range);
        const bodyBot = H * (1 - (Math.min(b.open, b.close) - min) / range);
        const bodyH = Math.max(1, bodyBot - bodyTop);
        const shadowH = Math.max(1, botY - topY);
        return `<div class="mb-cell">
          <div class="mb-shadow ${cls}" style="top:${topY.toFixed(1)}px;height:${shadowH.toFixed(1)}px"></div>
          <div class="mb-body ${cls}" style="top:${bodyTop.toFixed(1)}px;height:${bodyH.toFixed(1)}px"></div>
        </div>`;
      })
      .join("");
    return `<div class="mini-kbar" style="height:${H}px">${cells}</div>`;
  }

  // ---- 盤前精選當沖名單 -------------------------------------------------
  function pickCardHTML(p, rank) {
    const op = p.open_plan || {};
    const tagsHTML = (p.tags || [])
      .map((t) => `<span class="stag">${esc(t)}</span>`)
      .join("");
    const dirMap = {
      "做多優先": "dir-strong",
      "偏多可進": "dir-up",
      "中性看技術": "dir-neu",
      "保守做多": "dir-cau",
      "暫緩做多": "dir-stop",
    };
    const dirBadgeCls = dirMap[p.direction] || "dir-neu";
    const dirBadge = p.direction
      ? `<div class="pick-dir ${dirBadgeCls}">
          <b>${esc(p.direction)}</b>
          ${p.direction_note ? `<span>${esc(p.direction_note)}</span>` : ""}
        </div>`
      : "";
    const k = p.kline || {};
    const kSideCls =
      k.side === "多" ? "k-up" : k.side === "空" ? "k-down" : "k-mid";
    const kPatTags = (k.patterns || [])
      .map((t) => `<span class="k-tag">${esc(t)}</span>`)
      .join("");
    const klineBlock = k && k.text
      ? `<div class="pick-kline">
          <div class="pk-left">
            <div class="pk-head">
              <b>K 線</b>
              <span class="pk-side ${kSideCls}">${esc(k.side || "中")}</span>
              ${k.strength ? `<span class="pk-str">強度 ${k.strength}/3</span>` : ""}
            </div>
            <div class="pk-text">${esc(k.text)}</div>
            <div class="pk-tags">${kPatTags}</div>
          </div>
          <div class="pk-right">${miniKBarHTML(p.recent_bars)}</div>
        </div>`
      : "";
    const reasonsHTML = (p.reasons || [])
      .map((r) => `<li>${esc(r)}</li>`)
      .join("");
    const cautionsHTML = (p.cautions || [])
      .map((c) => `<li>${esc(c)}</li>`)
      .join("");
    const dirCls = (p.change_pct || 0) >= 0 ? "up" : "down";
    return `
      <div class="pick-card" data-code="${p.code}" data-name="${esc(p.name)}">
        <div class="pick-head">
          <div class="pick-rank">#${rank}</div>
          <div class="pick-title">
            <div class="pick-name">${esc(p.name)} <span class="pick-code">${p.code}</span></div>
            <div class="pick-meta">
              <span class="${dirCls}">${fmtPrice(p.last_close)}</span>
              <span class="${dirCls}">${fmtPct(p.change_pct || 0)}</span>
              <span>振幅 ${(p.amplitude_pct || 0).toFixed(1)}%</span>
              <span>${(p.turnover_yi || 0).toFixed(1)} 億</span>
              ${p.theme ? `<span class="pick-theme">${esc(p.theme)}</span>` : ""}
            </div>
          </div>
          <div class="pick-score">
            <div class="pick-score-num">${Math.round(p.score || 0)}</div>
            <div class="pick-score-lbl">當沖分</div>
          </div>
        </div>
        <div class="pick-tags">${tagsHTML}</div>
        ${dirBadge}
        ${klineBlock}
        <div class="pick-plan">
          <div class="pp-row"><b>進場</b>${esc(op.trigger || "—")}</div>
          <div class="pp-grid">
            <div><span>觸發</span><b>${fmtPrice(op.trigger_price || 0)}</b></div>
            <div><span>停利1</span><b class="up">${fmtPrice(op.target1 || 0)} (+${op.target1_pct}%)</b></div>
            <div><span>停利2</span><b class="up">${fmtPrice(op.target2 || 0)}</b></div>
            <div><span>停損</span><b class="down">${fmtPrice(op.stop || 0)} (-${op.stop_pct}%)</b></div>
          </div>
          <div class="pp-row"><b>出場</b>${esc(op.exit_time || "—")}</div>
          <div class="pp-row"><b>部位</b>${esc(op.position_hint || "—")}</div>
        </div>
        ${reasonsHTML ? `<div class="pick-block"><b>✅ 入選理由</b><ul>${reasonsHTML}</ul></div>` : ""}
        ${cautionsHTML ? `<div class="pick-block warn"><b>⚠️ 風險與不該追的條件</b><ul>${cautionsHTML}</ul></div>` : ""}
      </div>`;
  }

  let picksLoaded = false;
  async function loadPicks() {
    const wrap = document.getElementById("picks-list");
    if (!wrap) return;
    wrap.innerHTML = '<p class="loading">挑選盤前精選名單中…</p>';
    try {
      const d = await fetchJSON("/api/picks?top_n=8", {}, { attempts: 3, timeoutMs: 60000 });
      const picks = d.picks || [];
      if (!picks.length) {
        wrap.innerHTML =
          globalBiasHTML(d.global_bias, d.markets) +
          '<p class="loading">目前沒有符合嚴格條件的當沖標的(可能成交清淡或市場動能不足)。</p>';
        picksLoaded = true;
        return;
      }
      const biasHTML = globalBiasHTML(d.global_bias, d.markets);
      wrap.innerHTML = biasHTML + picks.map((p, i) => pickCardHTML(p, i + 1)).join("");
      wrap.querySelectorAll(".pick-card").forEach((card) => {
        card.addEventListener("click", (e) => {
          if (e.target.closest("a,button")) return;
          openDetail(card.dataset.code, card.dataset.name);
        });
      });
      picksLoaded = true;
    } catch (err) {
      wrap.innerHTML = `<div class="ai-unavailable"><p>挑選失敗:${esc(err.message)}</p>
        <button class="retry-btn" id="picks-retry">重試</button></div>`;
      document.getElementById("picks-retry").addEventListener("click", loadPicks);
    }
  }

  async function loadPremarket() {
    const btn = document.getElementById("pm-run-btn");
    const resultEl = document.getElementById("pm-result");
    const holdings = document.getElementById("pm-holdings").value.trim();
    const watch = document.getElementById("pm-watch").value.trim();
    btn.disabled = true;
    resultEl.innerHTML =
      '<p class="loading">產生盤前簡報中…<br><small>抓國際盤、分析持股、AI 整理計畫，約需 1–3 分鐘，請稍候</small></p>';
    try {
      const q = `holdings=${encodeURIComponent(holdings)}&watch=${encodeURIComponent(watch)}`;
      const d = await fetchJSON(`/api/premarket?${q}`, {}, { attempts: 1, timeoutMs: 240000 });
      resultEl.innerHTML = premarketHTML(d);
      resultEl.querySelectorAll(".srow").forEach((row) => {
        row.addEventListener("click", () => openDetail(row.dataset.code, row.dataset.name));
      });
    } catch (err) {
      resultEl.innerHTML = `<div class="ai-unavailable"><p>盤前簡報產生失敗：${esc(err.message)}</p></div>`;
    }
    btn.disabled = false;
  }

  // ---- 個股明細 -----------------------------------------------------------
  function kv(k, v) {
    return `<div class="kv"><div class="k">${k}</div><div class="v">${v}</div></div>`;
  }

  function planBlock(p) {
    return `
      <div class="plan-block">
        <h5>${p.strategy_name}　|　${p.action}</h5>
        <div class="kv-grid">
          ${kv("進場區間", fmtPrice(p.entry_low) + " ~ " + fmtPrice(p.entry_high))}
          ${kv("停利目標", fmtPrice(p.target) + "（+" + p.target_pct + "%）")}
          ${kv("停損價", fmtPrice(p.stop) + "（-" + p.stop_pct + "%）")}
          ${kv("風險報酬比", p.risk_reward ? "1 : " + p.risk_reward : "—")}
        </div>
        <div class="plan-times">
          <div><b>進場時機：</b>${p.entry_time}</div>
          <div><b>出場時機：</b>${p.exit_time}</div>
          <div><b>持有方式：</b>${p.holding}</div>
        </div>
      </div>`;
  }

  function modalHTML(d) {
    const ind = d.indicators;
    const sc = d.scores;
    const lv = d.levels;
    const inst = d.institutional;
    const num = (v, dp = 2) => (v === null || v === undefined ? "—" : Number(v).toFixed(dp));
    const instCell = (key) => {
      if (!inst || inst[key] == null) return "—";
      const v = inst[key];
      return `<span class="${v >= 0 ? "up" : "down"}">${v >= 0 ? "+" : ""}${v.toLocaleString("zh-Hant")} 張</span>`;
    };
    const obvText = ind.obv
      ? { up: "走高 ▲", down: "走低 ▼", flat: "持平" }[ind.obv.trend]
      : "—";

    const sigSection = (title, arr) => {
      if (!arr.length) return "";
      const rows = arr
        .map((s) => signalRow({ side: s[0], text: s[1] }))
        .join("");
      return `<div class="modal-section"><h4>${title}</h4><div class="signals">${rows}</div></div>`;
    };

    const newsRows = d.news.length
      ? d.news
          .map((n) => {
            const side = n.sentiment > 0 ? "多" : n.sentiment < 0 ? "空" : "中";
            return signalRow({ side, text: `${n.title}（${n.source}）` });
          })
          .join("")
      : '<div class="sig">近期無明顯新聞題材</div>';

    return `
      <h2>${esc(d.name)} <span class="stock-code">${d.code}</span>
        ${d.sector ? `<span class="sector">${esc(d.sector)}</span>` : ""}</h2>
      <div class="pi-val" style="margin-top:4px">收盤 ${fmtPrice(d.last_close)}
        <span class="chg ${dirClass(d.change_pct)}">${fmtPct(d.change_pct)}</span></div>

      <div class="modal-section">
        <h4>當日盤中走勢</h4>
        <div class="chart-label">Yahoo 1 分線（約延遲 15–20 分，非逐筆即時）</div>
        <div id="chart-intraday" class="chart-box small"></div>
        <div id="intraday-fallback" class="chart-fallback hidden"></div>
      </div>

      <div class="modal-section">
        <h4>技術線圖（近 90 個交易日）</h4>
        <div class="chart-label">K 線　·　均線 <span style="color:#f4b740">MA5</span>
          <span style="color:#5fa8e0">MA10</span> <span style="color:#c98bff">MA20</span>　·　成交量</div>
        <div id="chart-price" class="chart-box"></div>
        <div class="chart-label">MACD（12,26,9）　<span style="color:#f4b740">DIF</span>
          <span style="color:#5fa8e0">MACD</span></div>
        <div id="chart-macd" class="chart-box small"></div>
        <div class="chart-label">KD（9）　<span style="color:#f4b740">K</span>
          <span style="color:#5fa8e0">D</span></div>
        <div id="chart-kd" class="chart-box small"></div>
        <div id="chart-fallback" class="chart-fallback hidden"></div>
      </div>

      <div class="modal-section ai-section">
        <h4>AI 多代理分析（短線當沖觀點）</h4>
        <div id="ai-panel" data-code="${d.code}">
          <p class="ai-intro">由 Claude 扮演「看多研究員 ／ 看空研究員 ／ 交易員 ／ 風控」四個角色，
            綜合解讀本檔個股的技術面、基本面與消息面，給出短線操作判斷。</p>
          <button id="ai-run-btn" class="retry-btn">啟動 AI 分析</button>
        </div>
      </div>

      <div class="modal-section ai-section">
        <h4>深度投資分析（華爾街分析師觀點）</h4>
        <div id="deep-panel" data-code="${d.code}">
          <p class="ai-intro">由 Claude 以華爾街資深分析師角度，深度解讀商業模式、護城河、
            財務體質、估值、成長潛力與多空情境，給出買入／持有／避免建議（長期基本面）。
            分析較深入，約需 1–3 分鐘。</p>
          <button id="deep-run-btn" class="retry-btn">啟動深度分析</button>
        </div>
      </div>

      <div class="modal-section">
        <h4>綜合評分</h4>
        <div class="kv-grid">
          ${kv("技術面", num(sc.technical, 0))}
          ${kv("基本面", num(sc.fundamental, 0))}
          ${kv("消息面", num(sc.news, 0))}
          ${kv("當沖評分", num(sc.day, 0))}
          ${kv("隔日沖評分", num(sc.overnight, 0))}
        </div>
      </div>

      <div class="modal-section">
        <h4>技術指標</h4>
        <div class="kv-grid">
          ${kv("MA5", num(ind.ma5))}
          ${kv("MA10", num(ind.ma10))}
          ${kv("MA20", num(ind.ma20))}
          ${kv("MA60", num(ind.ma60))}
          ${kv("RSI(14)", num(ind.rsi14, 0))}
          ${kv("KD", ind.kd ? num(ind.kd.k, 0) + " / " + num(ind.kd.d, 0) : "—")}
          ${kv("MACD柱", ind.macd ? num(ind.macd.hist, 3) : "—")}
          ${kv("量能比", num(ind.vol_ratio) + " 倍")}
          ${kv("ATR(14)", num(ind.atr14))}
          ${kv("乖離率(10日)", ind.bias10 === null ? "—" : num(ind.bias10, 1) + "%")}
          ${kv("威廉指標 %R", num(ind.williams_r, 0))}
          ${kv("CCI(20)", num(ind.cci20, 0))}
          ${kv("ADX 趨勢強度", ind.dmi ? num(ind.dmi.adx, 0) : "—")}
          ${kv("+DI / -DI", ind.dmi ? num(ind.dmi.plus_di, 0) + " / " + num(ind.dmi.minus_di, 0) : "—")}
          ${kv("OBV 量能潮", obvText)}
          ${kv("週線中期趨勢", d.weekly ? esc(d.weekly.trend) : "—")}
        </div>
      </div>

      <div class="modal-section">
        <h4>當沖樞紐點參考價（Pivot Points）</h4>
        <div class="kv-grid">
          ${kv("壓力 R2", fmtPrice(lv.pivot.r2))}
          ${kv("壓力 R1", fmtPrice(lv.pivot.r1))}
          ${kv("樞紐 P", fmtPrice(lv.pivot.pivot))}
          ${kv("支撐 S1", fmtPrice(lv.pivot.s1))}
          ${kv("支撐 S2", fmtPrice(lv.pivot.s2))}
        </div>
        <div class="plan-times">
          <div>盤中站上 <b>R1</b> 偏多、續攻看 <b>R2</b>；跌破 <b>S1</b> 偏空、續弱看 <b>S2</b>；於 <b>P</b> 附近多空易拉鋸。</div>
        </div>
      </div>

      <div class="modal-section">
        <h4>波段支撐壓力 ・ 當日K線型態</h4>
        <div class="kv-grid">
          ${kv("20 日壓力", fmtPrice(lv.support_resistance.resistance))}
          ${kv("20 日支撐", fmtPrice(lv.support_resistance.support))}
          ${kv("當日K線", d.pattern.text)}
        </div>
      </div>

      ${
        d.backtest && d.backtest.trades
          ? `<div class="modal-section">
        <h4>歷史回測（隔日沖訊號，近一年）</h4>
        <div class="kv-grid">
          ${kv("符合進場次數", d.backtest.trades + " 次")}
          ${kv("隔日收紅勝率", d.backtest.win_rate + "%")}
          ${kv("平均報酬", d.backtest.avg_return + "%")}
          ${kv("最佳 / 最差", d.backtest.best + "% / " + d.backtest.worst + "%")}
        </div>
        <div class="plan-times"><div>回測規則：收盤站上 20MA、MACD 紅柱翻揚、RSI 50–78 時進場，隔日收盤出場 —— 僅供驗證參考。</div></div>
      </div>`
          : ""
      }

      ${
        inst
          ? `<div class="modal-section">
        <h4>三大法人買賣超（最近交易日）</h4>
        <div class="kv-grid">
          ${kv("外資", instCell("foreign_lots"))}
          ${kv("投信", instCell("trust_lots"))}
          ${kv("自營商", instCell("dealer_lots"))}
          ${kv("三大法人合計", instCell("inst_lots"))}
        </div>
        <div class="plan-times"><div>法人（外資／投信）站在買方，當沖偏多較有撐；
          投信買超對短線點火尤其關鍵。</div></div>
      </div>`
          : ""
      }

      <div class="modal-section">
        <h4>基本面</h4>
        <div class="kv-grid">
          ${kv("本益比 PE", num(d.fundamentals.pe, 1))}
          ${kv("股價淨值比 PB", num(d.fundamentals.pb, 1))}
          ${kv("EPS 年增率", d.fundamentals.eps_growth === null ? "—" : d.fundamentals.eps_growth + "%")}
          ${kv("殖利率", d.fundamentals.yield_pct === null ? "—" : d.fundamentals.yield_pct + "%")}
          ${kv("ROE", d.fundamentals.roe === null ? "—" : d.fundamentals.roe + "%")}
        </div>
      </div>

      ${sigSection("技術面訊號", d.signals.technical)}
      ${sigSection("基本面訊號", d.signals.fundamental)}

      <div class="modal-section"><h4>消息面新聞</h4><div class="signals">${newsRows}</div></div>

      <div class="modal-section">
        <h4>買賣計畫</h4>
        ${planBlock(d.plans.day)}
        ${planBlock(d.plans.overnight)}
      </div>

      <p style="font-size:0.76rem;color:var(--muted);margin-top:16px">⚠️ ${d.disclaimer}</p>
    `;
  }

  async function openDetail(code, name) {
    modalBody.innerHTML = '<p class="loading">載入個股明細…</p>';
    modal.classList.remove("hidden");
    try {
      const d = await fetchJSON(
        `/api/stock/${code}?name=${encodeURIComponent(name || "")}`,
        {},
        { attempts: 3, timeoutMs: 15000 }
      );
      modalBody.innerHTML = modalHTML(d);
      renderCharts(d);
      renderIntraday(d.code);
      const aiBtn = document.getElementById("ai-run-btn");
      if (aiBtn) aiBtn.addEventListener("click", () => runAIAnalysis(d.code));
      const deepBtn = document.getElementById("deep-run-btn");
      if (deepBtn) deepBtn.addEventListener("click", () => runDeepAnalysis(d.code));
    } catch (err) {
      modalBody.innerHTML = `
        <div class="error-box">
          <p>個股明細載入失敗：${err.message}</p>
          <button id="detail-retry" class="retry-btn">重試</button>
        </div>`;
      document
        .getElementById("detail-retry")
        .addEventListener("click", () => openDetail(code, name));
    }
  }

  // ---- 技術線圖 -----------------------------------------------------------
  let chartInstances = [];

  function destroyCharts() {
    chartInstances.forEach((c) => {
      try {
        c.remove();
      } catch (e) {
        /* 忽略已銷毀的圖表 */
      }
    });
    chartInstances = [];
  }

  function renderCharts(d) {
    destroyCharts();
    const priceEl = document.getElementById("chart-price");
    const macdEl = document.getElementById("chart-macd");
    const kdEl = document.getElementById("chart-kd");
    const fallback = document.getElementById("chart-fallback");
    if (!priceEl || !macdEl || !kdEl) return;

    if (typeof LightweightCharts === "undefined") {
      fallback.textContent = "圖表元件載入失敗，請確認網路後重新整理頁面。";
      fallback.classList.remove("hidden");
      return;
    }

    try {
      const hist = d.history.slice(-90);
      const start = d.history.length - hist.length;
      const s = d.series || {};
      const slc = (arr) => (arr || []).slice(start);
      const toLine = (arr) =>
        arr
          .map((v, i) => (v == null ? null : { time: hist[i].date, value: v }))
          .filter(Boolean);

      const base = {
        layout: { background: { color: "#182433" }, textColor: "#93a4b8", fontSize: 11 },
        grid: { vertLines: { color: "#22324a" }, horzLines: { color: "#22324a" } },
        rightPriceScale: { borderColor: "#2c3e54" },
        timeScale: { borderColor: "#2c3e54", timeVisible: false },
      };
      const lineOpts = (color) => ({
        color,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      });

      // 價格圖：K 線 + 均線 + 成交量
      const pc = LightweightCharts.createChart(priceEl, {
        ...base,
        width: priceEl.clientWidth,
        height: 260,
      });
      const candle = pc.addCandlestickSeries({
        upColor: "#e23b3b",
        downColor: "#1aa251",
        borderVisible: false,
        wickUpColor: "#e23b3b",
        wickDownColor: "#1aa251",
      });
      candle.setData(
        hist.map((h) => ({
          time: h.date,
          open: h.open,
          high: h.high,
          low: h.low,
          close: h.close,
        }))
      );
      [["ma5", "#f4b740"], ["ma10", "#5fa8e0"], ["ma20", "#c98bff"]].forEach(
        ([key, color]) => {
          pc.addLineSeries(lineOpts(color)).setData(toLine(slc(s[key])));
        }
      );
      const vol = pc.addHistogramSeries({
        priceScaleId: "",
        priceFormat: { type: "volume" },
        priceLineVisible: false,
      });
      vol.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
      vol.setData(
        hist.map((h) => ({
          time: h.date,
          value: h.volume,
          color: h.close >= h.open ? "rgba(226,59,59,0.45)" : "rgba(26,162,81,0.45)",
        }))
      );

      // MACD 圖
      const mc = LightweightCharts.createChart(macdEl, {
        ...base,
        width: macdEl.clientWidth,
        height: 150,
      });
      const mh = mc.addHistogramSeries({ priceLineVisible: false });
      mh.setData(
        slc(s.macd_hist)
          .map((v, i) =>
            v == null
              ? null
              : { time: hist[i].date, value: v, color: v >= 0 ? "#e23b3b" : "#1aa251" }
          )
          .filter(Boolean)
      );
      mc.addLineSeries(lineOpts("#f4b740")).setData(toLine(slc(s.macd_dif)));
      mc.addLineSeries(lineOpts("#5fa8e0")).setData(toLine(slc(s.macd_signal)));

      // KD 圖
      const kc = LightweightCharts.createChart(kdEl, {
        ...base,
        width: kdEl.clientWidth,
        height: 150,
      });
      kc.addLineSeries(lineOpts("#f4b740")).setData(toLine(slc(s.kd_k)));
      kc.addLineSeries(lineOpts("#5fa8e0")).setData(toLine(slc(s.kd_d)));

      chartInstances = [pc, mc, kc];
      chartInstances.forEach((c) => c.timeScale().fitContent());

      // 三張圖的時間軸連動
      let syncing = false;
      chartInstances.forEach((src) => {
        src.timeScale().subscribeVisibleLogicalRangeChange((range) => {
          if (syncing || !range) return;
          syncing = true;
          chartInstances.forEach((t) => {
            if (t !== src) t.timeScale().setVisibleLogicalRange(range);
          });
          syncing = false;
        });
      });
    } catch (err) {
      console.error("技術線圖繪製失敗", err);
      destroyCharts();
      fallback.textContent = "技術線圖繪製失敗：" + err.message;
      fallback.classList.remove("hidden");
    }
  }

  // ---- 當日盤中走勢 -------------------------------------------------------
  async function renderIntraday(code) {
    const el = document.getElementById("chart-intraday");
    const fallback = document.getElementById("intraday-fallback");
    if (!el) return;
    try {
      const d = await fetchJSON(
        `/api/intraday/${code}`,
        {},
        { attempts: 2, timeoutMs: 15000 }
      );
      if (!d.points || d.points.length === 0) {
        fallback.textContent = "盤中走勢暫無資料（非交易時段或來源無回應）。";
        fallback.classList.remove("hidden");
        return;
      }
      if (typeof LightweightCharts === "undefined") return;
      const up = d.last != null && d.prev_close != null && d.last >= d.prev_close;
      const color = up ? "#e23b3b" : "#1aa251";
      const chart = LightweightCharts.createChart(el, {
        layout: { background: { color: "#182433" }, textColor: "#93a4b8", fontSize: 11 },
        grid: { vertLines: { color: "#22324a" }, horzLines: { color: "#22324a" } },
        rightPriceScale: { borderColor: "#2c3e54" },
        timeScale: { borderColor: "#2c3e54", timeVisible: true, secondsVisible: false },
        width: el.clientWidth,
        height: 160,
      });
      const series = chart.addAreaSeries({
        lineColor: color,
        topColor: up ? "rgba(226,59,59,0.28)" : "rgba(26,162,81,0.28)",
        bottomColor: "rgba(0,0,0,0)",
        lineWidth: 2,
        priceLineVisible: false,
      });
      series.setData(d.points.map((p) => ({ time: p.t, value: p.price })));
      if (d.prev_close != null) {
        series.createPriceLine({
          price: d.prev_close,
          color: "#93a4b8",
          lineWidth: 1,
          lineStyle: 2,
          title: "昨收",
        });
      }
      chart.timeScale().fitContent();
      chartInstances.push(chart);
    } catch (err) {
      fallback.textContent = "盤中走勢載入失敗：" + err.message;
      fallback.classList.remove("hidden");
    }
  }

  // ---- AI 多代理分析 ------------------------------------------------------
  function aiResultHTML(d) {
    const a = d.analysis;
    return `
      <div class="ai-result">
        <div class="badges" style="margin-bottom:10px">
          <span class="action-badge ${actionClass(a.action)}">${a.action}</span>
          <span class="score-pill">交易員信心 <b>${a.confidence}</b>%</span>
          <span class="score-pill">風險等級 <b>${esc(a.risk_level)}</b></span>
        </div>
        <p class="ai-summary">${esc(a.summary)}</p>
        <div class="ai-role bull"><h5>看多研究員</h5><p>${esc(a.bull_case)}</p></div>
        <div class="ai-role bear"><h5>看空研究員</h5><p>${esc(a.bear_case)}</p></div>
        <div class="ai-role"><h5>交易員綜合判斷</h5><p>${esc(a.trader_decision)}</p></div>
        <div class="ai-role risk"><h5>風控提醒</h5><p>${esc(a.risk_notes)}</p></div>
        <p class="ai-model">分析引擎：${esc(d.model)}　·　AI 產出僅供參考，非投資建議</p>
      </div>`;
  }

  async function runAIAnalysis(code) {
    const panel = document.getElementById("ai-panel");
    if (!panel) return;
    panel.innerHTML =
      '<p class="loading">AI 多代理分析中…<br><small>Claude 正在進行多空辯論並評估風險，約需 15–45 秒</small></p>';
    try {
      const d = await fetchJSON(
        `/api/ai-analysis/${code}`,
        {},
        { attempts: 1, timeoutMs: 120000 }
      );
      if (!d.available) {
        panel.innerHTML = `<div class="ai-unavailable"><p>${esc(d.message)}</p></div>`;
        return;
      }
      panel.innerHTML = aiResultHTML(d);
    } catch (err) {
      panel.innerHTML = `
        <div class="ai-unavailable">
          <p>AI 分析失敗：${esc(err.message)}</p>
          <button id="ai-retry" class="retry-btn">重試</button>
        </div>`;
      document
        .getElementById("ai-retry")
        .addEventListener("click", () => runAIAnalysis(code));
    }
  }

  // ---- 深度投資分析 -------------------------------------------------------
  function recClass(rec) {
    if (rec === "買入") return "act-buy";
    if (rec === "持有") return "act-hold";
    return "act-avoid";
  }

  function deepResultHTML(d) {
    const a = d.analysis;
    const block = (title, text) =>
      `<div class="ai-role"><h5>${title}</h5><p>${esc(text)}</p></div>`;
    return `
      <div class="ai-result">
        <div class="badges" style="margin-bottom:10px">
          <span class="action-badge ${recClass(a.recommendation)}">${esc(a.recommendation)}</span>
          <span class="score-pill">護城河 <b>${a.moat_score}</b>／10</span>
          <span class="score-pill">${esc(a.valuation_verdict)}</span>
          <span class="score-pill">${esc(a.financial_trend)}</span>
        </div>
        <p class="ai-summary">${esc(a.summary)}</p>
        ${block("商業模式與護城河", a.business_moat)}
        ${block("產業趨勢", a.industry_trend)}
        ${block("財務體質（近 5 年）", a.financial_health)}
        ${block("估值分析", a.valuation)}
        ${block("未來成長潛力", a.growth_potential)}
        <div class="ai-role bull"><h5>多頭觀點</h5><p>${esc(a.bull_case)}</p></div>
        <div class="ai-role bear"><h5>空頭觀點</h5><p>${esc(a.bear_case)}</p></div>
        ${block("關鍵催化因素", a.key_catalysts)}
        <div class="ai-role risk"><h5>主要風險</h5><p>${esc(a.key_risks)}</p></div>
        ${block("短期展望（1 年內）", a.outlook_short)}
        ${block("長期展望（5 年以上）", a.outlook_long)}
        ${block("結論", a.conclusion)}
        <p class="ai-model">分析引擎：${esc(d.model)}　·　財務數字為 AI 依公開資訊推估、
          可能非最新，請以公司財報為準；非投資建議</p>
      </div>`;
  }

  async function runDeepAnalysis(code) {
    const panel = document.getElementById("deep-panel");
    if (!panel) return;
    panel.innerHTML =
      '<p class="loading">深度分析中…<br><small>Claude 正在進行機構等級研究，約需 1–3 分鐘，請勿關閉頁面</small></p>';
    try {
      const d = await fetchJSON(
        `/api/deep-analysis/${code}`,
        {},
        { attempts: 1, timeoutMs: 220000 }
      );
      if (!d.available) {
        panel.innerHTML = `<div class="ai-unavailable"><p>${esc(d.message)}</p></div>`;
        return;
      }
      panel.innerHTML = deepResultHTML(d);
    } catch (err) {
      panel.innerHTML = `
        <div class="ai-unavailable">
          <p>深度分析失敗：${esc(err.message)}</p>
          <button id="deep-retry" class="retry-btn">重試</button>
        </div>`;
      document
        .getElementById("deep-retry")
        .addEventListener("click", () => runDeepAnalysis(code));
    }
  }

  function closeModal() {
    modal.classList.add("hidden");
    destroyCharts();
  }

  // ---- 事件綁定 -----------------------------------------------------------
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const tab = btn.dataset.tab;
      currentTab = tab;
      document.getElementById("tab-screener").classList.toggle("hidden", tab !== "screener");
      document.getElementById("tab-categories").classList.toggle("hidden", tab !== "categories");
      document.getElementById("tab-premarket").classList.toggle("hidden", tab !== "premarket");
      document.getElementById("tab-watchlist").classList.toggle("hidden", tab !== "watchlist");
      if (tab === "categories" && !categoriesLoaded) loadCategories();
      if (tab === "premarket" && !picksLoaded) loadPicks();
      if (tab === "watchlist") renderWatchlist();
    });
  });

  document.querySelectorAll(".sort-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".sort-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentSort = btn.dataset.sort;
      renderScreener();
    });
  });

  document.getElementById("refresh-btn").addEventListener("click", async () => {
    const btn = document.getElementById("refresh-btn");
    btn.disabled = true;
    try {
      await fetchJSON("/api/refresh", { method: "POST" }, { attempts: 2, timeoutMs: 25000 });
    } catch (e) {
      console.warn("refresh 失敗，仍重新掃描", e);
    }
    categoriesLoaded = false;
    picksLoaded = false;
    await loadScreener();
    if (currentTab === "premarket") loadPicks();
    btn.disabled = false;
  });

  document.getElementById("pm-run-btn").addEventListener("click", loadPremarket);

  document.getElementById("wl-add-btn").addEventListener("click", async () => {
    const input = document.getElementById("wl-input");
    const codes = input.value
      .split(/[,，\s]+/)
      .map((c) => c.trim())
      .filter((c) => /^\d{4}$/.test(c));
    const list = getWatchlist();
    codes.forEach((c) => {
      if (!list.includes(c)) list.push(c);
    });
    setWatchlistInMemory(list);
    await persistWatchlist();
    input.value = "";
    renderWatchlist();
    renderScreener();
  });

  document.getElementById("modal-close").addEventListener("click", closeModal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeModal();
  });

  // ---- 登入 / 註冊 modal --------------------------------------------------
  const authModal = document.getElementById("auth-modal");
  const authTitle = document.getElementById("auth-title");
  const authEmail = document.getElementById("auth-email");
  const authPassword = document.getElementById("auth-password");
  const authErr = document.getElementById("auth-err");
  const authSubmit = document.getElementById("auth-submit");
  const authSwitchLink = document.getElementById("auth-switch-link");
  const accountStatus = document.getElementById("account-status");
  const accountBtn = document.getElementById("account-btn");
  let authMode = "signin"; // 或 "signup"

  function updateAuthMode() {
    if (authMode === "signin") {
      authTitle.textContent = "登入";
      authSubmit.textContent = "登入";
      authSwitchLink.textContent = "沒有帳號?註冊一個";
    } else {
      authTitle.textContent = "註冊";
      authSubmit.textContent = "建立帳號";
      authSwitchLink.textContent = "已經有帳號?改成登入";
    }
    authErr.textContent = "";
  }
  function openAuthModal() {
    authMode = "signin";
    updateAuthMode();
    authEmail.value = "";
    authPassword.value = "";
    authErr.textContent = "";
    authModal.classList.remove("hidden");
  }
  function closeAuthModal() {
    authModal.classList.add("hidden");
  }
  authSwitchLink.addEventListener("click", (e) => {
    e.preventDefault();
    authMode = authMode === "signin" ? "signup" : "signin";
    updateAuthMode();
  });
  document.getElementById("auth-close").addEventListener("click", closeAuthModal);
  authModal.addEventListener("click", (e) => {
    if (e.target === authModal) closeAuthModal();
  });

  authSubmit.addEventListener("click", async () => {
    if (!window.SB) {
      authErr.textContent = "雲端服務未載入，請重新整理頁面";
      return;
    }
    const email = authEmail.value.trim();
    const password = authPassword.value;
    if (!email || password.length < 6) {
      authErr.textContent = "請輸入 Email,密碼至少 6 碼";
      return;
    }
    authSubmit.disabled = true;
    authErr.textContent = "";
    try {
      if (authMode === "signup") {
        await window.SB.signUp(email, password);
        // 註冊完直接登入（若已關閉 email confirm）
        try {
          await window.SB.signIn(email, password);
        } catch (_) {
          authErr.textContent = "註冊成功,請至信箱完成驗證後再登入";
          return;
        }
      } else {
        await window.SB.signIn(email, password);
      }
      closeAuthModal();
    } catch (e) {
      authErr.textContent = (e && e.message) || "操作失敗";
    } finally {
      authSubmit.disabled = false;
    }
  });

  accountBtn.addEventListener("click", async () => {
    if (isLoggedIn()) {
      if (confirm("確定要登出?")) {
        await window.SB.signOut();
      }
    } else {
      openAuthModal();
    }
  });

  function updateAccountBar(user) {
    if (user) {
      const label = user.email || "已登入";
      accountStatus.textContent = label;
      accountStatus.classList.add("on");
      accountBtn.textContent = "登出";
    } else {
      accountStatus.textContent = "未登入（口袋名單僅存本機）";
      accountStatus.classList.remove("on");
      accountBtn.textContent = "登入 / 註冊";
    }
  }

  let lastAuthUserId; // undefined = 尚未載入過
  if (window.SB) {
    window.SB.onAuth(async (user) => {
      updateAccountBar(user);
      const uid = user ? user.id : null;
      if (lastAuthUserId !== undefined && uid === lastAuthUserId) return;
      lastAuthUserId = uid;
      if (user) {
        await migrateLocalToCloud();
      }
      await loadWatchlistFromBackend();
      if (currentTab === "watchlist") renderWatchlist();
      if (screenerData.length) renderScreener();
    });
  } else {
    updateAccountBar(null);
    loadWatchlistFromBackend();
  }

  // ---- 初始化 -------------------------------------------------------------
  loadScreener();
});
