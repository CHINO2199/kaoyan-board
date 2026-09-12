#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日学习记录录入器 · 百日研途看板
=======================================================================
把「当天的口述总结」一次性写进看板数据：

  1. daily_logs        —— 总时长 / 分科时长 / 分时段 / 完成任务 / 复盘 / 明日计划
  2. milestones[].days —— 当天每个任务的完成标记（1=蓝条 / 0=红条）
  3. data.enc          —— 重新加密（密码不落盘、不打屏）

设计要点（都在踩过坑之后固化下来）：
  * **合并而非替换**：`upsert_daily` 与 `upsert_milestone` 对整条记录 / `days` 都是
    「整体替换」，直接调会冲掉线上由 GitHub Actions 写入的 `memo`（墨墨进度）
    以及前几天的 `days`。本脚本自己做合并。
  * **计划框永不动**：只写 `days[当天]`，绝不改 `planned_start` / `planned_end`。
    除非显式传 `--allow-plan-change`（默认关闭，用于用户明确要求「改计划」时）。
  * **远端 memo 自动回收**：`data.enc` 有两个写入方，GitHub Actions 每 4 小时写一次
    `memo`。默认先 `git show origin/main:data.enc` 解出远端，把较新的 `memo` 并进来。
  * **默认 dry-run**：不加 `--apply` 只打印「将要发生什么」，一个字都不落盘。

用法
-----------------------------------------------------------------------
  python tools/daily_log.py --template                  # 打印 spec 模板
  python tools/daily_log.py --spec .local/day.json      # 预览（不落盘）
  python tools/daily_log.py --spec .local/day.json --apply
  python tools/daily_log.py --spec .local/day.json --apply --no-remote

spec（JSON）字段
-----------------------------------------------------------------------
  date          "2026-09-12"        必填，学习日（跨零点请填「前一天」）
  total_minutes 56                  可选，当日总分钟数（自动换算 total_hours）
  total_hours   0.9                 可选，直接给小时
  subjects      {"408": 0.9}        分科小时数（缺省则由 segments 推断）
  segments      [{"start":"22:01","end":"22:43","subject":"408","content":"…"}]
  completed_tasks ["计算机网络 · 第一章"]     当日完成事项（人类可读）
  reflection    "…"                 复盘
  tomorrow_plan ["…"]               明日计划
  done          ["m07"]             当天**做**了的任务：id / 标题子串 / range
  skip          ["m05"]             可选：计划覆盖当天但**不写记录**（保持无条）
  progress      {"m07": 20}         可选：顺带更新进度百分比
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import update  # noqa: E402  复用加解密与官方写入口径

TEMPLATE = {
    "date": "2026-09-12",
    "total_minutes": 56,
    "subjects": {"408": 0.9},
    "segments": [
        {"start": "22:01", "end": "22:43", "subject": "408", "content": "计算机网络 · 第一章（推进）"}
    ],
    "completed_tasks": ["计算机网络 · 基础：第一章"],
    "reflection": "",
    "tomorrow_plan": [],
    "done": ["m07"],
    "skip": [],
    "progress": {},
}


# ------------------------------------------------------------------ 工具
def load_spec(path_or_json: str) -> dict:
    if path_or_json.startswith("@"):
        path_or_json = path_or_json[1:]
    p = Path(path_or_json)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return json.loads(path_or_json)


def hhmm_to_min(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def seg_minutes(seg: dict) -> int:
    if not seg.get("start") or not seg.get("end"):
        return 0
    d = hhmm_to_min(seg["end"]) - hhmm_to_min(seg["start"])
    return d + 24 * 60 if d < 0 else d          # 允许跨零点


def fmt_h(minutes: float) -> str:
    return f"{minutes / 60:.1f}h（{int(minutes)}min）"


# ------------------------------------------------------------------ 远端合并
def read_remote(password: str):
    """从 origin/main 取 data.enc 并解密；取不到返回 None"""
    try:
        r = subprocess.run(["git", "show", "origin/main:data.enc"],
                           cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
    except Exception as e:
        print(f"  ! git 调用失败：{e}")
        return None
    if r.returncode != 0 or not r.stdout.strip():
        print("  ! 取不到 origin/main:data.enc（先 git fetch），跳过远端合并")
        return None
    try:
        return json.loads(update.decrypt_text(r.stdout, password))
    except Exception as e:
        print(f"  ! 远端 data.enc 解密失败：{e}")
        return None


def merge_remote(data: dict, remote: dict) -> list:
    """只回收远端独有的东西：较新的 memo + 本地缺失的日期。本地其余字段为权威。"""
    notes = []
    if not remote:
        return notes
    local = {e.get("date"): e for e in data.setdefault("daily_logs", [])}
    for re_ in remote.get("daily_logs", []):
        d = re_.get("date")
        if not d:
            continue
        le = local.get(d)
        if le is None:
            data["daily_logs"].append(re_)
            local[d] = re_
            notes.append(f"远端多出 {d} 的记录，已并入")
            continue
        rm = re_.get("memo")
        if not rm:
            continue
        lm = le.get("memo") or {}
        if not lm or (rm.get("checked_at") or "") > (lm.get("checked_at") or ""):
            le["memo"] = rm
            notes.append(f"{d} 墨墨进度 {rm.get('finished')}/{rm.get('total')}（远端较新，已并入）")
    data["daily_logs"].sort(key=lambda x: x.get("date", ""))
    return notes


# ------------------------------------------------------------------ 任务匹配
def plan_covers(m: dict, day: str) -> bool:
    ps, pe = m.get("planned_start"), m.get("planned_end")
    if not ps or ps > day:
        return False
    return not (pe and day > pe)


def match_tasks(ms: list, tokens: list):
    """token → 里程碑。支持 id 精确、标题子串、range 子串。返回 (命中表, 未命中表)"""
    hit, miss = {}, []
    for tk in tokens or []:
        t = str(tk).strip()
        if not t:
            continue
        exact = [m for m in ms if m.get("id") == t]
        if exact:
            hit[exact[0]["id"]] = exact[0]
            continue
        fuzzy = [m for m in ms if t in (m.get("title") or "") or t in (m.get("range") or "")]
        if fuzzy:
            hit[fuzzy[0]["id"]] = fuzzy[0]
            if len(fuzzy) > 1:
                print(f"  ! 「{t}」匹配到 {len(fuzzy)} 项，取第一项："
                      + " / ".join(f"{m['id']}·{m.get('title')}" for m in fuzzy))
        else:
            miss.append(t)
    return hit, miss


# ------------------------------------------------------------------ 主流程
def build(spec: dict, data: dict, allow_plan_change=False):
    day = spec["date"]
    log = data.setdefault("daily_logs", [])
    ms = data.setdefault("milestones", [])

    # ---- 1) 每日记录：先取旧 entry 合并（保住 memo 与未知字段） ----
    old = next((e for e in log if e.get("date") == day), None)
    entry = dict(old) if old else {"date": day}
    segs = spec.get("segments") or []
    subs = dict(spec.get("subjects") or {})
    if not subs and segs:
        acc = {}
        for s in segs:
            acc[s.get("subject", "综合")] = acc.get(s.get("subject", "综合"), 0) + seg_minutes(s) / 60
        subs = {k: round(v, 1) for k, v in acc.items()}
    if spec.get("total_minutes"):
        total = round(float(spec["total_minutes"]) / 60, 1)
    elif spec.get("total_hours"):
        total = round(float(spec["total_hours"]), 1)
    else:
        total = round(sum(subs.values()), 1)

    entry.update({
        "total_hours": total,
        "subject_hours": {k: round(float(v), 1) for k, v in subs.items()},
        "time_segments": segs,
        "completed_tasks": spec.get("completed_tasks") or [],
        "reflection": spec.get("reflection", ""),
        "tomorrow_plan": spec.get("tomorrow_plan") or [],
    })
    if old is None:
        log.append(entry)
    else:
        log[log.index(old)] = entry
    log.sort(key=lambda x: x.get("date", ""))

    # ---- 2) 里程碑 days[当天] ----
    done_hit, miss_tokens = match_tasks(ms, spec.get("done"))
    skip_hit, _ = match_tasks(ms, spec.get("skip"))
    rows, touched = [], set()
    for m in ms:
        mid = m.get("id")
        flag = None
        if mid in done_hit:
            flag, why = 1, "完成"
        elif mid in skip_hit:
            flag, why = None, "跳过（不写）"
        elif plan_covers(m, day):
            flag, why = 0, "计划覆盖当天 → 没做"
        else:
            flag, why = None, "计划未覆盖 → 不写"
        if flag is not None:
            m.setdefault("days", {})[day] = flag     # ★ 合并写入，绝不整体替换 days
            touched.add(mid)
            if flag == 1:
                if not m.get("actual_start") or m["actual_start"] > day:
                    m["actual_start"] = day
                if not m.get("actual_end") or m["actual_end"] < day:
                    m["actual_end"] = None        # 进行中：结束日留空
        rows.append((mid, m.get("subject"), m.get("title"), m.get("range"),
                     m.get("planned_start"), m.get("planned_end"), flag, why))

    # ---- 3) 进度（可选） ----
    prog = spec.get("progress") or {}
    for mid, val in prog.items():
        t = next((m for m in ms if m.get("id") == mid), None)
        if t:
            t["progress"] = int(val)
            if int(val) >= 100:
                t["status"] = "done"
                t["actual_end"] = t.get("actual_end") or day
            elif int(val) > 0:
                t["status"] = "ongoing"

    return entry, rows, miss_tokens, touched


def print_preview(day, entry, rows, miss_tokens):
    print(f"\n── 每日记录 {day} ─────────────────────────────────────────")
    print(f"  总时长 {fmt_h(float(entry['total_hours']) * 60)}"
          f" | 分科 " + " · ".join(f"{k} {v}h" for k, v in entry["subject_hours"].items()))
    for s in entry["time_segments"]:
        print(f"    {s.get('start')}–{s.get('end')}  【{s.get('subject')}】{s.get('content')}")
    print(f"  完成事项：{ '；'.join(entry['completed_tasks']) or '—' }")
    if entry.get("reflection"):
        print(f"  复盘：{entry['reflection']}")
    if entry.get("tomorrow_plan"):
        print(f"  明日：{'；'.join(entry['tomorrow_plan'])}")
    if entry.get("memo"):
        m = entry["memo"]
        print(f"  墨墨：{m.get('finished')}/{m.get('total')} 词（{m.get('study_minutes')}min，{m.get('checked_at')}）")

    print(f"\n── 甘特条（days[{day}]）────────────────────────────────────")
    print(f"  {'id':6}{'任务':32}{'计划':24}{'标记':6}说明")
    for mid, subj, title, rng, ps, pe, flag, why in rows:
        name = (title or "")[:24] + (f"（{rng}）" if rng else "")
        mark = {1: "蓝 1", 0: "红 0", None: "—"}[flag]
        plan = f"{(ps or '—')[-5:]}~{(pe or '—')[-5:]}"
        print(f"  {str(mid):6}{name:32}{plan:24}{mark:6}{why}")
    blue = [r[0] for r in rows if r[6] == 1]
    red = [r[0] for r in rows if r[6] == 0]
    print(f"\n  蓝条({len(blue)})：{blue}")
    print(f"  红条({len(red)})：{red}")
    if miss_tokens:
        print(f"\n  ⚠️  done 里这些没匹配到任务，请核对：{miss_tokens}")


def check_plan_unchanged(data, base):
    """计划框是否被动过（防御性检查）"""
    b = {m.get("id"): (m.get("planned_start"), m.get("planned_end")) for m in base.get("milestones", [])}
    n = {m.get("id"): (m.get("planned_start"), m.get("planned_end")) for m in data.get("milestones", [])}
    diff = [k for k in b if k in n and b[k] != n[k]]
    return diff


def main():
    ap = argparse.ArgumentParser(description="每日学习记录录入器")
    ap.add_argument("--spec", help="spec JSON：路径 / @路径 / 内联 JSON")
    ap.add_argument("--apply", action="store_true", help="落盘并重新加密（缺省只预览）")
    ap.add_argument("--no-remote", action="store_true", help="跳过 origin/main 的 memo 回收")
    ap.add_argument("--allow-plan-change", action="store_true",
                    help="允许改动 planned_start/planned_end（仅在用户明确要求改计划时使用）")
    ap.add_argument("--key", help="临时指定主密码")
    ap.add_argument("--template", action="store_true", help="打印 spec 模板后退出")
    args = ap.parse_args()

    if args.template:
        print(json.dumps(TEMPLATE, ensure_ascii=False, indent=2))
        return

    if not args.spec:
        print("× 需要 --spec（或 --template 看模板）")
        sys.exit(1)

    password = update.resolve_password(args.key)
    spec = load_spec(args.spec)
    if not spec.get("date"):
        print("× spec 缺少 date")
        sys.exit(1)

    data = update.load_json()
    base = json.loads(json.dumps(data, ensure_ascii=False))   # 快照，用于对比
    day = spec["date"]

    if not args.no_remote:
        print("· 回收远端（GitHub Actions）写入的墨墨进度…")
        for n in merge_remote(data, read_remote(password)):
            print("  ·", n)
        base = json.loads(json.dumps(data, ensure_ascii=False))

    entry, rows, miss_tokens, touched = build(spec, data, args.allow_plan_change)
    print_preview(day, entry, rows, miss_tokens)

    plan_diff = check_plan_unchanged(data, base)
    print(f"\n  计划框改动：{plan_diff if plan_diff else '无 ✅（planned_start/planned_end 未动）'}")

    if not args.apply:
        print("\n（预览模式，未写入任何文件；确认无误后加 --apply）")
        return

    if plan_diff and not args.allow_plan_change:
        print("× 检测到计划框被改动但未加 --allow-plan-change，已中止")
        sys.exit(2)

    bak_dir = ROOT / ".local"
    bak_dir.mkdir(exist_ok=True)
    bak = bak_dir / f"data.json.bak-{datetime.now():%Y%m%d-%H%M%S}"
    shutil.copyfile(update.DATA_JSON, bak)
    print(f"\n· 已备份 -> {bak.relative_to(ROOT)}")

    update.save_json(data)
    update.do_encrypt(data, password)
    print(f"✓ 已写入 data.json / data.enc（{day}，{len(touched)} 项任务标记）")
    print("  下一步：git status --short 核对 → git add data.enc → git commit →（用户）git push")


if __name__ == "__main__":
    main()
