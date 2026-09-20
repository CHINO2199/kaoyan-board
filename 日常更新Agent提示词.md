# 每日工作内容提交 & 写入看板 · 标准流程（SOP）

> 用途：主人每天口述一段学习总结 → 结构化 → 写进看板数据 → 重新加密 → 提交。
> 本文件是**唯一的操作依据**，Agent 每天照此执行，不要临场发明新流程。

---

## 一、主人怎么提交（推荐模板）

随意口述也能用，但按下面这个格式给我，最省事、最不容易出错：

```
日期：2026-09-12
今天（昨天）总计学了 56 分钟：
- 408：0.9h（两个专注时段：22:01-22:43 推进 42min、23:25-23:39 推进 14min，
  推进计网第一章；计算机网络 · 基础 标蓝，其余全部标红）
```

要点（有就给，没有我就推断或问你）：

| 要素 | 说明 |
|---|---|
| **日期** | 学习日。跨零点记到**前一天**（与墨墨同口径：凌晨 4 点前算前一天） |
| **总时长** | 分钟或小时都行 |
| **分科时长** | 如 `408: 0.9h`；只给时段也可以，我按时段算 |
| **分时段** | `起-止 + 做了什么`，用于每日看板的「分时段学习内容」时间轴 |
| **任务完成情况** | **最重要**：哪些任务今天做了（→ 蓝条），哪些没做（→ 红条） |
| **复盘 / 明日计划** | 可选 |
| **进度百分比** | 可选，如「计网基础推进到 40%」 |

> 判断口径：**你没提到的任务，只要它的计划区间覆盖当天，我一律按「没做」写红条。**
> 计划还没开始的任务不写（否则会出现「9/19 才开始的任务在 9/11 就红」）。

---

## 二、Agent 的固定执行步骤

### 0. 准备 spec

把上面那段话结构化成 JSON（`.local/day.json`，`.local/` 已被 .gitignore 排除）：

```bash
python tools/daily_log.py --template          # 打印模板
```

```jsonc
{
  "date": "2026-09-12",
  "total_minutes": 56,
  "segments": [
    {"start":"22:01","end":"22:43","subject":"408","content":"计算机网络 · 第一章（推进）"}
  ],
  "completed_tasks": ["计算机网络 · 基础：第一章"],
  "reflection": "",
  "tomorrow_plan": [],
  "done": ["m07"],        // 今天做了的任务：id / 标题子串（空格可省，如「30讲」）
  "skip": [],             // 可选：计划覆盖当天但不写记录
  "progress": {"m07": 40} // 可选：顺带更新进度
}
```

### 1. 预览（**必须**，默认 dry-run，不落盘）

```bash
python tools/daily_log.py --spec .local/day.json
```

核对三件事：

- 「每日记录」的时长 / 时段 / 完成事项对不对；
- 「甘特条」的蓝 / 红分布对不对（这就是日历上会出现的颜色）；
- 底部 `计划框改动：无 ✅`；
- 有 `⚠️ done 里这些没匹配到任务` 就说明任务名拼错了，改 spec 重跑。

### 2. 落盘 + 加密

```bash
python tools/daily_log.py --spec .local/day.json --apply
```

### 3. 抓墨墨单词进度（当晚固定动作）

```bash
python update.py --memo
```

> 若当天已有墨墨数据（GitHub Actions 每 4 小时会自己写入），脚本会自动以较新的一份为准，
> 不会互相覆盖。`daily_log.py` 在预览时也会先「回收远端 memo」。

### 4. 核对改动范围（不可跳过）

```bash
git status --short      # 期望：只有 data.enc 一行（M）
git diff --stat
```

**绝不要盲用 `git add -A`** —— 工作区里可能有主人随手放的私密文件（`进度/*.docx` 等）。

### 5. 提交

```bash
git add data.enc
git commit -m "log: 补录 2026-09-12 学习记录"
```

**推送（默认自动执行，Agent 完成，无需主人确认；2026-09-13 起）**：

```bash
# 首选：用 Python 包装 git（回显完整，不受 Git Bash 环境损坏影响）
python .local/gitp.py push origin main

# 备选：系统 shell 里直接推（走 Windows 凭据管理器缓存的 GitHub 凭据）
git push origin main
```

> 等价物：双击工作区里的 **`一键同步看板.lnk`**，其内容为
> `git add .; git commit -m 'update'; git push`。
> ⚠️ 该快捷方式是**盲 add 全部**——日常仍应先逐条核对 `git status --short`，只提交该提交的文件。
> Git Bash 里 `git push` 推不动，只是因为**非交互弹不出凭据窗口**，不是没权限（凭据在 Windows 凭据管理器里）。
>
> **环境坑**：Git Bash 工具链会中途崩坏（`dirname`/`cd`/`head` 找不到）→ 一律改用 `.local/gitp.py`。
> 另外沙箱内 git 对 `refs/remotes/*` 的写入**不落盘**（`git fetch` 报成功但 `origin/main` 随即消失，
> `git status -sb` 显示 `[gone]`）→ 用 Python 把**完整 40 位哈希**写进 `.git/refs/remotes/origin/main`；
> 要权威远端 SHA 用 `git ls-remote origin refs/heads/main`。

### 6. 推送后核验（必做，异常就停下报告）

1. `curl` 线上 `data.enc`，与本地比 sha256 —— 应逐字节相同、无 `<<<<<<<`
2. `curl` 线上 `index.html`，其 sha256 应与 `git show HEAD:index.html` 一致（证明 Pages 已部署）
3. 无头 Chrome 加载线上 URL，页面应停在**密码解锁页**（含 `type=password`），
   而非「还没有数据文件 / 数据文件已损坏」

> 现成脚本：`.local/check_live_dom.py`（加载线上并判定页面状态）。
> 只有这三步都过，才算这一天录入真正完成。

---

## 三、甘特图配色口径（写入时以此为准）

| 那天的情况 | `days[当天]` | 颜色 |
|---|---|---|
| 报了完成 | `1` | **蓝** |
| 明确说没做 / 没提（=没做） | `0` | **红** |
| 超出 `planned_end` 后补做 | `1` | **黄**（自动） |
| 今天尚未记录 | 不写 | 灰斜纹（自动） |

**计划框（上方紫虚线）是「预计完成区间」，一经确定即固定。**
除非主人明确说「改计划」，任何时候都不改 `planned_start` / `planned_end`。
`daily_log.py` 内置了防御：检测到计划框被改动但没加 `--allow-plan-change` 会直接中止。

---

## 四、两个必须记住的写入陷阱

`update.py` 的两个接口都是**整体替换**，直接调用会静默丢数据：

1. **`upsert_daily(entry)` 整条替换当天记录** → 会抹掉线上 GitHub Actions 写入的
   `memo`（墨墨单词进度）。`daily_log.py` 已改为「取出旧 entry → `dict(old)` → 再更新字段」。
2. **`upsert_milestone` 对 `days` 整体替换** → 会冲掉前几天的逐日记录。
   `daily_log.py` 已改为「`m.setdefault('days',{})[当天] = 1|0`」合并写入。

**另外**：`data.enc` 有两个写入方（本地脚本 + GitHub Actions 的墨墨同步）。
任何要**重建** `data.enc` 的操作，第一步先 `git fetch` 看远端有没有新提交；
若有（`memo-sync-bot` 的提交必然改 `data.enc`），必须以远端明文为基再叠加本地改动。

---

## 五、常见变体

| 场景 | 做法 |
|---|---|
| **补录某天**（不是今天） | spec 里 `date` 写那天，其余照常。当天没记录也能补 |
| **改计划**（主人明确要求） | 走 `update.upsert_milestone()` 改 `planned_*`，再 `python update.py --encrypt-only`；`daily_log.py` 的 `--allow-plan-change` 只在此时使用 |
| **同一任务拆新区间**（如每日一题 86–120 题） | 新建里程碑 `m03b`，设 `row: 'm03'`（与主块同行）、`range: '86–120 题'`、`planned_start/end` |
| **新建一个任务** | `update.upsert_milestone({id,title,subject,planned_start,planned_end})`，保留默认 `days: {}` |
| **删除一个任务**（整行删除） | ⚠️ `upsert_milestone` **只做新增/更新，不能删除**。正确做法：按 id 从 `data.json` 的 `milestones` 里剔除 → 写回明文 → `python update.py --encrypt-only`。删前先断言命中的 id 与预期一致（防止误删） |
| **只看不改** | `python update.py --verify`（解密 data.enc 打印摘要） |

### 改计划后的两个行为（已验证，别误判为 bug）

- **新建任务不会凭空出现实条**：`realDays()` 里 `start = actual_start || days 里最早的日期 || null`，
  为空就直接不画条。所以「今天开始的新任务」当天只显示紫虚线计划框 + 状态「未启动」，
  **不会**因为「计划覆盖今天却没记录」而画成红条（红条只出现在 `days` 有 `0` 的日期）。
- **`meta.updated_at` 只写进密文**：`update.do_encrypt()` 里显式说明「只进密文，不回写 `data.json`」，
  所以本地 `data.json` 的 `meta.updated_at` 看起来永远是旧的 —— 这是设计如此，
  前端读到的是密文里的新时间，不要拿它当「没更新」的证据。

---

## 六、收尾

- 临时文件（`.local/day.json`、备份）用完即删；`.local/` 不入库。
- 提交前若主人在工作区放过资料（`进度/`、`*.docx`、`*.lnk`），确认 `.gitignore` 覆盖到了。
- 每天可对主人说一句今天的进度小结与鼓励。
