"""
AI 智能分析層 —— TradingAgents 風格的多代理分析

把本 App 已算好的技術面／基本面／消息面資料餵給 Claude，讓它依序扮演
看多研究員 → 看空研究員 → 交易員 → 風控，產出結構化的短線交易判斷。

需要環境變數 ANTHROPIC_API_KEY；未設定時 analyze() 會回傳 available=False，
不會讓服務崩潰。

⚠️ 所有 AI 產出僅供教學與研究參考，不構成投資建議。
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel

# 依 Anthropic 官方建議，使用最新、最強的 Opus 模型
AI_MODEL = "claude-opus-4-7"

# AI 結果快取：同一檔個股（demo 資料固定）不重複呼叫 LLM，避免重複計費
_cache: dict[str, dict] = {}


class AIAnalysis(BaseModel):
    """多代理分析的結構化輸出。"""

    bull_case: str        # 看多研究員論點
    bear_case: str        # 看空研究員論點
    trader_decision: str  # 交易員綜合判斷
    action: Literal["強烈買進", "買進", "觀望", "偏空避開"]
    confidence: int       # 交易員信心度 0-100
    risk_level: Literal["低", "中", "高", "極高"]
    risk_notes: str       # 風控提醒
    summary: str          # 一句話總結


_SYSTEM_PROMPT = """你是「AI 台股短線決策系統」，運作方式參考 TradingAgents 多代理框架。
你會收到一檔台股的量化分析資料（技術面、基本面、消息面、三大法人買賣超、
週線中期趨勢、近一年歷史回測，以及規則式買賣計畫），請依序扮演以下四個角色，
完成一份「當沖／隔日沖」的短線交易分析：

1. 看多研究員（bull_case）：從提供的資料中，盡力找出做多的理由與有利訊號。
2. 看空研究員（bear_case）：從提供的資料中，盡力找出做空或避開的理由與風險訊號。
3. 交易員（trader_decision／action／confidence）：綜合多空雙方論點，
   針對台股短線（當沖當日了結、隔日沖留倉一晚）情境做出明確操作判斷。
4. 風控（risk_level／risk_notes）：評估這筆短線交易的風險等級與必須注意的事項。

規範：
- 只能根據「使用者提供的資料」推理，嚴禁捏造未提供的數據、新聞或財報。
- 情境固定為台股短線交易，不是長期投資。
- 一律使用繁體中文，語氣專業、簡潔，每段控制在 3~5 句。
- confidence 為 0–100 的整數，代表交易員對此操作判斷的信心。
- summary 為一句話總結（40 字以內）。
- 你的所有產出僅供教學與研究參考，絕不構成投資建議。"""


def ai_enabled() -> bool:
    """是否已設定 API 金鑰。"""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _fmt(value, suffix=""):
    return "—" if value is None else f"{value}{suffix}"


def _build_user_prompt(stock: dict) -> str:
    """把單一個股的完整分析結果整理成餵給 LLM 的文字。"""
    ind = stock["indicators"]
    sc = stock["scores"]
    piv = stock["levels"]["pivot"]
    sr = stock["levels"]["support_resistance"]
    fund = stock["fundamentals"]
    kd = ind.get("kd")
    macd = ind.get("macd")
    dmi = ind.get("dmi")
    obv = ind.get("obv")
    obv_txt = {"up": "走高", "down": "走低", "flat": "持平"}.get(
        obv["trend"] if obv else "", "—")
    day = stock["plans"]["day"]
    overnight = stock["plans"]["overnight"]

    def sig_lines(items):
        return "\n".join(f"  ({s[0]}) {s[1]}" for s in items) if items else "  （無）"

    news_lines = "\n".join(
        f"  ({'利多' if n['sentiment'] > 0 else '利空' if n['sentiment'] < 0 else '中性'}) {n['title']}"
        for n in stock["news"]
    ) or "  （近期無明顯新聞）"

    inst = stock.get("institutional")
    if inst:
        inst_text = (
            f"外資 {inst['foreign_lots']:+,} 張、投信 {inst['trust_lots']:+,} 張、"
            f"自營商 {inst['dealer_lots']:+,} 張；三大法人合計 {inst['inst_lots']:+,} 張"
        )
    else:
        inst_text = "（無三大法人資料）"

    weekly = stock.get("weekly") or {}
    weekly_text = f"週線中期趨勢：{weekly.get('trend', '—')}"

    bt = stock.get("backtest") or {}
    if bt.get("trades"):
        bt_text = (
            f"近一年回測（隔日沖訊號）：符合進場條件 {bt['trades']} 次，"
            f"隔日收紅勝率 {bt['win_rate']}%，平均報酬 {bt['avg_return']}%，"
            f"最佳 {bt['best']}%／最差 {bt['worst']}%"
        )
    else:
        bt_text = "近一年回測：樣本不足，無法評估"

    return f"""個股：{stock['name']}（{stock['code']}）　產業：{stock['sector']}
最新收盤：{stock['last_close']}　當日漲跌幅：{stock['change_pct']}%

【綜合評分 0-100】
技術面 {sc['technical']}｜基本面 {sc['fundamental']}｜消息面 {sc['news']}
當沖策略評分 {sc['day']}｜隔日沖策略評分 {sc['overnight']}

【技術指標】
MA5/10/20/60：{_fmt(ind['ma5'])} / {_fmt(ind['ma10'])} / {_fmt(ind['ma20'])} / {_fmt(ind['ma60'])}
RSI(14)：{_fmt(ind['rsi14'])}　KD：{_fmt(kd['k'] if kd else None)} / {_fmt(kd['d'] if kd else None)}　MACD柱：{_fmt(macd['hist'] if macd else None)}
乖離率(10)：{_fmt(ind['bias10'], '%')}　威廉%R：{_fmt(ind['williams_r'])}　CCI：{_fmt(ind['cci20'])}
ADX：{_fmt(dmi['adx'] if dmi else None)}（+DI {_fmt(dmi['plus_di'] if dmi else None)} / -DI {_fmt(dmi['minus_di'] if dmi else None)}）　OBV趨勢：{obv_txt}
量能比：{_fmt(ind['vol_ratio'], '倍')}　ATR(14)：{_fmt(ind['atr14'])}
當日K線型態：{stock['pattern']['text']}
20日壓力/支撐：{sr['resistance']} / {sr['support']}
樞紐點 R2/R1/P/S1/S2：{piv['r2']} / {piv['r1']} / {piv['pivot']} / {piv['s1']} / {piv['s2']}

【技術面訊號】
{sig_lines(stock['signals']['technical'])}

【基本面】
本益比：{_fmt(fund.get('pe'))}　股價淨值比：{_fmt(fund.get('pb'))}　EPS年增：{_fmt(fund.get('eps_growth'), '%')}　殖利率：{_fmt(fund.get('yield_pct'), '%')}　ROE：{_fmt(fund.get('roe'), '%')}
{sig_lines(stock['signals']['fundamental'])}

【消息面新聞】
{news_lines}

【三大法人買賣超（最近交易日，單位：張，正為買超、負為賣超）】
{inst_text}

【中期趨勢與歷史回測】
{weekly_text}
{bt_text}

【規則式買賣計畫（系統量化規則自動產生，供你參考）】
當沖：{day['action']}　進場 {day['entry_low']}~{day['entry_high']}　停利 {day['target']}　停損 {day['stop']}
隔日沖：{overnight['action']}　進場 {overnight['entry_low']}~{overnight['entry_high']}　停利 {overnight['target']}　停損 {overnight['stop']}

請依系統設定，完成這檔個股的多代理短線交易分析。"""


def _call_claude(stock: dict) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=AI_MODEL,
        max_tokens=8000,
        thinking={"type": "adaptive"},  # 深度推理，提升判斷精準度
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_prompt(stock)}],
        output_format=AIAnalysis,
    )
    parsed: AIAnalysis = response.parsed_output
    return {
        "available": True,
        "code": stock["code"],
        "name": stock["name"],
        "model": AI_MODEL,
        "analysis": parsed.model_dump(),
    }


def analyze(stock: dict) -> dict:
    """對單一個股執行 AI 多代理分析（結果會快取，避免重複計費）。"""
    code = stock["code"]
    if code in _cache:
        return _cache[code]

    if not ai_enabled():
        return {
            "available": False,
            "message": "尚未設定 ANTHROPIC_API_KEY，無法使用 AI 分析。"
            "請在 Render 服務的 Environment 分頁新增此環境變數後重新部署。",
        }

    try:
        result = _call_claude(stock)
    except Exception as exc:  # noqa: BLE001 - 任何失敗都回報前端，不讓服務崩潰
        return {"available": False, "message": f"AI 分析呼叫失敗：{exc}"}

    _cache[code] = result
    return result


def clear_cache() -> None:
    """清空 AI 結果快取（資料重新載入時呼叫）。"""
    _cache.clear()
