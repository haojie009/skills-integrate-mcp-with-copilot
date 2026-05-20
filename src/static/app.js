document.addEventListener("DOMContentLoaded", () => {
  const listEl = document.getElementById("list");
  const topPickEl = document.getElementById("top-pick");
  const listTitle = document.getElementById("list-title");
  const disclaimerEl = document.getElementById("disclaimer");
  const dataSourceEl = document.getElementById("data-source");
  const asOfEl = document.getElementById("as-of");
  const modal = document.getElementById("modal");
  const modalBody = document.getElementById("modal-body");

  let strategy = "day";

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

  // ---- 卡片渲染 -----------------------------------------------------------
  function cardHTML(item) {
    const s = item.scores;
    const p = item.plan;
    const sigs = item.top_signals.map(signalRow).join("");
    return `
      <div class="card" data-code="${item.code}">
        <div class="card-head">
          <span class="rank">#${item.rank}</span>
          <span class="stock-name">${item.name}</span>
          <span class="stock-code">${item.code}</span>
          <span class="sector">${item.sector}</span>
          <span class="price">
            <span class="last">${fmtPrice(item.last_close)}</span>
            <span class="chg ${dirClass(item.change_pct)}">${fmtPct(item.change_pct)}</span>
          </span>
        </div>
        <div class="badges" style="margin-top:10px">
          <span class="action-badge ${actionClass(p.action)}">${p.action}</span>
          <span class="score-pill">${item.strategy_label}評分 <b>${item.score.toFixed(0)}</b>／100</span>
        </div>
        <div class="subscores">
          ${bar("技術面", s.technical)}
          ${bar("基本面", s.fundamental)}
          ${bar("消息面", s.news)}
        </div>
        <div class="plan-grid">
          <div class="plan-item"><div class="pi-lbl">進場區間</div><div class="pi-val">${fmtPrice(p.entry_low)} ~ ${fmtPrice(p.entry_high)}</div></div>
          <div class="plan-item"><div class="pi-lbl">停利目標</div><div class="pi-val up">${fmtPrice(p.target)}（+${p.target_pct}%）</div></div>
          <div class="plan-item"><div class="pi-lbl">停損價</div><div class="pi-val down">${fmtPrice(p.stop)}（-${p.stop_pct}%）</div></div>
          <div class="plan-item"><div class="pi-lbl">風險報酬比</div><div class="pi-val">${p.risk_reward ? "1 : " + p.risk_reward : "—"}</div></div>
        </div>
        <div class="plan-times">
          <div><b>進場時機：</b>${p.entry_time}</div>
          <div><b>出場時機：</b>${p.exit_time}</div>
        </div>
        <div class="signals">${sigs || '<div class="sig">無明顯訊號</div>'}</div>
      </div>`;
  }

  function topPickHTML(item) {
    const p = item.plan;
    return `
      <span class="tp-tag">🏆 ${item.strategy_label}首選</span>
      <h2>${item.name} <span class="stock-code">${item.code}</span>
        <span class="action-badge ${actionClass(p.action)}">${p.action}</span></h2>
      <div class="tp-grid">
        <div>
          <div class="pi-lbl">最新收盤</div>
          <div class="pi-val">${fmtPrice(item.last_close)}
            <span class="chg ${dirClass(item.change_pct)}">${fmtPct(item.change_pct)}</span></div>
          <div class="pi-lbl" style="margin-top:8px">綜合評分</div>
          <div class="pi-val" style="color:var(--gold)">${item.score.toFixed(0)} / 100</div>
        </div>
        <div>
          <div class="pi-lbl">建議進場 ${fmtPrice(p.entry_low)} ~ ${fmtPrice(p.entry_high)}</div>
          <div class="pi-val up">停利 ${fmtPrice(p.target)}　<span class="down" style="font-weight:600">停損 ${fmtPrice(p.stop)}</span></div>
          <div class="plan-times">
            <div><b>進：</b>${p.entry_time}</div>
            <div><b>出：</b>${p.exit_time}</div>
          </div>
        </div>
      </div>`;
  }

  // ---- 載入排行 -----------------------------------------------------------
  function renderError(message) {
    disclaimerEl.textContent = "⚠️ 本工具僅供教學研究，非投資建議。";
    listEl.innerHTML = `
      <div class="error-box">
        <p>${message}</p>
        <button id="retry-btn" class="retry-btn">重新載入</button>
      </div>`;
    document.getElementById("retry-btn").addEventListener("click", loadRecommendations);
  }

  async function loadRecommendations() {
    topPickEl.classList.add("hidden");
    listEl.innerHTML =
      '<p class="loading">分析中…<br><small>免費主機若處於休眠，首次喚醒約需 30–60 秒，請稍候</small></p>';
    const onAttempt = (i, total) => {
      if (i > 1) {
        listEl.innerHTML = `<p class="loading">伺服器喚醒中，重試 ${i}/${total}…<br><small>請勿關閉頁面</small></p>`;
      }
    };
    try {
      const data = await fetchJSON(
        `/api/recommendations?strategy=${strategy}`,
        {},
        { onAttempt }
      );

      disclaimerEl.textContent = "⚠️ " + data.disclaimer;
      dataSourceEl.textContent = "資料來源：" + data.data_source;
      asOfEl.textContent = "資料截至：" + data.as_of;
      listTitle.textContent = `${data.strategy_name}建議排行（共 ${data.recommendations.length} 檔）`;

      const items = data.recommendations.map((r) => ({
        ...r,
        strategy_label: data.strategy_name,
      }));

      if (items.length) {
        topPickEl.innerHTML = topPickHTML(items[0]);
        topPickEl.classList.remove("hidden");
        topPickEl.onclick = () => openDetail(items[0].code);
      }

      listEl.innerHTML = items.map(cardHTML).join("");
      listEl.querySelectorAll(".card").forEach((card) => {
        card.addEventListener("click", () => openDetail(card.dataset.code));
      });
    } catch (err) {
      renderError(
        `資料載入失敗：${err.message}。免費主機可能仍在喚醒，請按下方按鈕重試。`
      );
      console.error(err);
    }
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
    const num = (v, dp = 2) => (v === null || v === undefined ? "—" : Number(v).toFixed(dp));
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
      <h2>${d.name} <span class="stock-code">${d.code}</span>
        <span class="sector">${d.sector}</span></h2>
      <div class="pi-val" style="margin-top:4px">收盤 ${fmtPrice(d.last_close)}
        <span class="chg ${dirClass(d.change_pct)}">${fmtPct(d.change_pct)}</span></div>

      <div class="modal-section ai-section">
        <h4>AI 多代理分析</h4>
        <div id="ai-panel" data-code="${d.code}">
          <p class="ai-intro">由 Claude 扮演「看多研究員 ／ 看空研究員 ／ 交易員 ／ 風控」四個角色，
            綜合解讀本檔個股的技術面、基本面與消息面，給出短線操作判斷。</p>
          <button id="ai-run-btn" class="retry-btn">啟動 AI 分析</button>
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

  async function openDetail(code) {
    modalBody.innerHTML = '<p class="loading">載入個股明細…</p>';
    modal.classList.remove("hidden");
    try {
      const d = await fetchJSON(
        `/api/stock/${code}`,
        {},
        { attempts: 3, timeoutMs: 15000 }
      );
      modalBody.innerHTML = modalHTML(d);
      const aiBtn = document.getElementById("ai-run-btn");
      if (aiBtn) aiBtn.addEventListener("click", () => runAIAnalysis(d.code));
    } catch (err) {
      modalBody.innerHTML = `
        <div class="error-box">
          <p>個股明細載入失敗：${err.message}</p>
          <button id="detail-retry" class="retry-btn">重試</button>
        </div>`;
      document
        .getElementById("detail-retry")
        .addEventListener("click", () => openDetail(code));
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

  function closeModal() {
    modal.classList.add("hidden");
  }

  // ---- 事件綁定 -----------------------------------------------------------
  document.querySelectorAll(".strategy-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".strategy-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      strategy = btn.dataset.strategy;
      loadRecommendations();
    });
  });

  document.getElementById("refresh-btn").addEventListener("click", async () => {
    const btn = document.getElementById("refresh-btn");
    btn.disabled = true;
    try {
      await fetchJSON("/api/refresh", { method: "POST" }, { attempts: 2, timeoutMs: 25000 });
    } catch (e) {
      console.warn("refresh 失敗，仍重新載入排行", e);
    }
    await loadRecommendations();
    btn.disabled = false;
  });

  document.getElementById("modal-close").addEventListener("click", closeModal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeModal();
  });

  // ---- 初始化 -------------------------------------------------------------
  loadRecommendations();
});
