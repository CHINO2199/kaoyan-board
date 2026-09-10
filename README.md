# 百日研途 · 考研冲刺看板

> 一个纯前端的考研百日倒计时 / 每日学习看板 / 里程碑甘特 / 笔记书架。
> 所有学习数据以 **AES-256 加密**后随站点一起托管，密码只在你本地浏览器里使用。

---

## 一、它长什么样

| 页面 | 内容 |
| --- | --- |
| **首页** | Three.js 粒子书本动效、数字翻滚的百日倒计时、每日一句、四科卡片（SVG 弧线连接） |
| **工作内容总览** | 距离考试 / 累计时长 / 里程碑完成度 / 连续打卡 四张统计卡、冲刺总进度、**大日历甘特图**（紫色虚线＝预计工期，蓝色实心＝实际完成，竖线＝今天）、学习强度热力图、学科投入分布 |
| **每日看板** | 日期切换器回看任意一天、**ECharts 环形圆盘图**（各科时长占比，圆心显示当日总时长）、分时段学习内容时间轴、已完成任务清单、复盘（Markdown 渲染）、明日计划 |
| **笔记书架** | 数学 / 408 / 政治 / 英语分类书架，书脊按学科着色、竖排标题＋上传日期；点击**进入独立阅读页**，Markdown 与 PDF 通用 |

主题为粉色系，支持 **深色 / 浅色**双主题（右上角切换，记忆在 localStorage）。

---

## 二、目录结构

```
.
├── index.html          # 单文件前端（Vue3 + Tailwind + ECharts + CryptoJS + Three.js，全部 CDN）
├── data.enc            # ★ 加密数据，网页唯一读取的数据源（可公开托管）
├── data.json           # 明文数据（本地工作文件，已被 .gitignore 排除）
├── data.sample.json    # 数据模板，字段说明都写在 _doc 里
├── update.py           # 加密 / 追加记录 / 同步笔记（含 PDF）/ 一键推送
├── notes_src/          # 笔记源文件：*.md 与 *.pdf（明文，已被排除）
├── notes_enc/          # ★ PDF 的加密产物 *.enc（随仓库发布，前端按需拉取解密）
├── tools/
│   └── verify_crypto.js  # 跨端加密一致性自检脚本
├── preview/            # 各页面效果截图
├── README.md
└── .gitignore
```

> ⚠️ **会上传的只有 `index.html`、`data.enc`、`notes_enc/*.enc`。**
> `data.json`、`notes_src/`、`ds-1.md` 都是明文，已在 `.gitignore` 中排除。
> 若你的仓库是 Public，请务必确认 `git status` 里没有它们。

---

## 三、本地预览

加密数据必须经 HTTP 读取（`file://` 下 fetch 会被浏览器拦截），起一个静态服务器即可：

```bash
# Python
python -m http.server 8080

# 或 Node
npx serve .
```

然后打开 <http://localhost:8080>，输入主密码解锁。

**示范密码：`kaoyan2027`** —— 这是仓库里 `data.enc` 的加密密码，请务必改成你自己的。

---

## 四、主密码与加密机制

```
data.json  ──AES-256-CBC──►  base64( IV[16] + 密文 )  ──►  data.enc
```

- **密钥派生**：主密码按 UTF-8 取字节 → 超出 32 字节截断 → 不足用空格补到 32 字节。
  Python 与前端 JS 的实现完全对齐（见 `update.py: derive_key` 与 `index.html` 里的 `deriveKey`）。
- **IV**：固定 16 字节 `1234567890123456`，前置在密文中。
- **前端**：CryptoJS 解出前 16 字节作 IV，其余作密文，AES-256-CBC 解密后去掉 PKCS7 padding，得到 JSON。
- **密钥缓存**：勾选「记住密钥」存在 localStorage（7 天），否则只存 sessionStorage，关掉标签页即失效。
  右上角锁形按钮可随时清除缓存并回到解锁页。

> 密码请只用 **ASCII 字符**。中文密码在 Python 侧按字节截断可能产生无效 UTF-8，导致两端密钥不一致。

修改主密码有两种方式：

```bash
# 方式一：环境变量（推荐，不写进代码）
export KAOYAN_KEY="your-new-password"      # Windows: set KAOYAN_KEY=your-new-password

# 方式二：改 update.py 里的 MASTER_PASSWORD 常量
```

改完后重新执行 `python update.py` 重新生成 `data.enc` 即可。

---

## 五、每天怎么用（Agent 工作流）

### 1. 说一句话就行

> "今天学了 10 个小时。数学刷真题做错题花了 4.5h；英语背单词做真题阅读 2h；政治看了强化课 1.5h；专业课背书 2h。数学线性代数还是错很多，明天得专项巩固。"

Agent 会把它结构化成：

```json
{
  "date": "2026-09-11",
  "total_hours": 10,
  "subject_hours": { "数学": 4.5, "英语": 2.0, "政治": 1.5, "408": 2.0 },
  "time_segments": [
    { "start": "07:00", "end": "09:00", "subject": "英语", "content": "背单词 + 真题阅读 2 篇" }
  ],
  "completed_tasks": ["数学真题第一套"],
  "reflection": "数学线性代数还是错很多，明天得专项巩固。",
  "tomorrow_plan": ["线代专项巩固 2h"]
}
```

### 2. 写入并加密

```bash
# 追加当天记录（可直接传 JSON 文件）
python update.py --daily @day.json --push

# 顺手更新里程碑
python update.py --milestone '{"id":"m3","progress":70}'

# 只同步笔记 + 重新加密
python update.py
```

`--push` 会执行 `git add data.enc index.html && git commit && git push`，GitHub Pages 约 1 分钟后生效。

### 3. 上传一篇笔记

把文件丢进 `notes_src/`，然后 `python update.py`：

| 文件类型 | 处理方式 |
| --- | --- |
| `*.md` | 正文直接写进 `data.json`（体积小，随 `data.enc` 一起加密） |
| `*.pdf` | **单独** AES 加密到 `notes_enc/<名字>.enc`，`data.json` 里只登记路径，前端点击时才拉取解密 |

两种都按 `file` 字段匹配已有笔记（更新）或新建：

- 标题：Markdown 取首个 `# 标题`；PDF 取文件名（支持 `os-操作系统讲义.pdf` 这种"学科-标题"命名，标题自动取横线后半段）
- 学科：先看文件名里的缩写（`ds / os / co / cn / math / zz / en`），再回退到内容关键词
- 上传日期：自动记为当天
- 重复执行是幂等的：PDF 源文件没改动就不会重新加密

> PDF 示例：`notes_src/os-输入输出管理.pdf` → `notes_enc/os-输入输出管理.enc`
> （46419 字节的 PDF 加密后是 46448 字节，只多了 16 字节 IV 与对齐填充，**没有 base64 的 33% 膨胀**）

### 4. PDF 是怎么加密与阅读的

```
notes_src/x.pdf  ──AES-256-CBC──►  notes_enc/x.enc（二进制：IV[16] + 密文）
                                          │  fetch（按需）
                                          ▼
                       前端用主密码解密 ──► Blob ──► 浏览器内置 PDF 阅读器
```

阅读端**没有引入 PDF.js**，而是解密后生成 `Blob` URL 交给浏览器内置阅读器（`<iframe>`）。
这样做的原因：不额外加载 1MB 依赖、不受 worker 版本/跨域问题影响，Chrome / Edge / Firefox / Safari
（含移动端）都能直接滚动、缩放、检索、打印，并提供「新窗口打开」「下载」两个入口。

> 想用 PDF.js 自绘也可以，但需要处理 worker 与主线程模块实例不一致的问题；
> 内置阅读器方案在可靠性和体积上都更划算。

---

## 六、数据字段速查

### meta
| 字段 | 说明 |
| --- | --- |
| `exam_date` | 考试日期，倒计时终点（默认当天 08:30） |
| `sprint_start` | 冲刺起点，用于算总进度 |
| `total_days` | 总天数，用于算冲刺百分比 |
| `quotes` | 每日一句，按日期轮换 |
| `subjects` | 学科顺序，决定卡片与配色顺序 |

### milestones[]
| 字段 | 说明 |
| --- | --- |
| `planned_start` / `planned_end` | **紫色虚线**：预计工期 |
| `actual_start` / `actual_end` | **蓝色实心**：实际工期；`actual_end` 为 `null` 表示仍在进行，条会延伸到今天 |
| `progress` | 0–100，决定紫条内部填充比例 |
| `status` | `pending` / `ongoing` / `done` |

### daily_logs[]
`subject_hours` 驱动环形圆盘图；`time_segments` 驱动分时段时间轴；`reflection` 支持 Markdown。

### notes[]
| 字段 | 说明 |
| --- | --- |
| `type` | `md` 或 `pdf`，决定阅读页用哪种渲染 |
| `content` | Markdown 原文（`type: md` 时使用） |
| `enc` | 加密 PDF 的相对路径（`type: pdf` 时使用） |
| `uploaded_at` | 显示在书脊底部与阅读页标签上 |
| `file` | 对应 `notes_src/` 里的源文件名，供脚本做增量匹配 |

---

## 七、部署到 GitHub Pages

```bash
git init
git add index.html data.enc data.sample.json update.py tools README.md .gitignore
git commit -m "init: 百日研途看板"
git remote add origin git@github.com:<你的账号>/<仓库名>.git
git push -u origin main
```

然后在仓库 **Settings → Pages** 里选择 `Deploy from a branch` → `main` / `root`，稍等片刻即可访问
`https://<你的账号>.github.io/<仓库名>/`。

> 私有仓库的 Pages 需要 GitHub Pro；公开仓库则意味着 `index.html` 和 `data.enc` 对所有人可见 ——
> 这正是加密存在的意义：**别人能拿到密文，但没有密码就什么也看不到。**

---

## 八、常见问题

**Q：打开页面一直显示「还没有数据文件」？**
`data.enc` 没被上传，或路径不对。检查它与 `index.html` 是否在同一层目录。

**Q：密码明明是对的，却说密码不正确？**
多半是密钥派生不一致，通常是密码里含中文或包含首尾空格。用 ASCII 密码重新加密一次。

**Q：甘特图上看不到某些任务？**
窗口默认显示「今天前 12 天 + 之后 58 天」，用右上角「上一月 / 下一月 / 回到今天」切换浏览范围。

**Q：怎么验证加密有没有问题？**
```bash
python update.py --verify        # Python 侧解密并打印摘要（含 PDF 清单）
node tools/verify_crypto.js      # 用前端同款逻辑解密，验证跨端一致
```

**Q：PDF 点开提示「找不到加密文件」？**
说明 `notes_enc/*.enc` 没被推送。执行 `python update.py --push`，确认 `data.enc` 与 `notes_enc/` 都进了仓库。

**Q：PDF 能正常打开但中文是乱码/方块？**
那是 PDF 自身没有嵌入中文字体（多见于扫描件或某些导出工具）。可以「下载」后用本地阅读器确认，
本项目的加密链路不影响 PDF 内部质量。

**Q：PDF 文件名用中文会不会有问题？**
在 GitHub Pages 上一般没问题（浏览器会自动做 URL 编码）。若遇到取不到文件，
把文件名改成英文（如 `os-io-chapter5.pdf`）再 `python update.py` 即可。

**Q：想临时看看效果，不想输密码？**
解锁页左下或浏览器控制台执行 `__demo(true)` 载入内置示范数据，`__demo(false)` 退出。
（示范数据不含 PDF 文件，PDF 需要真实主密码解锁后才能解密。）

---

每一小时都算数。祝上岸。
