#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
墨墨背单词进度 · 自动同步（供 GitHub Actions 定时任务使用）
=======================================================================
流程：解密 data.enc → 抓取墨墨今日复习情况 → 写入当天记录 → 重新加密 data.enc

设计要点：
  - 以 data.enc 为唯一数据源，**不依赖 data.json**（本地明文不进 CI）
  - 数据无变化时直接退出，不产生无意义的提交
  - 需要环境变量：KAOYAN_KEY（主密码）、MAIMEMO_TOKEN（墨墨开放 API token）

本地也可手动运行：
  KAOYAN_KEY=xxx MAIMEMO_TOKEN=yyy python tools/memo_sync.py
=======================================================================
"""

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from update import decrypt_text, encrypt_text, fetch_memo, attach_memo  # noqa: E402

DATA_ENC = ROOT / "data.enc"


def get_env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def main() -> None:
    key = get_env("KAOYAN_KEY")
    if not key:
        print("× 缺少环境变量 KAOYAN_KEY（主密码）")
        sys.exit(1)
    if not get_env("MAIMEMO_TOKEN"):
        print("× 缺少环境变量 MAIMEMO_TOKEN")
        sys.exit(1)
    if not DATA_ENC.exists():
        print("× 找不到 data.enc")
        sys.exit(1)

    # 1) 解密现有数据
    try:
        data = json.loads(decrypt_text(DATA_ENC.read_text(encoding="utf-8"), key))
    except Exception as e:
        print("× data.enc 解密失败（KAOYAN_KEY 是否正确？）：%s" % e)
        sys.exit(1)

    # 2) 抓取墨墨今日复习情况
    memo = fetch_memo()
    if not memo:
        print("× 未能获取墨墨数据（token 是否过期？）")
        sys.exit(1)

    day = memo.get("date") or date.today().isoformat()
    total = memo.get("total", 0)
    done = memo.get("finished", 0)

    # 3) 与已有数据比对，无变化就不提交
    old = None
    for item in data.get("daily_logs", []):
        if item.get("date") == day:
            old = item.get("memo")
            break
    if old and old.get("finished") == done and old.get("total") == total \
            and old.get("study_minutes") == memo.get("study_minutes") \
            and old.get("forgotten_count") == memo.get("forgotten_count"):
        print("· 数据无变化，跳过提交（%s：%d/%d 词）" % (day, done, total))
        return

    # 4) 写入并重新加密
    attach_memo(data, memo, day)
    data.setdefault("meta", {})["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    DATA_ENC.write_text(encrypt_text(raw, key), encoding="utf-8")
    print("✓ 已更新 data.enc（%s：%d/%d 词，%.1f 分钟）" % (day, done, total, memo.get("study_minutes", 0)))


if __name__ == "__main__":
    main()
