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


def _get_screener() -> list:
    """取得（並快取）依當沖適合度排序的個股清單。"""
    global _screener_cache
    if _screener_cache is None:
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
    rows = _get_screener()
    return {
        "status": "ok",
        "commit": os.environ.get("RENDER_GIT_COMMIT", "unknown")[:7],
        "mode": data_provider.DATA_MODE,
        "data_source": data_provider.data_source_label(),
        "screener_stocks": len(rows),
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


@app.get("/api/ai-analysis/{code}")
def ai_analysis(code: str, name: str = ""):
    """對指定個股執行 Claude 多代理 AI 分析（需設定 ANTHROPIC_API_KEY）。"""
    result = _get_detail(code, name)
    if result is None:
        raise HTTPException(status_code=404, detail=f"查無代號 {code}")
    return {"disclaimer": DISCLAIMER, **ai_advisor.analyze(result)}


@app.post("/api/refresh")
def refresh():
    """清空快取，下次請求會重新掃描與分析。"""
    global _screener_cache
    _screener_cache = None
    _detail_cache.clear()
    ai_advisor.clear_cache()
    data_provider.reset_caches()
    return {"status": "refreshed"}
