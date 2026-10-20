# BioReport 双语 HTML 性能优化实施手册

- 版本：v1.0（2026-10-20）
- 性质：活文档。同一主题的后续迭代追加新 Part/章节，不另起文档。
- 配套材料：`bilingual-html-performance-investigation.md`（现状与基线）、`adr-bilingual-html-delivery.md`（ADR 提案）
- 施工方式：每阶段的代码块提示词整段粘贴给编码 Agent；**验收权在用户手里，不接受编码 Agent 自报通过**。

---

## 0. 背景与决策记录

### 0.1 现状基线（引自调查文档，本手册所有验收对照此基线）

| 指标 | 当前基线 |
| --- | ---: |
| 最终双语单 HTML | 60,286,093 bytes（约 57.5 MiB） |
| 单语言未压缩 HTML | 约 67.7 MB |
| 首屏显示（中文，`file://`，Playwright Chromium） | 约 10.57 秒 |
| 切换英文后显示 | 约 8.93 秒 |
| DEG 表 | 23,076 行，itables 序列化约 20.94 MB/语言 |
| CJK 字体（HarmonyOS Sans regular + bold） | 约 16.42 MB/语言 |
| Plotly runtime + 初始化脚本 | runtime 约 4.85 MB；初始化约 12.05 MB/语言 |
| Mermaid runtime | 约 2.67 MB/语言 |

### 0.2 本轮已确认的决策（2026-10-20，用户对三个待确认项均无偏好，按以下默认执行）

1. **快赢先行**：Phase 1 不动交付架构，先做五项优化，先见效；架构迁移放 Phase 2。
2. **目标交付形态**：Phase 2 迁移为「单一 Quarto website 项目 → ZIP 网站包 + 本地 HTTP 启动入口」；同时评估「双 HTML + 共享 assets 目录」变体作为保留双击打开的备选（PoC 已证明 `file://` 下普通 CSS/JS/字体可读，只有 3 个 ES module 被 Chromium CORS 拦截）。
3. **过渡期保留 legacy 单文件选项**：Phase 1 优化后的单文件作为 legacy 交付保留至少一个大版本，输出弃用提示，下游迁移完成后在下一主版本移除。

### 0.3 目标指标（估计值，需实测校正）

| 指标 | 基线 | Phase 1 目标 | Phase 2 目标 |
| --- | ---: | ---: | ---: |
| 交付体积 | 60.29 MB（单文件） | ≤ 25 MB（单文件） | ZIP 压缩 ≤ 30 MB，解压 ≤ 80 MB |
| 首屏显示 | 10.57 秒 | ≤ 5 秒 | 入口 ≤ 2 秒；Results 首开 ≤ 5 秒 |
| 语言切换 | 8.93 秒 | 二次切换 ≤ 1 秒 | 普通链接跳转，≤ 2 秒 |
| 表格首次可搜索 | 随首屏阻塞 | 进入 Results 后 ≤ 3 秒 | 同左 |

---

## 1. 阶段总览

| 阶段 | 内容 | 风险 | 依赖 |
| --- | --- | --- | --- |
| Phase 1A | 构建期资源瘦身：字体子集化、Plotly partial bundle、Mermaid 预渲染 SVG | 低 | 无 |
| Phase 1B | 外壳 JS：语言切换缓存 + 闲时预解压 | 低 | 无 |
| Phase 1C | DEG 表紧凑序列化 + 延迟初始化 | 中（触碰表格展示链路） | 无 |
| Phase 2 | 共享资源 website 包（ADR 目标架构） | 高 | Phase 1 验收完成 |
| Phase 3 | 打包、迁移策略、文档与弃用提示 | 低 | Phase 2 验收完成 |

Phase 1A/1B/1C 互相独立，可并行下发三个编码 Agent 会话，也可串行。每个阶段必须独立验收后再进下一阶段。

---

## 2. Phase 1A：构建期资源瘦身

**改动锚点**：`bioreport/utils/font_stage.py`、`bioreport/renderer.py`、`bioreport/utils/render_output.py::show_figure`、`templates/_quarto-single.yml.j2`。

**原则**：只改资源生成与引用方式，不动报告内容、章节结构、分析逻辑。

### 提示词 P1A（整段粘贴）

```text
在现有 BioReport 仓库基础上做构建期资源瘦身，目标是降低 RNA-seq 双语单 HTML 的体积。
禁止推倒重写任何渲染逻辑，先读代码再改；所有结论和改动标注文件路径。

背景：当前单语言 HTML 约 67.7 MB，其中 CJK 字体（HarmonyOS Sans regular + bold）约
16.42 MB 以 Base64 内嵌在 CSS 里，Plotly runtime 约 4.85 MB 内嵌，Mermaid runtime
约 2.67 MB 内嵌。相关代码：bioreport/utils/font_stage.py、bioreport/renderer.py、
bioreport/utils/render_output.py::show_figure、templates/_quarto-single.yml.j2。

任务 1：字体子集化。
- 在构建流程中，渲染完成后收集该报告 HTML 实际出现的全部字符（两语言分别收集或合并
  收集，取并集），用 fonttools 的 pyftsubset 对 HarmonyOS Sans regular 和 bold 做子集化，
  保留 woff2 格式，再 Base64 内嵌。
- 子集化必须保留：报告正文全部字符、UI 文案全部字符（含语言切换按钮、表格控件提示
  文字）、Plotly 悬浮框可能出现的字符（坐标轴标签、图例、基因名所需的 ASCII + 常用符号）。
  建议字符集 = 报告文本并集 + ASCII 全量 + 常用标点符号表，构建时打印子集后字体大小。
- 验收硬性要求：不允许出现缺字（豆腐块）。构建脚本输出被剔除但被引用的字符警告。
- 注意 PDF 输出路径是否共用字体：若共用且 PDF 需要完整字体，PDF 路径保留完整字体，
  只对 HTML 内嵌做子集化。先查 font_stage.py 确认两条路径的关系再动手。

任务 2：Plotly partial bundle。
- 先静态扫描仓库中所有 Plotly 图表调用，列出实际使用的 trace 类型清单（scatter/bar/
  heatmap/box/violin 等），把清单打印出来。
- 若只用到 plotly-basic 覆盖的类型，把 show_figure 内嵌的完整 plotly.js 替换为对应
  partial bundle（本地文件，禁止 CDN）。若超出 basic 覆盖范围，选能覆盖的最小官方
  bundle，并在输出中说明取舍。
- 替换后用真实报告实测：所有图表渲染、悬浮、缩放、下载 PNG 功能正常。

任务 3：Mermaid 预渲染。
- 先列出报告中所有 Mermaid 图的位置和数量。
- 若全部为静态图（无运行期动态生成），构建期用 mermaid-cli（mmdc）预渲染为 SVG 内嵌，
  移除 Mermaid runtime 的 2.67 MB。若有运行期动态场景，保留 runtime 并在输出中说明。
- 预渲染 SVG 必须保留原图的文字可选中性和清晰度，主题配色与报告一致。

通用约束：
- 保持完全离线，禁止引入任何 CDN/外网引用。
- 每个任务完成后用同一测试项目重新生成报告，输出新旧体积对照（最终文件、字体段、
  script 总量），并用 Playwright Chromium 在 file:// 下实测首屏时间。
- 三个任务分成三个独立 commit，便于单独回退。
```

### Phase 1A 验收 checklist（用户手测）

| 操作 | 期望现象 | 不通过时的处理 |
| --- | --- | --- |
| 用同一项目重新生成报告，看构建日志 | 打印子集字符数、子集后字体大小、Plotly trace 清单、Mermaid 图数量 | 缺任何一项输出，打回要求补日志 |
| 对比新旧最终 HTML 文件大小 | 明显下降（预期单项字体就省约 15 MB×2 语言的 Base64 体积） | 无变化说明未生效，检查 embed 配置是否仍引用旧字体 |
| 断网打开报告，通读中文全文 + 切英文 | 无任何豆腐块/缺字符号 | 有缺字则扩大子集字符集（通常是表格控件或 Plotly 悬浮文案漏了） |
| 逐张图表测试悬浮、缩放、框选、下载 PNG | 与旧版行为一致 | 缺失功能说明 trace 类型超出 bundle 覆盖，换更大 bundle |
| 检查 Mermaid 图 | 显示清晰、配色与报告一致 | 模糊或错位则检查 SVG 主题参数 |
| 断网 + DevTools Network 面板 | 无任何外网请求 | 出现 CDN 请求直接打回 |

---

## 3. Phase 1B：外壳 JS——语言切换缓存与闲时预解压

**改动锚点**：`bioreport/i18n.py::combine_language_editions` 生成的外层 HTML 外壳脚本。

**原则**：只改外壳 JS 的解码/缓存策略，不动两份内嵌报告本身；单文件交付形态不变。

### 提示词 P1B（整段粘贴）

```text
在现有 BioReport 仓库中，只修改 bioreport/i18n.py::combine_language_editions 生成的
外层 HTML 外壳脚本，优化语言切换性能。先读现有实现再改，不改 Quarto 渲染流程、不改
内嵌的两份报告内容。

现状问题：外壳把两份 gzip+Base64 的完整 HTML 放在 script 节点里。打开时 atob → 逐字节
拷贝 → DecompressionStream('gzip') → iframe.srcdoc；每次切换语言都重新跑完整链路，
没有缓存。本机实测首屏约 10.57 秒，切换约 8.93 秒。

任务：
1. 缓存已解压结果：每份语言解压后的完整 HTML 字符串缓存在内存 Map（key=语言），
   切换时命中缓存直接赋 iframe.srcdoc，不再重复解码解压。二次切换应接近瞬时。
2. 闲时预解压：首屏渲染完成后，用 requestIdleCallback（退化 setTimeout）或 Web Worker
   在后台解压另一份语言并存入缓存。用户首次切换时若预解压已完成则瞬时，未完成则显示
   加载提示并继续当前解压。
3. 内存保护：两份解压后 HTML 合计约 135 MB 字符串，属可接受范围；但iframe.srcdoc
   赋值前 revoke 旧的 blob/清理不再需要的中间 Uint8Array，避免峰值内存翻倍。
4. 解压路径加 try/catch：DecompressionStream 不可用的旧浏览器给出明确提示文案
  （中英文各一句），而不是白屏。

验收（编码 Agent 自测 + 用户复测）：
- Playwright Chromium file:// 实测：首屏时间、首次切换时间、二次切换时间，输出
  对照表（基线：10.57 / 8.93 秒）。二次切换必须 ≤ 1 秒。
- 连续来回切换 10 次无内存持续增长（performance.memory 或任务管理器观察）、无报错。
- Chrome 之外用 Firefox 实测一次（DecompressionStream 兼容性路径）。
- 单文件交付形态、双击打开方式完全不变。
```

### Phase 1B 验收 checklist（用户手测）

| 操作 | 期望现象 | 不通过时的处理 |
| --- | --- | --- |
| 双击打开报告 | 首屏时间与旧版相当或更快 | 变慢说明预解压抢占了主线程，要求改为更保守的调度 |
| 首次切换语言 | 有加载提示或已瞬时（取决于预解压是否完成） | 白屏/卡死打回 |
| 二次及以后来回切换 | ≤ 1 秒，无闪烁重建 | 仍数秒说明缓存未命中，要求出示缓存逻辑说明 |
| DevTools Console | 无任何报错 | 有报错打回 |
| 模拟旧浏览器（或要求 Agent 演示降级路径） | 出现明确提示而非白屏 | 白屏打回 |

---

## 4. Phase 1C：DEG 表紧凑序列化与延迟初始化

**改动锚点**：`omics/rna/qmd/modules/results/deg.qmd`、`bioreport/utils/visualize_utils.py` 中的 `display_gene_expression_table`。

**原则**：完整保留 23,076 行数据和全部表格交互（排序、分页、搜索、复制、导出），**禁止以截断数据换速度**；只改序列化格式和初始化时机。

### 提示词 P1C（整段粘贴）

```text
在现有 BioReport 仓库中优化差异表达表的加载性能。先读
omics/rna/qmd/modules/results/deg.qmd 和 bioreport/utils/visualize_utils.py 的
display_gene_expression_table，理解当前 itables 的完整展示链路再动手。禁止推倒重写，
禁止减少任何一行数据，禁止移除排序/分页/搜索/复制/导出中的任何功能。

现状问题：完整 DEG DataFrame（当前样例 23,076 行）直接交给 itables，序列化内容约
20.94 MB/语言进入首屏 HTML，是单语言最大数据块，且首屏就要解析初始化。

任务：
1. 紧凑序列化：把表数据从 itables 默认序列化格式改为紧凑 JSON（array-of-arrays，
   列名单独一份，不带逐行键名），嵌入页面。对比新旧序列化体积并输出（预期减半左右）。
   数字列在序列化前按展示精度做合理 round（先确认当前展示精度，不改变展示结果）。
2. 延迟初始化：页面加载时不构建 DataTable，只渲染表格区域的占位骨架（含"表格加载中"
   提示）。当用户滚动到 Results 章节或表格容器进入视口（IntersectionObserver）时，
   再用内嵌的紧凑 JSON 构建 DataTable，启用 deferRender: true。
3. 保留 itables/DataTables 的全部既有功能：排序、分页、搜索、复制、导出按钮，逐项
   列在输出里并逐张截图证明可用。
4. 若 itables 的 Python API 不支持上述自定义，允许绕过 itables 直接用 DataTables
   原生 JS 初始化（离线，JS 库文件随报告内嵌，禁止 CDN），但样式必须与报告主题一致。

验收：
- 新旧报告对比：DEG 行数完全一致（23,076 行逐行抽验首尾与随机 100 行）。
- 首屏 HTML 中 script 段体积对照表；首屏时间与表格首次可搜索时间实测。
- 表格所有交互真实浏览器操作通过，含导出 CSV 的行数校验。
```

### Phase 1C 验收 checklist（用户手测）

| 操作 | 期望现象 | 不通过时的处理 |
| --- | --- | --- |
| 打开报告，不滚动 | 表格区域是占位骨架，首屏明显变快 | 首屏仍阻塞说明初始化未延迟，打回 |
| 滚动到 DEG 表格 | 出现加载提示后表格渲染 | 空白或无提示打回 |
| 搜索任意基因名、排序、翻页 | 结果正确 | 数据缺失打回（重点怀疑序列化丢行） |
| 导出 CSV，对比行数 | 23,076 行 + 表头 | 行数不符打回 |
| 数值列抽查 | 与旧版展示精度一致 | 精度变化需说明是否可接受 |

---

## 5. Phase 2：共享资源 website 包（ADR 目标架构）

**前置条件**：Phase 1 全部验收完成；ADR《RNA-seq 双语 HTML 交付改为共享资源网站包》已确认（2026-10-20 确认按默认策略执行）。

**改动锚点**：`bioreport/cli.py`（双语渲染循环）、`bioreport/modules.py::compose_report(..., website=True)`、`bioreport/i18n.py`、`templates/_quarto.yml.j2`、`bioreport/renderer.py`、`bioreport/utils/font_stage.py`、`bioreport/utils/render_output.py::show_figure`。

**已验证事实（来自调查文档与 PoC，可直接引用给编码 Agent）**：
- PoC（Quarto 1.8.26，`/tmp/bioreport-quarto-shared-poc`）已验证单一 Quarto website 项目可输出 `index.html`、`zh/report.html`、`en/report.html`，两语言共用一份 `site_libs`（18 个文件），字体 CSS 相对路径跨语言可引用。
- `compose_report(..., website=True)` 已为每个页面写入语言初始化代码，两语言页面可作为同一项目的不同源文件渲染。
- 当前实现把两语言生成到同名 `qmd/site-*.qmd` 再两次渲染，**不能只合并两个现有目录**（实测 35 组重复文件、字体 CSS 绝对路径错误）。
- Chromium `file://` 拦截 Quarto 的 3 个 ES module 请求；本地 HTTP 服务下全部 200。
- `show_figure` 每页内嵌一次约 4.85 MB Plotly runtime，website 模式下四页共约 19.4 MB，必须改为共享静态文件。

### 提示词 P2（整段粘贴）

```text
在现有 BioReport 仓库实施 ADR《RNA-seq 双语 HTML 交付改为共享资源网站包》。
这是一次架构迁移，先完整阅读 docs/adr-bilingual-html-delivery.md 和
docs/bilingual-html-performance-investigation.md，再读 bioreport/cli.py、
bioreport/modules.py、bioreport/i18n.py、templates/_quarto.yml.j2、
bioreport/renderer.py、bioreport/utils/font_stage.py、
bioreport/utils/render_output.py。禁止推倒重写分析逻辑与模块内容；PDF 输出路径不动。

目标产物结构：
<project_id>_report/
├── index.html          # 轻量语言入口，不含任何完整报告内容
├── zh/...              # 中文各章节页面
├── en/...              # 英文各章节页面
├── site_libs/          # 两语言共享，仅一份
├── assets/             # 字体、Plotly runtime、DEG 数据等共享静态资源
└── serve-report.py     # 本地 HTTP 启动入口

实施要求：
1. 单一 Quarto website 项目一次构建：两语言页面作为同一项目的不同源文件
   （zh/ 与 en/ 路径前缀），统一 render 清单与输出根目录。不要跑两套 project 再拼目录
   ——已有实测证据显示那会重复资源。
2. 语言切换：普通相对链接，切换时尽量保留对应章节锚点（zh/results.html#deg ↔
   en/results.html#deg）。
3. Plotly runtime 共享：show_figure 改为引用 assets/ 下唯一一份 plotly 静态 JS
  （沿用 Phase 1A 选定的 partial bundle），含图表页面引用它。禁止 CDN。
4. DEG 数据外置：完整数据写入 assets/ 下 JSON（沿用 Phase 1C 的紧凑格式），Results
   页面打开/表格进入视口时客户端 fetch 加载。保留排序、分页、搜索、复制、导出全部
   功能。不做 DataTables server-side processing（离线包没有后端）。
5. 字体 CSS 改相对路径：已有实验发现 font_stage 生成绝对路径导致 404，必须改为
   项目内相对路径并实测两语言页面字体均生效。
6. serve-report.py：零依赖（标准库 http.server），自动开浏览器，打印访问地址；
   不访问任何外网。README 同时写明 python -m http.server 等价命令。
7. 打包：构建产物压缩为 <project_id>_report.zip；CLI 摘要、日志、产物命名同步更新。

迁移兼容（已确认的决策）：
- report.layout: single 保留为 legacy 路径，输出弃用提示（指向 ZIP 包文档），
  下一主版本再移除。迁移不能静默覆盖同名旧产物。

验收（编码 Agent 自测清单，用户将逐项复测）：
- 产物清点：site_libs、字体、Plotly runtime 各仅一份；输出文件清单与体积统计。
- 两语言页面内容、导航、锚点、品牌、Plotly 交互、DEG 表全功能，真实浏览器逐项通过。
- 断网 + ZIP 解压 + serve-report.py 启动：全部资源来自包内，DevTools 无外网请求、
  无严重 console 错误。
- 性能对照表：ZIP 压缩/解压体积、构建耗时、入口首屏、Results 首开、表格首次可搜索、
  语言切换，对照基线（60.29 MB 单文件，首屏 10.57 秒，切换 8.93 秒）。
```

### Phase 2 验收 checklist（用户手测）

| 操作 | 期望现象 | 不通过时的处理 |
| --- | --- | --- |
| 解压 ZIP，看目录结构 | 与目标结构一致，site_libs/字体/Plotly 各一份 | 重复资源打回（对照"35 组重复文件"旧问题） |
| 运行 serve-report.py | 自动开浏览器到入口页 | 需要手工装依赖则打回（要求零依赖） |
| 入口页 | 轻量、秒开、只有语言选择 | 入口包含完整报告内容打回 |
| 进入中文 → 切英文 → 切回 | 链接跳转正常，锚点落到对应章节 | 锚点丢失记录为已知问题或打回，按严重度 |
| 断网状态下完整走一遍 | 全部功能可用 | 任何外网请求打回 |
| DEG 表搜索/排序/分页/导出 | 与 single 版行为一致，行数 23,076 | 功能缺失打回 |
| DevTools Console/Network | 无 404、无外网、无严重报错 | 字体 404 是已知旧坑，重点复查相对路径 |
| 旧命令 `report.layout: single` | 仍产出单 HTML + 弃用提示 | 静默失败或静默覆盖旧产物打回 |

---

## 6. Phase 3：迁移收尾与文档

### 提示词 P3（整段粘贴）

```text
BioReport 双语交付迁移收尾。前置：Phase 2 已验收。

任务：
1. 更新 README.md 与 docs/README.zh-CN.md：新产物 <project_id>_report.zip 的打开方式
  （解压 → python serve-report.py，或 python -m http.server 等价命令）、旧单 HTML 的
   legacy 状态与移除时间表、程序化调用方迁移示例（旧产物名 → 新产物名对照）。
2. 明确写出 file:// 双击限制的说明：Quarto ES module 在 Chromium file:// 下被 CORS
   拦截，双击 index.html 不可用，必须走本地 HTTP；给出 Windows/macOS/Linux 三平台的
   启动命令。
3. 评估「双 HTML + 共享 assets 目录」变体：若去掉 Quarto 的 3 个 ES module 依赖后
   file:// 可完整运行，给出该变体作为可选交付的改造成本评估（不做实现，只出评估），
   供产品侧决定是否补一个双击打开的交付形态。
4. 更新 CLI 帮助文本与验证脚本，跑全量测试。
```

---

## 7. 风险与回退

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 字体子集漏字 | 报告出现豆腐块 | 字符集 = 报告文本并集 + ASCII 全量 + 控件文案；构建期告警；PDF 路径保留完整字体 |
| itables 绕过后样式/功能回归 | 表格体验下降 | P1C 要求逐项截图证明功能；样式对齐主题 |
| Plotly partial bundle 缺 trace 类型 | 个别图表渲染失败 | 先静态扫描 trace 清单再选 bundle；失败则换更大 bundle |
| Web Worker/requestIdleCallback 兼容性 | 旧浏览器预解压失效 | 降级为同步解压 + 加载提示，功能不受影响 |
| website 包 file:// 不可用 | 用户习惯双击打开 | legacy 单文件过渡保留；Phase 3 评估双击变体 |
| 迁移期下游调用方断裂 | 自动化管道失败 | 不静默覆盖旧产物；弃用提示提前一个主版本 |

## 8. 基线对照表（施工后填写）

| 指标 | 基线 | Phase 1 实测 | Phase 2 实测 |
| --- | ---: | ---: | ---: |
| 交付体积 | 60.29 MB | 22,819,339 bytes（22.82 MB） | （待填） |
| 首屏显示 | 10.57 s | 3.64 s（单次样本） | （待填） |
| 首次语言切换 | 8.93 s | 3.12 s 绘制；6.36 s 自动化往返 | （待填） |
| 二次语言切换 | 8.93 s | 0.173 s 绘制；十次最大 0.206 s | （待填） |
| 表格首次可搜索 | 随首屏 | 首表 0.93 s；完整 DEG 就绪 ≤ 1.96 s | （待填） |
| 构建耗时 | （补测） | 73.6 s | （待填） |

---

## Part 2 · 实施证据续记（2026-10-20）

以下是实现与自动化自测证据，供用户复测；不代表用户已验收。

### 2.1 基线数据行数核对

本地真实项目 `examples/X101SC26098749-Z01-J001/data/res/DEG/Salt_vs_AC_DEG.csv` 为 **23,075 条数据 + 1 行表头 = 23,076 文件行**。后续完整性验收以源 CSV 的数据行数为准，不补造记录。`output/theme-delivery-tables/tables-validation.json` 已验证中英文完整 DEG 导出均为 23,075 条，与源文件逐行逐值一致，且排序、搜索、分页与导出可用；另小鼠样例 33,824 条 DEG 同样通过，证据为 `output/theme-accessible-tables-source/tables-validation.json`。

### 2.2 Phase 1A · 字体子集化

实现：`bioreport/utils/html_fonts.py`、CLI 双语合并前调用、`fonttools[woff]` 显式依赖。

- 对两语言的 HTML、转义 UI / 图表文字及内嵌 SVG 文字收集字符并集，补足 ASCII、标点及常见科学符号。
- 仅重写真实 CSS style 块内的 `BioReport-CN` font-face；正文、脚本数值及代码示例不改写。
- TTF 转为 WOFF2，保留字形 hinting。重新打开字体核对所有“原字体具有且报告引用”的字形；删除任何引用字形会终止构建。
- 不修改包内字体文件及 PDF 字体路径。双语字体引用使用同一字符并集，后一次转换可复用缓存。
- 实际 CLI 输出 `font-subset-metrics.json` 和字体大小 / 字符数日志。

同一番茄项目隔离对照：

| 指标 | 主题优化后、未子集化 | 仅字体子集化 |
|---|---:|---:|
| 双语单 HTML | 61,039,849 bytes | 27,683,903 bytes |
| 每语言 CJK 原始字体 | 16,420,124 bytes | 250,988 bytes |
| 字符并集 | — | 2,781 codepoints |
| 被删除但被引用的字形 | — | 0 |

证据：`output/font-subset-poc-20261020/font-subset-metrics.json`。转换与重新合并约 8.85 秒；该数字不是完整报告构建时间。单元测试验证转义字符、SVG 字符、两语言字形并集、正文 / 数据不变及 PDF 原字体不变。

### 2.3 Phase 1A · 官方 Plotly Cartesian bundle

现有 RNA 图包含 scatter、bar、heatmap 和 violin。basic 不覆盖后两者，因此采用本地随包携带的 **plotly-cartesian 3.4.0**，与当前 Python Plotly 使用的 JS 版本一致。[官方 bundle 说明](https://github.com/plotly/plotly.js/blob/main/dist/README.md#plotlyjs-cartesian)

- 文件：`bioreport/assets/js/plotly-cartesian-3.4.0.min.js`，1,418,287 bytes。
- 来源、版本和 SHA-256：同目录 `plotly-cartesian-manifest.json`；保留官方 MIT license。
- 自定义 trace 超出 Cartesian 或 JS 版本不匹配时回退匹配的完整本地运行库；禁止运行期下载。
- 核心按实际 figure trace 选择，保留全部图表数据与配置。普通 RNA 路径每语言 / 页面只加载一次。
- 构建资产诊断写入 `html-assets.jsonl`，CLI 输出静态调用及真实 trace 清单，避免诊断信息进入 HTML 正文。

真实 CLI 生成 `output/performance-fonts-cartesian-20261020/X101SC26098749-Z01-J001_report.html` 为 **24,983,249 bytes**；完整构建 110.2 秒。每语言 CJK 字体为 247,860 bytes，字符并集 2,695，引用字形删除数 0。与“仅字体”对照的字符集不同，是因为内嵌运行库文本不同；需要的实际报告字符仍通过保留检查。

`tests/verify_plotly_bundle.py` 在断网 Chromium 中验证 scatter / bar / heatmap / violin 初始化及每种 trace 的原生 PNG 下载；`output/cartesian-bundle-validation/verification.json` 通过。版本变化回退、3D 自定义 trace 回退和运行库只加载一次也有回归测试。

### 2.4 Phase 1A · Mermaid 构建期静态 SVG

实现：`bioreport/utils/mermaid_static.py`、`bioreport/modules.py` 与 `scripts/precompile_mermaid.py/.mjs`。四个中英文工作流 / 关于页图已用官方 Mermaid CLI 12.0.0 编译为随包 SVG，内容摘要与 manifest 严格匹配后内嵌。普通构建无需安装 Node；修改或新增的未缓存图保留原生 Mermaid 回退。PDF 保持原路径。

- SVG 保留真实文字和可访问名称，ID 及内部引用按模块隔离。
- 两语言流程图 / 关于页断网浏览器验证：`output/phase1a-svg-browser/theme-audit.json` 为 PASS，文字可实际选择，外网请求为零。
- 独立 Quarto smoke 验证保留图注与 `@fig-pipeline-clean` 交叉引用。
- 最终图表 sizing 回归发现手机端普通图表绘图区曾被边距挤至 2px，现按边距保留最小高度；长标签富集图使用有键盘焦点的内部横向滚动，PCA 单独监听可见容器尺寸并串行更新。真实 PCA 隐藏 / 显示、四视口和高分辨率 PNG 导出，以及五类 Cartesian 图的手机端绘图区 / PNG 下载检查通过。
- 当前完整报告候选：`output/performance-phase1a-responsive-20261020/X101SC26098749-Z01-J001_report.html`。该候选全部 8 张表格的搜索、排序、分页、导出及源数据逐值对照通过，证据：`output/phase1a-responsive-tables/tables-validation.json`。
- CSV 按钮随后补充 `footer: false`，消除 DataTables 默认空白导出页脚；独立真实浏览器验证 2 条数据严格导出为表头 + 2 行，并保留极小 p 值完整精度。

### 2.5 Phase 1A 完成时的阶段边界（历史，最新见 2.9）

Phase 1A 资源优化已实现，自动化完整四视口及可访问性检查仍在执行。最新 CSV 页脚设置已纳入 `output/theme-performance-final-20261020` 重新构建；全部 8 张表格再次通过源数据与导出检查，证据为 `output/theme-final-tables/tables-validation.json`。上述自动化结果供用户复测，不代表用户已验收。

Phase 1B 语言缓存 / 闲时解压、Phase 1C 紧凑延迟表格、Phase 2 网站包迁移及 Phase 3 文档迁移尚未完整实施。首屏、切换、表格可搜索时间及十次切换内存趋势尚待测量，不能用文件体积代替这些性能验收。

### 2.6 Phase 1A 资源与性能历史样本（当时尚未实施 Phase 1B / 1C）

最终源码重新构建的候选：`output/theme-performance-final-20261020/X101SC26098749-Z01-J001_report.html`。

| 指标 | 实测 |
|---|---:|
| 最终双语 HTML | 22,900,971 bytes |
| 中文解压 HTML | 21,873,304 bytes |
| 英文解压 HTML | 21,839,664 bytes |
| 中文 script 内容合计 | 14,249,651 bytes |
| 英文 script 内容合计 | 14,249,679 bytes |
| 静态 Mermaid | 每语言 2 个 SVG，运行库 0 |
| 首屏 loading 隐藏 | 5.78 s |
| 切到 Results 至搜索控件出现 | 0.36 s |
| 中文 → 英文 / 英文 → 中文 | 9.14 / 8.85 s |

证据：上述目录 `resource-metrics.json`、`performance-measurement.json`；复测命令为 `python scripts/measure_report_performance.py <report.html> --output <metrics.json>`。Chromium 151.0.7922.34，1440×900，完全阻断外网，浏览器异常为零。时间为共享主机负载下的一次冷导航样本，非稳定性保证；Results 只测控件可见，不等同于全表搜索时延。

结论边界：当前体积达到 Phase 1 的 25 MB 估计目标，但首屏本次样本仍高于 5 s，二次切换远高于 1 s。不能据此宣称 Phase 1 全部通过。后续应按 Phase 1B / 1C 实施并独立复测；不以资源瘦身取代缓存及懒加载工作。

全量源码测试：`python -m pytest -q` 为 **207 passed, 3 skipped**（36.95 s），日志 `/tmp/bioreport-phase1a-final-suite.log`。这只代表自动化自测，用户验收仍按本手册 checklist 执行。

四视口最终自动化结果：`output/phase1a-responsive-browser/theme-audit.json` 为 **PASS**，覆盖中英文 × 7 章节 × 4 视口（56 组合），页面溢出 0、浏览器异常 0、外网请求 0。此轮布局与图表检查针对 `performance-phase1a-responsive-20261020` 候选；随后最终报告仅补入 CSV 空白页脚修复，已另用 `output/theme-final-tables/tables-validation.json` 对最终报告全部表格完成集成复测。用户手工验收状态仍未填写。

### 2.7 Phase 1B · 解压缓存与保留页面

实现：`bioreport/i18n.py::combine_language_editions`。两语言解压字符串和解压中的 Promise 分别缓存，首屏完成后用闲时回调（退化 setTimeout）预解压另一语言。实际浏览器证明仅缓存字符串仍需重建图表 / 表格，因此最多保留两份 live iframe，缓存命中时交换可见页面；单文件与 file:// 交付不变。保留章节 hash、表格状态与主题，不创建第三份语言页面。临时 Uint8Array 随解压函数结束释放，无持久 Blob URL。

加载失败显示中英文错误与重试入口；缺失 DecompressionStream 的真实浏览器模拟及 gzip 损坏后恢复重试均已覆盖。缓存失败 Promise 会移除，避免永久复用拒绝结果。首次章节恢复触发布局后，等待两帧绘制再撤销加载提示。

十次真实鼠标切换的计时从子页面收到 DOM click 到外壳绘制后隐藏 loading，以 Performance API 记录；同时保留 Python / Playwright 调用往返耗时，避免将 iframe 可见性切换后约 3 秒的自动化返回等待误算为用户绘制时延。浏览器测量脚本 `scripts/verify_language_cache.py` 同时校验原 DOM 对象仍在、两个 iframe 上限、hash / 主题、解压次数及降级路径。

- Chromium 151.0.7922.34：十次最大切换 0.126 s；GC 后 JS heap 首末差 137,536 bytes，未持续增长；两语言只解压 2 次。
- Firefox 153.0：十次最大切换 0.025 s；解压、主题 / 章节保留与不支持解压时的提示均通过。Firefox 未使用不支持的 Chromium heap API。
- 两浏览器异常与外网请求均为零。结果：`output/performance-phase1b-20261020/chromium-cache.json`、`firefox-cache.json`。JS heap 不代表浏览器进程全部常驻内存，不能据此宣称 native 内存为零。

### 2.8 Phase 1C · 紧凑 JSON 与可见后初始化

实现：`bioreport/utils/html_table.py`、`visualize_utils.py`、`render_output.ensure_table_runtime`。数据采用单份列名 + array-of-arrays JSON；复用 ITables 已有的离线 DataTables bundle，原生 DataTable 开启 deferRender。仅在容器进入视野后解析 JSON 和初始化；隐藏标签页待激活并滚动进入后再初始化，旧浏览器无 IntersectionObserver 时立即初始化。加载 / 失败 / 重试文案双语化；占位骨架不使用动画。website 分支写相同 payload 到内容寻址的共享 JSON，后续 Phase 2 复用。

数字仅在 display render 中格式化；排序、过滤、复制及 CSV 返回原始值。手册 P1C 曾建议序列化前 round，但这与原主题任务“不改变底层数值和精度”冲突，故保留原始有限数值，不在 Python 阶段 round。字符串、列名与 script JSON 的 HTML 注入边界均有回归测试，同一数据重复展示使用不同 DOM ID。

同一番茄项目完整 DEG 紧凑 payload 为 3,309,450 bytes / 语言，23,075 条数据；前一候选已去除 Styler 后的 ITables DEG 模块脚本为 3,601,499 bytes，不能拿此阶段小幅变化声称再次减半。最初 20.94 MB 历史基线的主要冗余已在此前原始数值改造中移除。当前各表依次为 100 / 23,075 / 654 / 870 行，数据未截断；100 行表达预览沿用原配置。

最新全量源码测试为 209 passed, 3 skipped（35.51 s），随后缓存恢复与占位补充的相关 10 项测试通过。独立真实浏览器已验证极小 p 值完整 CSV 精度与键盘滚动，完整双语复制 / CSV / 搜索 / 分页 / 排序及最终新占位样式仍在复测，未提前宣称用户验收通过。

### 2.9 Phase 1 最终自动化自测汇总（不代替用户验收）

最新报告：`output/performance-phase1-complete-20261020/X101SC26098749-Z01-J001_report.html`，**22,819,339 bytes**。实际 CLI 构建 73.6 s；随后仅重新打包外壳，修复英文切换失败后重试的目标语言，两份内层渲染 HTML 未改。报告 manifest 已重新计算 SHA-256，`provenance-validation.json` 为 PASS（84 个记录）。性能样本采于这处 44-byte 重试分支修复之前，metrics 同时记录测量体积及当前体积。

| 验证项 | 自动化证据 |
|---|---|
| 首屏 / 首次与二次切换 / 首表可搜索 | 报告目录 `performance-measurement.json`；3.64 s / 3.12 s / 0.173 s / 0.93 s |
| 十次缓存切换、两个 iframe / 解压次数、主题与章节、旧浏览器提示 | 报告目录 `chromium-cache.json`、`firefox-cache.json` |
| 完整双语 8 表搜索 / 排序 / 分页 / 实际复制 / CSV / 源文件逐值对照 | `output/phase1-complete-tables/tables-validation.json` 为 PASS；DEG 23,075 条 |
| 新表格在首页不初始化、可见后加载 | 上述表格脚本的首页零 ready-table 断言及各表 visible_to_ready_s，最慢 1.96 s |
| Results / About × 双语 × 4 视口 | `output/phase1-complete-ui/theme-audit.json` 为 PASS（16 组合），axe 0、异常 0、外网 0 |
| 原完整章节主题覆盖 | `output/phase1a-responsive-browser/theme-audit.json` 为 PASS（56 组合）；其余未改页面保持前轮证据 |
| 原生 hover / 拖框缩放 / Autoscale / PNG，交互不改 trace 数据 | `output/cartesian-bundle-validation/verification.json`，scatter / bar / heatmap / violin / 长标签富集容器共 5 图通过 |
| PCA 隐藏与显示、四视口排列及高清 PNG | `output/pca-responsive/verification.json` |
| 字体 | 最新目录 `font-subset-metrics.json`，1979 codepoints，每语言 CJK 238,608 bytes，引用字形删除 0 |
| 全量源码测试与错误恢复补充 | 209 passed, 3 skipped（49.13 s）；最新外壳损坏 gzip、失败后中文 / 英文重试恢复的相关 6 项再次通过 |

Chromium 十次最长绘制切换 0.206 s；GC 后 JS heap 从 75,998,536 到 76,118,880 bytes（差 120,344）。Firefox 十次最长 0.016 s。两者无异常 / 外网请求。

切换基线是自动化调用口径。最新首次 / 二次调用往返分别 6.36 / 3.39 s；真实 DOM click 至完成绘制分别 3.12 / 0.173 s，两类数据保留，不能混为一谈。首屏 / 体积 / 二次切换 / 表格就绪均达到 Phase 1 估计目标的本机自测样本；未证明所有接收方硬件上的稳定时延。用户手测 checklist 仍留给用户填写。

后续继续 Phase 2 单项目共享资源网站包及 Phase 3 迁移文档。已按确认策略补充零依赖启动器的默认自动开浏览器与 `--no-browser` 开关；网站路径、共享字体、ZIP 打包、默认交付与 PDF 并存尚未实施完毕，不提前声称迁移完成。Git 工作区仍未提交，Phase 1A 的三个独立提交尚未交付；现有工作区包含任务开始前的修改，不能将其混入资源提交。
