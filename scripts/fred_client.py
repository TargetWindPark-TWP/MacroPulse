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
        抓取觀測值。
        - observation_start: 'YYYY-MM-DD'，不設定則抓最近 limit 筆
        - frequency: 'a' 年 | 'q' 季 | 'm' 月 | 'w' 週 | 'd' 日
        - aggregation_method: 'avg' | 'sum' | 'eop'
        """
        params: dict = {
            "series_id":  series_id,
            "sort_order": "asc",
            "limit":      limit,
        }
        if observation_start:
            params["observation_start"] = observation_start
        if frequency:
            params["frequency"]            = frequency
            params["aggregation_method"]   = aggregation_method

        data = self._get("series/observations", params)
        raw  = data.get("observations", [])

        return [
            {
                "date":  o["date"],
                "value": float(o["value"]) if o["value"] not in (".", "") else None,
            }
            for o in raw
        ]

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


# ─── CNN Fear & Greed ─────────────────────────────────────────────────────────

def fetch_cnn_fear_greed() -> Optional[dict]:
    """
    抓取 CNN 恐懼貪婪指數。
    來源：CNN Business 非官方 API（免費，無需 Key）
    """
    try:
        r = requests.get(CNN_FNG, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()

        current = data.get("fear_and_greed", {})
        score   = current.get("score")
        rating  = current.get("rating", "")

        # 歷史數據（過去 2 年）
        historical = data.get("fear_and_greed_historical", {}).get("data", [])
        obs = []
        for pt in historical:
            ts = pt.get("x")
            if ts:
                d   = datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")
                obs.append({"date": d, "value": round(pt.get("y", 0), 1)})

        # 加上今天
        if score is not None:
            obs.append({
                "date":   date.today().isoformat(),
                "value":  round(float(score), 1),
                "rating": rating,
            })

        obs.sort(key=lambda x: x["date"])

        return {
            "series_id":       "CNN_FNG",
            "name":            "CNN Fear & Greed Index",
            "current_score":   round(float(score), 1) if score else None,
            "current_rating":  rating,
            "observations":    obs,
            "fetched_at":      datetime.utcnow().isoformat() + "Z",
        }

    except Exception as e:
        log.warning(f"CNN Fear & Greed fetch failed: {e}")
        return None


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


def compute_mom_pct(obs: list[dict]) -> list[dict]:
    """Month-over-Month % 變化（與上期相比的百分比）"""
    result = []
    for i in range(1, len(obs)):
        cur  = obs[i]
        prev = obs[i - 1]
        if cur["value"] is None or prev["value"] is None or prev["value"] == 0:
            continue
        pct = (cur["value"] - prev["value"]) / abs(prev["value"]) * 100
        result.append({
            "date":  cur["date"],
            "value": round(pct, 3),
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
    抓取單一指標，同時儲存：
      - raw_observations  原始數據（FRED 原始值，如 CPI=332.4）
      - yoy_observations  年增率 YoY%
      - mom_observations  月增率 MoM% 或月變化量
    """
    sid  = indicator["id"]
    log.info(f"  Fetching {sid} ({indicator['name']})...")

    # ── CNN Fear & Greed 特殊處理（已改為 VIXCLS，此段保留相容性）──────────
    if sid == "CNN_FNG":
        result = fetch_cnn_fear_greed()
        if result:
            existing = load_existing(data_dir, sid)
            if force or is_new_data(existing, result["observations"]):
                save_data(data_dir, sid, result)
                latest = result["observations"][-1] if result["observations"] else {}
                return {"id": sid, "status": "updated", "latest": latest}
        return {"id": sid, "status": "skipped"}

    # ── FRED 指標 ──────────────────────────────────────────────────────────────
    transform = indicator.get("transform", "none")
    freq      = indicator.get("frequency", "monthly")

    # 日頻序列聚合為月頻（減少資料量，圖表更清晰）
    fred_frequency = "m" if freq == "daily" else None

    # 抓取原始數據
    raw_obs = client.get_observations(
        series_id = sid,
        limit     = indicator.get("fred_limit", 132),
        frequency = fred_frequency,
    )

    if not raw_obs:
        log.warning(f"  {sid}: 未取得任何數據")
        return {"id": sid, "status": "no_data"}

    # ── 計算三種衍生數據（函數都在同一檔案內，直接呼叫）─────────────────────
    raw_clean = [o for o in raw_obs if o["value"] is not None]

    # 年增率 YoY%
    if freq == "quarterly":
        yoy_obs = compute_yoy_quarterly(raw_clean)
    elif freq in ("monthly", "daily"):
        yoy_obs = compute_yoy(raw_clean)
    else:
        yoy_obs = []

    # 月增率 MoM%（月頻與週頻指標）
    if freq in ("monthly", "weekly", "daily"):
        mom_obs = compute_mom_pct(raw_clean)
    else:
        mom_obs = []

    # 取最新值
    latest_raw = get_latest_value(raw_clean)
    latest_yoy = get_latest_value(yoy_obs)
    latest_mom = get_latest_value(mom_obs)

    # 主要展示數據（維持向下相容）
    transformed = transform_observations(raw_clean, transform, freq)
    latest      = get_latest_value(transformed)

    # ── 比較是否有新數據 ────────────────────────────────────────────────────
    existing = load_existing(data_dir, sid)
    if not force and not is_new_data(existing, raw_clean):
        log.info(f"  {sid}: 無新數據，跳過")
        return {"id": sid, "status": "no_new_data", "latest": latest}

    # ── 儲存 ────────────────────────────────────────────────────────────────
    payload = {
        "series_id":  sid,
        "name":       indicator["name"],
        "name_en":    indicator.get("name_en", ""),
        "category":   indicator["category"],
        "unit":       indicator["unit"],
        "raw_unit":   indicator.get("raw_unit", ""),
        "frequency":  freq,
        "transform":  transform,
        "source":     indicator.get("source", "FRED"),

        # 原始數據
        "raw_observations":   raw_clean[-132:],
        "latest_raw_date":    latest_raw["date"]  if latest_raw else "",
        "latest_raw_value":   latest_raw["value"] if latest_raw else None,

        # 年增率
        "yoy_observations":   yoy_obs[-120:],
        "latest_yoy_date":    latest_yoy["date"]  if latest_yoy else "",
        "latest_yoy_value":   latest_yoy["value"] if latest_yoy else None,

        # 月增率（或週變化）
        "mom_observations":   mom_obs[-120:],
        "latest_mom_date":    latest_mom["date"]  if latest_mom else "",
        "latest_mom_value":   latest_mom["value"] if latest_mom else None,

        # 主要展示數據（向下相容）
        "observations":       transformed,
        "latest_date":        latest["date"]  if latest else "",
        "latest_value":       latest["value"] if latest else None,

        "fetched_at":         datetime.utcnow().isoformat() + "Z",
        "count":              len(raw_clean),
    }

    save_data(data_dir, sid, payload)
    log.info(
        f"  {sid}: ✓ 原始={latest_raw['value'] if latest_raw else 'N/A'} "
        f"({indicator.get('raw_unit','')})  "
        f"YoY={latest_yoy['value'] if latest_yoy else 'N/A'}%  "
        f"MoM={latest_mom['value'] if latest_mom else 'N/A'}%  "
        f"({latest_raw['date'] if latest_raw else ''})"
    )
    return {"id": sid, "status": "updated", "latest": latest}
