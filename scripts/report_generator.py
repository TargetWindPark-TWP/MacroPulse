"""
MacroPulse — 報告生成器
生成 Markdown 格式的每日/週/月報
"""
from __future__ import annotations
import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# ─── Helpers ──────────────────────────────────────────────────────────────────

CAT_LABELS = {
    "inflation": "🔥 通膨指標",
    "growth":    "📈 經濟成長",
    "labor":     "👷 勞動市場",
    "sentiment": "💭 信心指數",
    "rates":     "🏦 利率與債券",
    "credit":    "⚠️ 信用與違約",
    "housing":   "🏠 房市",
}

TREND_ARROW = {
    "up":   "▲",
    "down": "▼",
    "flat": "→",
}


def fmt_val(v, unit="") -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return f"{v:.2f} {unit}".strip()
    return f"{v} {unit}".strip()


def trend_emoji(latest, prev) -> str:
    """判斷趨勢方向"""
    if latest is None or prev is None:
        return "→"
    if latest > prev:
        return "▲"
    elif latest < prev:
        return "▼"
    return "→"


def signal_emoji(series_id: str, value) -> str:
    """根據指標特性回傳紅綠燈 emoji"""
    if value is None:
        return "⚪"
    v = float(value)

    # 殖利率曲線
    if series_id == "T10Y2Y":
        return "🔴" if v < 0 else ("🟡" if v < 0.5 else "🟢")

    # 通膨類指標
    inflation_ids = {"CPIAUCSL", "CPILFESL", "PCEPI", "PCEPILFE", "PPIACO", "PPIFIS"}
    if series_id in inflation_ids:
        return "🔴" if v > 3.5 else ("🟡" if v > 2.5 else "🟢")

    # 失業率
    if series_id == "UNRATE":
        return "🔴" if v > 5 else ("🟡" if v > 4 else "🟢")

    # PMI
    if series_id == "NAPM":
        return "🔴" if v < 48 else ("🟡" if v < 50 else "🟢")

    # CNN Fear & Greed
    if series_id == "CNN_FNG":
        return "😱" if v < 25 else ("😰" if v < 40 else ("😌" if v < 60 else ("😏" if v < 75 else "🤑")))

    # 信用違約率
    credit_ids = {"DRCCLACBS", "DRCONGACBS", "DRSFRMACBS"}
    if series_id in credit_ids:
        return "🔴" if v > 3 else ("🟡" if v > 2 else "🟢")

    return "⚪"


def get_two_latest(observations: list) -> tuple:
    """取最新兩筆有效數值"""
    valid = [o for o in observations if o.get("value") is not None]
    if not valid:
        return None, None
    latest = valid[-1]
    prev   = valid[-2] if len(valid) >= 2 else None
    return latest, prev


# ─── Table Builder ────────────────────────────────────────────────────────────

def build_indicator_table(category: str, indicators: list, all_data: dict) -> str:
    """建立單一類別的 Markdown 表格"""
    cat_inds = [i for i in indicators if i.get("category") == category]
    if not cat_inds:
        return ""

    rows = []
    for ind in cat_inds:
        sid  = ind["id"]
        data = all_data.get(sid)
        if not data:
            rows.append(f"| {ind['name']} | {sid} | — | — | — | — |")
            continue

        obs = data.get("observations", [])
        latest, prev = get_two_latest(obs)

        lv  = latest["value"] if latest else None
        ld  = latest["date"]  if latest else "—"
        pv  = prev["value"]   if prev   else None

        unit  = ind.get("unit", "")
        sig   = signal_emoji(sid, lv)
        trend = trend_emoji(lv, pv)
        diff  = f"{lv - pv:+.2f}" if lv is not None and pv is not None else "—"

        rows.append(
            f"| {sig} {ind['name']} | `{sid}` | **{fmt_val(lv, unit)}** | {diff} | {trend} | {ld} |"
        )

    if not rows:
        return ""

    header = f"### {CAT_LABELS.get(category, category)}\n\n"
    table  = "| 指標 | Series ID | 最新值 | 與前期差 | 趨勢 | 日期 |\n"
    table += "|------|-----------|--------|----------|------|------|\n"
    table += "\n".join(rows) + "\n"
    return header + table + "\n"


# ─── Report Templates ─────────────────────────────────────────────────────────

def generate_daily_report(all_data: dict, indicators: list, today: date) -> str:
    """每日市場數據報告"""
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # 關注每日更新的指標
    daily_ids = {"DGS2", "DGS10", "DGS30", "T10Y2Y", "BAMLH0A0HYM2", "CNN_FNG", "FEDFUNDS"}

    lines = [
        f"# 📊 MacroPulse 每日總經速報",
        f"",
        f"> **{today.isoformat()}** · 自動生成 · 資料來源：FRED (St. Louis Fed) + CNN Business",
        f"",
    ]

    # 殖利率快覽
    lines.append("## 🏦 今日利率與殖利率")
    lines.append("")
    lines.append("| 指標 | 最新值 | 說明 |")
    lines.append("|------|--------|------|")

    rate_map = {
        "FEDFUNDS":     ("Fed Funds Rate",  "聯邦基金利率"),
        "DGS2":         ("2Y Treasury",     "2年期公債殖利率"),
        "DGS10":        ("10Y Treasury",    "10年期公債殖利率"),
        "DGS30":        ("30Y Treasury",    "30年期公債殖利率"),
        "T10Y2Y":       ("10Y−2Y Spread",   "殖利率曲線利差（負值=倒掛）"),
        "BAMLH0A0HYM2": ("HY Spread",       "高收益債信用利差"),
    }
    for sid, (label, note) in rate_map.items():
        d = all_data.get(sid)
        if d:
            obs   = d.get("observations", [])
            l, _  = get_two_latest(obs)
            v     = fmt_val(l["value"] if l else None, d.get("unit", "%"))
            sig   = signal_emoji(sid, l["value"] if l else None)
            lines.append(f"| {sig} **{label}** | {v} | {note} |")

    lines.append("")

    # CNN 恐懼貪婪
    fng = all_data.get("CNN_FNG")
    if fng:
        score  = fng.get("current_score")
        rating = fng.get("current_rating", "")
        sig    = signal_emoji("CNN_FNG", score)
        lines.append(f"## {sig} CNN 恐懼貪婪指數")
        lines.append("")
        lines.append(f"**當前指數：{score}** — *{rating}*")
        lines.append("")
        lines.append("| 範圍 | 評級 |")
        lines.append("|------|------|")
        lines.append("| 0–24 | 😱 Extreme Fear 極度恐懼 |")
        lines.append("| 25–44 | 😰 Fear 恐懼 |")
        lines.append("| 45–55 | 😌 Neutral 中性 |")
        lines.append("| 56–74 | 😏 Greed 貪婪 |")
        lines.append("| 75–100 | 🤑 Extreme Greed 極度貪婪 |")
        lines.append("")

    # 最近更新的其他指標
    lines.append("## 📈 最近公布指標")
    lines.append("")
    for cat in ["inflation", "growth", "labor", "sentiment"]:
        tbl = build_indicator_table(cat, indicators, all_data)
        if tbl:
            lines.append(tbl)

    lines += [
        "---",
        f"*自動生成於 {ts} · [FRED](https://fred.stlouisfed.org) · [CNN Fear & Greed](https://edition.cnn.com/markets/fear-and-greed)*",
    ]
    return "\n".join(lines)


def generate_weekly_report(all_data: dict, indicators: list, today: date) -> str:
    """每週總結報告"""
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    iso = today.isocalendar()
    week_str = f"{iso[0]}-W{iso[1]:02d}"

    lines = [
        f"# 📋 MacroPulse 週報 {week_str}",
        f"",
        f"> {today.isoformat()} · 自動生成",
        f"",
        f"## 本週重點",
        f"",
        f"### 📌 初次申請失業救濟金",
        f"",
    ]

    for sid in ["ICSA", "CCSA"]:
        d = all_data.get(sid)
        if d:
            obs   = d.get("observations", [])
            l, p  = get_two_latest(obs)
            lv    = l["value"] if l else None
            pv    = p["value"] if p else None
            diff  = f"{lv - pv:+,.0f}" if lv and pv else "—"
            ind   = next((i for i in indicators if i["id"] == sid), {})
            name  = ind.get("name", sid)
            lines.append(f"- **{name}**：{lv:,.0f} 人（{l['date'] if l else '—'}），前期差 {diff} 人")

    lines.append("")

    # 完整表格
    lines.append("## 完整指標一覽")
    lines.append("")
    for cat in CAT_LABELS:
        tbl = build_indicator_table(cat, indicators, all_data)
        if tbl:
            lines.append(tbl)

    lines += [
        "---",
        f"*自動生成於 {ts}*",
    ]
    return "\n".join(lines)


def generate_monthly_report(all_data: dict, indicators: list, today: date) -> str:
    """月度深度報告"""
    ts       = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    ym_str   = today.strftime("%Y 年 %m 月")

    lines = [
        f"# 📊 MacroPulse 月報 — {ym_str}",
        f"",
        f"> 自動生成於 {ts}",
        f"",
        f"## 一、通膨現況",
        f"",
    ]

    for sid in ["CPIAUCSL", "CPILFESL", "PCEPI", "PCEPILFE"]:
        d = all_data.get(sid)
        if not d:
            continue
        obs  = d.get("observations", [])
        l, _ = get_two_latest(obs)
        ind  = next((i for i in indicators if i["id"] == sid), {})
        sig  = signal_emoji(sid, l["value"] if l else None)
        lines.append(f"- {sig} **{ind.get('name', sid)}**：{fmt_val(l['value'] if l else None, d.get('unit',''))} （{l['date'] if l else '—'}）")

    lines += ["", "## 二、就業市場", ""]

    for sid in ["PAYEMS", "UNRATE", "ICSA", "CCSA"]:
        d = all_data.get(sid)
        if not d:
            continue
        obs  = d.get("observations", [])
        l, _ = get_two_latest(obs)
        ind  = next((i for i in indicators if i["id"] == sid), {})
        sig  = signal_emoji(sid, l["value"] if l else None)
        lines.append(f"- {sig} **{ind.get('name', sid)}**：{fmt_val(l['value'] if l else None, d.get('unit',''))} （{l['date'] if l else '—'}）")

    lines += ["", "## 三、利率與殖利率曲線", ""]

    for sid in ["FEDFUNDS", "DGS2", "DGS10", "T10Y2Y"]:
        d = all_data.get(sid)
        if not d:
            continue
        obs  = d.get("observations", [])
        l, _ = get_two_latest(obs)
        ind  = next((i for i in indicators if i["id"] == sid), {})
        sig  = signal_emoji(sid, l["value"] if l else None)
        lines.append(f"- {sig} **{ind.get('name', sid)}**：{fmt_val(l['value'] if l else None, d.get('unit',''))} （{l['date'] if l else '—'}）")

    lines += ["", "## 四、完整指標表", ""]

    for cat in CAT_LABELS:
        tbl = build_indicator_table(cat, indicators, all_data)
        if tbl:
            lines.append(tbl)

    lines += [
        "---",
        f"*資料來源：FRED (St. Louis Fed) | 自動生成於 {ts}*",
    ]
    return "\n".join(lines)


# ─── Dashboard JSON ───────────────────────────────────────────────────────────

def write_index_json(all_data: dict, indicators: list, docs_dir: Path) -> None:
    """
    生成 GitHub Pages dashboard 使用的 JSON 彙整檔。
    """
    docs_dir.mkdir(parents=True, exist_ok=True)

    summary = []
    for ind in indicators:
        sid  = ind["id"]
        data = all_data.get(sid)
        if not data:
            continue

        obs        = data.get("observations", [])
        l, p       = get_two_latest(obs)
        latest_val = l["value"] if l else None
        prev_val   = p["value"] if p else None

        summary.append({
            "id":          sid,
            "name":        ind["name"],
            "name_en":     ind.get("name_en", ""),
            "category":    ind["category"],
            "unit":        ind.get("unit", ""),
            "frequency":   ind.get("frequency", ""),
            "latest_date": l["date"] if l else None,
            "latest_value":latest_val,
            "prev_value":  prev_val,
            "change":      round(latest_val - prev_val, 3) if latest_val is not None and prev_val is not None else None,
            "signal":      signal_emoji(sid, latest_val),
            "source":      ind.get("source", "FRED"),
            "updated_at":  data.get("fetched_at", ""),
        })

    # 個別 series 的完整觀測值也存到 docs/data/
    for sid, data in all_data.items():
        obs = data.get("observations", [])
        (docs_dir / f"{sid}.json").write_text(
            json.dumps({"id": sid, "observations": obs[-240:]}, ensure_ascii=False),  # 最近 240 筆
            encoding="utf-8",
        )

    # 彙整 index
    index = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "indicators":   summary,
    }
    (docs_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
