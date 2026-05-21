"""
台股資料來源層

支援兩種模式（以環境變數 STOCK_DATA_MODE 切換）：

  demo  — 內建一組可重現的示範資料，無需網路即可完整展示分析流程。
  live  — 抓取真實行情：價量歷史取自 Yahoo Finance、本益比等基本面取自
          證交所 OpenAPI。EPS 成長率、ROE、新聞不在免費來源中，會留白。

⚠️ demo 模式的價量、基本面與新聞皆為「模擬資料」，僅供功能展示，
   不代表任何真實個股現況，切勿作為交易依據。
"""

from __future__ import annotations

import os
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

# 分析所需的歷史交易日數
HISTORY_DAYS = 160

# 預設 live（抓真實行情）；抓取失敗會自動退回 demo。
DATA_MODE = os.environ.get("STOCK_DATA_MODE", "live").lower()


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


def _demo_institutional(code):
    """demo 模式的三大法人買賣超（單位：張），可重現。"""
    rnd = random.Random(int(code) * 31 + 7)
    foreign = rnd.randint(-6000, 11000)
    trust = rnd.randint(-1500, 3500)
    dealer = rnd.randint(-1200, 1200)
    return {
        "foreign_lots": foreign,
        "trust_lots": trust,
        "dealer_lots": dealer,
        "inst_lots": foreign + trust + dealer,
    }


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
        "institutional": _demo_institutional(profile["code"]),
    }


# ---------------------------------------------------------------------------
# live 模式：即時行情
# ---------------------------------------------------------------------------
# 價量歷史取自 Yahoo Finance（每檔一次請求，較不易觸發流量限制）；
# 本益比／淨值比／殖利率取自證交所 OpenAPI。
# EPS 成長率、ROE 與新聞不在免費來源中，live 模式下會留白。
# 任一個股抓取失敗會略過該檔；全部失敗則整體退回 demo 模式。

_YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_TWSE_PERATIO = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    )
}
# 證交所 OpenAPI 需明確要求 JSON，否則可能回傳 HTML 或空白
_TWSE_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
}


def _twse_get_json(url, timeout=20):
    """對證交所 OpenAPI 發 GET 並解析 JSON；非 JSON 時拋出含回應內容的錯誤。"""
    import requests

    resp = requests.get(url, headers=_TWSE_HEADERS, timeout=timeout)
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError as exc:
        content_type = resp.headers.get("Content-Type", "?")
        snippet = resp.text[:160].replace("\n", " ").strip()
        raise ValueError(
            f"非 JSON 回應 status={resp.status_code} type={content_type} "
            f"len={len(resp.text)} body={snippet!r}"
        ) from exc


def _safe_float(value):
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _parse_yahoo_chart(payload):
    """把 Yahoo chart API 的 JSON 解析成 OHLCV 歷史（由舊到新）。"""
    result = payload["chart"]["result"][0]
    timestamps = result["timestamp"]
    quote = result["indicators"]["quote"][0]
    opens, highs = quote["open"], quote["high"]
    lows, closes, volumes = quote["low"], quote["close"], quote["volume"]

    history = []
    for i, ts in enumerate(timestamps):
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        if None in (o, h, l, c):  # Yahoo 偶有缺值，略過該日
            continue
        history.append({
            "date": datetime.fromtimestamp(ts, timezone.utc).date().isoformat(),
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
            "volume": int((volumes[i] or 0) / 1000),  # 股 → 張
        })
    return history


def _fetch_yahoo_history(code):
    """從 Yahoo Finance 抓單一上市個股近一年的日 K 線。"""
    import requests

    url = _YAHOO_CHART.format(symbol=f"{code}.TW")
    resp = requests.get(
        url,
        params={"range": "1y", "interval": "1d"},
        headers=_HTTP_HEADERS,
        timeout=12,
    )
    resp.raise_for_status()
    return _parse_yahoo_chart(resp.json())[-HISTORY_DAYS:]


def _parse_twse_fundamentals(rows):
    """把證交所 BWIBBU_ALL 的資料整理成 {代號: 基本面} 字典。"""
    result = {}
    for row in rows:
        code = (row.get("Code") or row.get("證券代號") or "").strip()
        if not code:
            continue
        result[code] = {
            "pe": _safe_float(row.get("PEratio") or row.get("本益比")),
            "pb": _safe_float(row.get("PBratio") or row.get("股價淨值比")),
            "yield_pct": _safe_float(row.get("DividendYield") or row.get("殖利率")),
            "eps_growth": None,
            "roe": None,
        }
    return result


def _fetch_twse_fundamentals():
    """抓取全市場本益比／淨值比／殖利率。"""
    return _parse_twse_fundamentals(_twse_get_json(_TWSE_PERATIO, timeout=15))


# ---------------------------------------------------------------------------
# 全市場選股：Yahoo Finance
# ---------------------------------------------------------------------------
# 證交所封鎖雲端伺服器 IP，雲端一律抓不到；Yahoo 雲端可正常存取，
# 但只能逐檔抓，故鎖定一份精選的高流動性個股清單（當沖該盯的標的）。

_TWSE_T86 = "https://openapi.twse.com.tw/v1/fund/T86"  # 三大法人（僅住家 IP 可用）

# 精選高流動性個股（代號, 名稱）—— 當沖選股掃描範圍
_UNIVERSE = [
    ("2330", "台積電"), ("2317", "鴻海"), ("2454", "聯發科"), ("2308", "台達電"),
    ("2382", "廣達"), ("2303", "聯電"), ("3711", "日月光投控"), ("2412", "中華電"),
    ("3045", "台灣大"), ("4904", "遠傳"),
    ("2881", "富邦金"), ("2882", "國泰金"), ("2891", "中信金"), ("2886", "兆豐金"),
    ("2884", "玉山金"), ("2892", "第一金"), ("2885", "元大金"), ("2880", "華南金"),
    ("2890", "永豐金"), ("2887", "台新金"), ("2883", "開發金"), ("2888", "新光金"),
    ("2889", "國票金"), ("5880", "合庫金"), ("5871", "中租-KY"), ("2801", "彰銀"),
    ("1216", "統一"), ("2912", "統一超"), ("1227", "佳格"), ("1229", "聯華"),
    ("1210", "大成"), ("1722", "台肥"),
    ("1301", "台塑"), ("1303", "南亞"), ("1326", "台化"), ("6505", "台塑化"),
    ("1717", "長興"),
    ("2002", "中鋼"), ("2014", "中鴻"), ("2027", "大成鋼"), ("1101", "台泥"),
    ("1102", "亞泥"),
    ("2603", "長榮"), ("2609", "陽明"), ("2615", "萬海"), ("2606", "裕民"),
    ("5608", "四維航"), ("2618", "長榮航"), ("2610", "華航"),
    ("3034", "聯詠"), ("2379", "瑞昱"), ("3443", "創意"), ("3035", "智原"),
    ("8016", "矽創"), ("5269", "祥碩"), ("8299", "群聯"), ("3529", "力旺"),
    ("6415", "矽力-KY"), ("3661", "世芯-KY"), ("6533", "晶心科"),
    ("2449", "京元電子"), ("6147", "頎邦"), ("6239", "力成"), ("2408", "南亞科"),
    ("3037", "欣興"), ("8046", "南電"), ("2368", "金像電"), ("3533", "嘉澤"),
    ("4958", "臻鼎-KY"), ("3702", "大聯大"),
    ("3231", "緯創"), ("2356", "英業達"), ("2376", "技嘉"), ("4938", "和碩"),
    ("6669", "緯穎"), ("2357", "華碩"), ("2353", "宏碁"), ("2324", "仁寶"),
    ("2345", "智邦"), ("2301", "光寶科"), ("6285", "啟碁"), ("2354", "鴻準"),
    ("2347", "聯強"), ("2392", "正崴"),
    ("3017", "奇鋐"), ("3324", "雙鴻"), ("6230", "超眾"),
    ("2327", "國巨"), ("2492", "華新科"), ("3026", "禾伸堂"), ("2383", "台光電"),
    ("3023", "信邦"), ("2421", "建準"), ("2393", "億光"),
    ("2409", "友達"), ("3481", "群創"), ("6116", "彩晶"), ("3008", "大立光"),
    ("3406", "玉晶光"), ("3019", "亞光"),
    ("6770", "力積電"), ("5347", "世界先進"),
    ("1503", "士電"), ("1519", "華城"), ("1513", "中興電"), ("1504", "東元"),
    ("2371", "大同"),
    ("2049", "上銀"), ("1590", "亞德客-KY"), ("2360", "致茂"), ("2395", "研華"),
    ("2059", "川湖"),
    ("2207", "和泰車"), ("2105", "正新"), ("1536", "和大"), ("2231", "為升"),
    ("2227", "裕日車"),
    ("1402", "遠東新"), ("1476", "儒鴻"), ("1477", "聚陽"), ("9910", "豐泰"),
    ("9904", "寶成"), ("9921", "巨大"), ("9914", "美利達"),
    ("2542", "興富發"), ("2548", "華固"), ("2545", "皇翔"), ("5522", "遠雄"),
    ("2727", "王品"), ("2707", "晶華"), ("2731", "雄獅"), ("8454", "富邦媒"),
    ("6446", "藥華藥"), ("1795", "美時"), ("4174", "浩鼎"), ("1762", "中化生"),
    ("2474", "可成"), ("2634", "漢翔"), ("8033", "雷虎"), ("6121", "新普"),
]

_SECTOR_BY_CODE = {p["code"]: p["sector"] for p in _DEMO_PROFILES}
_NAME_BY_CODE = {p["code"]: p["name"] for p in _DEMO_PROFILES}

# 全市場快取（各一次抓全市場）
_fund_cache: dict = {}
_fund_loaded = False
_t86_cache: dict = {}
_t86_loaded = False


def _fetch_t86():
    """抓三大法人買賣超日報（一次請求取得全市場）。"""
    return _twse_get_json(_TWSE_T86, timeout=15)


def _t86_value(row, *substrs):
    """在 T86 列中以欄名子字串比對取值（容忍中英文欄名差異）。"""
    for key, value in row.items():
        flat = str(key).replace(" ", "")
        if all(sub in flat for sub in substrs):
            num = _safe_float(value)
            if num is not None:
                return num
    return None


def _parse_t86(rows):
    """三大法人買賣超日報 → {代號: {外資／投信／自營／合計 張數}}。"""
    result = {}
    for row in rows:
        code = (row.get("Code") or row.get("證券代號") or "").strip()
        if not code:
            continue
        inst = _t86_value(row, "三大法人", "買賣超")
        trust = _t86_value(row, "投信", "買賣超")
        foreign = _t86_value(row, "外陸資", "買賣超")
        if inst is None and trust is None and foreign is None:
            continue
        inst = inst or 0.0
        trust = trust or 0.0
        foreign = foreign or 0.0
        result[code] = {
            "foreign_lots": round(foreign / 1000),
            "trust_lots": round(trust / 1000),
            "dealer_lots": round((inst - foreign - trust) / 1000),
            "inst_lots": round(inst / 1000),
        }
    return result


def _one_stock_institutional(code):
    """取單一個股三大法人買賣超（共用全市場 T86 快取）。"""
    global _t86_cache, _t86_loaded
    if not _t86_loaded:
        try:
            _t86_cache = _parse_t86(_fetch_t86())
        except Exception as exc:  # noqa: BLE001
            print(f"[data_provider] T86 法人資料抓取失敗：{exc}")
            _t86_cache = {}
        _t86_loaded = True
    return _t86_cache.get(code)


def _fetch_yahoo_quote(code):
    """抓單一個股最近數日日 K，回傳當日量價 dict（資料不足回 None）。"""
    import requests

    url = _YAHOO_CHART.format(symbol=f"{code}.TW")
    resp = requests.get(
        url,
        params={"range": "7d", "interval": "1d"},
        headers=_HTTP_HEADERS,
        timeout=8,
    )
    resp.raise_for_status()
    hist = _parse_yahoo_chart(resp.json())
    if len(hist) < 2:
        return None
    last, prev = hist[-1], hist[-2]
    return {
        "open": last["open"],
        "high": last["high"],
        "low": last["low"],
        "close": last["close"],
        "change": round(last["close"] - prev["close"], 2),
        "volume_shares": last["volume"] * 1000,  # _parse_yahoo_chart 的 volume 為張
        "turnover": last["close"] * last["volume"] * 1000,
    }


def _load_yahoo_screener():
    """以多執行緒對精選清單逐檔抓 Yahoo 報價，組成選股清單。"""

    def task(item):
        code, name = item
        try:
            quote = _fetch_yahoo_quote(code)
        except Exception:  # noqa: BLE001 - 單檔失敗略過即可
            return None
        return {"code": code, "name": name, **quote} if quote else None

    rows = []
    with ThreadPoolExecutor(max_workers=16) as pool:
        for result in pool.map(task, _UNIVERSE):
            if result:
                rows.append(result)
    return rows


def _one_stock_fundamentals(code):
    """取單一個股基本面（共用全市場 BWIBBU_ALL 快取）。"""
    global _fund_cache, _fund_loaded
    if not _fund_loaded:
        try:
            _fund_cache = _fetch_twse_fundamentals()
        except Exception as exc:  # noqa: BLE001
            print(f"[data_provider] 基本面抓取失敗，留白：{exc}")
            _fund_cache = {}
        _fund_loaded = True
    f = _fund_cache.get(code) or {}
    return {
        "pe": f.get("pe"),
        "pb": f.get("pb"),
        "yield_pct": f.get("yield_pct"),
        "eps_growth": None,
        "roe": None,
    }


def _demo_screener_rows():
    """demo 模式的選股清單：用內建示範股最新一天的量價與法人買賣超。"""
    rows = []
    for profile in _DEMO_PROFILES:
        history = _generate_history(profile)
        last, prev = history[-1], history[-2]
        rows.append({
            "code": profile["code"],
            "name": profile["name"],
            "open": last["open"],
            "high": last["high"],
            "low": last["low"],
            "close": last["close"],
            "change": round(last["close"] - prev["close"], 2),
            "volume_shares": last["volume"] * 1000,
            "turnover": last["close"] * last["volume"] * 1000,
            **_demo_institutional(profile["code"]),
        })
    return rows


# ---------------------------------------------------------------------------
# 對外介面
# ---------------------------------------------------------------------------

_actual_source = "demo"
_last_live_error = None


def load_screener():
    """回傳精選個股（live）或示範股（demo）的單日量價列表。"""
    global _actual_source, _last_live_error
    if DATA_MODE == "live":
        rows = []
        try:
            rows = _load_yahoo_screener()
            if len(rows) < 10:
                raise ValueError(f"Yahoo 僅取得 {len(rows)} 檔，視為抓取失敗")
            _last_live_error = None
        except Exception as exc:  # noqa: BLE001
            _last_live_error = f"{type(exc).__name__}: {exc}"
            print(f"[data_provider] Yahoo 選股抓取失敗，退回 demo：{exc}")
            rows = []
        if rows:
            # 嘗試補上三大法人（雲端通常抓不到，失敗就略過）
            t86 = {}
            try:
                t86 = _parse_t86(_fetch_t86())
            except Exception as exc:  # noqa: BLE001
                print(f"[data_provider] T86 法人資料未取得（雲端正常現象）：{exc}")
            for row in rows:
                inst = t86.get(row["code"])
                if inst:
                    row.update(inst)
            _actual_source = "live"
            return rows
    _actual_source = "demo"
    return _demo_screener_rows()


def last_live_error():
    """回傳最近一次 live 抓取失敗的錯誤訊息（成功或未啟用則為 None）。"""
    return _last_live_error


def load_one_stock(code, name=""):
    """抓單一個股的完整資料（日 K 歷史＋基本面），供個股明細分析使用。"""
    name = name or _NAME_BY_CODE.get(code, code)
    sector = _SECTOR_BY_CODE.get(code, "")

    if DATA_MODE == "live":
        try:
            history = _fetch_yahoo_history(code)
            if len(history) >= 70:
                return {
                    "code": code,
                    "name": name,
                    "sector": sector,
                    "fundamentals": _one_stock_fundamentals(code),
                    "institutional": _one_stock_institutional(code),
                    "news": [],
                    "history": history,
                }
            print(f"[data_provider] {code} 歷史資料不足（{len(history)} 筆）")
        except Exception as exc:  # noqa: BLE001
            print(f"[data_provider] {code} live 明細抓取失敗：{exc}")

    # demo 模式或 live 失敗：若為內建示範股則回傳示範資料
    for profile in _DEMO_PROFILES:
        if profile["code"] == code:
            return _build_demo_stock(profile)
    return None


def reset_caches():
    """清空全市場基本面與法人快取（資料重新整理時呼叫）。"""
    global _fund_cache, _fund_loaded, _t86_cache, _t86_loaded
    _fund_cache = {}
    _fund_loaded = False
    _t86_cache = {}
    _t86_loaded = False


def data_source_label():
    if _actual_source == "live":
        return "即時行情 Yahoo Finance (live)"
    return "內建示範資料 (demo)"
