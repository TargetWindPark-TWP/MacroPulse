"""
MacroPulse — 主執行腳本
用法：
  python scripts/run.py                    # 自動判斷模式
  python scripts/run.py --mode daily       # 只抓取每日指標
  python scripts/run.py --mode monthly     # 只抓取月頻指標
  python scripts/run.py --mode fetch-all   # 強制抓取所有指標
  python scripts/run.py --force            # 忽略快取
"""
from __future__ import annotations
import os, sys, json, logging, argparse
from datetime import date, datetime
from pathlib import Path

import yaml

# 加入 scripts/ 到路徑
sys.path.insert(0, str(Path(__file__).parent))
from fred_client import FREDClient, fetch_indicator, load_existing, save_data
from report_generator import generate_daily_report, generate_weekly_report, generate_monthly_report, write_index_json
from excel_generator import generate_excel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

ROOT       = Path(__file__).parent.parent
CONFIG_F   = ROOT / "config" / "indicators.yaml"
DATA_DIR   = ROOT / "data"
REPORT_DIR = ROOT / "reports"
EXCEL_DIR  = ROOT / "reports" / "excel"
DOCS_DIR   = ROOT / "docs" / "data"


# ─── Mode Detection ──────────────────────────────────────────────────────────

def determine_mode() -> str:
    """根據今天的日期自動決定應該抓取哪些頻率的指標。"""
    today = date.today()
    modes = {"daily"}  # 每次都抓每日指標

    # 週四 → 抓週頻指標
    if today.weekday() == 3:
        modes.add("weekly")

    d = today.day
    # 月初 (1-5) → 月度 early_month
    if 1 <= d <= 5:
        modes.add("monthly_early")
    # 月中 (10-16) → 月度 mid_month
    if 10 <= d <= 16:
        modes.add("monthly_mid")
    # 月末 (20-31) → 月度 end_month
    if d >= 20:
        modes.add("monthly_end")
        # 季末月（1/4/7/10月）的月末 → 加上季度
        if today.month in (1, 4, 7, 10):
            modes.add("quarterly")

    log.info(f"日期 {today} → 執行模式：{modes}")
    return ",".join(sorted(modes))


def schedule_matches(indicator: dict, modes: set[str]) -> bool:
    """判斷指標的排程是否在本次執行模式中。"""
    sched = indicator.get("schedule", "monthly")
    freq  = indicator.get("frequency", "monthly")

    # fetch-all 模式 → 全部抓
    if "fetch_all" in modes:
        return True

    mapping = {
        "daily":          "daily",
        "weekly_thursday":"weekly",
        "early_month":    "monthly_early",
        "mid_month":      "monthly_mid",
        "end_month":      "monthly_end",
        "quarterly":      "quarterly",
    }
    target = mapping.get(sched, "monthly_mid")
    return target in modes


# ─── Alert Check ─────────────────────────────────────────────────────────────

def check_alerts(indicators: list[dict], data_dir: Path) -> list[str]:
    """檢查是否有指標觸發警示閾值，回傳警示訊息列表。"""
    alerts = []
    for ind in indicators:
        sid    = ind["id"]
        thres  = ind.get("alert", {})
        if not thres:
            continue

        existing = load_existing(data_dir, sid)
        if not existing:
            continue

        latest_val = existing.get("latest_value")
        if latest_val is None:
            continue
        latest_date = existing.get("latest_date", "")
        name = ind["name"]

        # 殖利率曲線倒掛
        if sid == "T10Y2Y" and "inversion" in thres:
            if latest_val < thres["inversion"]:
                alerts.append(f"🔴 **殖利率倒掛**：{name} = {latest_val:.2f}%（{latest_date}）")
            if "deep_inversion" in thres and latest_val < thres["deep_inversion"]:
                alerts.append(f"🚨 **深度殖利率倒掛**：{name} = {latest_val:.2f}%，衰退前兆！")

        # 通膨過高
        if "high" in thres and latest_val > thres["high"]:
            alerts.append(f"⚠️ **{name}** = {latest_val:.2f}（{latest_date}）> 警示水位 {thres['high']}")

        # 低於警示
        if "low" in thres and latest_val < thres["low"]:
            alerts.append(f"⚠️ **{name}** = {latest_val:.2f}（{latest_date}）< 警示水位 {thres['low']}")

        # CNN 恐懼貪婪極端值
        if sid == "CNN_FNG":
            if "extreme_fear" in thres and latest_val < thres["extreme_fear"]:
                alerts.append(f"😱 **CNN 極度恐懼**：指數 = {latest_val}（{latest_date}）可能出現潛在買點")
            if "extreme_greed" in thres and latest_val > thres["extreme_greed"]:
                alerts.append(f"🤑 **CNN 極度貪婪**：指數 = {latest_val}（{latest_date}）市場過熱警示")

        # PMI 跌破 50
        if sid == "NAPM":
            if "low" in thres and latest_val < thres["low"]:
                alerts.append(f"📉 **ISM PMI 跌破 50**：{latest_val:.1f}（{latest_date}），製造業進入收縮區間")

        # 就業市場警示
        if sid == "ICSA" and "high" in thres and latest_val > thres["high"]:
            alerts.append(f"👷 **初領失業金偏高**：{latest_val:,.0f} 人（{latest_date}）")

    return alerts


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="MacroPulse Economic Data Tracker")
    parser.add_argument("--mode",  default="", help="執行模式")
    parser.add_argument("--force", action="store_true", help="強制重新抓取")
    args = parser.parse_args()

    # 載入設定
    config = yaml.safe_load(CONFIG_F.read_text(encoding="utf-8"))
    indicators = config["indicators"]

    # 決定模式
    mode_str = args.mode or determine_mode()
    modes    = set(mode_str.replace("-", "_").split(","))
    log.info(f"執行模式：{modes}")

    # 初始化 FRED Client
    api_key = os.environ.get("FRED_API_KEY", "")
    if not api_key:
        log.error("❌ 環境變數 FRED_API_KEY 未設定")
        sys.exit(1)

    client = FREDClient(api_key)

    # 篩選本次需要抓取的指標
    targets = [ind for ind in indicators if schedule_matches(ind, modes)]
    log.info(f"本次抓取 {len(targets)} / {len(indicators)} 個指標")

    # 執行抓取
    DATA_DIR.mkdir(exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(exist_ok=True)

    results, updated_ids = [], []
    for ind in targets:
        try:
            r = fetch_indicator(client, ind, DATA_DIR, force=args.force)
            results.append(r)
            if r["status"] == "updated":
                updated_ids.append(ind["id"])
        except Exception as e:
            log.error(f"  ✗ {ind['id']} 失敗：{e}")
            results.append({"id": ind["id"], "status": "error", "error": str(e)})

    log.info(f"完成：{len(updated_ids)} 個指標有新數據")

    # 生成報告（只有在有新數據時）
    if updated_ids or "fetch_all" in modes:
        all_data = {}
        for ind in indicators:
            existing = load_existing(DATA_DIR, ind["id"])
            if existing:
                all_data[ind["id"]] = existing

        today = date.today()

        # 每日報告（每次都生成）
        if "daily" in modes:
            rpt = generate_daily_report(all_data, indicators, today)
            (REPORT_DIR / f"daily_{today.isoformat()}.md").write_text(rpt, encoding="utf-8")
            (REPORT_DIR / "latest_daily.md").write_text(rpt, encoding="utf-8")
            log.info("✓ 每日報告已生成")

        # 週報（每週五生成）
        if today.weekday() == 4:
            rpt = generate_weekly_report(all_data, indicators, today)
            (REPORT_DIR / f"weekly_{today.isoformat()}.md").write_text(rpt, encoding="utf-8")
            (REPORT_DIR / "latest_weekly.md").write_text(rpt, encoding="utf-8")
            log.info("✓ 週報已生成")

        # 月報（月末生成）
        if today.day >= 28 and today.month != (today.replace(day=28) + __import__("datetime").timedelta(days=4)).month:
            rpt = generate_monthly_report(all_data, indicators, today)
            ym  = today.strftime("%Y-%m")
            (REPORT_DIR / f"monthly_{ym}.md").write_text(rpt, encoding="utf-8")
            (REPORT_DIR / "latest_monthly.md").write_text(rpt, encoding="utf-8")
            log.info("✓ 月報已生成")

        # 更新 GitHub Pages 的 JSON index（供 dashboard 讀取）
        write_index_json(all_data, indicators, DOCS_DIR)
        log.info("✓ Dashboard JSON 已更新")

        # 生成 Excel 報告
        EXCEL_DIR.mkdir(parents=True, exist_ok=True)
        excel_path = generate_excel(all_data, indicators, EXCEL_DIR)
        log.info(f"✓ Excel 報告已生成：{excel_path.name}")

    # 警示檢查
    alert_msgs = check_alerts(indicators, DATA_DIR)
    if alert_msgs:
        alert_content = f"# ⚠️ MacroPulse 總經警示\n\n{date.today().isoformat()}\n\n"
        alert_content += "\n".join(f"- {a}" for a in alert_msgs)
        (REPORT_DIR / ".alerts").write_text(alert_content, encoding="utf-8")
        log.warning(f"發出 {len(alert_msgs)} 個警示")
        for a in alert_msgs:
            log.warning(f"  {a}")
    else:
        # 無警示時清除舊的 alert 檔
        alert_f = REPORT_DIR / ".alerts"
        if alert_f.exists():
            alert_f.unlink()

    # 輸出執行摘要
    summary = {
        "run_at":     datetime.utcnow().isoformat() + "Z",
        "mode":       mode_str,
        "targets":    len(targets),
        "updated":    len(updated_ids),
        "updated_ids":updated_ids,
        "alerts":     len(alert_msgs),
        "errors":     sum(1 for r in results if r["status"] == "error"),
    }
    (DATA_DIR / "_run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info(f"✅ 執行完成：{summary}")


if __name__ == "__main__":
    main()
