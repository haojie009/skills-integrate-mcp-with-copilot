# 台股當沖／隔日沖選股助手 — 原始碼

FastAPI 應用程式：以技術面、基本面、消息面綜合評分，提供台股當沖／隔日沖參考訊號。

## 檔案

| 檔案 | 說明 |
| ---- | ---- |
| `app.py` | FastAPI 入口與 API 路由 |
| `analysis.py` | 技術指標、三面向評分、買賣計畫產生 |
| `data_provider.py` | 資料來源層（demo 模擬資料／live 證交所 API） |
| `static/` | 前端單頁應用（`index.html`／`app.js`／`styles.css`） |

## 執行

從 repo 根目錄：

```bash
pip install -r requirements.txt
uvicorn app:app --app-dir src --reload
```

- 前端頁面：<http://127.0.0.1:8000>
- API 文件：<http://127.0.0.1:8000/docs>

## API 端點

| 方法 | 端點 | 說明 |
| ---- | ---- | ---- |
| GET  | `/api/recommendations?strategy=day\|overnight` | 選股建議排行 |
| GET  | `/api/stock/{code}` | 單一個股完整分析 |
| GET  | `/api/health` | 健康檢查 |
| POST | `/api/refresh` | 重新載入並分析資料 |

> ⚠️ 所有評分與買賣計畫皆為量化規則自動產生，僅供教學研究，非投資建議。
