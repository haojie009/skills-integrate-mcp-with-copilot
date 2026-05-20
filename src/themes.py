"""
個股題材分類

以人工整理的「題材 → 代表個股」對照表，配合當日量價計算各題材熱度，
並提供全市場成交量排行。

題材為市場常見的概念分類，每個題材僅列代表性個股、非完整名單；
分類屬人工整理，可能與個別認定有出入，僅供參考。
"""

# 題材 → 代表個股代號（皆為上市）
THEMES = {
    "AI 伺服器": ["2317", "2382", "3231", "2356", "2376", "4938", "6669"],
    "晶圓代工": ["2330", "2303", "6770", "5347"],
    "IC 設計": ["2454", "3034", "3443", "3035", "2379", "8016"],
    "半導體封測": ["3711", "2449", "6147", "6239"],
    "散熱": ["3017", "3324", "6230"],
    "航運": ["2603", "2609", "2615", "2606", "5608"],
    "金融": ["2881", "2882", "2891", "2886", "2884", "2892", "2885"],
    "重電綠能": ["1503", "1519", "1513", "1504", "2371"],
    "機器人自動化": ["2049", "1590", "2308"],
    "被動元件": ["2327", "2492", "3026"],
    "面板": ["2409", "3481", "6116"],
    "鋼鐵": ["2002", "2014", "2027", "2031"],
    "生技醫療": ["6446", "1795", "4174"],
    "電動車零組件": ["1536", "2231", "1522"],
}


def _slim(stock):
    """個股精簡資訊（給分類頁顯示用）。"""
    return {
        "code": stock["code"],
        "name": stock["name"],
        "close": stock.get("close"),
        "change_pct": stock.get("change_pct", 0.0),
        "score": stock.get("score", 0),
    }


def build_categories(rows, volume_top=40):
    """依已評分的選股清單組出成交量排行與題材熱度。

    rows 每筆需含 code/name/close/change_pct/turnover_yi/volume_shares/score。
    """
    by_code = {r["code"]: r for r in rows}

    # 成交量排行（依當日成交張數）
    ranked = sorted(rows, key=lambda r: r.get("volume_shares") or 0, reverse=True)
    volume_ranking = [
        {
            **_slim(r),
            "rank": i,
            "volume_lots": round((r.get("volume_shares") or 0) / 1000),
        }
        for i, r in enumerate(ranked[:volume_top], start=1)
    ]

    # 題材熱度（依成分股當日平均漲跌幅排序）
    themes = []
    for name, codes in THEMES.items():
        members = [by_code[c] for c in codes if c in by_code]
        if not members:
            continue
        avg_change = sum(m.get("change_pct", 0.0) for m in members) / len(members)
        turnover = sum(m.get("turnover_yi", 0.0) for m in members)
        up_count = sum(1 for m in members if m.get("change_pct", 0.0) > 0)
        leader = max(members, key=lambda m: m.get("change_pct", 0.0))
        themes.append({
            "name": name,
            "avg_change": round(avg_change, 2),
            "member_count": len(members),
            "up_count": up_count,
            "turnover_yi": round(turnover, 1),
            "leader": _slim(leader),
            "members": sorted(
                (_slim(m) for m in members),
                key=lambda m: m["change_pct"],
                reverse=True,
            ),
        })
    themes.sort(key=lambda t: t["avg_change"], reverse=True)

    return {"volume_ranking": volume_ranking, "themes": themes}
