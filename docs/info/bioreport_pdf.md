# BioReport v2.0 字体渲染、PDF 排版优化与防篡改加密指南

本文档针对 `BioReport v2.0.0`（基于 `Python CLI + Jinja2 + Quarto + Typst / HTML` 架构）提供可直接落地的代码级改造方案，重点解决以下三个核心问题：
1. **全链路内置字体渲染**：统一使用 `bioreport/assets/fonts` 下的内置字体，彻底消除 PDF、HTML 和统计图表中的字体回退（Fallback）与锯齿感。
2. **PDF 行距与版式深度优化**：解决当前中文行距过窄、表格跨页断行、标题粘连、长路径/SHA256 溢出以及已知的 Markdown 渲染与绘图裁切问题。
3. **PDF 防编辑加密保护**：在报告生成管线末尾自动注入 AES-256 权限锁（支持客户直接免密打开阅读与打印，但彻底禁止编辑、删改页面或修改内容）。

---

## 一、 全链路内置字体优化方案（PDF + HTML + 统计图表）

假设你的 `bioreport/assets/fonts/` 目录下存放了以下三类字体文件（支持 `.ttf` 或 `.otf`，如果使用的是其他开源字体，只需将下方配置中的字体家族名称替换为你实际的字体名即可）：
* **中文主字体**：`HarmonyOS_Sans_SC_Regular.ttf`、`HarmonyOS_Sans_SC_Bold.ttf`（字体族名：`HarmonyOS Sans SC`）
* **西文与数字字体**：`Inter-Regular.ttf`、`Inter-SemiBold.ttf`、`Inter-Bold.ttf`（字体族名：`Inter`）
* **代码与哈希等宽字体**：`JetBrainsMono-Regular.ttf`（字体族名：`JetBrains Mono`）

---

### 1.1 PDF 端（Quarto + Typst）加载内置字体

从报告第 17 页的架构图可以看到，`BioReport` 在渲染时会创建**临时 Quarto 项目目录**。如果仅在 YAML 中写相对路径，临时目录切换时极易找不到字体。最稳妥的做法是**“环境变量注入 + Typst 字体回退链”**双管齐下：

#### 第一步：在 Python 编排器（CLI）中注入 `TYPST_FONT_PATHS`
在调用 `quarto render` 的 Python 代码中，将 `bioreport/assets/fonts` 的绝对路径写入环境变量，Typst 编译器会自动扫描该目录下的所有字体文件：

```python
import os
import subprocess
from pathlib import Path

def render_quarto_report(temp_qmd_dir: Path, bioreport_root: Path):
    font_dir = (bioreport_root / "assets" / "fonts").resolve()
    
    # 复制当前环境变量并注入 Typst 字体搜索路径
    env = os.environ.copy()
    env["TYPST_FONT_PATHS"] = str(font_dir)
    
    # 执行 Quarto 渲染
    cmd = ["quarto", "render", str(temp_qmd_dir)]
    subprocess.run(cmd, env=env, check=True)
```

#### 第二步：在 Typst 模板中配置“西文优先 + 中文无缝回退”
在你的 Typst 样式文件（如 `typst-template.typ` 或 `typst-show.typ`）中，使用数组形式指定字体栈。Typst 会优先使用 `Inter` 渲染所有的英文字母与数字，遇到汉字时自动无缝切换到 `HarmonyOS Sans SC`：

```typst
// 1. 正文与标题字体栈：西文用 Inter，中文用 HarmonyOS Sans SC
#set text(
  font: ("Inter", "HarmonyOS Sans SC", "Source Han Sans SC", "Noto Sans CJK SC"),
  size: 10pt,
  fill: rgb("#1F2937"),
  lang: "zh",
  region: "cn"
)

// 2. 等宽字体栈：用于路径、软件版本、SHA256 哈希值
#show raw: set text(
  font: ("JetBrains Mono", "HarmonyOS Sans SC"),
  size: 8.5pt
)
```

---

### 1.2 HTML 端（单文件 / 多页 HTML）加载内置字体

为了让 HTML 报告在客户没有安装这些字体的电脑上也能完美显示，需要在共享 CSS 主题（如 `bioreport/assets/styles/custom.css`）中通过 `@font-face` 声明本地字体，并在 Quarto 配置中开启 `embed-resources: true`（Quarto 会自动把字体转为 Base64 内嵌进单文件 HTML 中）。

#### 第一步：编写 `bioreport/assets/styles/fonts.css`
*(注：强烈建议放一份 `.woff2` 格式在 `assets/fonts` 下用于 HTML，体积比 `.ttf` 小 70%，加载极快；直接用 `.ttf` 也可以)*

```css
/* 西文字体 Inter */
@font-face {
  font-family: 'BioReport-Inter';
  src: url('../fonts/Inter-Regular.ttf') format('truetype');
  font-weight: 400;
  font-style: normal;
  font-display: swap;
}
@font-face {
  font-family: 'BioReport-Inter';
  src: url('../fonts/Inter-Bold.ttf') format('truetype');
  font-weight: 700;
  font-style: normal;
  font-display: swap;
}

/* 中文字体 HarmonyOS Sans SC */
@font-face {
  font-family: 'BioReport-CN';
  src: url('../fonts/HarmonyOS_Sans_SC_Regular.ttf') format('truetype');
  font-weight: 400;
  font-style: normal;
  font-display: swap;
}
@font-face {
  font-family: 'BioReport-CN';
  src: url('../fonts/HarmonyOS_Sans_SC_Bold.ttf') format('truetype');
  font-weight: 700;
  font-style: normal;
  font-display: swap;
}

/* 等宽字体 JetBrains Mono */
@font-face {
  font-family: 'BioReport-Mono';
  src: url('../fonts/JetBrainsMono-Regular.ttf') format('truetype');
  font-weight: 400;
  font-style: normal;
  font-display: swap;
}

/* 全局应用与行距优化 */
:root {
  --bs-body-font-family: 'BioReport-Inter', 'BioReport-CN', -apple-system, BlinkMacSystemFont, sans-serif;
  --bs-font-monospace: 'BioReport-Mono', monospace;
}

body {
  font-family: var(--bs-body-font-family);
  line-height: 1.75;           /* 解决 HTML 行距拥挤 */
  color: #1F2937;
  font-variant-numeric: tabular-nums; /* 数字等宽对齐 */
}

code, pre, .file-path, .sha256-hash {
  font-family: var(--bs-font-monospace);
  font-size: 0.875em;
  word-break: break-all;       /* 防止长路径撑破表格 */
}

/* 表格数字列右对齐优化 */
table.dataframe td:not(:first-child),
.gt_table td.gt_right {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
```

#### 第二步：在 Quarto `_quarto.yml` 中启用内嵌
```yaml
format:
  html:
    css:
      - assets/styles/fonts.css
    embed-resources: true   # 关键：将字体文件自动打包进单文件 HTML，离线可用
```

---

### 1.3 Python 统计图表与架构图（Matplotlib / Seaborn / Plotly）字体同步

报告中的图 1~图 14 目前使用的是 Matplotlib 默认的 `DejaVu Sans`，与正文风格割裂。只需在你的绘图公共模块初始化时运行以下函数，即可把 `bioreport/assets/fonts` 中的字体动态注册进 Matplotlib：

```python
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib import font_manager

def init_bioreport_plot_style(bioreport_root: Path):
    """注册内置字体并初始化高颜值生信绘图全局样式"""
    font_dir = bioreport_root / "assets" / "fonts"
    
    # 1. 动态扫描并注册 assets/fonts 下的所有 .ttf / .otf 字体
    for font_file in font_dir.glob("*.[to]tf"):
        font_manager.fontManager.addfont(str(font_file))
    
    # 2. 全局样式与字体栈配置
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Inter", "HarmonyOS Sans SC", "Source Han Sans SC", "DejaVu Sans"],
        "axes.unicode_minus": False,       # 解决负号 '-' 显示为方块的问题（如图10、图11）
        
        # 字号层级标准化
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.labelsize": 10,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 9,
        "legend.frameon": False,           # 去掉图例丑陋的边框
        
        # 边框与网格美化
        "axes.spines.top": False,          # 隐藏顶部边框
        "axes.spines.right": False,        # 隐藏右侧边框
        "axes.edgecolor": "#D1D5DB",
        "axes.linewidth": 0.8,
        "grid.color": "#F3F4F6",
        "grid.linestyle": "--",
        "grid.alpha": 0.8,
        
        # 导出质量设置（强烈建议 PDF 报告使用 svg 矢量格式！）
        "savefig.dpi": 300,
        "savefig.bbox": "tight",           # 关键！彻底解决图 4、5、9 边缘文字被裁切的问题
        "savefig.pad_inches": 0.12,        # 留出 0.12 英寸安全边距
        "svg.fonttype": "none",            # 导出 SVG 时保留文本对象，由 Typst 统一渲染字体
    })
```

---

## 二、 PDF 排版深度优化与行距调整（Typst 模板与 Bug 修复）

### 2.1 为什么现在的 PDF 看起来“行距很窄、很挤”？
Typst 引擎默认针对西文排版设计，其默认行距（`leading`）仅为 `0.65em`，段落间距（`spacing`）也偏小。对于方块字结构的中文而言，`0.65em` 会导致上下两行汉字几乎贴在一起（如报告第 4 页的方法描述和第 18 页的参考文献）；同时，表格默认的单元格内边距（`inset: 5pt`）太小，导致数据表看起来密密麻麻。

### 2.2 生产级 Typst 样式模板（直接替换或合入你的模板）

将以下配置加入你的 `bioreport` Typst 模板文件（如 `template.typ`），即可一次性解决**行距过窄、标题粘连、表格粗糙、跨页孤行、图注混乱**等所有排版问题：

```typst
// ============================================================================
// BioReport v2.0 生产级 Typst 视觉与排版规范
// ============================================================================

#let brand-primary = rgb("#1E3A8A")   // 深海科技蓝（主色）
#let brand-accent  = rgb("#2563EB")   // 亮蓝（强调色）
#let text-main     = rgb("#1F2937")   // 正文深炭灰（比纯黑更护眼高级）
#let text-muted    = rgb("#6B7280")   // 图注与次要信息灰
#let bg-subtle     = rgb("#F8FAFC")   // 浅灰底色（用于表格斑马纹与信息框）
#let border-light  = rgb("#E2E8F0")   // 柔和边框色

// 1. 页面与页眉页脚设置
#set page(
  paper: "a4",
  margin: (top: 2.6cm, bottom: 2.4cm, left: 2.2cm, right: 2.2cm),
  header: context {
    if counter(page).get().first() > 1 [
      #set text(size: 8.5pt, fill: text-muted)
      #grid(
        columns: (1fr, 1fr),
        align(left)[*PRJ-RNA-PDF-001* | RNA-seq 转录组分析报告],
        align(right)[CygnusX BioOps · BioReport]
      )
      #v(-4pt)
      #line(length: 100%, stroke: 0.5pt + border-light)
    ]
  },
  footer: context {
    if counter(page).get().first() > 1 [
      #line(length: 100%, stroke: 0.5pt + border-light)
      #v(4pt)
      #set text(size: 8.5pt, fill: text-muted)
      #grid(
        columns: (1fr, auto, 1fr),
        align(left)[Confidential · 仅供科研参考],
        align(center)[第 #counter(page).display() 页 / 共 #counter(page).final().first() 页],
        align(right)[Powered by BioReport v2.0.0]
      )
    ]
  }
)

// 2. 解决行距过窄问题：大幅提升中文阅读呼吸感！
#set par(
  leading: 0.95em,          // 行距从默认的 0.65em 提升至 0.95em（相当于约 1.65 倍行高）
  spacing: 1.5em,           // 段落间距设为 1.5em，层次分明
  justify: true,            // 两端对齐
  linebreaks: "optimized"   // 开启 Typst 最优断行算法
)

// 3. 解决标题数字与文字粘连问题（如 "1项目概况" -> "1  项目概况"）
#set heading(numbering: "1.1")
#show heading: it => block(
  above: if it.level == 1 { 2.0em } else { 1.5em },
  below: 1.0em,
  breakable: false,         // 严禁标题出现在页面最底部而与下文分离
)[
  #if it.level == 1 {
    set text(size: 16pt, weight: "bold", fill: brand-primary)
    // 一级标题左侧增加一根竖向品牌色装饰条，拉大编号与标题间距
    box(fill: brand-accent, width: 4pt, height: 14pt, radius: 1.5pt, baseline: 15%)
    h(8pt)
    if it.numbering != none {
      counter(heading).display(it.numbering)
      h(0.6em)              // 关键：章节号与中文之间留出 0.6em 间距
    }
    it.body
    v(4pt)
    line(length: 100%, stroke: 1pt + border-light)
  } else if it.level == 2 {
    set text(size: 12.5pt, weight: "bold", fill: brand-primary)
    if it.numbering != none {
      counter(heading).display(it.numbering)
      h(0.5em)
    }
    it.body
  } else {
    set text(size: 11pt, weight: "bold", fill: text-main)
    if it.numbering != none {
      counter(heading).display(it.numbering)
      h(0.5em)
    }
    it.body
  }
]

// 4. 现代三线表美化：加大行高、斑马纹、防跨页断行
#set table(
  stroke: (x, y) => (
    top: if y == 0 { 1.2pt + brand-primary } else if y == 1 { 0.8pt + brand-primary } else { 0pt },
    bottom: 1.2pt + brand-primary,
    left: 0pt,
    right: 0pt,
  ),
  fill: (x, y) => if y == 0 {
    rgb("#EFF6FF")          // 表头淡蓝底色
  } else if calc.odd(y) {
    white
  } else {
    bg-subtle               // 偶数行极淡斑马纹
  },
  inset: (x: 8pt, y: 7pt),  // 加大单元格上下内边距，彻底告别表格拥挤
)

// 表头加粗，表格内数字使用等宽对齐字体
#show table.cell.where(y: 0): set text(weight: "bold", fill: brand-primary, size: 9.5pt)
#show table.cell: set text(size: 9pt, number-type: "tabular")

// 5. 图注（Figure Caption）降噪与精致化（解决图注与正文混作一团的问题）
#show figure: set block(above: 1.4em, below: 1.4em, breakable: false)
#show figure.caption: it => block(
  width: 92%,
  inset: (top: 6pt, bottom: 4pt),
)[
  #set par(leading: 0.75em, justify: true)
  #set text(size: 8.5pt, fill: text-muted)
  #strong(text(fill: brand-primary)[#it.supplement #it.counter.display()#it.separator])
  #h(4pt)
  #it.body
]

// 6. 自定义组件：底部数据来源与路径信息微缩框（替代原来重复的大段正文说明）
#let meta-note(summary, path: none) = block(
  width: 100%,
  fill: bg-subtle,
  stroke: (left: 2.5pt + rgb("#94A3B8")),
  inset: (x: 10pt, y: 6pt),
  radius: (right: 3pt),
  above: 0.6em,
  below: 1.4em,
  breakable: false
)[
  #set text(size: 8pt, fill: text-muted)
  #set par(leading: 0.7em)
  #summary
  #if path != none [
    #linebreak()
    *完整结果路径：*#raw(path)
  ]
]
```

---

### 2.3 报告中发现的 5 处具体排版问题修复方法

#### 修复 1：第 4 页 `##结果分析方法` 和 `##实际提供的软件版本` 未解析成标题
* **原因**：在生成第 4 页的 Markdown 模板中，`##结果分析方法` 直接跟在了句号 `。` 后面，没有换行，且 `##` 后缺少空格。
* **修改方法**：在对应的 `.qmd` 或 Jinja2 模板中，确保所有 Markdown 标题前后都有**独立空行**，且 `#` 后必须带有一个空格：
  ```markdown
  ...STAR 比对分类统计 [5]。

  ## 2.2 结果分析方法

  仅说明当前启用的结果模块；过滤与绘图参数见对应图注...

  ## 2.3 实际提供的软件版本
  ```

#### 修复 2：第 16、17、18 页长路径与 SHA256 哈希值溢出截断
* **现象**：第 16 页的 SHA256（64位连续十六进制字符）右侧被加上连字符截断（`...aa8739b90-`），第 17 页的路径因为过长且无空格，在 `/` 处无法自动优雅换行。
* **修改方法**：在 Python 渲染数据进入模板前，写一个简单的过滤器，为路径的 `/`、`_` 后插入**零宽空格（`\u200b`）**，让 Typst 可以在任意斜杠处优雅换行，不留大白块：
  ```python
  def format_breakable_str(s: str, mode: str = "path") -> str:
      """为长路径或 SHA256 插入零宽空格，实现 PDF 表格内完美自动折行"""
      if mode == "path":
          # 建议先转为相对路径，并在 '/' 和 '_' 后允许断行
          return s.replace("/", "/\u200b").replace("_", "_\u200b")
      elif mode == "sha256":
          # 每 8 个字符插入一个零宽空格，确保 64 位哈希完整显示绝不截断
          return "\u200b".join(s[i:i+8] for i in range(0, len(s), 8))
      return s
  ```

#### 修复 3：第 14-15 页、17-18 页表格“孤行跨页”（只剩 2 行掉到下一页）
* **原因**：第 13、14 页把 12 个富集条目拆成了两张图（`条目 1-8` 和 `条目 9-12`），两张图占满了 75% 的页面高度，导致下方的 10 行表格放不下，最后 2 行被挤到了第 15 页。
* **修改方法**：
  1. **不要把 Top 12 拆成两张图！** 12 个 GO Term 完全可以画在一张气泡图里（设 `figsize=(7.5, 4.5)`），不仅视觉上大小一致（消除图 12、图 14 只有 4 个点却拉得老高的空旷感），而且一张图 + 一张 10 行预览表刚好完美装进一页 A4 纸！
  2. 对于 10 行以内的短预览表，在 Quarto/Typst 中用 `#block(breakable: false)[ ... ]` 包裹，强制整个小表格同页显示。

#### 修复 4：第 6~8 页 R1 / R2 质控图改为“左右双栏并排”
* 第 6 页的 `R1 / R2 Sequence Quality`（图 2、图 3）和第 7-8 页的 `R1 / R2 FastQ Screen`（图 4、图 5）结构完全对称，上下堆叠既占页数又不方便对比。
* 在 Quarto `.qmd` 中直接使用 `layout-ncol: 2` 即可实现左右并排：
  ```markdown
  ::: {layout-ncol=2}
  ![Fastp: R1 过滤后碱基质量](path/to/r1_quality.svg){#fig-r1-qual}

  ![Fastp: R2 过滤后碱基质量](path/to/r2_quality.svg){#fig-r2-qual}
  :::
  ```

#### 修复 5：第 11 页热图（图 9）顶部标题裁切与图例重叠、第 3 页数学公式统一
* **图 9 热图修复**：绘制热图时，顶部的分组注释条（Group `1` 和 `2`）的 Legend 压在了红蓝色块上，且标题 `Group` 被切了一半。在 Seaborn / Matplotlib 中将图例移至右上角外侧：
  ```python
  # 将分组图例放置在热图正上方偏右，留出呼吸空间
  ax.legend(title="Group", bbox_to_anchor=(0.5, 1.08), loc="lower center", ncol=2, frameon=False)
  plt.savefig("heatmap.svg", bbox_inches="tight", pad_inches=0.15)
  ```
* **第 3 页统计口径公式统一**：将第 3 页的 `原始 P<0.05; 上调 Log2FC > 1.0, 下调 Log2FC<-1.0` 统一改写为标准 LaTeX 数学公式：
  `统计口径：原始 $P < 0.05$；上调 $\log_2\text{FC} > 1.0$，下调 $\log_2\text{FC} < -1.0$`。

---

## 三、 PDF 防篡改与禁止编辑加密方案（Python 后处理）

### 3.1 PDF 权限控制原理说明
在 PDF 标准（ISO 32000-2 / PDF 2.0）中，密码分为两种：
1. **用户密码（User Password / 打开密码）**：设为空字符串 `""` 时，**客户双击 PDF 即可直接打开阅读，无需输入任何密码**，使用体验完全不受影响。
2. **所有者密码（Owner Password / 权限密码）**：由你的 `BioReport` 系统掌握。配合权限位（Permissions）使用 **AES-256（R=6）** 加密后，Adobe Acrobat、WPS、Foxit、Edge 等主流阅读器会直接**置灰禁用“编辑文本”、“修改页面”、“插入批注”、“篡改内容”等所有编辑功能**。如果要强行解除编辑限制，必须输入正确的 Owner Password。

---

### 3.2 方案一：使用 `pikepdf` 进行工业级 AES-256 权限锁死（强烈推荐）

`pikepdf` 底层基于 C++ 的 `QPDF` 引擎，是 Python 生态中处理 PDF 加密最稳定、速度最快、兼容性最好的库。

#### 安装依赖：
```bash
pip install pikepdf
```

#### 核心加密代码（直接集成到 `BioReport` 渲染完成后的收尾步骤）：

```python
import pikepdf
from pathlib import Path

def lock_pdf_permissions(
    pdf_path: str | Path,
    owner_password: str,
    allow_copy_text: bool = False,
    allow_print: bool = True,
    user_password: str = ""
) -> None:
    """
    为 BioReport 生成的 PDF 报告添加 AES-256 防编辑加密锁。
    
    参数:
        pdf_path: 生成的 PDF 文件路径（原地加密覆盖）
        owner_password: 管理员密码（必填，用于锁定编辑权限，切勿泄露给普通用户）
        allow_copy_text: 是否允许客户用鼠标选中并复制报告中的文字（默认 False 严防抄袭篡改，若需方便客户复制基因名可设为 True）
        allow_print: 是否允许客户高清打印该 PDF（默认 True）
        user_password: 打开密码（默认为空字符串 ""，即客户双击直接免密打开阅读）
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"未找到待加密的 PDF 文件: {pdf_path}")

    # 1. 定义严格的只读权限矩阵
    permissions = pikepdf.Permissions(
        modify_other=False,        # 禁止编辑文档内容（文字、图表）
        modify_assembly=False,     # 禁止插入、删除、旋转或拆分页面
        modify_annotation=False,   # 禁止添加批注、签名或高亮修改
        modify_form=False,         # 禁止修改表单字段
        extract=allow_copy_text,   # 控制是否允许复制/提取文本与图片
        accessibility=True,        # 允许屏幕阅读器辅助访问（符合无障碍规范）
        print_lowres=allow_print,  # 允许打印
        print_highres=allow_print  # 允许高清打印
    )

    # 2. 使用 PDF 2.0 最高安全等级 R=6 (AES-256) 进行加密保存
    with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
        # 可选：写入自定义防伪元数据
        with pdf.open_metadata() as meta:
            meta["dc:creator"] = ["CygnusX BioOps - BioReport v2.0.0"]
            meta["pdf:Producer"] = "BioReport Secure PDF Engine (Protected)"
        
        pdf.save(
            pdf_path,
            encryption=pikepdf.Encryption(
                user=user_password,      # "" 代表免密直接打开
                owner=owner_password,    # 锁定编辑权限的私钥密码
                allow=permissions,
                R=6                      # R=6 对应 256-bit AES 加密
            )
        )
```

---

### 3.3 方案二：使用纯 Python 库 `pypdf`（无需 C++ 依赖的轻量备选）

如果你的运行环境不方便安装带 C++ 扩展的 `pikepdf`，也可以使用纯 Python 实现的 `pypdf`（需安装 `pip install pypdf cryptography`）：

```python
from pypdf import PdfReader, PdfWriter
from pypdf.constants import UserAccessPermissions
from pathlib import Path

def lock_pdf_with_pypdf(pdf_path: str | Path, owner_password: str) -> None:
    """使用纯 Python pypdf 锁定 PDF，仅允许阅读与打印，禁止任何编辑"""
    pdf_path = Path(pdf_path)
    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    for page in reader.pages:
        writer.add_page(page)

    # 仅开启打印权限（PRINT + PRINT_TO_REPRESENTATION），其余编辑权限全部关闭
    read_only_permissions = (
        UserAccessPermissions.PRINT | 
        UserAccessPermissions.PRINT_TO_REPRESENTATION
    )

    writer.encrypt(
        user_password="",                # 免密打开
        owner_password=owner_password,   # 锁定编辑权限
        permissions_flag=read_only_permissions,
        algorithm="AES-256"              # 256位高强度加密
    )

    with open(pdf_path, "wb") as f:
        writer.write(f)
```

---

### 3.4 进阶建议：在配置文件中集成加密开关

你可以在 `report.rna.pdf.json`（或 YAML 配置）中增加一个 `security` 字段，让 `BioReport` 引擎自动完成加密并在第 16 页《溯源信息》中记录保护状态：

```json
{
  "project_id": "PRJ-RNA-PDF-001",
  "output": {
    "format": "pdf",
    "layout": "single",
    "security": {
      "enable_read_only_lock": true,
      "allow_copy_text": true,
      "allow_print": true,
      "owner_password_env": "BIOREPORT_OWNER_SECRET"
    }
  }
}
```

* **关于 `allow_copy_text` 的实用建议**：由于生信报告的第 11、12、13 页包含大量基因 ID（如 `ENSMUSG00000000184`）和 GO Term，科研客户在阅读报告时经常需要复制基因 ID 去 NCBI 或 Ensembl 查询。因此建议将 `modify_*`（所有编辑、修改、删页权限）全部设为 `False`，但将 `extract`（复制文字）设为 `True`——这样既能保证**PDF 无法被编辑篡改**，又不会影响课题组老师复制基因名！