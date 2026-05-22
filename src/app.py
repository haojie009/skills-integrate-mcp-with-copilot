"""
台股當沖選股雷達 API

掃描全市場上市個股，依「流動性、波動度、動能」挑出最適合當沖的標的；
點選個股可再做技術面／基本面／消息面分析、技術線圖與 Claude AI 多代理判斷。

啟動方式：
    uvicorn app:app --app-dir src --reload

資料來源以環境變數 STOCK_DATA_MODE 控制（live / demo），Render 預設 live。

──────────────────────────────────────────────────────────────────────────
⚠️  風險聲明
    本系統所有評分、訊號與買賣計畫皆由公開資料與量化規則自動產生，
    僅供教學與研究參考，不構成任何投資建議或買賣要約。
    當沖屬高風險交易，可能造成大幅虧損，請自行評估並承擔風險。
──────────────────────────────────────────────────────────────────────────
"""

import os
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse

import ai_advisor
import analysis
import data_provider
import themes


class UTF8JSONResponse(JSONResponse):
    """明確標註 charset=utf-8，避免直接以瀏覽器開啟 API 時中文亂碼。"""

    media_type = "application/json; charset=utf-8"


app = FastAPI(
    title="台股當沖選股雷達",
    description="掃描全市場上市個股，依流動性、波動、動能挑出當沖標的（非投資建議）",
    version="2.0.0",
    default_response_class=UTF8JSONResponse,
)

current_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=os.path.join(current_dir, "static")), name="static")

DISCLAIMER = (
    "本系統評分與買賣計畫由公開資料及量化規則自動產生，僅供教學研究參考，"
    "不構成投資建議。當沖屬高風險交易，請自行評估並承擔盈虧。"
)

# 記憶體快取
_screener_cache: list | None = None   # 排序後的當沖選股清單
_detail_cache: dict = {}              # code -> analyze_stock 結果
_premarket_cache: dict = {}           # holdings|watch -> 盤前簡報
_screener_lock = threading.Lock()     # 避免冷啟動時多個請求重複載入
_markets_cache: dict = {"data": None, "fetched_at": 0.0}
_MARKETS_TTL = 600                    # 全球盤勢快取 10 分鐘


def _get_markets():
    """取得（並快取）國際盤前指標,10 分鐘 TTL,避免每次都打 Yahoo。"""
    now = time.time()
    if _markets_cache["data"] is None or now - _markets_cache["fetched_at"] > _MARKETS_TTL:
        try:
            _markets_cache["data"] = data_provider.load_global_markets()
            _markets_cache["fetched_at"] = now
        except Exception:
            if _markets_cache["data"] is None:
                _markets_cache["data"] = []
    return _markets_cache["data"]


def _get_screener() -> list:
    """取得（並快取）依當沖適合度排序的個股清單。

    載入需逐檔抓 Yahoo（數十秒），故加鎖避免並發重複載入；
    切勿在健康檢查等需快速回應的路徑呼叫。
    """
    global _screener_cache
    if _screener_cache is None:
        with _screener_lock:
            if _screener_cache is None:  # 雙重檢查
                scored = []
                for row in data_provider.load_screener():
                    item = {**row, **analysis.screen_score(row)}
                    item["theme"] = themes.theme_of(item["code"])
                    scored.append(item)
                scored.sort(key=lambda x: x["score"], reverse=True)
                for rank, item in enumerate(scored, start=1):
                    item["rank"] = rank
                _screener_cache = scored
    return _screener_cache


def _get_detail(code: str, name: str = ""):
    """取得（並快取）單一個股的完整分析。查無資料回傳 None。"""
    if code in _detail_cache:
        return _detail_cache[code]
    stock = data_provider.load_one_stock(code, name)
    if stock is None:
        return None
    result = analysis.analyze_stock(stock)
    _detail_cache[code] = result
    return result


@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


@app.get("/api/health")
def health():
    """輕量健康檢查 — 必須立即回應，不可觸發選股載入（Render 健檢逾時 5 秒）。"""
    return {
        "status": "ok",
        "commit": os.environ.get("RENDER_GIT_COMMIT", "unknown")[:7],
        "mode": data_provider.DATA_MODE,
        "finmind": bool(data_provider.FINMIND_TOKEN),
        "data_source": data_provider.data_source_label(),
        "screener_stocks": len(_screener_cache or []),
        "screener_loaded": _screener_cache is not None,
        "live_error": data_provider.last_live_error(),
        "ai_enabled": ai_advisor.ai_enabled(),
    }


@app.get("/api/screener")
def screener(limit: int = 200):
    """全市場當沖選股排行（依當沖適合度由高到低）。"""
    rows = _get_screener()
    return {
        "data_source": data_provider.data_source_label(),
        "mode": data_provider.DATA_MODE,
        "live_error": data_provider.last_live_error(),
        "disclaimer": DISCLAIMER,
        "total": len(rows),
        "stocks": rows[: max(1, limit)],
    }


@app.get("/api/picks")
def picks(top_n: int = 8):
    """盤前精選當沖名單:結合全球盤勢與昨日量價,挑出最值得當沖的前 N 檔。

    每檔含進場/停損/停利計畫,並依族群套用全球隔夜變化(費半、ADR、油、債息...)
    給出今日該優先做多/中性/保守/暫緩做多的方向。
    """
    rows = _get_screener()
    markets = _get_markets()
    bias = analysis.global_bias(markets)
    return {
        "data_source": data_provider.data_source_label(),
        "disclaimer": DISCLAIMER,
        "markets": markets,
        "global_bias": bias,
        "picks": analysis.daytrade_picks(rows, top_n=top_n, markets=markets),
    }


@app.get("/api/categories")
def categories():
    """個股分類：全市場成交量排行與熱門題材。"""
    rows = _get_screener()
    return {
        "data_source": data_provider.data_source_label(),
        "disclaimer": DISCLAIMER,
        **themes.build_categories(rows),
    }


@app.get("/api/stock/{code}")
def stock_detail(code: str, name: str = ""):
    """單一個股完整分析：技術指標、線圖序列、訊號、買賣計畫。"""
    result = _get_detail(code, name)
    if result is None:
        raise HTTPException(status_code=404, detail=f"查無代號 {code}，或歷史資料不足")
    return {"disclaimer": DISCLAIMER, **result}


@app.get("/api/intraday/{code}")
def intraday(code: str):
    """個股當日盤中走勢（Yahoo 1 分 K，約延遲 15–20 分）。"""
    return data_provider.load_intraday(code)


@app.get("/api/ai-analysis/{code}")
def ai_analysis(code: str, name: str = ""):
    """對指定個股執行 Claude 多代理 AI 分析（需設定 ANTHROPIC_API_KEY）。"""
    result = _get_detail(code, name)
    if result is None:
        raise HTTPException(status_code=404, detail=f"查無代號 {code}")
    return {"disclaimer": DISCLAIMER, **ai_advisor.analyze(result)}


@app.get("/api/deep-analysis/{code}")
def deep_analysis(code: str, name: str = ""):
    """對指定個股執行華爾街分析師等級的深度投資分析（需設定 ANTHROPIC_API_KEY）。"""
    result = _get_detail(code, name)
    if result is None:
        raise HTTPException(status_code=404, detail=f"查無代號 {code}")
    return {"disclaimer": DISCLAIMER, **ai_advisor.deep_analyze(result)}


def _summarize_for_briefing(code: str, name: str = ""):
    """把個股分析整理成盤前簡報用的精簡摘要。"""
    d = _get_detail(code, name)
    if d is None:
        return None
    ind = d["indicators"]
    kd = ind.get("kd") or {}
    piv = d["levels"]["pivot"]
    sr = d["levels"]["support_resistance"]
    inst = d.get("institutional") or {}
    return {
        "code": d["code"],
        "name": d["name"],
        "last_close": d["last_close"],
        "change_pct": d["change_pct"],
        "technical": d["scores"]["technical"],
        "weekly": (d.get("weekly") or {}).get("trend", "—"),
        "rsi": ind.get("rsi14"),
        "kd_k": kd.get("k"),
        "kd_d": kd.get("d"),
        "inst_lots": inst.get("inst_lots"),
        "r1": piv["r1"], "r2": piv["r2"], "s1": piv["s1"], "s2": piv["s2"],
        "res20": sr["resistance"], "sup20": sr["support"],
        "stop": d["plans"]["day"]["stop"],
        "pattern": d["pattern"]["text"],
    }


@app.get("/api/premarket")
def premarket(holdings: str = "", watch: str = ""):
    """每日盤前簡報：國際盤前情緒、族群輪動、持股風險檢查與情境計畫。"""
    key = f"{holdings.strip()}|{watch.strip()}"
    if key in _premarket_cache:
        return _premarket_cache[key]

    codes_h = [c.strip() for c in holdings.split(",") if c.strip()][:10]
    codes_w = [c.strip() for c in watch.split(",") if c.strip()][:10]
    screener = _get_screener()
    name_by_code = {s["code"]: s["name"] for s in screener}

    holdings_data = [
        s for c in codes_h
        if (s := _summarize_for_briefing(c, name_by_code.get(c, "")))
    ]
    watch_data = [
        s for c in codes_w
        if (s := _summarize_for_briefing(c, name_by_code.get(c, "")))
    ]

    markets = _get_markets()
    cats = themes.build_categories(screener)
    briefing = ai_advisor.premarket_briefing(
        markets, cats["themes"], holdings_data, watch_data
    )

    result = {
        "disclaimer": DISCLAIMER,
        "markets": markets,
        "holdings": holdings_data,
        "watch": watch_data,
        **briefing,
    }
    _premarket_cache[key] = result
    return result


@app.post("/api/refresh")
def refresh():
    """清空快取，並在背景重新掃描。"""
    global _screener_cache
    _screener_cache = None
    _detail_cache.clear()
    _premarket_cache.clear()
    _markets_cache["data"] = None
    _markets_cache["fetched_at"] = 0.0
    ai_advisor.clear_cache()
    data_provider.reset_caches()
    threading.Thread(target=_get_screener, daemon=True).start()
    return {"status": "refreshed"}


# 啟動時即在背景預先載入選股清單，縮短使用者首次開啟的等待
threading.Thread(target=_get_screener, daemon=True).start()
