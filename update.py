#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
百日研途 · 数据更新脚本
=======================================================================
职责：
  1. 把 notes_src/*.md 的正文同步进 data.json 的 notes（自动补上传日期）
  2. 把 data.json 加密为 data.enc（AES-256-CBC，base64(IV + 密文)）
  3. 追加/更新每日记录、里程碑，并可选地 git 提交推送

用法：
  python update.py                              # 同步笔记 + 重新加密
  python update.py --daily day.json             # 追加当天记录（JSON 文件）
  python update.py --daily '{"date":"..."}'     # 追加当天记录（内联 JSON）
  python update.py --milestone '{"id":"m3","progress":70}'
  python update.py --verify                     # 解密 data.enc 并打印摘要
  python update.py --push                       # 提交并推送到 GitHub
  python update.py --key mypassword             # 临时指定主密码

依赖：pip install pycryptodome
主密码：优先读环境变量 KAOYAN_KEY，否则用下方 MASTER_PASSWORD。
        必须使用 ASCII 字符（前后端按字节 ljust(32)[:32] 对齐）。
=======================================================================
"""

import argparse
import base64
import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ---------------------------------------------------------------- 路径与配置
ROOT = Path(__file__).resolve().parent
DATA_JSON = ROOT / "data.json"
DATA_ENC = ROOT / "data.enc"
NOTES_DIR = ROOT / "notes_src"          # 明文源：*.md / *.pdf（.gitignore 排除）
NOTES_ENC = ROOT / "notes_enc"          # 加密产物：PDF 的 .enc（随仓库一起发布）

MASTER_PASSWORD = os.environ.get("KAOYAN_KEY", "YOUR_MASTER_PASSWORD_HERE")
KEY_FILE = ROOT / ".kaoyan_key"   # 本地密码文件（.gitignore 已排除），省去每次设环境变量
IV = b"1234567890123456"          # 16 字节固定 IV（与前端保持一致）
KEY_LEN = 32                      # AES-256
FILL = b" "                       # 与 Python str.ljust / JS padEnd 等价的空格填充

# 书脊配色仅由前端负责；这里只做数据结构规范
VALID_STATUS = {"pending", "ongoing", "done"}


def resolve_password(cli_key=None) -> str:
    """密码来源优先级：--key > 环境变量 KAOYAN_KEY > .kaoyan_key 文件 > 脚本常量"""
    if cli_key:
        return cli_key
    env = os.environ.get("KAOYAN_KEY")
    if env:
        return env
    if KEY_FILE.exists():
        text = KEY_FILE.read_text(encoding="utf-8").strip()
        if text:
            return text
    return MASTER_PASSWORD


# ---------------------------------------------------------------- 密钥与加解密
def derive_key(password: str) -> bytes:
    """主密码 -> 32 字节密钥（按 UTF-8 字节截断 + 空格补齐，与前端完全一致）"""
    raw = password.encode("utf-8")
    if len(raw) > KEY_LEN:
        raw = raw[:KEY_LEN]
    return raw + FILL * (KEY_LEN - len(raw))


def _aes():
    try:
        from Crypto.Cipher import AES                      # pycryptodome
        return AES
    except ImportError:
        print("× 缺少依赖：请先执行  pip install pycryptodome")
        sys.exit(1)


def encrypt_text(raw: bytes, password: str) -> str:
    """加密为 base64(IV + 密文)，用于 data.enc"""
    from Crypto.Util.Padding import pad
    AES = _aes()
    cipher = AES.new(derive_key(password), AES.MODE_CBC, IV)
    return base64.b64encode(IV + cipher.encrypt(pad(raw, AES.block_size))).decode("ascii")


def encrypt_bytes(raw: bytes, password: str) -> bytes:
    """加密为二进制 IV + 密文，用于 PDF 等大文件（不产生 base64 的 33% 膨胀）"""
    from Crypto.Util.Padding import pad
    AES = _aes()
    cipher = AES.new(derive_key(password), AES.MODE_CBC, IV)
    return IV + cipher.encrypt(pad(raw, AES.block_size))


def decrypt_text(b64: str, password: str) -> str:
    from Crypto.Util.Padding import unpad
    AES = _aes()
    blob = base64.b64decode("".join(b64.split()))
    if len(blob) <= 16:
        raise ValueError("密文长度异常")
    plain = AES.new(derive_key(password), AES.MODE_CBC, blob[:16]).decrypt(blob[16:])
    return unpad(plain, AES.block_size).decode("utf-8")


# ---------------------------------------------------------------- 读写工具
def load_json() -> dict:
    if not DATA_JSON.exists():
        print(f"× 找不到 {DATA_JSON.name}，请先复制 data.sample.json 为 data.json")
        sys.exit(1)
    with DATA_JSON.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: dict) -> None:
    with DATA_JSON.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_arg_json(value: str) -> dict:
    """支持内联 JSON 字符串，或 @路径 指向的 JSON 文件"""
    if value.startswith("@"):
        with open(value[1:], "r", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(value)


# ---------------------------------------------------------------- 业务动作
def sync_notes(data: dict, today: str, password: str) -> int:
    """扫描 notes_src/ 同步笔记，按 file 字段匹配：找到则更新，找不到则新增。

    - ``*.md``  → 正文直接写进 data.json（体积小，随 data.enc 一起加密）
    - ``*.pdf`` → 单独 AES 加密到 ``notes_enc/<stem>.enc``（二进制，无 base64 膨胀），
                  data.json 里只登记相对路径，前端点击时才按需拉取解密
    """
    if not NOTES_DIR.exists():
        return 0
    notes = data.setdefault("notes", [])
    by_file = {n.get("file"): n for n in notes if n.get("file")}
    changed = 0

    # ---------------- Markdown ----------------
    for md in sorted(NOTES_DIR.glob("*.md")):
        text = md.read_text(encoding="utf-8")
        title = _title_of(md, text)
        entry = by_file.get(md.name)
        if entry is None:
            entry = {
                "id": "n-" + md.stem,
                "subject": _guess_subject(md.stem, text),
                "title": title,
                "file": md.name,
                "type": "md",
                "uploaded_at": today,
                "tags": [],
                "content": "",
            }
            notes.append(entry)
            by_file[md.name] = entry
            changed += 1
            print(f"  + 新增笔记 {md.name} -> 《{title}》")
        entry["type"] = "md"
        if entry.get("content") != text:
            entry["content"] = text
            changed += 1
            print(f"  · 已同步正文 {md.name}（{len(text)} 字）")
        if not entry.get("uploaded_at"):
            entry["uploaded_at"] = today

    # ---------------- PDF ----------------
    for pdf in sorted(NOTES_DIR.glob("*.pdf")):
        NOTES_ENC.mkdir(exist_ok=True)
        enc_rel = f"notes_enc/{pdf.stem}.enc"
        enc_path = NOTES_ENC / (pdf.stem + ".enc")
        stale = (not enc_path.exists()) or pdf.stat().st_mtime > enc_path.stat().st_mtime
        if stale:
            enc_path.write_bytes(encrypt_bytes(pdf.read_bytes(), password))
            changed += 1
            print(f"  · 已加密 {pdf.name} -> {enc_rel}（{enc_path.stat().st_size / 1048576:.2f} MB）")

        entry = by_file.get(pdf.name)
        if entry is None:
            entry = {
                "id": "n-" + pdf.stem,
                "subject": _guess_subject(pdf.stem, pdf.name),
                "title": _pdf_title(pdf.stem),
                "file": pdf.name,
                "type": "pdf",
                "uploaded_at": today,
                "tags": ["PDF"],
                "content": "",
            }
            notes.append(entry)
            by_file[pdf.name] = entry
            changed += 1
            print(f"  + 新增 PDF 笔记 {pdf.name} -> 《{entry['title']}》")
        entry["type"] = "pdf"
        entry["enc"] = enc_rel
        entry["content"] = ""
        entry["size_kb"] = round(enc_path.stat().st_size / 1024) if enc_path.exists() else 0
        if not entry.get("uploaded_at"):
            entry["uploaded_at"] = today

    for n in notes:
        n.setdefault("type", "md")
    return changed


def _title_of(path: Path, text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return path.stem


def _pdf_title(stem: str) -> str:
    """支持「408-操作系统讲义.pdf」这类命名：去掉学科前缀作为标题"""
    prefix = {"math", "en", "eng", "zz", "ds", "os", "co", "cn", "cs", "pol",
              "408", "英语", "数学", "政治", "专业课"}
    for sep in ("-", "_", "·", " "):
        if sep in stem:
            head, tail = stem.split(sep, 1)
            if tail.strip() and head.strip().lower() in prefix:
                return tail.strip()
    return stem


def _guess_subject(stem: str, text: str) -> str:
    """先按文件名里的缩写判断（en-1 / os-1 / math-1 这类），再退回内容关键词。

    注意：两字母缩写必须按"词边界"匹配，否则 'co' 会命中 'could'、'os' 会命中 'those'。
    """
    import re
    alias = {
        "ds": "408", "os": "408", "co": "408", "cn": "408", "cs": "408",
        "math": "数学", "gd": "数学",
        "zz": "政治", "pol": "政治",
        "en": "英语", "eng": "英语", "english": "英语",
    }
    stem_l = stem.lower()
    for key, subj in alias.items():
        if re.search(r"(^|[^a-z])" + re.escape(key) + r"([^a-z]|$)", stem_l):
            return subj

    keyword = {
        "408": ["数据结构", "计算机", "操作系统", "计算机网络", "组成原理", "机组", "计网", "指令", "进程"],
        "数学": ["数学", "高数", "线代", "概率", "微积分", "极限", "导数", "级数", "矩阵"],
        "政治": ["政治", "马原", "毛中特", "史纲", "思修", "时政", "抗战", "矛盾"],
        "英语": ["英语", "单词", "词汇", "阅读", "作文", "长难句", "翻译", "语法"],
    }
    probe = text[:800]
    for subj, words in keyword.items():
        if any(w in probe for w in words):
            return subj
    return "408"


def upsert_daily(data: dict, entry: dict) -> str:
    """按 date 覆盖或追加一条每日记录"""
    if not entry.get("date"):
        entry["date"] = date.today().isoformat()

    # 补齐与校验
    sh = entry.get("subject_hours", {}) or {}
    entry["subject_hours"] = {k: round(float(v), 1) for k, v in sh.items()}
    if not entry.get("total_hours"):
        entry["total_hours"] = round(sum(entry["subject_hours"].values()), 1)
    else:
        entry["total_hours"] = round(float(entry["total_hours"]), 1)
    entry.setdefault("time_segments", [])
    entry.setdefault("completed_tasks", [])
    entry.setdefault("reflection", "")
    entry.setdefault("tomorrow_plan", [])

    logs = data.setdefault("daily_logs", [])
    for i, item in enumerate(logs):
        if item.get("date") == entry["date"]:
            logs[i] = entry
            print(f"  · 更新 {entry['date']} 记录（{entry['total_hours']}h）")
            return entry["date"]
    logs.append(entry)
    print(f"  + 新增 {entry['date']} 记录（{entry['total_hours']}h）")
    logs.sort(key=lambda x: x.get("date", ""))
    return entry["date"]


def upsert_milestone(data: dict, patch: dict) -> str:
    """按 id 或 title 更新里程碑；不存在则以该 patch 新建"""
    ms = data.setdefault("milestones", [])
    target = None
    for m in ms:
        if patch.get("id") and m.get("id") == patch["id"]:
            target = m
            break
        if patch.get("title") and m.get("title") == patch["title"]:
            target = m
            break
    if target is None:
        patch.setdefault("id", "m-" + datetime.now().strftime("%m%d%H%M"))
        patch.setdefault("subject", "综合")
        patch.setdefault("planned_start", date.today().isoformat())
        patch.setdefault("planned_end", patch["planned_start"])
        patch.setdefault("actual_start", None)
        patch.setdefault("actual_end", None)
        patch.setdefault("progress", 0)
        patch.setdefault("status", "pending")
        patch.setdefault("note", "")
        ms.append(patch)
        print(f"  + 新增里程碑《{patch.get('title')}》")
        return patch["id"]

    for k, v in patch.items():
        if k == "id":
            continue
        target[k] = v
    # 状态自动推演
    if target.get("progress", 0) >= 100 or target.get("actual_end"):
        target["status"] = "done"
        target.setdefault("actual_end", date.today().isoformat())
        if target.get("progress", 0) < 100:
            target["progress"] = 100
    elif target.get("actual_start") or target.get("progress", 0) > 0:
        target["status"] = "ongoing"
    print(f"  · 更新里程碑《{target.get('title')}》 -> {target.get('status')} {target.get('progress')}%")
    return target["id"]


def do_encrypt(data: dict, password: str) -> None:
    # 写入数据版本时间（只进密文，不回写 data.json），前端页脚会显示"数据更新于 …"，
    # 便于确认浏览器拿到的是不是最新一份
    data.setdefault("meta", {})["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    DATA_ENC.write_text(encrypt_text(raw, password), encoding="utf-8")
    kb = DATA_ENC.stat().st_size / 1024
    print(f"✓ 已生成 {DATA_ENC.name}（{kb:.1f} KB，明文 {len(raw)} 字节）")


def do_pull() -> None:
    """推送前先同步远端：墨墨自动同步任务（GitHub Actions）会不定期提交 data.enc，
    不先 pull 的话本地推送会被拒绝。data.json 不在仓库里，pull 不会影响本地明文。"""
    r = subprocess.run(["git", "pull", "--rebase", "--autostash", "--no-edit"],
                       cwd=ROOT, capture_output=True, text=True)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if r.returncode != 0:
        print("! git pull 失败，请手动处理后再推送：")
        print("  " + out.replace("\n", "\n  ")[:600])
        sys.exit(1)
    tail = (out.splitlines() or ["已是最新"])[-1]
    print(f"  · git pull: {tail}")


def do_push(message: str) -> None:
    """提交并推送。注意：data.json / notes_src 属私密明文，已被 .gitignore 排除"""
    try:
        subprocess.run(["git", "add", "data.enc", "index.html"], cwd=ROOT, check=True)
        r = subprocess.run(["git", "commit", "-m", message], cwd=ROOT,
                           capture_output=True, text=True)
        print((r.stdout or r.stderr).strip())
        subprocess.run(["git", "push"], cwd=ROOT, check=True)
        print("✓ 已推送到远端，GitHub Pages 将在 1 分钟内更新")
    except subprocess.CalledProcessError as e:
        print(f"× git 操作失败：{e}")
        sys.exit(1)


def fetch_memo():
    """调用 tools/memo.py 抓取墨墨背单词今日复习情况"""
    script = ROOT / "tools" / "memo.py"
    if not script.exists():
        print("  ! 未找到 tools/memo.py，跳过墨墨数据")
        return None
    try:
        r = subprocess.run([sys.executable, str(script), "--json"],
                           capture_output=True, text=True, encoding="utf-8", timeout=150)
        if r.returncode != 0:
            msg = (r.stdout or r.stderr or "").strip().replace("\n", " ")[:140]
            print("  ! 墨墨数据获取失败：%s" % msg)
            return None
        memo = json.loads(r.stdout)
        if memo.get("error"):
            print("  ! 墨墨数据获取失败：%s" % memo["error"])
            return None
        return memo
    except Exception as e:
        print("  ! 墨墨数据获取异常：%s" % e)
        return None


def attach_memo(data: dict, memo: dict, day=None) -> None:
    """把墨墨复习数据挂到当天记录；当天还没有记录时自动创建一条骨架"""
    day = day or memo.get("date") or date.today().isoformat()
    logs = data.setdefault("daily_logs", [])
    for item in logs:
        if item.get("date") == day:
            item["memo"] = memo
            print("  · 已写入 %s 的墨墨数据（%d/%d 词，%.1f 分钟）"
                  % (day, memo.get("finished", 0), memo.get("total", 0), memo.get("study_minutes", 0)))
            return
    logs.append({
        "date": day, "total_hours": 0, "subject_hours": {},
        "time_segments": [], "completed_tasks": [],
        "reflection": "", "tomorrow_plan": [], "memo": memo,
    })
    logs.sort(key=lambda x: x.get("date", ""))
    print("  + %s 暂无学习记录，已创建骨架并写入墨墨数据" % day)


def do_verify(password: str) -> None:
    if not DATA_ENC.exists():
        print("× data.enc 不存在")
        sys.exit(1)
    text = decrypt_text(DATA_ENC.read_text(encoding="utf-8"), password)
    data = json.loads(text)
    meta = data.get("meta", {})
    logs = data.get("daily_logs", [])
    ms = data.get("milestones", [])
    total = sum(float(l.get("total_hours", 0)) for l in logs)
    print("✓ 解密成功")
    print(f"  考试日期 : {meta.get('exam_date')}  冲刺起点 : {meta.get('sprint_start')}")
    print(f"  每日记录 : {len(logs)} 天，累计 {total:.1f}h（最近 {logs[-1]['date'] if logs else '—'}）")
    print(f"  里程碑   : {len(ms)} 项，已完成 {sum(1 for m in ms if m.get('status') == 'done')} 项")
    note_list = data.get("notes", [])
    pdfs = [n for n in note_list if n.get("type") == "pdf"]
    print(f"  笔记     : {len(note_list)} 份（Markdown {len(note_list) - len(pdfs)} · PDF {len(pdfs)}）")
    for p in pdfs:
        ok = "✓" if (ROOT / p.get("enc", "")).exists() else "× 缺失"
        print(f"             [{ok}] {p.get('enc')}")


# ---------------------------------------------------------------- 入口
def main() -> None:
    ap = argparse.ArgumentParser(description="百日研途数据更新工具")
    ap.add_argument("--daily", help="追加/覆盖每日记录：内联 JSON 或 @文件路径")
    ap.add_argument("--milestone", help="更新里程碑：内联 JSON 或 @文件路径")
    ap.add_argument("--sync-notes", action="store_true", help="仅同步 notes_src/*.md")
    ap.add_argument("--encrypt-only", action="store_true", help="仅重新加密，不做同步")
    ap.add_argument("--verify", action="store_true", help="解密 data.enc 并打印摘要")
    ap.add_argument("--push", action="store_true", help="提交并推送到 GitHub")
    ap.add_argument("--memo", action="store_true",
                    help="抓取墨墨背单词今日复习情况，写入当天记录（每晚推送前建议加上）")
    ap.add_argument("--key", help="临时指定主密码（也可用环境变量 KAOYAN_KEY 或 .kaoyan_key 文件）")
    ap.add_argument("--today", help="覆盖“今天”的日期（YYYY-MM-DD），便于补录")
    args = ap.parse_args()

    password = resolve_password(args.key)
    today = args.today or date.today().isoformat()

    if password == "YOUR_MASTER_PASSWORD_HERE":
        print("! 提醒：你还在使用默认占位主密码。")
        print("  请任选一种方式设置自己的密码后重新运行：")
        print("    1) 把密码写入本目录的 .kaoyan_key 文件（推荐，已被 .gitignore 排除）")
        print('    2) PowerShell: $env:KAOYAN_KEY="你的密码"')
        print('    3) python update.py --key 你的密码')

    if args.verify:
        do_verify(password)
        return

    if args.push:
        do_pull()                     # 先同步远端，避免与自动同步任务的提交冲突

    data = load_json()
    touched = False

    if args.daily:
        upsert_daily(data, load_arg_json(args.daily))
        touched = True
    if args.milestone:
        upsert_milestone(data, load_arg_json(args.milestone))
        touched = True
    if args.memo:
        memo = fetch_memo()
        if memo:
            attach_memo(data, memo, today)
            touched = True

    if not args.encrypt_only:
        n = sync_notes(data, today, password)
        touched = touched or n > 0

    if touched:
        save_json(data)

    do_encrypt(data, password)

    if args.push:
        do_push(f"log: update {today}")


if __name__ == "__main__":
    main()
