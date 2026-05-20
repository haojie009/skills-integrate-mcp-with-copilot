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

## 技術棧

- 後端：FastAPI（純 Python 計算指標，無需 numpy／pandas）
- 前端：原生 HTML / CSS / JavaScript（單頁應用）
- 資料：`demo` 內建模擬資料／`live` 串接證交所公開 API

## 本機執行

```bash
pip install -r requirements.txt
uvicorn app:app --app-dir src --reload
```

開啟瀏覽器進入 <http://127.0.0.1:8000> 即可使用。

### 資料來源切換

| 環境變數 `STOCK_DATA_MODE` | 說明 |
| -------------------------- | ---- |
| `demo`（預設）             | 內建可重現的模擬資料，免網路 |
| `live`                     | 透過 `twse.com.tw` 公開 API 抓真實價量與基本面 |

```bash
STOCK_DATA_MODE=live uvicorn app:app --app-dir src
```

> live 模式若遇網路限制或抓取失敗，會自動退回 demo 資料。

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
| GET  | `/api/recommendations?strategy=day\|overnight` | 選股建議排行 |
| GET  | `/api/stock/{code}` | 單一個股完整分析 |
| GET  | `/api/health` | 服務健康檢查 |
| POST | `/api/refresh` | 重新載入並分析資料 |

## 專案結構

```
src/
  app.py             FastAPI 入口與 API 路由
  analysis.py        技術指標、三面向評分、買賣計畫
  data_provider.py   demo／live 資料來源
  static/            前端頁面（index.html / app.js / styles.css）
render.yaml          Render 一鍵部署設定
requirements.txt     Python 相依套件
```

---

&copy; 教學專案 · MIT License
