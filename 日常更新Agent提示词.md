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

**推送（Agent 可自行完成，2026-09-13 起）**：

```powershell
# 在 PowerShell 里执行（走 Windows 凭据管理器缓存的 GitHub 凭据）
Set-Location 'C:\Users\33270\Desktop\ky\每日工作'; git push origin main
```

> 等价物：双击工作区里的 **`一键同步看板.lnk`**，其内容为
> `git add .; git commit -m 'update'; git push`。
> ⚠️ 该快捷方式是**盲 add 全部**——日常仍应先逐条核对 `git status --short`，只提交该提交的文件。
> Git Bash 里 `git push` 推不动，只是因为**非交互弹不出凭据窗口**，不是没权限。

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
| **只看不改** | `python update.py --verify`（解密 data.enc 打印摘要） |

---

## 六、收尾

- 临时文件（`.local/day.json`、备份）用完即删；`.local/` 不入库。
- 提交前若主人在工作区放过资料（`进度/`、`*.docx`、`*.lnk`），确认 `.gitignore` 覆盖到了。
- 每天可对主人说一句今天的进度小结与鼓励。
