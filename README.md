# 台股當沖／隔日沖選股助手

結合 **技術面 ＋ 基本面 ＋ 消息面** 三大面向，對台股個股做量化評分，
並依「當沖」與「隔日沖」兩種策略，告訴你 **買哪支、幾點進場、幾點出場、停利停損設多少**。

> ⚠️ **風險聲明**：本工具所有評分、訊號與買賣計畫皆由公開資料與量化規則自動產生，
> 僅供教學與研究參考，**不構成任何投資建議**。當沖／隔日沖屬高風險交易，
> 可能造成大幅虧損，請務必自行評估並承擔盈虧。

---

## 功能

- **三面向評分（0–100）**
  - 技術面：均線排列、RSI、KD、MACD、布林通道、量能、ATR、乖離率(BIAS)、
    威廉指標(%R)、CCI、DMI/ADX 趨勢強度、OBV 量能潮、樞紐點(Pivot)支撐壓力、K 線型態
  - 基本面：本益比、股價淨值比、EPS 成長率、殖利率、ROE
  - 消息面：以關鍵字對新聞標題做多空情緒評分
- **兩種策略**：當沖（當日沖銷）、隔日沖（留倉一晚），權重各自不同
- **買賣計畫**：自動算出進場區間、停利價、停損價、風險報酬比、進出場時間
- **選股排行**：依綜合評分排序，首選股以金色卡片突顯
- **個股明細**：點任一卡片可看完整指標、訊號與新聞
- **技術線圖**：K 線＋均線＋成交量、MACD、KD 三張連動圖表（lightweight-charts）
- **AI 多代理分析**：參考 [TradingAgents](https://github.com/TauricResearch/TradingAgents)
  的多代理架構，由 Claude 扮演「看多研究員 ／ 看空研究員 ／ 交易員 ／ 風控」
  四個角色，對個股做出短線交易判斷（需設定 `ANTHROPIC_API_KEY`，點開個股時即時執行）

## 技術棧

- 後端：FastAPI（純 Python 計算指標，無需 numpy／pandas）
- 前端：原生 HTML / CSS / JavaScript（單頁應用）
- 圖表：lightweight-charts（K 線／MACD／KD）
- 資料：`live` 真實行情（Yahoo Finance＋證交所）／`demo` 內建模擬資料

## 本機執行

```bash
pip install -r requirements.txt
uvicorn app:app --app-dir src --reload
```

開啟瀏覽器進入 <http://127.0.0.1:8000> 即可使用。

### 資料來源切換

| 環境變數 `STOCK_DATA_MODE` | 說明 |
| -------------------------- | ---- |
| `live`（Render 預設）      | 價量取自 Yahoo Finance、本益比等取自證交所 OpenAPI |
| `demo`                     | 內建可重現的模擬資料，免網路 |

```bash
STOCK_DATA_MODE=demo uvicorn app:app --app-dir src
```

> live 模式下個股若抓取失敗會略過該檔，全部失敗才整體退回 demo。
> EPS 成長率、ROE、新聞不在免費資料來源中，live 模式這幾欄會留白。

## 部署到 Render

本 repo 已內建 `render.yaml`（Render Blueprint），一鍵即可上架：

1. 確認此 repo 已推上 GitHub。
2. 登入 <https://render.com> → 點 **New +** → **Blueprint**。
3. 選擇此 repo，Render 會自動讀取 `render.yaml`。
4. 按下 **Apply**，等 build 完成後即取得對外網址（例如 `https://tw-stock-trading-assistant.onrender.com`）。

若想手動建立 Web Service，設定如下：

| 項目 | 值 |
| ---- | -- |
| Environment  | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app:app --app-dir src --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/api/health` |

> Render 免費方案有對外網路，可把環境變數 `STOCK_DATA_MODE` 設為 `live` 改抓即時資料。

## API

| 方法 | 路徑 | 說明 |
| ---- | ---- | ---- |
| GET  | `/api/screener?limit=200` | 全市場當沖選股排行 |
| GET  | `/api/categories` | 成交量排行與熱門題材分類 |
| GET  | `/api/stock/{code}?name=` | 單一個股完整分析 |
| GET  | `/api/ai-analysis/{code}` | Claude 多代理 AI 分析 |
| GET  | `/api/health` | 服務健康檢查 |
| POST | `/api/refresh` | 清空快取、重新掃描 |

## AI 多代理分析

`/api/ai-analysis/{code}` 會把該個股已算好的技術／基本／消息面資料，
交給 Claude（`claude-opus-4-7`）以 TradingAgents 風格的多代理流程推理：
看多研究員找做多理由 → 看空研究員找風險 → 交易員下判斷 → 風控評估風險等級。

啟用方式：設定環境變數 `ANTHROPIC_API_KEY`。

- 本機：`export ANTHROPIC_API_KEY=sk-ant-...` 後再啟動服務
- Render：到服務的 **Environment** 分頁新增 `ANTHROPIC_API_KEY`，存檔後自動重新部署

未設定金鑰時，App 仍可正常運作，僅 AI 分析區塊會顯示「尚未設定金鑰」。
AI 分析在點開個股時即時呼叫，每檔結果會快取以避免重複計費。

## 專案結構

```
src/
  app.py             FastAPI 入口與 API 路由
  analysis.py        技術指標、三面向評分、買賣計畫
  data_provider.py   demo／live 資料來源
  ai_advisor.py      Claude 多代理 AI 分析層
  static/            前端頁面（index.html / app.js / styles.css）
render.yaml          Render 一鍵部署設定
requirements.txt     Python 相依套件
```

---

&copy; 教學專案 · MIT License
