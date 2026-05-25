# 📊 MacroPulse — 自動化總體經濟指標追蹤

> 免費、全自動，基於 GitHub Actions + FRED API 的美國總體經濟數據追蹤系統。
> 涵蓋 30+ 指標，依各項數據發布頻率自動執行，並生成 Markdown 報告 + GitHub Pages 儀表板。

---

## ✨ 功能特色

| 功能 | 說明 |
|------|------|
| 🤖 **全自動排程** | 依各指標實際發布週期自動觸發（每日/週/月/季） |
| 📊 **30+ 指標** | 通膨、就業、利率、信用、房市、信心、CNN 恐懼貪婪 |
| 📝 **自動報告** | 每日速報 + 週報 + 月報，Markdown 格式 |
| 🌐 **儀表板** | GitHub Pages 免費靜態網頁，圖表互動展示 |
| ⚠️ **智慧警示** | 殖利率倒掛、通膨過高、PMI 跌破 50 等自動發 Issue |
| 💰 **完全免費** | GitHub Actions（公開 repo 無限制） + FRED API（免費） |

---

## 🚀 快速設定（5 分鐘）

### 步驟 1：Fork 此 Repository

點擊右上角 **Fork** 按鈕，建立你自己的副本。

### 步驟 2：申請免費 FRED API Key

1. 前往 [https://fredaccount.stlouisfed.org/login/secure/](https://fredaccount.stlouisfed.org/login/secure/)
2. 免費註冊帳號
3. 登入後 → **My Account** → **API Keys** → **Request API Key**
4. 複製你的 32 位元 API Key

### 步驟 3：設定 GitHub Secret

1. 進入你 Fork 的 repo → **Settings** → **Secrets and variables** → **Actions**
2. 點擊 **New repository secret**
3. Name: `FRED_API_KEY`，Value: 貼上你的 API Key
4. 點擊 **Add secret**

### 步驟 4：啟用 GitHub Pages

1. **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: **main** / **docs** 資料夾
4. 儲存後，幾分鐘內你的儀表板網址就會出現

### 步驟 5：手動觸發第一次執行（可選）

1. 進入 **Actions** → **MacroPulse Economic Tracker**
2. 點擊 **Run workflow**
3. Mode: `fetch-all`，Force: `true`
4. 等待約 3-5 分鐘完成

完成後，`data/` 資料夾會有所有指標的 JSON 數據，`reports/` 會有最新報告。

---

## 📅 排程說明

| 排程 | 時間（台灣時間） | 抓取指標 |
|------|-----------------|----------|
| **每個工作日** | 06:30 | 殖利率、CNN 恐懼貪婪、HY 信用利差 |
| **每週四** | 20:30 | 初次/續領失業救濟金、30年期房貸利率 |
| **月初 1-3 日** | 21:00 | NFP 非農、失業率、ISM PMI |
| **月中 10-16 日** | 21:00 | CPI、PPI、零售銷售、工業生產 |
| **月末 20-31 日** | 21:00 | PCE、個人收支、CCI、新屋銷售 |
| **季末月末** | 21:00 | GDP、信用違約率 |

GitHub Actions 自動判斷當天日期，只抓取當日應公布的指標，避免浪費 API 請求。

---

## 📈 追蹤指標完整清單

### 🔥 通膨指標
| 指標 | FRED Series | 頻率 | 說明 |
|------|------------|------|------|
| CPI | CPIAUCSL | 月 | 消費者物價指數 |
| Core CPI | CPILFESL | 月 | 核心 CPI（食品/能源除外） |
| PCE | PCEPI | 月 | 個人消費支出物價指數 |
| Core PCE | PCEPILFE | 月 | Fed 政策 2% 目標指標 |
| PPI | PPIACO | 月 | 生產者物價指數 |
| WPI/Core PPI | PPIFIS | 月 | 躉售物價指數 |

### 📈 經濟成長
| 指標 | FRED Series | 頻率 |
|------|------------|------|
| Real GDP | GDPC1 | 季 |
| 零售銷售 | RSXFS | 月 |
| 工業生產 | INDPRO | 月 |
| ISM PMI | NAPM | 月 |
| 耐久財訂單 | DGORDER | 月 |

### 👷 勞動市場
| 指標 | FRED Series | 頻率 |
|------|------------|------|
| 非農就業 NFP | PAYEMS | 月 |
| 失業率 | UNRATE | 月 |
| 初次申請失業金 | ICSA | 週 |
| 續領失業救濟金 | CCSA | 週 |
| 平均時薪 | CES0500000003 | 月 |
| JOLTS 職位空缺 | JTSJOL | 月 |

### 🏦 利率與債券
| 指標 | FRED Series | 頻率 |
|------|------------|------|
| Fed Funds Rate | FEDFUNDS | 月 |
| 2年期公債殖利率 | DGS2 | 日 |
| 10年期公債殖利率 | DGS10 | 日 |
| 30年期公債殖利率 | DGS30 | 日 |
| 10Y-2Y 利差 | T10Y2Y | 日 |
| 30年期房貸利率 | MORTGAGE30US | 週 |

### 💭 信心指數
| 指標 | 來源 | 頻率 |
|------|------|------|
| CNN 恐懼貪婪指數 | CNN Business | 日 |
| 密大消費者信心 | UMCSENT (FRED) | 月 |
| Conference Board CCI | CONCCONF (FRED) | 月 |

### ⚠️ 信用與違約
| 指標 | FRED Series | 頻率 |
|------|------------|------|
| 信用卡違約率 | DRCCLACBS | 季 |
| 消費性貸款違約率 | DRCONGACBS | 季 |
| 住宅抵押貸款違約率 | DRSFRMACBS | 季 |
| HY 信用利差 | BAMLH0A0HYM2 | 日 |

### 🏠 房市
| 指標 | FRED Series | 頻率 |
|------|------------|------|
| 新屋開工 | HOUST | 月 |
| 新屋銷售 | HSN1F | 月 |
| 成屋銷售 | EXHOSLUSM495S | 月 |

---

## ⚠️ 智慧警示系統

以下情況會自動在 GitHub 建立 Issue：

| 觸發條件 | 說明 |
|---------|------|
| 10Y-2Y < 0 | 殖利率曲線倒掛（歷史衰退前兆） |
| CPI > 3.0% | 通膨過高警示 |
| Core PCE > 2.5% | Fed 超標警示 |
| ISM PMI < 50 | 製造業進入收縮區間 |
| 初領失業金 > 300K | 就業市場走弱 |
| CNN FNG < 20 | 極度恐懼（潛在買點） |
| CNN FNG > 80 | 極度貪婪（潛在風險） |

---

## 💰 成本分析

| 項目 | 費用 |
|------|------|
| GitHub Actions（公開 repo） | **免費・無限制** |
| FRED API | **免費**（120 req/min，無商業限制） |
| GitHub Pages | **免費** |
| CNN Fear & Greed | **免費**（非官方 API） |
| **總計** | **$0 / 月** |

---

## 📁 專案結構

```
macropulse/
├── .github/workflows/
│   └── macropulse.yml      # GitHub Actions 排程設定
├── config/
│   └── indicators.yaml     # 指標定義（頻率、轉換、警示閾值）
├── scripts/
│   ├── run.py              # 主執行腳本
│   ├── fred_client.py      # FRED API 客戶端
│   ├── report_generator.py # Markdown 報告生成
│   └── determine_mode.py   # 排程模式判斷
├── data/                   # 自動生成的 JSON 數據（git 追蹤）
├── reports/                # 自動生成的 Markdown 報告
├── docs/                   # GitHub Pages 儀表板
│   ├── index.html          # 互動儀表板
│   └── data/               # 儀表板用 JSON
├── requirements.txt
└── README.md
```

---

## 🔧 本地測試

```bash
# 安裝依賴
pip install -r requirements.txt

# 設定 API Key
export FRED_API_KEY="你的32位元Key"

# 抓取所有指標
python scripts/run.py --mode fetch-all --force

# 只抓每日指標
python scripts/run.py --mode daily
```

---

## 📚 延伸：台灣指標

台灣指標由於無法透過統一 API 取得，目前透過官方網站連結追蹤：

| 指標 | 機構 | 網址 |
|------|------|------|
| 景氣對策信號 | 國發會 | [index.ndc.gov.tw](https://index.ndc.gov.tw) |
| CPI/WPI/GDP/失業率 | 主計總處 | [stat.gov.tw](https://www.stat.gov.tw) |
| 外銷訂單/工業生產 | 經濟部 | [moea.gov.tw](https://www.moea.gov.tw) |
| 央行利率/M1b/M2 | 中央銀行 | [cbc.gov.tw](https://www.cbc.gov.tw) |
| NPL 違約率 | 金管會 | [fsc.gov.tw](https://www.fsc.gov.tw) |
| 不動產成交量 | 內政部 | [pip.moi.gov.tw](https://pip.moi.gov.tw) |

---

*MacroPulse — 總體經濟智慧追蹤 | GitHub Actions + FRED API | 完全免費*
