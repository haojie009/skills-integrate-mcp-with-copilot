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
_deep_cache: dict[str, dict] = {}


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
    _deep_cache.clear()


# ===========================================================================
# 深度投資分析（華爾街分析師觀點，長期基本面）
# ===========================================================================


class DeepAnalysis(BaseModel):
    """華爾街分析師等級的深度投資分析輸出。"""

    summary: str               # 一段話總評
    business_moat: str         # 商業模式與護城河
    moat_score: int            # 護城河強度 1-10
    industry_trend: str        # 產業趨勢
    financial_health: str      # 財務體質（近 5 年）
    financial_trend: Literal["體質轉強", "體質持平", "體質轉弱"]
    valuation: str             # 估值分析
    valuation_verdict: Literal["明顯低估", "合理偏低", "估值合理", "合理偏高", "明顯高估"]
    growth_potential: str      # 未來 5–10 年成長潛力
    bull_case: str             # 多頭論點
    bear_case: str             # 空頭論點
    key_catalysts: str         # 關鍵催化因素
    key_risks: str             # 主要風險
    outlook_short: str         # 短期展望（1 年內）
    outlook_long: str          # 長期展望（5 年以上）
    recommendation: Literal["買入", "持有", "避免"]
    conclusion: str            # 中性結論與理由


_DEEP_SYSTEM_PROMPT = """你是一位華爾街資深股票分析師，擅長對台股個股做機構等級的深度研究。
你會收到一檔台股的基本資訊與目前的技術面摘要，請依你對該公司的了解，
產出一份完整、專業的投資分析報告，涵蓋以下面向：

- business_moat：商業模式與護城河（品牌影響力、網路效應、轉換成本、成本優勢、專利或獨家技術）
- moat_score：護城河強度評分，1–10 的整數
- industry_trend：產業趨勢
- financial_health：以近 5 年角度評估營收成長、淨利趨勢、自由現金流、利潤率、負債水準、ROE
- financial_trend：判斷財務體質是轉強、持平或轉弱
- valuation：估值分析（本益比與同業比較、折現現金流 DCF 概念、產業平均估值）
- valuation_verdict：估值結論（明顯低估／合理偏低／估值合理／合理偏高／明顯高估）
- growth_potential：未來 5–10 年成長潛力（市場規模、產業成長率、擴張機會、新產品、AI／技術優勢）
- bull_case／bear_case：多頭與空頭論點，雙方都要有依據
- key_catalysts：關鍵催化因素
- key_risks：主要風險
- outlook_short／outlook_long：短期（1 年內）與長期（5 年以上）展望
- recommendation：最終建議（買入／持有／避免）
- conclusion：相對中性的結論與理由

重要規範：
- 一律使用繁體中文，專業但易懂，每段控制在 3~6 句。
- 財務數字若引用自你的知識，請說明「依公開資訊推估」，並提醒實際數字以公司最新財報為準
  （你的知識有時效限制，可能非最新）。
- 這是長期投資角度的基本面分析，與短線當沖不同。
- 所有產出僅供教學與研究參考，絕不構成投資建議。"""


def _build_deep_prompt(stock: dict) -> str:
    sc = stock.get("scores") or {}
    weekly = stock.get("weekly") or {}
    sector = stock.get("sector") or "（未分類）"
    return f"""請以華爾街資深分析師的角度，深度分析以下台股個股：

公司：{stock['name']}（{stock['code']}）　產業：{sector}
目前股價：{stock['last_close']}　當日漲跌幅：{stock.get('change_pct', 0)}%
技術面評分：{sc.get('technical', '—')}／100　週線中期趨勢：{weekly.get('trend', '—')}

請依系統設定，產出完整的機構等級深度投資分析報告。"""


def _call_claude_deep(stock: dict) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=AI_MODEL,
        max_tokens=12000,
        thinking={"type": "adaptive"},
        system=_DEEP_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_deep_prompt(stock)}],
        output_format=DeepAnalysis,
    )
    return {
        "available": True,
        "code": stock["code"],
        "name": stock["name"],
        "model": AI_MODEL,
        "analysis": response.parsed_output.model_dump(),
    }


def deep_analyze(stock: dict) -> dict:
    """對單一個股執行華爾街分析師等級的深度投資分析（結果會快取）。"""
    code = stock["code"]
    if code in _deep_cache:
        return _deep_cache[code]

    if not ai_enabled():
        return {
            "available": False,
            "message": "尚未設定 ANTHROPIC_API_KEY，無法使用深度分析。",
        }

    try:
        result = _call_claude_deep(stock)
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "message": f"深度分析呼叫失敗：{exc}"}

    _deep_cache[code] = result
    return result


# ===========================================================================
# 盤前簡報（盤前情報整理 + 風險檢查 + 交易計畫）
# ===========================================================================


class PremarketBriefing(BaseModel):
    """每日盤前簡報的結構化輸出。"""

    summary: str             # 一句話盤前總結
    market_sentiment: str    # 大盤與國際盤前情緒
    key_events: str          # 今日重要財經事件
    bullish_factors: str     # 今日主要利多
    bearish_factors: str     # 今日主要利空
    sector_rotation: str     # 熱門題材與資金流向
    holdings_check: str      # 持股盤前風險檢查
    scenario_plan: str       # 開高／開低／平盤三情境應對
    avoid_mistakes: str      # 今日最需避免的交易錯誤
    discipline_note: str     # 風控與交易紀律提醒


_PREMARKET_SYSTEM_PROMPT = """你是一位資深的台股盤前交易員，同時擔任使用者的風控助理與交易紀律檢查員。
你會收到今天的國際盤前指標、題材族群強弱、使用者的持股與觀察股資料，
請做一份「盤前情報整理 ＋ 風險檢查 ＋ 交易計畫」，涵蓋：

- market_sentiment：大盤與國際盤前情緒（美股、費半、台積電 ADR、匯率、債息、原物料、加密貨幣）
- key_events：今日可能影響台股的重要財經事件（依你的知識列出，並提醒使用者自行查證最新行事曆）
- bullish_factors／bearish_factors：今日主要利多與利空
- sector_rotation：熱門題材與資金可能流向、族群強弱與延續性
- holdings_check：持股盤前風險檢查（技術位階、法人動向、是否接近壓力或跌破支撐、需留意事件）
- scenario_plan：開高、開低、平盤三種情境的應對觀察重點
- avoid_mistakes：今日最需要避免的交易錯誤（追高、過度交易、單一產業過度集中、槓桿）
- discipline_note：風控與交易紀律提醒
- summary：一句話盤前總結

最重要的規範：
- 絕對不要直接叫使用者買進或賣出某一支股票。你的角色是盤前助理與風控，不是報明牌。
- 請改為列出觀察價、支撐、壓力、停損參考，以及加碼／減碼的「條件」，讓使用者自己判斷。
- 一律以保守的風險控管角度分析。
- key_events 若引用自你的知識，請說明可能非最新、需自行查證最新財經行事曆。
- 一律使用繁體中文，專業但易懂，每段控制在 3~6 句。
- 僅供教學與研究參考，不構成投資建議。"""


def _v(value):
    return "—" if value is None else value


def _premarket_stock_line(s):
    return (
        f"  {s['name']}（{s['code']}）：收 {_v(s['last_close'])}（{_v(s['change_pct'])}%）；"
        f"技術評分 {_v(s['technical'])}；週線 {_v(s['weekly'])}；"
        f"RSI {_v(s['rsi'])}；KD {_v(s['kd_k'])}/{_v(s['kd_d'])}；"
        f"三大法人 {_v(s['inst_lots'])} 張；壓力 R1 {_v(s['r1'])}／R2 {_v(s['r2'])}；"
        f"支撐 S1 {_v(s['s1'])}／S2 {_v(s['s2'])}；20日壓力/支撐 {_v(s['res20'])}/{_v(s['sup20'])}；"
        f"參考停損 {_v(s['stop'])}；當日K線 {_v(s['pattern'])}"
    )


def _build_premarket_prompt(markets, themes, holdings, watch):
    mkt_lines = []
    for m in markets:
        if m.get("price") is None:
            mkt_lines.append(f"  {m['name']}：資料暫無")
        else:
            chg = m.get("change_pct") or 0
            mkt_lines.append(f"  {m['name']}：{m['price']}（{chg:+}%）")
    strong = sorted(themes, key=lambda t: t["avg_change"], reverse=True)[:5]
    weak = sorted(themes, key=lambda t: t["avg_change"])[:3]
    strong_txt = "、".join(f"{t['name']}({t['avg_change']:+}%)" for t in strong) or "—"
    weak_txt = "、".join(f"{t['name']}({t['avg_change']:+}%)" for t in weak) or "—"
    holdings_txt = "\n".join(_premarket_stock_line(s) for s in holdings) or "  （使用者未提供持股）"
    watch_txt = "\n".join(_premarket_stock_line(s) for s in watch) or "  （使用者未提供觀察股）"

    return f"""請做今天的台股盤前簡報。

【國際盤前指標（最近收盤）】
{chr(10).join(mkt_lines)}

【題材族群強弱（依成分股當日平均漲跌幅）】
強勢族群：{strong_txt}
弱勢族群：{weak_txt}

【我的持股】
{holdings_txt}

【觀察股】
{watch_txt}

請依系統設定，完成今天的盤前情報整理、風險檢查與交易計畫。"""


def premarket_briefing(markets, themes, holdings, watch):
    """產生每日盤前簡報。"""
    if not ai_enabled():
        return {"available": False, "message": "尚未設定 ANTHROPIC_API_KEY，無法產生盤前簡報。"}
    try:
        import anthropic

        client = anthropic.Anthropic()
        response = client.messages.parse(
            model=AI_MODEL,
            max_tokens=10000,
            thinking={"type": "adaptive"},
            system=_PREMARKET_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": _build_premarket_prompt(markets, themes, holdings, watch),
            }],
            output_format=PremarketBriefing,
        )
        return {
            "available": True,
            "model": AI_MODEL,
            "briefing": response.parsed_output.model_dump(),
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "message": f"盤前簡報產生失敗：{exc}"}
