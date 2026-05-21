document.addEventListener("DOMContentLoaded", () => {
  const listEl = document.getElementById("list");
  const listTitle = document.getElementById("list-title");
  const disclaimerEl = document.getElementById("disclaimer");
  const dataSourceEl = document.getElementById("data-source");
  const modal = document.getElementById("modal");
  const modalBody = document.getElementById("modal-body");

  let screenerData = [];
  let currentSort = "score";
  let categoriesLoaded = false;

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
    if (tag === "小型爆發" || tag === "投信買超") return "tag-gold";
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
            ${inst}
          </div>
        </div>
        <div class="sscore">
          <div class="sscore-num" style="color:${scoreColor(s.score)}">${Math.round(s.score)}</div>
          <div class="sscore-lbl">當沖分</div>
        </div>
      </div>`;
  }

  function renderScreener() {
    const sorted = [...screenerData].sort(
      (a, b) => (b[currentSort] ?? 0) - (a[currentSort] ?? 0)
    );
    listEl.innerHTML = sorted.map((s, i) => screenerRowHTML(s, i + 1)).join("");
    listEl.querySelectorAll(".srow").forEach((row) => {
      row.addEventListener("click", () =>
        openDetail(row.dataset.code, row.dataset.name)
      );
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
      '<p class="loading">掃描全市場中…<br><small>免費主機若處於休眠，首次喚醒約需 30–60 秒，請稍候</small></p>';
    const onAttempt = (i, total) => {
      if (i > 1) {
        listEl.innerHTML = `<p class="loading">伺服器喚醒中，重試 ${i}/${total}…<br><small>請勿關閉頁面</small></p>`;
      }
    };
    try {
      const data = await fetchJSON(
        "/api/screener?limit=300",
        {},
        { onAttempt, timeoutMs: 45000 }
      );
      disclaimerEl.textContent = "⚠️ " + data.disclaimer;
      dataSourceEl.textContent = "資料來源：" + data.data_source;
      screenerData = data.stocks || [];
      listTitle.textContent = `當沖適合度排行（顯示 ${screenerData.length} 檔，掃描 ${data.total} 檔）`;

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
    destroyCharts();
  }

  // ---- 事件綁定 -----------------------------------------------------------
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const tab = btn.dataset.tab;
      document.getElementById("tab-screener").classList.toggle("hidden", tab !== "screener");
      document.getElementById("tab-categories").classList.toggle("hidden", tab !== "categories");
      if (tab === "categories" && !categoriesLoaded) loadCategories();
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
    await loadScreener();
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
  loadScreener();
});
