"""
台股當沖／隔日沖分析引擎

提供三大面向的分析：
  - 技術面：均線、RSI、KD、MACD、布林通道、量能、ATR
  - 基本面：本益比、股價淨值比、EPS 成長、殖利率、ROE
  - 消息面：以關鍵字對新聞標題做情緒評分

並依當沖（day）與隔日沖（overnight）兩種策略，計算綜合評分與買賣計畫。

⚠️ 本檔所有運算僅供教學與研究，非投資建議。
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 技術指標（純 Python，不依賴 numpy / pandas）
# ---------------------------------------------------------------------------


def sma(values, period):
    """簡單移動平均"""
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _ema_series(values, period):
    k = 2 / (period + 1)
    ema = values[0]
    out = [ema]
    for v in values[1:]:
        ema = v * k + ema * (1 - k)
        out.append(ema)
    return out


def rsi(closes, period=14):
    """相對強弱指標 (Wilder 平滑法)"""
    if len(closes) <= period:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def macd(closes, fast=12, slow=26, signal=9):
    """MACD：回傳 DIF、MACD 訊號線與柱狀體（含前一日柱狀體）"""
    if len(closes) < slow + signal:
        return None
    ema_fast = _ema_series(closes, fast)
    ema_slow = _ema_series(closes, slow)
    dif = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = _ema_series(dif, signal)
    hist = [d - s for d, s in zip(dif, signal_line)]
    return {
        "dif": dif[-1],
        "signal": signal_line[-1],
        "hist": hist[-1],
        "hist_prev": hist[-2],
    }


def kd(highs, lows, closes, period=9):
    """KD 隨機指標 (9 日)"""
    if len(closes) < period:
        return None
    k, d = 50.0, 50.0
    for i in range(period - 1, len(closes)):
        window_high = max(highs[i - period + 1: i + 1])
        window_low = min(lows[i - period + 1: i + 1])
        if window_high == window_low:
            rsv = 50.0
        else:
            rsv = (closes[i] - window_low) / (window_high - window_low) * 100
        k = k * 2 / 3 + rsv / 3
        d = d * 2 / 3 + k / 3
    return {"k": k, "d": d}


def atr(highs, lows, closes, period=14):
    """平均真實區間 — 用來衡量波動度"""
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    return sum(trs[-period:]) / period


def bollinger(closes, period=20, mult=2.0):
    """布林通道"""
    if len(closes) < period:
        return None
    window = closes[-period:]
    mid = sum(window) / period
    variance = sum((x - mid) ** 2 for x in window) / period
    sd = variance ** 0.5
    return {"mid": mid, "upper": mid + mult * sd, "lower": mid - mult * sd}


# ---------------------------------------------------------------------------
# 消息面：關鍵字情緒分析
# ---------------------------------------------------------------------------

_POSITIVE_WORDS = [
    "創高", "創新高", "新高", "法說", "樂觀", "調升", "看好", "利多", "成長",
    "突破", "大漲", "漲停", "加碼", "買超", "旺季", "報價調漲", "獲利成長",
    "營收創高", "接單", "訂單滿載", "擴產", "升評", "目標價調高",
]
_NEGATIVE_WORDS = [
    "下修", "利空", "認賠", "賣超", "衰退", "訴訟", "跌停", "示警", "虧損",
    "砍單", "庫存調整", "疲弱", "降評", "不如預期", "殺盤", "重挫", "減產",
    "出貨下滑", "目標價調降", "違約",
]


def score_headline(title):
    """單一新聞標題情緒分數：正向 +1／負向 -1（可累加）"""
    score = 0
    for w in _POSITIVE_WORDS:
        if w in title:
            score += 1
    for w in _NEGATIVE_WORDS:
        if w in title:
            score -= 1
    return score


# ---------------------------------------------------------------------------
# 三大面向評分（皆為 0~100）
# ---------------------------------------------------------------------------


def _clamp(value, low=0.0, high=100.0):
    return max(low, min(high, value))


def technical_analysis(history):
    """依價量歷史計算技術面評分與指標明細。

    history: list[dict]，每筆含 open/high/low/close/volume，時間由舊到新。
    """
    closes = [d["close"] for d in history]
    highs = [d["high"] for d in history]
    lows = [d["low"] for d in history]
    volumes = [d["volume"] for d in history]
    last = closes[-1]

    ma5 = sma(closes, 5)
    ma10 = sma(closes, 10)
    ma20 = sma(closes, 20)
    ma60 = sma(closes, 60)
    rsi14 = rsi(closes, 14)
    macd_v = macd(closes)
    kd_v = kd(highs, lows, closes)
    atr14 = atr(highs, lows, closes)
    boll = bollinger(closes)
    vol_ma5 = sma(volumes, 5) or volumes[-1]
    vol_ratio = volumes[-1] / vol_ma5 if vol_ma5 else 1.0
    change_pct = (last / closes[-2] - 1) * 100 if len(closes) > 1 else 0.0

    score = 50.0
    signals = []

    # 均線多空排列
    if ma20 and last > ma20:
        score += 10
        signals.append(("多", f"股價站上 20 日均線（{ma20:.1f}）"))
    elif ma20:
        score -= 10
        signals.append(("空", f"股價跌破 20 日均線（{ma20:.1f}）"))
    if ma5 and ma20 and ma5 > ma20:
        score += 10
        signals.append(("多", "5 日均線在 20 日均線之上，短線多頭排列"))
    if ma20 and ma60 and ma20 > ma60:
        score += 5
        signals.append(("多", "中期均線呈多頭排列"))
    elif ma20 and ma60:
        score -= 5

    # RSI
    if rsi14 is not None:
        if 50 <= rsi14 <= 70:
            score += 10
            signals.append(("多", f"RSI {rsi14:.0f}，多方力道健康"))
        elif rsi14 > 80:
            score -= 10
            signals.append(("空", f"RSI {rsi14:.0f} 過熱，追高風險大"))
        elif rsi14 < 30:
            score += 4
            signals.append(("多", f"RSI {rsi14:.0f} 進入超賣，留意反彈"))

    # MACD
    if macd_v:
        if macd_v["hist"] > 0 and macd_v["hist"] > macd_v["hist_prev"]:
            score += 10
            signals.append(("多", "MACD 紅柱放大，動能增強"))
        elif macd_v["hist"] < 0:
            score -= 8
            signals.append(("空", "MACD 綠柱，動能偏弱"))

    # KD
    if kd_v:
        if kd_v["k"] > kd_v["d"] and kd_v["k"] < 80:
            score += 8
            signals.append(("多", f"KD 黃金交叉（K{kd_v['k']:.0f}/D{kd_v['d']:.0f}）"))
        elif kd_v["k"] < kd_v["d"]:
            score -= 8
            signals.append(("空", f"KD 死亡交叉（K{kd_v['k']:.0f}/D{kd_v['d']:.0f}）"))
        if kd_v["k"] > 88:
            score -= 5

    # 量能
    if vol_ratio > 1.5 and change_pct > 0:
        score += 10
        signals.append(("多", f"爆量上漲（量能 {vol_ratio:.1f} 倍）"))
    elif vol_ratio > 1.5 and change_pct < 0:
        score -= 8
        signals.append(("空", f"爆量下跌（量能 {vol_ratio:.1f} 倍）"))
    elif vol_ratio < 0.6:
        signals.append(("中", "量能偏低，觀望氣氛濃"))

    # 布林通道位置
    if boll:
        if last >= boll["upper"]:
            score -= 4
            signals.append(("空", "觸及布林上軌，短線乖離偏大"))
        elif last <= boll["lower"]:
            score += 4
            signals.append(("多", "靠近布林下軌，留意跌深反彈"))

    volatility_pct = (atr14 / last) if (atr14 and last) else 0.02

    return {
        "score": round(_clamp(score), 1),
        "signals": signals,
        "indicators": {
            "ma5": _r(ma5), "ma10": _r(ma10), "ma20": _r(ma20), "ma60": _r(ma60),
            "rsi14": _r(rsi14), "kd": {k: _r(v) for k, v in kd_v.items()} if kd_v else None,
            "macd": {k: _r(v, 3) for k, v in macd_v.items()} if macd_v else None,
            "atr14": _r(atr14), "vol_ratio": _r(vol_ratio),
            "change_pct": _r(change_pct),
            "bollinger": {k: _r(v) for k, v in boll.items()} if boll else None,
        },
        "volatility_pct": volatility_pct,
    }


def fundamental_analysis(fundamentals):
    """基本面評分。fundamentals 含 pe / pb / eps_growth / yield_pct / roe。"""
    score = 50.0
    signals = []
    pe = fundamentals.get("pe")
    pb = fundamentals.get("pb")
    growth = fundamentals.get("eps_growth")
    dividend = fundamentals.get("yield_pct")
    roe = fundamentals.get("roe")

    if pe is not None:
        if pe < 15:
            score += 15
            signals.append(("多", f"本益比 {pe:.1f} 偏低，評價有吸引力"))
        elif pe <= 25:
            score += 5
        elif pe > 40:
            score -= 10
            signals.append(("空", f"本益比 {pe:.1f} 偏高，評價已不便宜"))

    if pb is not None:
        if pb < 2:
            score += 10
            signals.append(("多", f"股價淨值比 {pb:.1f}，相對保守"))
        elif pb > 4:
            score -= 5

    if growth is not None:
        if growth > 20:
            score += 15
            signals.append(("多", f"EPS 年增 {growth:.0f}%，成長強勁"))
        elif growth >= 5:
            score += 8
        elif growth < 0:
            score -= 12
            signals.append(("空", f"EPS 年減 {abs(growth):.0f}%，獲利衰退"))

    if dividend is not None:
        if dividend > 4:
            score += 8
            signals.append(("多", f"殖利率 {dividend:.1f}%，現金股利優於大盤"))
        elif dividend < 1:
            score -= 3

    if roe is not None:
        if roe > 15:
            score += 8
            signals.append(("多", f"ROE {roe:.0f}%，股東權益報酬率亮眼"))
        elif roe < 5:
            score -= 6
            signals.append(("空", f"ROE 僅 {roe:.0f}%，獲利效率偏弱"))

    return {"score": round(_clamp(score), 1), "signals": signals}


def news_analysis(news):
    """消息面評分。news: list[dict]，每筆含 title / source / date。"""
    if not news:
        return {"score": 50.0, "signals": [("中", "近期無明顯新聞題材")], "scored_news": []}

    scored = []
    total = 0
    for item in news:
        s = score_headline(item["title"])
        total += s
        scored.append({**item, "sentiment": s})

    # 每則新聞最多正負各貢獻 8 分
    score = _clamp(50 + total * 8)
    signals = []
    for n in scored:
        if n["sentiment"] > 0:
            signals.append(("多", f"利多：{n['title']}"))
        elif n["sentiment"] < 0:
            signals.append(("空", f"利空：{n['title']}"))
    if not signals:
        signals.append(("中", "新聞情緒中性，無明確方向"))

    return {"score": round(score, 1), "signals": signals, "scored_news": scored}


# ---------------------------------------------------------------------------
# 綜合評分與買賣計畫
# ---------------------------------------------------------------------------

# 各策略對三大面向的權重（當沖更看重技術與消息題材）
STRATEGY_WEIGHTS = {
    "day": {"tech": 0.50, "news": 0.35, "fund": 0.15},
    "overnight": {"tech": 0.45, "news": 0.35, "fund": 0.20},
}


def _tick_size(price):
    if price < 10:
        return 0.01
    if price < 50:
        return 0.05
    if price < 100:
        return 0.1
    if price < 500:
        return 0.5
    if price < 1000:
        return 1.0
    return 5.0


def round_tick(price):
    """將價格四捨五入到台股最接近的升降單位"""
    tick = _tick_size(price)
    return round(round(price / tick) * tick, 2)


def _action_label(score):
    if score >= 72:
        return "強烈買進"
    if score >= 60:
        return "買進"
    if score >= 46:
        return "觀望"
    return "偏空避開"


def _clamp_pct(value, low, high):
    return max(low, min(high, value))


def build_trade_plan(strategy, score, last_close, volatility_pct):
    """依策略與評分產生進出場價位與時間計畫。"""
    action = _action_label(score)
    actionable = score >= 60

    if strategy == "day":
        # 當沖：當日了結，停利停損較緊
        target_pct = _clamp_pct(volatility_pct * 0.9, 0.012, 0.04)
        stop_pct = _clamp_pct(volatility_pct * 0.6, 0.008, 0.02)
        entry_low = round_tick(last_close * 0.997)
        entry_high = round_tick(last_close * 1.005)
        entry_time = "09:00–09:35　開盤後觀察量價，回測不破當日開盤價／前日收盤即分批進場"
        exit_time = "13:00 前分批停利；最晚 13:25 強制平倉，當沖不留倉"
        holding = "當日沖銷（T 日買、T 日賣）"
    else:
        # 隔日沖：尾盤進、隔日早盤出
        target_pct = _clamp_pct(volatility_pct * 1.2, 0.018, 0.055)
        stop_pct = _clamp_pct(volatility_pct * 0.8, 0.012, 0.03)
        entry_low = round_tick(last_close * 0.998)
        entry_high = round_tick(last_close * 1.008)
        entry_time = "13:00–13:25　尾盤確認收紅、量增且站上 5 日均線後進場"
        exit_time = "隔日 09:00–09:35 早盤拉高出場；若開盤跳空跌破停損價立即停損"
        holding = "持有一晚（T 日買、T+1 日早盤賣）"

    return {
        "strategy": strategy,
        "strategy_name": "當沖" if strategy == "day" else "隔日沖",
        "action": action,
        "actionable": actionable,
        "entry_low": entry_low,
        "entry_high": entry_high,
        "target": round_tick(last_close * (1 + target_pct)),
        "target_pct": round(target_pct * 100, 2),
        "stop": round_tick(last_close * (1 - stop_pct)),
        "stop_pct": round(stop_pct * 100, 2),
        "risk_reward": round(target_pct / stop_pct, 2) if stop_pct else None,
        "entry_time": entry_time,
        "exit_time": exit_time,
        "holding": holding,
    }


def analyze_stock(stock):
    """對單一個股做完整分析，回傳含三面向、綜合評分與兩種策略計畫的結果。"""
    history = stock["history"]
    last_close = history[-1]["close"]

    tech = technical_analysis(history)
    fund = fundamental_analysis(stock["fundamentals"])
    news = news_analysis(stock.get("news", []))

    scores = {}
    plans = {}
    for strategy, w in STRATEGY_WEIGHTS.items():
        composite = (
            tech["score"] * w["tech"]
            + news["score"] * w["news"]
            + fund["score"] * w["fund"]
        )
        composite = round(composite, 1)
        scores[strategy] = composite
        plans[strategy] = build_trade_plan(
            strategy, composite, last_close, tech["volatility_pct"]
        )

    return {
        "code": stock["code"],
        "name": stock["name"],
        "sector": stock["sector"],
        "last_close": last_close,
        "change_pct": tech["indicators"]["change_pct"],
        "scores": {
            "technical": tech["score"],
            "fundamental": fund["score"],
            "news": news["score"],
            "day": scores["day"],
            "overnight": scores["overnight"],
        },
        "indicators": tech["indicators"],
        "signals": {
            "technical": tech["signals"],
            "fundamental": fund["signals"],
            "news": news["signals"],
        },
        "news": news["scored_news"],
        "fundamentals": stock["fundamentals"],
        "plans": plans,
        "history": history,
    }


def _r(value, digits=2):
    return None if value is None else round(value, digits)
