# 2026 灯具设计师理论题库刷题站 · 开发规格

纯静态站点，**零构建**（原生 HTML/CSS/ES Modules），直接部署到 GitHub Pages 仓库根目录即可运行。
不引入 npm 依赖、打包器、框架。不写 TypeScript。

站点标题：`2026 第五届全国工业设计职业技能大赛 灯具设计师理论题库`
副标题：`2026 年全国行业职业技能竞赛 · 灯具设计师赛项`

---

## 1. 数据契约（唯一权威，不可改）

运行时只加载 `data/questions.json`（同目录，相对路径）。用 `fetch('data/questions.json')` 加载。

```json
{
  "meta": {
    "title": "2026 第五届全国工业设计职业技能大赛 灯具设计师理论题库",
    "version": "2026-c5-r1",
    "total": 700,
    "activeTotal": 700
  },
  "chapters": [
    { "id": "c1", "name": "3D打印与增材制造", "order": 1, "count": 70 }
  ],
  "questions": [
    {
      "id": "qs001",
      "no": 1,
      "page": 2,
      "type": "single",
      "chapter": "c1",
      "stem": "STL文件采用一系列（　　）平面来逼近原来的模型。",
      "options": [
        { "key": "A", "text": "小三角形" },
        { "key": "B", "text": "小四边形" },
        { "key": "C", "text": "空间三角形" },
        { "key": "D", "text": "空间四边形" }
      ],
      "answer": ["A"],
      "explain": "",
      "flag": "",
      "dupOf": null,
      "note": ""
    }
  ]
}
```

字段约定：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 稳定唯一：题型前缀 + 3 位题号，`qs001` / `qm001` / `qj001`。**三个大题各自从 1 编号，所以 id 必须带前缀，否则会重号** |
| `no` | number | PDF 该大题内的原始题号（单选 1–440 / 多选 1–100 / 判断 1–160） |
| `page` | number | PDF 页码 |
| `type` | `"single" \| "multi" \| "judge"` | 单选 / 多选 / 判断 |
| `chapter` | string | 章节 id，必须存在于顶层 `chapters[].id` |
| `stem` | string | 题干。占位符统一为 `（　　）`（全角括号 + 两个全角空格）；判断题题干不带占位符且以句号收尾 |
| `options` | array | `single`/`multi` 为 4 项，`judge` 固定为 `[{"key":"T","text":"正确"},{"key":"F","text":"错误"}]` |
| `answer` | string[] | 正确答案 key 数组。`single`/`judge` 长度为 1；`multi` 长度 ≥ 2 |
| `explain` | string | 解析，题库无解析时为空字符串（本期全空） |
| `flag` | string | 空串正常；`"review"` 源数据有疑点但可正常作答；`"broken"` 题目已损坏，**前端始终排除，不给开关** |
| `dupOf` | `null` 或 string | 重复题指向保留题的 `id`；默认不在任何练习中抽取（可通过「包含重复题」设置开启） |
| `note` | string | 校对备注（题干做过规范化处理等），正常题为空串 |

`chapters[]` 元素带 `count`（该章节可练题数）。`meta.total` 为数组总长度，`meta.activeTotal` 为实际可练题数（已排除重复题与 broken 题），首页「题库总数」用它。

`chapters` 至少包含 `c1`…`c8` 八个正课章节。章节可能为空——UI 必须能容忍，显示「暂无题目」而不是崩。

### 判分规则（硬要求）

- `single` / `judge`：所选 key 集合与 `answer` 集合完全相等 → 对，否则错。
- `multi`：**全对才给分**。漏选或多选一律判错，没有任何部分分。
- 单选题若用户只选了一项，直接判定；多选题必须点「提交答案」才判定。

### 选项乱序规则

- 只对 `single`/`multi` 生效，`judge` 永远不乱序。
- 乱序必须是**确定性**的：同一道题在同一次作答中反复渲染（比如回看）顺序不变。用 `seed = hash(question.id + shuffleSalt)` 洗牌，不要直接用 `Math.random()`。
- 乱序后显示字母 A/B/C/D 仍按位置从 A 开始重新编号，但判分必须映射回原始 `key`。
- 每个会话随机生成一次 `shuffleSalt`（sessionStorage 存，避免刷新后同题顺序突变）。

### 题号显示

三个大题题号各自从 1 开始，直接显示 `no` 会出现三个「No.1」。界面统一用 `questionNoLabel()`：
`单071` / `多012` / `判003`（题型简称 + 三位题号），练习卡片再追加 PDF 页码 `P10`。

---

## 2. 功能需求（全部要实现）

路由用 hash：`#/`、`#/chapters` 等。无后端。

### 2.1 首页 `#/`

- 大标题 + 副标题 + 可练题数 / 章节数 / 累计已答
- 四个数字卡：可练题目、已练题数、今日待复习、错题本数量
- 快捷入口：开始练习、模拟考试、今日复习、错题本
- 八个章节进度条（已练/总数 + 正确率），点击进章节练习
- 连续打卡天数（当天有任一答题记录算打卡）

### 2.2 章节练习 `#/chapters` + `#/practice`

- `#/chapters`：卡片列表，每张卡显示章节名、题数、已练数、正确率、进度条；点击 → `#/practice?chapter=c1`
- `#/practice` 支持 query：`chapter=<id>`、`scope=all|wrong|favorite|review`、`shuffle=1`
- 一次一题。单选/判断点击选项立即判定并显示对错与正确答案；多选勾选后点「提交」判定。
- 判定后显示：✓/✗ 反馈条、正确答案（多选显示 "ABC"）、「下一题」按钮（可设置自动下一题，1.2s 后跳）。
- 顶部进度：`第 n / N 题` + 进度条 + 退出按钮。
- 「上一题」回看已答题（只读，不重复计分）。
- 会话结束显示小结：答对数/总数、正确率、用时、错题列表（可一键重练错题）。
- 每题可 ★ 收藏；答错自动进错题本。

### 2.3 模拟考试 `#/exam`

- 设置页：范围（全部 / 指定章节）、题量（20 / 50 / 100 / 全部）、时长（30 / 60 / 90 / 120 分钟）、是否选项乱序。
- 题型配比：按范围内实际题型比例抽取，保证单选、多选、判断都有（某题型不足则不限）。
- 考试中：倒计时（最后 60s 变红）；答题卡面板（已答/未答/标记不同颜色，点击跳转）；可标记「不确定」；可提前交卷（二次确认）。
- 时间到自动交卷。
- 成绩页：得分（每题 1 分）、正确率、用时、按题型拆分正确率、逐题回顾（你的答案 vs 正确答案）。成绩存本地历史（最多 20 条）。

### 2.4 错题本 `#/wrong`

- 列表：题干摘要、类型、错误次数、最近错误时间、章节
- 操作：开始重练（`#/practice?scope=wrong`）、单题「已掌握」移出、清空
- 支持按章节/题型筛选
- 重练答对不自动移出（用户手动标「已掌握」），但显示「连续答对 2 次」提示

### 2.5 收藏 `#/favorites`

- 列表 + 开始重练（`#/practice?scope=favorite`）+ 取消收藏

### 2.6 记忆曲线 `#/review`

- 简化版间隔重复（SM-2 lite）：
  - 状态 `{ level: 0..5, due: 'YYYY-MM-DD', lastSeen: ISO, reps, lapses }`
  - 间隔表：`[1, 2, 4, 7, 15, 30]` 天
  - 答对：`level = min(level+1, 5)`，`due = 今天 + 间隔[level]`
  - 答错：`level = 0`，`due = 今天`
  - 新题（未学过）不进复习队列
- 页面：今日待复习数量、按 level 分组的数量（0–5 六档）、「开始今日复习」按钮 → `#/practice?scope=review`
- 复习顺序：先 level 低的，再按 due 升序。

### 2.7 统计 `#/stats` + 设置 `#/settings`

统计：累计答题数、累计正确率、连续打卡、最长连续打卡、近 14 天答题量柱状图（纯 CSS，不引库）、各章节正确率横向条形图、考试历史列表。

设置：选项乱序（默认开）、答题后自动下一题（默认关）、主题跟随系统/浅色/深色、包含重复题（默认关）、数据导出（下载 JSON）/ 导入 / 清空所有数据（二次确认）、版本号。

---

## 3. 本地存储

前缀统一 `lamp26:`（与上一届 `lampq:` 区分，两站数据互不干扰）。键：

- `lamp26:progress` → `{ [questionId]: { seen, correct, wrong, lastSeen, level, due, reps, lapses } }`
- `lamp26:wrong` → `{ [questionId]: { count, lastWrongAt, streak } }`
- `lamp26:favorites` → `string[]`
- `lamp26:settings` → `{ shuffle, autoNext, theme, includeDup }`
- `lamp26:stats` → `{ daily: { 'YYYY-MM-DD': { answered, correct } }, examHistory: [] }`
- `lamp26:session` → sessionStorage，乱序 salt + 未完成的考试状态（刷新可恢复考试）

所有写入要 try/catch 兜底（隐私模式 / 配额满）。

---

## 4. 文件布局

```
index.html
404.html
css/style.css
js/app.js          # 入口：加载数据、hash 路由、全局壳（顶栏/底栏）
js/store.js        # localStorage 读写、默认值、导出导入、迁移
js/srs.js          # 记忆曲线调度
js/quiz.js         # 出题队列、选项乱序、判分、题号标签
js/ui.js           # DOM 辅助（h()、toast、modal、进度条等）
js/views/home.js
js/views/chapters.js
js/views/practice.js
js/views/exam.js
js/views/wrong.js
js/views/favorites.js
js/views/review.js
js/views/stats.js
js/views/settings.js
data/questions.json
docs/题库校对表.xlsx
tools/{extract,parse,build}.py
```

`index.html` 用 `<script type="module" src="js/app.js"></script>`。

---

## 5. 样式与体验要求

- 移动端优先，桌面居中最大宽度 860px。
- 中文正文字体栈：`system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif`。
- 暖调学院风（纸本质感），CSS 变量做主题，`[data-theme="dark"]` 覆盖；主色 `#33526e`，正确 `#3f6b52`，错误 `#a5433a`。
- 选项按钮要有明显的选中/正确/错误三态（正确绿边、错误红边、漏选的多选正确答案用虚绿边提示）。
- 所有按钮有 `:active` 反馈，禁用态有样式。
- 无障碍：选项用 `<button>`，可 Tab 聚焦，`aria-label` 补全。
- 不用 alert 做交互，用自定义 toast / modal。
- 空状态要有文案。

---

## 6. 数据现状（2026-10 实测）

`data/questions.json` 由 `tools/extract.py` + `tools/parse.py` + `tools/build.py` 从源 PDF 生成，**不要再手工覆盖**。

- `questions` 共 **700** 条：单选 440 / 多选 100 / 判断 160；
- 重复题 0、损坏题 0，**可练 700 题**；
- 章节：
  | id | 名称 | 题数 |
  |---|---|---|
  | c1 | 3D打印与增材制造 | 70 |
  | c2 | PDM与数字化设计 | 69 |
  | c3 | 设计史与设计理论 | 130 |
  | c4 | 机械制图与机械设计 | 158 |
  | c5 | 灯具设计与照明技术 | 137 |
  | c6 | 材料工艺与质量安全 | 52 |
  | c7 | AI辅助设计与CMF | 50 |
  | c8 | 逆向设计与产品开发 | 34 |

  章节由 PDF 的题块区间确定（三节各自成块），块内少量混排题按关键词改判 22 条。
- 选项数量：单选/多选均为 4 个；判断题固定 2 个。布局仍按 `options.length` 自适应，不要写死。
- `flag` 全为空，`dupOf` 全为 `null`，`explain` 全为空（题库本身无解析）。
- 已知源 PDF 瑕疵（保留原样，未改）：
  - 单选 Q317 选项 `100 1x / 110 1x / 120 1x / 130 lx` 里的 `1x` 是 PDF 把 `lx` 打成 `l`+`x`，保留原样；
  - 单选 Q353「比列」应为「比例」，保留原样；
  - 判断题 Q122「拉上有多于两种的不同产品流拉。」疑为原文错字，保留原样；
  - 判断题 Q151–Q154 的题干本身就是长段说明文，不是截断。

---

## 7. 验收标准

1. `python -m http.server 8123` 打开 `http://localhost:8123/`，全部页面可访问，控制台无报错。
2. 走通：章节练习 → 多选判分（全对/漏选/多选三种情况）→ 错题进入错题本 → 收藏 → 模拟考试计时交卷 → 记忆曲线出现待复习 → 统计页数字变化 → 设置里切换乱序/深色模式 → 导出导入。
3. 700 题规模下列表不卡顿；首页初始渲染 < 1s。
4. 刷新页面状态不丢（localStorage）。
5. 所有界面文案中文。
