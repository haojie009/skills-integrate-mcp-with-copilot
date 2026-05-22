"""
台股當沖／隔日沖分析引擎

提供三大面向的分析：
  - 技術面：均線、RSI、KD、MACD、布林通道、量能、ATR、乖離率、威廉指標、
            CCI、DMI/ADX、OBV、樞紐點支撐壓力、K 線型態
  - 基本面：本益比、股價淨值比、EPS 成長、殖利率、ROE
  - 消息面：以關鍵字對新聞標題做情緒評分

並依當沖（day）與隔日沖（overnight）兩種策略，計算綜合評分與買賣計畫。

⚠️ 本檔所有運算僅供教學與研究，非投資建議。
"""

from __future__ import annotations

from datetime import date

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


def bias(closes, period=10):
    """乖離率：股價偏離均線的百分比，短線過大易拉回／反彈"""
    ma = sma(closes, period)
    if ma is None or ma == 0:
        return None
    return (closes[-1] - ma) / ma * 100


def williams_r(highs, lows, closes, period=14):
    """威廉指標 %R：-100~0，越接近 0 越超買、越接近 -100 越超賣"""
    if len(closes) < period:
        return None
    hh = max(highs[-period:])
    ll = min(lows[-period:])
    if hh == ll:
        return -50.0
    return (hh - closes[-1]) / (hh - ll) * -100


def cci(highs, lows, closes, period=20):
    """順勢指標 CCI：衡量價格偏離統計均值的程度"""
    if len(closes) < period:
        return None
    tp = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(len(closes))]
    window = tp[-period:]
    ma = sum(window) / period
    mean_dev = sum(abs(x - ma) for x in window) / period
    if mean_dev == 0:
        return 0.0
    return (tp[-1] - ma) / (0.015 * mean_dev)


def dmi(highs, lows, closes, period=14):
    """趨勢指標 DMI：回傳 +DI、-DI 與 ADX（趨勢強度）"""
    n = len(closes)
    if n < period * 2 + 1:
        return None
    trs, plus_dm, minus_dm = [], [], []
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if (up > down and up > 0) else 0.0)
        minus_dm.append(down if (down > up and down > 0) else 0.0)
        trs.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))

    def _wilder(values):
        out = [sum(values[:period])]
        for v in values[period:]:
            out.append(out[-1] - out[-1] / period + v)
        return out

    str_ = _wilder(trs)
    sp = _wilder(plus_dm)
    sm = _wilder(minus_dm)
    plus_di = [100 * p / t if t else 0.0 for p, t in zip(sp, str_)]
    minus_di = [100 * m / t if t else 0.0 for m, t in zip(sm, str_)]
    dx = []
    for p, m in zip(plus_di, minus_di):
        total = p + m
        dx.append(100 * abs(p - m) / total if total else 0.0)
    if len(dx) >= period:
        adx = sum(dx[:period]) / period
        for v in dx[period:]:
            adx = (adx * (period - 1) + v) / period
    else:
        adx = sum(dx) / len(dx) if dx else 0.0
    return {"plus_di": plus_di[-1], "minus_di": minus_di[-1], "adx": adx}


def obv(closes, volumes):
    """能量潮 OBV：以量能累積確認價格趨勢，回傳值與近期方向"""
    if len(closes) < 6:
        return None
    series = [0.0]
    acc = 0.0
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            acc += volumes[i]
        elif closes[i] < closes[i - 1]:
            acc -= volumes[i]
        series.append(acc)
    prev = series[-6]
    if series[-1] > prev:
        trend = "up"
    elif series[-1] < prev:
        trend = "down"
    else:
        trend = "flat"
    return {"value": series[-1], "trend": trend}


def pivot_points(history):
    """古典樞紐點：以前一交易日 HLC 推算當日盤中支撐壓力參考價"""
    last = history[-1]
    h, l, c = last["high"], last["low"], last["close"]
    p = (h + l + c) / 3
    return {
        "r2": p + (h - l),
        "r1": 2 * p - l,
        "pivot": p,
        "s1": 2 * p - h,
        "s2": p - (h - l),
    }


def support_resistance(history, period=20):
    """近 N 日波段高低點，作為支撐與壓力參考"""
    window = history[-period:]
    return {
        "resistance": max(d["high"] for d in window),
        "support": min(d["low"] for d in window),
        "period": period,
    }


def candlestick_pattern(history):
    """辨識最後一根 K 線型態，回傳 (多／空／中, 說明)"""
    last = history[-1]
    prev = history[-2]
    o, h, l, c = last["open"], last["high"], last["low"], last["close"]
    rng = h - l
    if rng <= 0:
        return ("中", "平盤線，無明顯方向")
    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l
    bull = c >= o
    prev_bull = prev["close"] >= prev["open"]

    if bull and not prev_bull and c >= prev["open"] and o <= prev["close"]:
        return ("多", "多頭吞噬，買方轉強")
    if not bull and prev_bull and o >= prev["close"] and c <= prev["open"]:
        return ("空", "空頭吞噬，賣方轉強")
    if body < rng * 0.12:
        return ("中", "十字星，多空拉鋸、留意變盤")
    if bull and body > rng * 0.6:
        return ("多", "長紅K，買盤積極")
    if not bull and body > rng * 0.6:
        return ("空", "長黑K，賣壓沉重")
    if lower > body * 2 and lower >= upper:
        return ("多", "長下影線（槌子線），低檔有撐")
    if upper > body * 2 and upper >= lower:
        return ("空", "長上影線（流星線），高檔遇壓")
    return ("中", "一般K線，型態中性")


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

    bias10 = bias(closes, 10)
    wr = williams_r(highs, lows, closes)
    cci20 = cci(highs, lows, closes)
    dmi_v = dmi(highs, lows, closes)
    obv_v = obv(closes, volumes)
    pivots = pivot_points(history)
    sr = support_resistance(history, 20)
    pattern = candlestick_pattern(history)

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

    # 乖離率
    if bias10 is not None:
        if bias10 > 7:
            score -= 6
            signals.append(("空", f"乖離率 +{bias10:.1f}%，短線過熱、拉回機率高"))
        elif bias10 < -7:
            score += 5
            signals.append(("多", f"乖離率 {bias10:.1f}%，跌深、易現反彈"))

    # 威廉指標
    if wr is not None:
        if wr <= -80:
            score += 4
            signals.append(("多", f"威廉指標 {wr:.0f}，落入超賣區"))
        elif wr >= -20:
            score -= 5
            signals.append(("空", f"威廉指標 {wr:.0f}，進入超買區"))

    # CCI 順勢指標
    if cci20 is not None:
        if cci20 > 250:
            score -= 5
            signals.append(("空", f"CCI {cci20:.0f}，漲勢過度延伸"))
        elif cci20 > 100:
            score += 5
            signals.append(("多", f"CCI {cci20:.0f}，順勢偏多動能"))
        elif cci20 < -100:
            score -= 5
            signals.append(("空", f"CCI {cci20:.0f}，空方動能強"))

    # DMI / ADX 趨勢強度
    if dmi_v:
        if dmi_v["adx"] >= 25 and dmi_v["plus_di"] > dmi_v["minus_di"]:
            score += 7
            signals.append(("多", f"ADX {dmi_v['adx']:.0f}，趨勢明確且 +DI 主導偏多"))
        elif dmi_v["adx"] >= 25 and dmi_v["minus_di"] > dmi_v["plus_di"]:
            score -= 7
            signals.append(("空", f"ADX {dmi_v['adx']:.0f}，趨勢明確且 -DI 主導偏空"))
        elif dmi_v["adx"] < 20:
            signals.append(("中", f"ADX {dmi_v['adx']:.0f}，趨勢不明、盤整格局"))

    # OBV 量價確認
    if obv_v:
        if change_pct > 0 and obv_v["trend"] == "up":
            score += 5
            signals.append(("多", "OBV 同步走高，量價齊揚"))
        elif change_pct > 0 and obv_v["trend"] == "down":
            score -= 5
            signals.append(("空", "股價漲但 OBV 走低，量價背離"))
        elif change_pct < 0 and obv_v["trend"] == "down":
            score -= 3
            signals.append(("空", "OBV 持續走低，賣壓未歇"))

    # 當日 K 線型態
    if pattern[0] == "多":
        score += 5
        signals.append(("多", f"K線型態：{pattern[1]}"))
    elif pattern[0] == "空":
        score -= 5
        signals.append(("空", f"K線型態：{pattern[1]}"))

    # 支撐 / 壓力位置
    if last >= sr["resistance"] * 0.99:
        score -= 4
        signals.append(("空", f"逼近 20 日壓力 {sr['resistance']:.1f}，留意賣壓"))
    elif last <= sr["support"] * 1.01:
        score += 4
        signals.append(("多", f"靠近 20 日支撐 {sr['support']:.1f}，跌深有撐"))

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
            "bias10": _r(bias10),
            "williams_r": _r(wr),
            "cci20": _r(cci20),
            "dmi": {k: _r(v) for k, v in dmi_v.items()} if dmi_v else None,
            "obv": {"value": _r(obv_v["value"], 0), "trend": obv_v["trend"]} if obv_v else None,
        },
        "levels": {
            "pivot": {k: round_tick(v) for k, v in pivots.items()},
            "support_resistance": {
                "resistance": round_tick(sr["resistance"]),
                "support": round_tick(sr["support"]),
                "period": sr["period"],
            },
        },
        "pattern": {"side": pattern[0], "text": pattern[1]},
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


# ---------------------------------------------------------------------------
# 圖表用指標序列
# ---------------------------------------------------------------------------


def _sma_series(values, period):
    """簡單移動平均序列（前 period-1 筆為 None）。"""
    out = []
    for i in range(len(values)):
        if i + 1 < period:
            out.append(None)
        else:
            out.append(sum(values[i + 1 - period:i + 1]) / period)
    return out


def macd_series(closes, fast=12, slow=26, signal=9):
    """回傳 DIF、訊號線、柱狀體三條序列（與 closes 等長）。"""
    if len(closes) < 2:
        return [], [], []
    ema_fast = _ema_series(closes, fast)
    ema_slow = _ema_series(closes, slow)
    dif = [f - s for f, s in zip(ema_fast, ema_slow)]
    sig = _ema_series(dif, signal)
    hist = [d - s for d, s in zip(dif, sig)]
    return dif, sig, hist


def kd_series(highs, lows, closes, period=9):
    """回傳 K、D 兩條序列（與 closes 等長，前 period-1 筆為 None）。"""
    k, d = 50.0, 50.0
    ks, ds = [], []
    for i in range(len(closes)):
        if i + 1 < period:
            ks.append(None)
            ds.append(None)
            continue
        window_high = max(highs[i - period + 1:i + 1])
        window_low = min(lows[i - period + 1:i + 1])
        if window_high == window_low:
            rsv = 50.0
        else:
            rsv = (closes[i] - window_low) / (window_high - window_low) * 100
        k = k * 2 / 3 + rsv / 3
        d = d * 2 / 3 + k / 3
        ks.append(k)
        ds.append(d)
    return ks, ds


def chart_series(history):
    """產生繪製技術線圖所需的指標序列（每條皆與 history 等長）。"""
    closes = [d["close"] for d in history]
    highs = [d["high"] for d in history]
    lows = [d["low"] for d in history]
    dif, sig, hist = macd_series(closes)
    ks, ds = kd_series(highs, lows, closes)
    return {
        "ma5": [_r(x) for x in _sma_series(closes, 5)],
        "ma10": [_r(x) for x in _sma_series(closes, 10)],
        "ma20": [_r(x) for x in _sma_series(closes, 20)],
        "macd_dif": [_r(x, 3) for x in dif],
        "macd_signal": [_r(x, 3) for x in sig],
        "macd_hist": [_r(x, 3) for x in hist],
        "kd_k": [_r(x) for x in ks],
        "kd_d": [_r(x) for x in ds],
    }


# ---------------------------------------------------------------------------
# 當沖選股：以單日量價評估「當沖適合度」
# ---------------------------------------------------------------------------


def screen_score(row):
    """依單日量價計算當沖適合度（0~100）與標籤。

    row 需含 open/high/low/close/change/turnover（成交金額，元）。
    當沖最看重三件事：流動性（進得去出得來）、波動度（有空間賺）、動能（今天有在動）。
    """
    close = row["close"]
    change = row.get("change") or 0.0
    prev_close = close - change
    if prev_close <= 0:
        prev_close = close
    high = row.get("high") or close
    low = row.get("low") or close
    turnover_yi = (row.get("turnover") or 0.0) / 1e8  # 成交金額（億元）

    change_pct = change / prev_close * 100
    amplitude_pct = (high - low) / prev_close * 100
    abs_chg = abs(change_pct)

    score = 0.0
    tags = []

    # 流動性（當沖第一要件）
    if turnover_yi >= 10:
        score += 35
        tags.append("大量")
    elif turnover_yi >= 3:
        score += 30
    elif turnover_yi >= 1:
        score += 22
    elif turnover_yi >= 0.3:
        score += 10
    # 低於 0.3 億：流動性太差，不加分

    # 波動度（振幅甜蜜點 3.5%~9%）
    if 3.5 <= amplitude_pct <= 9:
        score += 32
        tags.append("波動足")
    elif 2 <= amplitude_pct < 3.5:
        score += 20
    elif 9 < amplitude_pct <= 13:
        score += 24
    elif amplitude_pct > 13:
        score += 12  # 過度激烈，易追高殺低
    else:
        score += 6

    # 動能（今天有沒有在走）
    if abs_chg >= 5:
        score += 22
    elif abs_chg >= 2:
        score += 16
    elif abs_chg >= 1:
        score += 9
    else:
        score += 3
    if change_pct >= 3:
        tags.append("強勢")
    elif change_pct <= -3:
        tags.append("弱勢")

    # 小型有爆發力：非權值大量、但振幅與漲跌幅都大
    if turnover_yi < 8 and amplitude_pct >= 6 and abs_chg >= 4:
        score += 11
        tags.append("小型爆發")

    # 三大法人買賣超（當沖時機條件之一）
    inst_lots = row.get("inst_lots")
    if inst_lots is not None:
        volume_lots = (row.get("volume_shares") or 0) / 1000
        inst_ratio = inst_lots / volume_lots if volume_lots > 0 else 0.0
        if inst_ratio >= 0.15:
            score += 14
            tags.append("法人大買")
        elif inst_ratio >= 0.05:
            score += 8
            tags.append("法人偏多")
        elif inst_ratio <= -0.15:
            score -= 10
            tags.append("法人賣超")
        elif inst_ratio <= -0.05:
            score -= 4
        if (row.get("trust_lots") or 0) >= 500 and "投信買超" not in tags:
            tags.append("投信買超")

    # 飆股雷達：大漲 ＋ 爆量 ＋ 突破前高
    vol_ratio = row.get("vol_ratio") or 1.0
    breakout = bool(row.get("breakout"))
    hot_score = 0.0
    if change_pct > 0:
        hot_score = change_pct * 2.5 + min(vol_ratio, 5.0) * 6 + (18 if breakout else 0)
    hot_score = round(_clamp(hot_score), 1)
    if change_pct >= 4 and vol_ratio >= 1.8:
        score += 8
        tags.append("飆股訊號")
    if breakout and change_pct > 0:
        tags.append("突破前高")
    if vol_ratio >= 2.5 and "爆量" not in tags:
        tags.append("爆量")

    return {
        "score": round(_clamp(score), 1),
        "change_pct": round(change_pct, 2),
        "amplitude_pct": round(amplitude_pct, 2),
        "turnover_yi": round(turnover_yi, 2),
        "vol_ratio": round(vol_ratio, 2),
        "breakout": breakout,
        "hot_score": hot_score,
        "inst_lots": inst_lots,
        "trust_lots": row.get("trust_lots"),
        "tags": tags,
    }


# ---------------------------------------------------------------------------
# 盤前當沖精選：從掃描結果挑出隔日最值得當沖的個股,附上進場/停損/停利計畫
# ---------------------------------------------------------------------------


def _pick_reasons(row):
    """列出個股入選的量化理由（盤前可讀的摘要）。"""
    reasons = []
    tags = row.get("tags") or []
    turn = row.get("turnover_yi") or 0
    amp = row.get("amplitude_pct") or 0
    chg = row.get("change_pct") or 0

    if turn >= 10:
        reasons.append(f"成交 {turn:.1f} 億,流動性充足,進出順暢")
    elif turn >= 3:
        reasons.append(f"成交 {turn:.1f} 億,流動性達到當沖門檻")
    if "波動足" in tags:
        reasons.append(f"振幅 {amp}% 落在當沖甜蜜點(3.5–9%)")
    elif amp >= 3:
        reasons.append(f"振幅 {amp}% 提供操作空間")
    if "突破前高" in tags:
        reasons.append("突破近 20 日新高,空方套牢壓力被洗掉")
    if "爆量" in tags and "突破前高" not in tags:
        reasons.append(f"量能放大至均量 {row.get('vol_ratio')} 倍,主力動作明顯")
    if "強勢" in tags:
        reasons.append(f"今日強漲 +{chg}%,動能延續機率高")
    if "法人大買" in tags:
        reasons.append(f"三大法人合計買超 {row.get('inst_lots')} 張,有資金撐盤")
    elif "法人偏多" in tags:
        reasons.append(f"三大法人小幅買超 {row.get('inst_lots')} 張")
    if "投信買超" in tags:
        reasons.append(f"投信買超 {row.get('trust_lots')} 張,中期主力鎖籌碼")
    if "小型爆發" in tags:
        reasons.append("中小型股爆量+大漲,適合短線快進快出")
    if "飆股訊號" in tags:
        reasons.append("符合飆股雷達:大漲 + 爆量 + 突破前高")
    return reasons[:5]


def _pick_cautions(row):
    """列出個股的風險警示與不該追的條件。"""
    cautions = []
    tags = row.get("tags") or []
    chg = row.get("change_pct") or 0
    amp = row.get("amplitude_pct") or 0

    if chg >= 8:
        cautions.append(f"昨日已大漲 {chg}%,跳空高開 >2% 不建議追,等回測進")
    elif chg >= 5:
        cautions.append("漲幅已高,只在回測不破開盤價時進,不追高")
    if amp >= 10:
        cautions.append(f"振幅 {amp}% 偏激烈,部位減半操作")
    if "法人賣超" in tags:
        cautions.append("三大法人賣超,動能可能不續,只做短進短出")
    if chg <= -3:
        cautions.append("昨收弱勢,需確認開盤站上開盤價且翻紅才考慮")
    if not cautions:
        cautions.append("若開盤跳空高開超過 2% 改觀望,等回測再進")
    return cautions[:3]


def daytrade_picks(rows, top_n=8):
    """從掃描結果挑出明日最適合當沖的前 N 檔,附上盤前可直接執行的計畫。

    嚴格度比一般 screener 高:必須有流動性 + 波動 + 動能,且排除昨日大跌+法人賣超的組合。
    每檔回傳:入選理由、開盤觸發價、停損、停利、什麼狀況該放棄。
    """
    def qualified(r):
        if (r.get("turnover_yi") or 0) < 3:        # 流動性不足
            return False
        if (r.get("amplitude_pct") or 0) < 3:      # 波動太小,沒空間
            return False
        if (r.get("score") or 0) < 60:             # 綜合分過低
            return False
        # 排除:昨日跌深 + 法人賣超(動能反向)
        chg = r.get("change_pct") or 0
        inst = r.get("inst_lots") or 0
        if chg < -3 and inst < -500:
            return False
        return True

    candidates = [r for r in rows if qualified(r)]
    candidates.sort(
        key=lambda r: (r.get("score") or 0) * 0.7 + (r.get("hot_score") or 0) * 0.3,
        reverse=True,
    )

    picks = []
    for r in candidates[: max(1, top_n)]:
        last_close = r["close"]
        amp_pct = (r.get("amplitude_pct") or 4.0) / 100.0
        # 觸發價:盤後預期開盤站上昨收即可進
        trigger_price = round_tick(last_close * (1 + amp_pct * 0.15))
        target1 = round_tick(last_close * (1 + amp_pct * 0.45))
        target2 = round_tick(last_close * (1 + amp_pct * 0.75))
        stop = round_tick(last_close * (1 - amp_pct * 0.35))
        risk_pct = round((last_close - stop) / last_close * 100, 2)
        reward1_pct = round((target1 - last_close) / last_close * 100, 2)

        picks.append({
            "code": r["code"],
            "name": r["name"],
            "last_close": last_close,
            "change_pct": r.get("change_pct"),
            "turnover_yi": r.get("turnover_yi"),
            "amplitude_pct": r.get("amplitude_pct"),
            "vol_ratio": r.get("vol_ratio"),
            "score": r.get("score"),
            "hot_score": r.get("hot_score"),
            "tags": r.get("tags") or [],
            "theme": r.get("theme"),
            "inst_lots": r.get("inst_lots"),
            "trust_lots": r.get("trust_lots"),
            "reasons": _pick_reasons(r),
            "cautions": _pick_cautions(r),
            "open_plan": {
                "trigger": f"開盤 5–10 分鐘站穩 {trigger_price} 以上且量續放,順勢做多",
                "trigger_price": trigger_price,
                "target1": target1,
                "target1_pct": reward1_pct,
                "target2": target2,
                "stop": stop,
                "stop_pct": risk_pct,
                "exit_time": "13:00 起分批停利,13:25 強制平倉,絕不留倉",
                "position_hint": (
                    "單檔不超過總部位 10%(飆股訊號 / 小型爆發 降至 7%)"
                    if "飆股訊號" in (r.get("tags") or []) or "小型爆發" in (r.get("tags") or [])
                    else "單檔不超過總部位 15%"
                ),
            },
        })
    return picks


# ---------------------------------------------------------------------------
# 多時間框架：週線趨勢
# ---------------------------------------------------------------------------


def _to_weekly(history):
    """把日 K 聚合成週 K（依 ISO 週）。"""
    weeks = {}
    order = []
    for bar in history:
        iso = date.fromisoformat(bar["date"]).isocalendar()
        key = (iso[0], iso[1])
        if key not in weeks:
            weeks[key] = {"high": bar["high"], "low": bar["low"], "close": bar["close"]}
            order.append(key)
        else:
            wk = weeks[key]
            wk["high"] = max(wk["high"], bar["high"])
            wk["low"] = min(wk["low"], bar["low"])
            wk["close"] = bar["close"]
    return [weeks[k] for k in order]


def weekly_trend(history):
    """以週線均線判斷中期趨勢（多頭／空頭／盤整）。"""
    weekly = _to_weekly(history)
    closes = [w["close"] for w in weekly]
    if len(closes) < 11:
        return {"trend": "資料不足", "ma5": None, "ma10": None, "last": None}
    ma5 = sma(closes, 5)
    ma10 = sma(closes, 10)
    last = closes[-1]
    if last >= ma5 >= ma10:
        trend = "多頭"
    elif last <= ma5 <= ma10:
        trend = "空頭"
    else:
        trend = "盤整"
    return {"trend": trend, "ma5": _r(ma5), "ma10": _r(ma10), "last": _r(last)}


# ---------------------------------------------------------------------------
# 歷史回測：驗證隔日沖進場規則
# ---------------------------------------------------------------------------


def backtest(history):
    """回測簡易隔日沖規則：訊號日收盤進場、隔日收盤出場。

    進場條件：收盤站上 20MA、MACD 紅柱且翻揚、RSI 在 50~78。
    """
    closes = [b["close"] for b in history]
    if len(closes) < 45:
        return None
    trades = []
    for i in range(35, len(closes) - 1):
        window = closes[: i + 1]
        ma20 = sma(window, 20)
        rsi14 = rsi(window, 14)
        macd_v = macd(window)
        if ma20 is None or rsi14 is None or macd_v is None:
            continue
        bullish = (
            window[-1] > ma20
            and macd_v["hist"] > 0
            and macd_v["hist"] > macd_v["hist_prev"]
            and 50 <= rsi14 <= 78
        )
        if bullish:
            trades.append((closes[i + 1] - closes[i]) / closes[i] * 100)
    if not trades:
        return {"trades": 0, "win_rate": None, "avg_return": None,
                "best": None, "worst": None}
    wins = sum(1 for r in trades if r > 0)
    return {
        "trades": len(trades),
        "win_rate": round(wins / len(trades) * 100, 1),
        "avg_return": round(sum(trades) / len(trades), 2),
        "best": round(max(trades), 2),
        "worst": round(min(trades), 2),
    }


def analyze_stock(stock):
    """對單一個股做完整分析，回傳含三面向、綜合評分與兩種策略計畫的結果。"""
    history = stock["history"]
    last_close = history[-1]["close"]

    tech = technical_analysis(history)
    fund = fundamental_analysis(stock["fundamentals"])
    news = news_analysis(stock.get("news", []))
    weekly = weekly_trend(history)
    bt = backtest(history)

    # 週線趨勢校正：中期多頭順勢加分、空頭逆勢扣分
    wk_adj = {"多頭": 3.0, "空頭": -5.0}.get(weekly["trend"], 0.0)

    scores = {}
    plans = {}
    for strategy, w in STRATEGY_WEIGHTS.items():
        composite = (
            tech["score"] * w["tech"]
            + news["score"] * w["news"]
            + fund["score"] * w["fund"]
        )
        composite = round(_clamp(composite + wk_adj), 1)
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
        "levels": tech["levels"],
        "pattern": tech["pattern"],
        "signals": {
            "technical": tech["signals"],
            "fundamental": fund["signals"],
            "news": news["signals"],
        },
        "news": news["scored_news"],
        "fundamentals": stock["fundamentals"],
        "institutional": stock.get("institutional"),
        "weekly": weekly,
        "backtest": bt,
        "plans": plans,
        "history": history,
        "series": chart_series(history),
    }


def _r(value, digits=2):
    return None if value is None else round(value, digits)
