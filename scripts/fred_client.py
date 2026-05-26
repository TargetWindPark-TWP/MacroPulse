"""
MacroPulse — FRED API Client + CNN Fear & Greed Fetcher
免費資料來源：
  - FRED (St. Louis Fed) — 所有美國總經指標，免費 API，120 req/min
  - CNN Business unofficial API — Fear & Greed Index
"""
from __future__ import annotations
import os, json, time, logging, requests
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

FRED_BASE = "https://api.stlouisfed.org/fred"
CNN_FNG   = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
HEADERS   = {
    "User-Agent": "MacroPulse/1.0 (github.com; economic-research-bot)",
    "Accept": "application/json",
}


# ─── FRED Client ──────────────────────────────────────────────────────────────

class FREDClient:
    def __init__(self, api_key: str, rate_limit_delay: float = 0.6):
        if not api_key:
            raise ValueError("FRED_API_KEY is required. Free signup: https://fredaccount.stlouisfed.org/")
        self.api_key = api_key
        self.delay   = rate_limit_delay  # 最多 ~100 req/min，安全邊際
        self._last_call = 0.0

    def _get(self, endpoint: str, params: dict) -> dict:
        """Rate-limited GET request to FRED API."""
        # 避免超過速率限制
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

        params["api_key"]   = self.api_key
        params["file_type"] = "json"
        url = f"{FRED_BASE}/{endpoint}"

        for attempt in range(3):
            try:
                r = requests.get(url, params=params, headers=HEADERS, timeout=30)
                self._last_call = time.time()
                r.raise_for_status()
                data = r.json()
                if "error_message" in data:
                    raise ValueError(f"FRED API error: {data['error_message']}")
                return data
            except requests.exceptions.RequestException as e:
                if attempt == 2:
                    raise
                wait = 2 ** attempt
                log.warning(f"Attempt {attempt+1} failed ({e}), retrying in {wait}s...")
                time.sleep(wait)

    def get_series_info(self, series_id: str) -> dict:
        """取得序列的 metadata（名稱、單位、最新公布日期）"""
        data = self._get("series", {"series_id": series_id})
        s = data["seriess"][0]
        return {
            "id":           s["id"],
            "title":        s["title"],
            "units":        s["units"],
            "frequency":    s["frequency"],
            "observation_start": s["observation_start"],
            "observation_end":   s["observation_end"],
            "last_updated": s["last_updated"],
        }

    def get_observations(
      self,
      series_id: str,
      observation_start: Optional[str] = None,
      limit: int = 120,
      frequency: Optional[str] = None,
      aggregation_method: str = "avg",
    ) -> list[dict]:
      """
      抓取最新 limit 筆觀測值。
      策略：用 sort_order=desc 從最新往舊抓，取得後倒轉為升序供圖表使用。
      """
      params: dict = {
        "series_id":     series_id,
        "sort_order":    "desc",                       # 最新的先回傳
        "limit":         limit,
        "observation_end": date.today().isoformat(),   # 確保抓到今天為止
      }
      # 注意：不設 observation_start，讓 FRED 回傳最新的 limit 筆
      if frequency:
        params["frequency"]          = frequency
        params["aggregation_method"] = aggregation_method

      data = self._get("series/observations", params)
      raw  = data.get("observations", [])

      observations = [
          {
              "date":  o["date"],
              "value": float(o["value"]) if o["value"] not in (".", "") else None,
          }
          for o in raw
      ]

      # ← 關鍵：倒轉回升序（舊→新），YoY 計算和圖表才正確
      return list(reversed(observations))

    def get_release_dates(self, days_back: int = 7) -> list[dict]:
        """
        查詢最近幾天有哪些數據發布（用來判斷今天是否需要抓取）。
        回傳：[{"release_id": ..., "release_name": ..., "date": "YYYY-MM-DD"}, ...]
        """
        since = (date.today() - timedelta(days=days_back)).isoformat()
        data  = self._get("releases/dates", {
            "realtime_start": since,
            "realtime_end":   date.today().isoformat(),
            "include_release_dates_with_no_data": "true",
        })
        return data.get("release_dates", [])


# ─── Data Processing ──────────────────────────────────────────────────────────

def compute_yoy(obs: list[dict]) -> list[dict]:
    """Year-over-Year % 變化（適用月頻序列，需 12 筆基期）"""
    result = []
    for i in range(12, len(obs)):
        cur  = obs[i]
        prev = obs[i - 12]
        if cur["value"] is None or prev["value"] is None or prev["value"] == 0:
            continue
        pct = (cur["value"] - prev["value"]) / abs(prev["value"]) * 100
        result.append({"date": cur["date"], "value": round(pct, 3)})
    return result


def compute_yoy_quarterly(obs: list[dict]) -> list[dict]:
    """Year-over-Year % 變化（季頻序列，4 筆基期）"""
    result = []
    for i in range(4, len(obs)):
        cur  = obs[i]
        prev = obs[i - 4]
        if cur["value"] is None or prev["value"] is None or prev["value"] == 0:
            continue
        pct = (cur["value"] - prev["value"]) / abs(prev["value"]) * 100
        result.append({"date": cur["date"], "value": round(pct, 3)})
    return result


def compute_mom_change(obs: list[dict]) -> list[dict]:
    """Month-over-Month 絕對變化（適用 NFP 等月增量指標）"""
    result = []
    for i in range(1, len(obs)):
        cur  = obs[i]
        prev = obs[i - 1]
        if cur["value"] is None or prev["value"] is None:
            continue
        result.append({
            "date":  cur["date"],
            "value": round(cur["value"] - prev["value"], 3),
        })
    return result


def transform_observations(obs: list[dict], transform: str, frequency: str = "monthly") -> list[dict]:
    """根據設定的 transform 轉換數據"""
    clean = [o for o in obs if o["value"] is not None]
    if transform == "yoy":
        if frequency == "quarterly":
            return compute_yoy_quarterly(clean)
        return compute_yoy(clean)
    elif transform == "mom_change":
        return compute_mom_change(clean)
    elif transform == "thousands":
        return [{"date": o["date"], "value": round(o["value"] / 1000, 1)} for o in clean]
    else:  # none / raw
        return clean


def get_latest_value(obs: list[dict]) -> Optional[dict]:
    """取得最新的非 None 觀測值"""
    for o in reversed(obs):
        if o.get("value") is not None:
            return o
    return None


# ─── Persistence ──────────────────────────────────────────────────────────────

def load_existing(data_dir: Path, series_id: str) -> Optional[dict]:
    """載入既有的本地數據檔"""
    path = data_dir / f"{series_id}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def save_data(data_dir: Path, series_id: str, payload: dict) -> Path:
    """儲存數據到 JSON 檔案"""
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / f"{series_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def is_new_data(existing: Optional[dict], observations: list[dict]) -> bool:
    """比較是否有新的觀測值（避免重複寫入）"""
    if not existing:
        return True
    existing_latest = existing.get("latest_date", "")
    new_latest = observations[-1]["date"] if observations else ""
    return new_latest > existing_latest


# ─── Main Fetch Orchestrator ──────────────────────────────────────────────────

def fetch_indicator(
    client: FREDClient,
    indicator: dict,
    data_dir: Path,
    start_date: Optional[str] = None,
    force: bool = False,
) -> dict:
    """
    抓取單一指標、處理轉換、儲存結果。
    回傳 summary dict。
    """
    sid = indicator["id"]
    log.info(f"  Fetching {sid} ({indicator['name']})...")

    # CNN Fear & Greed 特殊處理
    if sid == "CNN_FNG":
        result = fetch_cnn_fear_greed()
        if result:
            existing = load_existing(data_dir, sid)
            if force or is_new_data(existing, result["observations"]):
                save_data(data_dir, sid, result)
                latest = result["observations"][-1] if result["observations"] else {}
                return {"id": sid, "status": "updated", "latest": latest}
        return {"id": sid, "status": "skipped"}

    # FRED 指標
    # 自動計算 start_date（取得足夠的基期數據）
    transform = indicator.get("transform", "none")
    freq      = indicator.get("frequency", "monthly")

    if not start_date:
        if freq == "quarterly":
            start_date = (date.today() - timedelta(days=365 * 22)).isoformat()
        elif freq in ("daily", "weekly"):
            start_date = (date.today() - timedelta(days=365 * 3)).isoformat()
        else:
            start_date = (date.today() - timedelta(days=365 * 12)).isoformat()

    # 日頻 → 聚合為月頻（減少數據量，圖表更清晰）
    fred_frequency = None
    if freq == "daily":
        fred_frequency = "m"  # 月均值

    raw_obs = client.get_observations(
        series_id          = sid,
        observation_start  = start_date,
        limit              = indicator.get("fred_limit", 120),
        frequency          = fred_frequency,
    )

    transformed = transform_observations(raw_obs, transform, freq)
    latest      = get_latest_value(transformed)

    # 比較是否有新數據
    existing = load_existing(data_dir, sid)
    if not force and not is_new_data(existing, transformed):
        log.info(f"  {sid}: 無新數據，跳過")
        return {"id": sid, "status": "no_new_data", "latest": latest}

    # 儲存
    payload = {
        "series_id":   sid,
        "name":        indicator["name"],
        "name_en":     indicator.get("name_en", ""),
        "category":    indicator["category"],
        "unit":        indicator["unit"],
        "frequency":   freq,
        "transform":   transform,
        "source":      indicator.get("source", "FRED"),
        "raw_observations":  raw_obs[-60:],    # 保留最近 60 筆原始值
        "observations":      transformed,       # 轉換後（用於圖表）
        "latest_date":       latest["date"] if latest else "",
        "latest_value":      latest["value"] if latest else None,
        "fetched_at":        datetime.utcnow().isoformat() + "Z",
        "count":             len(transformed),
    }

    save_data(data_dir, sid, payload)
    log.info(f"  {sid}: ✓ 最新 {latest['date']} = {latest['value']} {indicator['unit']}")
    return {"id": sid, "status": "updated", "latest": latest}
