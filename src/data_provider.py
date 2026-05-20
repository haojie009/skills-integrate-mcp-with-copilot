"""
台股資料來源層

支援兩種模式（以環境變數 STOCK_DATA_MODE 切換）：

  demo  （預設）— 內建一組可重現的示範資料，無需網路即可完整展示分析流程。
  live  — 透過證交所公開 API 抓取真實價量與基本面資料。

⚠️ demo 模式的價量、基本面與新聞皆為「模擬資料」，僅供功能展示，
   不代表任何真實個股現況，切勿作為交易依據。
"""

from __future__ import annotations

import os
import random
from datetime import date, timedelta

# 分析所需的歷史交易日數
HISTORY_DAYS = 160

DATA_MODE = os.environ.get("STOCK_DATA_MODE", "demo").lower()


# ---------------------------------------------------------------------------
# 示範個股設定檔
# ---------------------------------------------------------------------------
# regime 只是用來產生不同走勢型態，讓分析結果具有多樣性。
#   total_drift  ：整段期間的累積漲跌幅
#   daily_vol    ：每日波動度
#   kick         ：近期 kick_days 天的額外動能（製造新鮮的買賣訊號）
_DEMO_PROFILES = [
    {
        "code": "2330", "name": "台積電", "sector": "半導體",
        "base_price": 880, "total_drift": 0.22, "daily_vol": 0.016,
        "intraday": 0.012, "kick": 0.006, "kick_days": 6, "base_volume": 32000,
        "fundamentals": {"pe": 22.5, "pb": 6.1, "eps_growth": 28, "yield_pct": 1.8, "roe": 28},
        "news": [
            "外資調升台積電目標價，看好 AI 訂單滿載",
            "台積電法說釋出樂觀展望，先進製程報價調漲",
            "三大法人連三日買超台積電",
        ],
    },
    {
        "code": "2317", "name": "鴻海", "sector": "電子代工",
        "base_price": 185, "total_drift": 0.14, "daily_vol": 0.018,
        "intraday": 0.014, "kick": 0.004, "kick_days": 5, "base_volume": 45000,
        "fundamentals": {"pe": 14.2, "pb": 1.5, "eps_growth": 12, "yield_pct": 4.2, "roe": 11},
        "news": [
            "鴻海 AI 伺服器接單暢旺，營收創高",
            "電動車布局擴產，法人看好成長",
        ],
    },
    {
        "code": "2454", "name": "聯發科", "sector": "半導體",
        "base_price": 1120, "total_drift": 0.10, "daily_vol": 0.022,
        "intraday": 0.018, "kick": -0.002, "kick_days": 5, "base_volume": 8000,
        "fundamentals": {"pe": 19.8, "pb": 4.0, "eps_growth": 8, "yield_pct": 3.5, "roe": 21},
        "news": [
            "聯發科旗艦晶片出貨樂觀",
            "手機市場需求疲弱，法人下修出貨預估",
        ],
    },
    {
        "code": "2308", "name": "台達電", "sector": "電子零組件",
        "base_price": 360, "total_drift": 0.26, "daily_vol": 0.019,
        "intraday": 0.015, "kick": 0.007, "kick_days": 6, "base_volume": 14000,
        "fundamentals": {"pe": 24.0, "pb": 4.6, "eps_growth": 24, "yield_pct": 2.2, "roe": 19},
        "news": [
            "台達電電源供應器接單滿載，題材升溫",
            "AI 散熱訂單加碼，外資升評",
        ],
    },
    {
        "code": "2303", "name": "聯電", "sector": "半導體",
        "base_price": 52, "total_drift": -0.05, "daily_vol": 0.02,
        "intraday": 0.016, "kick": -0.004, "kick_days": 5, "base_volume": 60000,
        "fundamentals": {"pe": 13.0, "pb": 1.9, "eps_growth": -8, "yield_pct": 5.0, "roe": 9},
        "news": [
            "成熟製程競爭加劇，聯電報價承壓",
            "外資賣超聯電，目標價調降",
        ],
    },
    {
        "code": "2881", "name": "富邦金", "sector": "金融保險",
        "base_price": 88, "total_drift": 0.12, "daily_vol": 0.013,
        "intraday": 0.01, "kick": 0.003, "kick_days": 5, "base_volume": 28000,
        "fundamentals": {"pe": 11.5, "pb": 1.3, "eps_growth": 15, "yield_pct": 5.5, "roe": 13},
        "news": [
            "富邦金前四月獲利成長，獲利動能穩健",
        ],
    },
    {
        "code": "2412", "name": "中華電", "sector": "電信",
        "base_price": 128, "total_drift": 0.03, "daily_vol": 0.008,
        "intraday": 0.006, "kick": 0.0, "kick_days": 4, "base_volume": 9000,
        "fundamentals": {"pe": 25.5, "pb": 2.4, "eps_growth": 2, "yield_pct": 4.0, "roe": 9},
        "news": [],
    },
    {
        "code": "3008", "name": "大立光", "sector": "光學元件",
        "base_price": 2600, "total_drift": -0.16, "daily_vol": 0.024,
        "intraday": 0.02, "kick": -0.006, "kick_days": 6, "base_volume": 1200,
        "fundamentals": {"pe": 17.0, "pb": 2.1, "eps_growth": -14, "yield_pct": 3.8, "roe": 12},
        "news": [
            "大立光出貨下滑，法人下修全年預估",
            "手機鏡頭規格升級不如預期，股價示警",
        ],
    },
    {
        "code": "2603", "name": "長榮", "sector": "航運",
        "base_price": 195, "total_drift": 0.30, "daily_vol": 0.03,
        "intraday": 0.024, "kick": 0.009, "kick_days": 5, "base_volume": 70000,
        "fundamentals": {"pe": 8.5, "pb": 1.6, "eps_growth": 35, "yield_pct": 6.5, "roe": 22},
        "news": [
            "貨櫃運價連續調漲，長榮營收創高",
            "紅海情勢推升運價，航運題材大漲",
            "投信買超長榮，盤面點火",
        ],
    },
    {
        "code": "2609", "name": "陽明", "sector": "航運",
        "base_price": 78, "total_drift": 0.08, "daily_vol": 0.032,
        "intraday": 0.026, "kick": -0.003, "kick_days": 5, "base_volume": 85000,
        "fundamentals": {"pe": 9.0, "pb": 1.4, "eps_growth": 6, "yield_pct": 4.5, "roe": 15},
        "news": [
            "陽明運價走勢震盪，法人看法分歧",
        ],
    },
    {
        "code": "2002", "name": "中鋼", "sector": "鋼鐵",
        "base_price": 24, "total_drift": -0.10, "daily_vol": 0.012,
        "intraday": 0.01, "kick": -0.003, "kick_days": 5, "base_volume": 40000,
        "fundamentals": {"pe": 38.0, "pb": 0.9, "eps_growth": -22, "yield_pct": 1.5, "roe": 3},
        "news": [
            "鋼價疲弱，中鋼獲利衰退",
            "中國鋼鐵減產不如預期，市場示警",
        ],
    },
    {
        "code": "3711", "name": "日月光投控", "sector": "半導體封測",
        "base_price": 165, "total_drift": 0.20, "daily_vol": 0.02,
        "intraday": 0.016, "kick": 0.006, "kick_days": 6, "base_volume": 22000,
        "fundamentals": {"pe": 16.5, "pb": 2.3, "eps_growth": 18, "yield_pct": 3.2, "roe": 17},
        "news": [
            "先進封裝需求成長，日月光接單樂觀",
            "外資加碼半導體封測族群",
        ],
    },
]


# ---------------------------------------------------------------------------
# 工具函式
# ---------------------------------------------------------------------------

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


def _round_tick(price):
    tick = _tick_size(price)
    return round(round(price / tick) * tick, 2)


def _recent_weekdays(n, end):
    """回傳截至 end（含）的最近 n 個工作日，由舊到新。"""
    days = []
    d = end
    while len(days) < n:
        if d.weekday() < 5:  # 0=Mon ... 4=Fri
            days.append(d)
        d -= timedelta(days=1)
    return list(reversed(days))


# ---------------------------------------------------------------------------
# demo 模式：產生可重現的模擬價量資料
# ---------------------------------------------------------------------------

def _generate_history(profile):
    """依設定檔產生一段隨機漫步的 OHLCV 歷史。"""
    rnd = random.Random(int(profile["code"]) * 7 + 13)
    days = HISTORY_DAYS
    daily_drift = (1 + profile["total_drift"]) ** (1 / days) - 1

    dates = _recent_weekdays(days, date(2026, 5, 20))
    history = []
    price = float(profile["base_price"])
    prev_close = price

    for i in range(days):
        in_kick = i >= days - profile["kick_days"]
        shock = rnd.gauss(0, 1) * profile["daily_vol"]
        extra = profile["kick"] if in_kick else 0.0
        ret = daily_drift + shock + extra
        close = max(price * (1 + ret), 1.0)

        gap = rnd.gauss(0, profile["intraday"] * 0.4)
        open_ = prev_close * (1 + gap)
        hi = max(open_, close) * (1 + abs(rnd.gauss(0, profile["intraday"])))
        lo = min(open_, close) * (1 - abs(rnd.gauss(0, profile["intraday"])))

        move_factor = 1 + abs(ret) / profile["daily_vol"] * 0.5
        vol = profile["base_volume"] * move_factor * rnd.uniform(0.7, 1.35)
        if in_kick:
            vol *= 1.5

        history.append({
            "date": dates[i].isoformat(),
            "open": _round_tick(open_),
            "high": _round_tick(hi),
            "low": _round_tick(lo),
            "close": _round_tick(close),
            "volume": int(vol),  # 單位：張
        })
        prev_close = close
        price = close

    return history


def _build_demo_stock(profile):
    today = date(2026, 5, 20).isoformat()
    news = [
        {"title": t, "source": "示範資料", "date": today}
        for t in profile["news"]
    ]
    return {
        "code": profile["code"],
        "name": profile["name"],
        "sector": profile["sector"],
        "fundamentals": dict(profile["fundamentals"]),
        "news": news,
        "history": _generate_history(profile),
    }


def _load_demo():
    return [_build_demo_stock(p) for p in _DEMO_PROFILES]


# ---------------------------------------------------------------------------
# live 模式：證交所公開 API
# ---------------------------------------------------------------------------
# 注意：本服務若部署在有網路限制的環境（例如 Claude Code 雲端沙箱），
# openapi.twse.com.tw 可能不在允許清單中而失敗，此時會自動退回 demo 模式。

_TWSE_DAILY = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
_TWSE_PERATIO = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"


def _fetch_live_history(code, months=8):
    """以證交所 STOCK_DAY API 抓取近數月日 K 線。"""
    import requests

    history = []
    cursor = date(2026, 5, 1)
    for _ in range(months):
        params = {
            "response": "json",
            "date": cursor.strftime("%Y%m%d"),
            "stockNo": code,
        }
        resp = requests.get(_TWSE_DAILY, params=params, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
        for row in payload.get("data", []):
            # row: [日期, 成交股數, 成交金額, 開盤, 最高, 最低, 收盤, 漲跌價差, 成交筆數]
            try:
                y, m, d = row[0].split("/")
                iso = f"{int(y) + 1911:04d}-{int(m):02d}-{int(d):02d}"
                history.append({
                    "date": iso,
                    "open": float(row[3].replace(",", "")),
                    "high": float(row[4].replace(",", "")),
                    "low": float(row[5].replace(",", "")),
                    "close": float(row[6].replace(",", "")),
                    "volume": int(float(row[1].replace(",", "")) / 1000),
                })
            except (ValueError, IndexError):
                continue
        # 往前一個月
        cursor = (cursor.replace(day=1) - timedelta(days=1)).replace(day=1)

    history.sort(key=lambda r: r["date"])
    return history[-HISTORY_DAYS:]


def _fetch_live_fundamentals():
    """抓取全市場本益比／淨值比／殖利率。"""
    import requests

    resp = requests.get(_TWSE_PERATIO, timeout=15)
    resp.raise_for_status()
    result = {}
    for row in resp.json():
        code = row.get("Code")
        if not code:
            continue
        result[code] = {
            "pe": _safe_float(row.get("PEratio")),
            "pb": _safe_float(row.get("PBratio")),
            "yield_pct": _safe_float(row.get("DividendYield")),
            "eps_growth": None,
            "roe": None,
        }
    return result


def _safe_float(value):
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _load_live():
    """live 模式：抓真實資料，任何個股失敗即退回該檔的 demo 資料。"""
    fundamentals = {}
    try:
        fundamentals = _fetch_live_fundamentals()
    except Exception as exc:  # noqa: BLE001 - 網路/解析失敗都退回 demo
        print(f"[data_provider] 基本面抓取失敗，改用 demo：{exc}")

    stocks = []
    for profile in _DEMO_PROFILES:
        code = profile["code"]
        try:
            history = _fetch_live_history(code)
            if len(history) < 60:
                raise ValueError("歷史資料不足")
            stocks.append({
                "code": code,
                "name": profile["name"],
                "sector": profile["sector"],
                "fundamentals": fundamentals.get(code) or dict(profile["fundamentals"]),
                "news": [],  # 真實新聞需另接新聞 API
                "history": history,
            })
        except Exception as exc:  # noqa: BLE001
            print(f"[data_provider] {code} live 抓取失敗，改用 demo：{exc}")
            stocks.append(_build_demo_stock(profile))
    return stocks


# ---------------------------------------------------------------------------
# 對外介面
# ---------------------------------------------------------------------------

def load_stocks():
    """載入所有個股資料。回傳 list[dict]。"""
    if DATA_MODE == "live":
        try:
            return _load_live()
        except Exception as exc:  # noqa: BLE001
            print(f"[data_provider] live 模式失敗，全面退回 demo：{exc}")
    return _load_demo()


def data_source_label():
    return "證交所即時資料 (live)" if DATA_MODE == "live" else "內建示範資料 (demo)"
