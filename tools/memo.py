#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
墨墨背单词 · 今日复习情况速查
=======================================================================
用法：
  python tools/memo.py            # 打印人类可读摘要
  python tools/memo.py --json     # 输出 JSON（供 update.py / Agent 消费）

Token 来源（按优先级）：
  1. 环境变量 MAIMEMO_TOKEN
  2. 项目根目录的 .memo_token 文件（已被 .gitignore 排除）

说明：墨墨学习数据接口为 Beta，且需在 App 内开启「自动同步」；
      若当日未打开 App 初始化，统计可能不准。
=======================================================================
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://open.maimemo.com/open/api/v1"
CN = timezone(timedelta(hours=8))


def get_token() -> str:
    tok = (os.environ.get("MAIMEMO_TOKEN") or "").strip()
    if tok:
        return tok
    f = ROOT / ".memo_token"
    if f.exists():
        v = f.read_text(encoding="utf-8-sig").strip()
        if v:
            return v
    return ""


def call(path: str, body: dict, token: str) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body or {}).encode("utf-8"),
        method="POST",
    )
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def collect(verbose: bool = False) -> dict:
    token = get_token()
    if not token:
        raise RuntimeError("未找到 MAIMEMO_TOKEN：请设置环境变量，或在项目根目录创建 .memo_token 文件")

    out = {}
    errs = []

    # 1) 今日进度
    try:
        p = (call("/study/get_study_progress", {}, token).get("data") or {}).get("progress") or {}
        out["finished"] = int(p.get("finished") or 0)
        out["total"] = int(p.get("total") or 0)
        out["study_minutes"] = round((p.get("study_time") or 0) / 60000.0, 1)
    except Exception as e:
        errs.append("progress: %s" % e)
        out.setdefault("finished", 0)
        out.setdefault("total", 0)
        out.setdefault("study_minutes", 0.0)

    out["remaining"] = max(0, out["total"] - out["finished"])

    # 2) 今日单词明细
    try:
        d = call("/study/get_today_items", {"limit": 1000}, token).get("data") or {}
        items = d.get("today_items") or []
        out["new_words"] = sum(1 for i in items if i.get("is_new"))
        forgotten = [
            i.get("voc_spelling")
            for i in items
            if i.get("is_finished") and i.get("first_response") == "FORGET"
        ]
        out["forgotten_count"] = len(forgotten)
        out["forgotten_sample"] = forgotten[:12]
        out["unfinished_count"] = sum(1 for i in items if not i.get("is_finished"))
    except Exception as e:
        errs.append("today_items: %s" % e)
        out.setdefault("new_words", 0)
        out.setdefault("forgotten_count", 0)
        out.setdefault("forgotten_sample", [])
        out.setdefault("unfinished_count", 0)

    # 3) 计划总词数
    try:
        out["plan_total"] = int(
            (call("/study/query_study_records", {"as_count": True}, token).get("data") or {}).get("count") or 0
        )
    except Exception as e:
        errs.append("records: %s" % e)
        out["plan_total"] = 0

    now = datetime.now(CN)
    out["date"] = now.strftime("%Y-%m-%d")
    out["checked_at"] = now.strftime("%Y-%m-%d %H:%M")
    if errs:
        out["errors"] = errs
    return out


def render(m: dict) -> str:
    total = m.get("total") or 0
    done = m.get("finished") or 0
    pct = round(done / total * 100) if total else 0
    bar_len = 24
    filled = int(bar_len * pct / 100)
    bar = "█" * filled + "░" * (bar_len - filled)

    lines = []
    lines.append("")
    lines.append("  墨墨背单词 · %s" % m.get("checked_at", ""))
    lines.append("  " + "─" * 46)
    lines.append("  今日进度   %s  %d/%d（%d%%）" % (bar, done, total, pct))
    lines.append("  学习时长   %.1f 分钟" % (m.get("study_minutes") or 0))
    lines.append("  今日新词   %d 个" % (m.get("new_words") or 0))
    lines.append("  首答遗忘   %d 个%s" % (
        m.get("forgotten_count") or 0,
        ("  → " + "、".join(m.get("forgotten_sample") or [])) if m.get("forgotten_sample") else "",
    ))
    if m.get("plan_total"):
        lines.append("  计划总量   %d 词" % m["plan_total"])
    if m.get("remaining"):
        lines.append("  ⚠ 还有 %d 词没复习完" % m["remaining"])
    else:
        lines.append("  ✓ 今日复习已全部完成")
    if m.get("errors"):
        lines.append("  ! 部分接口异常：%s" % "; ".join(m["errors"]))
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    as_json = "--json" in sys.argv
    try:
        m = collect()
    except Exception as e:
        if as_json:
            print(json.dumps({"error": str(e)}, ensure_ascii=False))
        else:
            print("× %s" % e)
        sys.exit(1)

    if as_json:
        print(json.dumps(m, ensure_ascii=False, indent=2))
    else:
        print(render(m))


if __name__ == "__main__":
    main()
