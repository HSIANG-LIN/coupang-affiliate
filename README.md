# 🔥 酷澎分潤自動化系統

Coupang Affiliate Automation Hub — 跨平台比價・自動掃描・Threads 文案生成・零 Token 自動化

## 🚀 功能

| 功能 | 說明 | 排程 |
|------|------|------|
| 🎯 自動價格掃描 | 掃金盒子 + 追蹤商品，低點自動推播 | 每天 08:00 |
| 🔥 每日好康速報 | 跨平台比價 10 個熱門品項 | 每天 09:00 |
| ⚖️ 跨平台比價 | 酷澎 / momo / 蝦皮 / PChome 即時比價 | 手動 + 自動 |
| 🔍 高佣商品挖掘 | 掃 25 關鍵字找高分潤率商品 | 每週日 21:00 |
| 📈 每週總結 | 價格變化 + 低點 + 比價統計 | 每週日 20:00 |
| 📝 Threads 文案 | 價格低點自動生成可複製文案 | 即時 |
| 📊 Dashboard | 金盒子・搜尋・文案・追蹤・比價・歷史 | localhost:8512 |

## 🏗 架構

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Coupang    │     │    momo      │     │  Shopee /   │
│  Partners   │     │  JSON-LD     │     │  PChome     │
│  API        │     │  (curl)      │     │ (Playwright)│
└──────┬──────┘     └──────┬───────┘     └──────┬──────┘
       │                   │                    │
       └───────────┬───────┴────────────────────┘
                   ▼
        ┌──────────────────┐
        │  coupang_compare  │  跨平台比價引擎
        │  coupang_auto_scan│  自動掃描 + 警示
        │  coupang_discover │  高佣商品挖掘
        └────────┬─────────┘
                 ▼
        ┌──────────────────┐
        │  Hermes Cron     │  no_agent, 零 token
        │  (Telegram 推播)  │
        └──────────────────┘
                 ▼
        ┌──────────────────┐
        │  Streamlit       │  Dashboard (port 8512)
        │  Dashboard       │
        └──────────────────┘
```

## 📦 檔案結構

```
coupang/
├── coupang_api.py          # Coupang Partners API 客戶端
├── coupang_auto_scan.py    # 自動價格掃描 + 低點警示
├── coupang_compare.py      # 跨平台比價引擎
├── coupang_discover.py     # 高佣商品挖掘器
├── coupang_tracker.py      # 價格追蹤核心
├── coupang_dashboard.py    # Streamlit Dashboard
├── coupang_bot.py          # Telegram Bot 介面
├── coupang_promo.py        # Promo queue 管理
├── coupang_dreaming.py     # 每週策略分析
├── coupang_video.py        # 影片產生器
├── index.html              # 首頁 landing page
├── products.json           # 追蹤商品清單
├── price_history.json      # 價格歷史資料
└── .env                    # API keys (不推)
```

## 🛠 安裝

```bash
# 1. Clone
git clone https://github.com/HSIANG-LIN/coupang-affiliate.git
cd coupang-affiliate

# 2. 設定 API keys
cp .env.example .env
# 編輯 .env 填入 Coupang API keys

# 3. 安裝依賴
pip install streamlit requests

# 4. 啟動 Dashboard
streamlit run coupang_dashboard.py --server.port 8512
```

## ⏰ Cron Jobs

所有 cron job 透過 Hermes Agent 管理，使用 `no_agent=True` 模式（純腳本，零 token）。

| Job | Schedule | Script |
|-----|----------|--------|
| 自動價格掃描 | `0 8 * * *` | coupang_auto_scan.py |
| 每日好康速報 | `0 9 * * *` | coupang_daily_deals.py |
| 每週總結 | `0 20 * * 0` | coupang_weekly_report.py |
| 高佣商品挖掘 | `0 21 * * 0` | coupang_discover.py |

## 📝 License

Private — 僅供個人使用
