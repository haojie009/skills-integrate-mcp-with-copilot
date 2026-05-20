"""
台股當沖／隔日沖選股助手 API

結合「技術面 + 基本面 + 消息面」對台股個股評分，
並依當沖（day）與隔日沖（overnight）兩種策略給出進出場價位與時間建議。

啟動方式：
    cd src && uvicorn app:app --reload

資料來源以環境變數 STOCK_DATA_MODE 控制（demo / live），預設 demo。

──────────────────────────────────────────────────────────────────────────
⚠️  風險聲明
    本系統所有評分、訊號與買賣計畫皆由公開資料與量化規則自動產生，
    僅供教學與研究參考，不構成任何投資建議或買賣要約。
    當沖與隔日沖屬高風險交易，可能造成大幅虧損，請自行評估並承擔風險。
──────────────────────────────────────────────────────────────────────────
"""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

import analysis
import data_provider

app = FastAPI(
    title="台股當沖／隔日沖選股助手",
    description="以技術面、基本面、消息面綜合評分，提供當沖與隔日沖參考訊號（非投資建議）",
    version="1.0.0",
)

current_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=os.path.join(current_dir, "static")), name="static")

DISCLAIMER = (
    "本系統評分與買賣計畫由公開資料及量化規則自動產生，僅供教學研究參考，"
    "不構成投資建議。當沖／隔日沖屬高風險交易，請自行評估並承擔盈虧。"
)

# 啟動時載入並分析一次，結果快取於記憶體
_analyzed: list[dict] = []


def _refresh():
    global _analyzed
    stocks = data_provider.load_stocks()
    _analyzed = [analysis.analyze_stock(s) for s in stocks]
    return _analyzed


_refresh()


def _as_of() -> str:
    if _analyzed:
        return _analyzed[0]["history"][-1]["date"]
    return ""


def _top_signals(result: dict, limit: int = 4) -> list:
    """挑出最具代表性的訊號（技術面優先，多空交錯呈現）。"""
    picked = []
    for face in ("technical", "news", "fundamental"):
        for sig in result["signals"][face]:
            if sig[0] in ("多", "空"):
                picked.append({"face": face, "side": sig[0], "text": sig[1]})
    return picked[:limit]


@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "stocks": len(_analyzed), "data_source": data_provider.data_source_label()}


@app.get("/api/recommendations")
def recommendations(strategy: str = "day"):
    """依策略回傳排序後的選股建議。strategy = day（當沖）｜overnight（隔日沖）。"""
    if strategy not in ("day", "overnight"):
        raise HTTPException(status_code=400, detail="strategy 僅接受 day 或 overnight")

    items = []
    for r in _analyzed:
        plan = r["plans"][strategy]
        items.append({
            "code": r["code"],
            "name": r["name"],
            "sector": r["sector"],
            "last_close": r["last_close"],
            "change_pct": r["change_pct"],
            "score": r["scores"][strategy],
            "scores": r["scores"],
            "action": plan["action"],
            "actionable": plan["actionable"],
            "plan": plan,
            "top_signals": _top_signals(r),
        })
    items.sort(key=lambda x: x["score"], reverse=True)
    for rank, item in enumerate(items, start=1):
        item["rank"] = rank

    return {
        "strategy": strategy,
        "strategy_name": "當沖" if strategy == "day" else "隔日沖",
        "data_source": data_provider.data_source_label(),
        "as_of": _as_of(),
        "disclaimer": DISCLAIMER,
        "recommendations": items,
    }


@app.get("/api/stock/{code}")
def stock_detail(code: str):
    """單一個股完整分析：三大面向訊號、指標、新聞與兩種策略計畫。"""
    for r in _analyzed:
        if r["code"] == code:
            return {"disclaimer": DISCLAIMER, "as_of": _as_of(), **r}
    raise HTTPException(status_code=404, detail=f"查無代號 {code} 的個股")


@app.post("/api/refresh")
def refresh():
    """重新載入並分析資料（live 模式會重新抓取證交所資料）。"""
    _refresh()
    return {"status": "refreshed", "stocks": len(_analyzed), "as_of": _as_of()}
