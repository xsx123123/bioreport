# BioReport UI/UX Runtime Validation — v2

日期：2026-10-14

## 调查边界

本轮为只读调查，没有修改源代码、配置、模板、现有报告产物，也没有提交 Git。

现有 HTML 产物：

- `output/rna-html-review-navbar/report.html`
- 文件大小约 53 MB
- 生成时间：2026-10-14 16:42
- 配套截图：`output/rna-html-review-navbar/nav-desktop.png`、`nav-mobile.png`

该产物早于当前工作区部分未提交修改，因此只能作为已有产物证据，不能代表当前源码重新渲染后的最终状态。

## 1. 已获得运行验证的结论

- 生成 HTML 包含 6 个 `.report-page` 页面。
- 生成 HTML 包含 18 个 `.plotly-graph-div`。
- 生成 HTML 包含 8 个表格节点，其中 7 个仍显示 ITables 初始化占位文本。
- About 页面正文包含 13 个语义标题，层级为 H2/H3。
- About 页面 TOC 实际包含全部 13 个对应链接，不是只生成了一个链接。
- TOC 使用 Quarto 生成的嵌套 `<ul class="collapse">` 结构。
- 导航脚本包含页面切换、`aria-current` 更新、TOC 页面过滤、Plotly resize 和 Mermaid 延迟渲染逻辑。
- `node tests/report_navigation.cjs` 通过。

## 2. 高可信推断的确认与修正

### 已确认

- 页面切换依赖 hash 和 `.report-page[data-active="true"]`。
- 页面切换后脚本会调用已初始化 Plotly 图表的 `Plotly.Plots.resize()`。
- Mermaid 被延迟到目标页面显示后再渲染，以避免隐藏页面没有尺寸。
- `toc-depth: 3` 会排除 `index.qmd` 中的 H4“分析声明”。

### 被修正

“About 只有一个 TOC 链接”不成立。Pandoc/Quarto 已经生成了全部 About 标题和链接；问题发生在页面路由与 Bootstrap 折叠状态的交互层。

## 3. About TOC 的准确根因

Quarto 模板配置位于：

- `templates/_quarto.yml.j2:85-99`

其中启用了 `toc: true`、`toc-depth: 3` 和 `toc-location: right`。

最终 HTML 的 About TOC 结构是：

```html
<li>
  <a href="#关于本项目">关于本项目</a>
  <ul class="collapse">
    <li><a href="#项目介绍about-bioreport">项目介绍（About BioReport）</a></li>
    ...
  </ul>
</li>
```

`templates/theme/report-pages.html:192-215` 的 `selectPage()` 只对每个 TOC 链接所在的 `li` 设置 `hidden`，没有给对应祖先的 `.collapse` 添加 `show`，也没有调用 Bootstrap collapse API。

因此：

1. About 根链接属于当前页面，保持可见。
2. About 子链接所在的 `li` 可能解除 `hidden`。
3. 但它们的祖先 `<ul class="collapse">` 仍处于折叠状态。
4. Bootstrap 的折叠样式继续隐藏整个子目录。

这不是 QMD 标题解析失败，也不是 CSS 选择器遗漏标题，而是 TOC 子树展开状态没有随页面路由同步。

## 4. 视口尺寸验证

要求验证的视口为 1440、1280、768 和 390 px。

本轮未获得真实 `getComputedStyle()` 或 `getBoundingClientRect()` 数据。Playwright Chromium 在当前环境启动后因 Crashpad 权限限制退出：

```text
setsockopt: Operation not permitted (1)
TargetClosedError
```

因此以下项目均未宣称通过：

- Navbar 和 Logo 实际尺寸
- 导航项实际位置和间距
- 正文主容器与 TOC 实际宽度
- PCA、Heatmap、Volcano 实际宽度
- 图表父容器宽度
- 横向溢出
- KPI 卡片换行
- 表格工具栏溢出

已有截图：

- `output/rna-html-review-navbar/nav-desktop.png`：1440×900
- `output/rna-html-review-navbar/nav-mobile.png`：480×900

截图可用于静态视觉参考，但不能替代浏览器计算样式测量。

## 5. Plotly 与 ITables

### Plotly

生成 HTML 中的图表节点宽度为 `100%`，高度根据图表不同约为 320–1690 px。绘图配置包含 `responsive: true`。

相关代码：

- `omics/rna/analysis/pca_plotly.py:101-181`
- `omics/rna/analysis/plotly_heatmap.py:104-134`
- `templates/theme/report-pages.html:209-214`
- `templates/theme/styles.css:198-208`

未能在真实浏览器中验证：

- 隐藏页面切换后图表是否正确 resize
- 窗口缩小时是否发生裁切
- PCA 双子图在窄视口下的可读性
- 图例和坐标轴是否溢出
- 图形宽度是否与说明段落一致

### ITables

`omics/rna/analysis/plot_utils.py` 配置了 Copy、CSV、Excel 按钮以及分页相关选项。最终 HTML 中仍可见 ITables v2.7.3 初始化占位内容，说明表格依赖客户端脚本完成初始化。

未能在真实浏览器中验证：

- 搜索框、导出按钮和分页是否可用
- 表头字体和行高的最终计算值
- 首列和数值列对齐
- 隐藏页面表格列宽
- 页面切换后的列宽重算

静态样式位于 `templates/theme/itables_saas.css:28-128`。

## 6. Mermaid 与 About 语义

- About 标题在最终 HTML 中是语义 H2/H3，不是普通文本。
- Mermaid 路由脚本在目标页面可见后调用 `mermaidAPI.render()`。
- 本轮未能确认最终 Mermaid SVG、首次打开隐藏页面时的初始化结果。
- Logo 原始 PNG 为 1,392,401 字节；最终 HTML 中以约 1,856,558 字符的 `data:image/png;base64` URI 嵌入，约占 54,697,023 字节 HTML 的 3.39%。这里是文件体积占比，不是屏幕显示面积。

## 7. 浏览器证据路径与未完成项

可用静态证据：

- `output/rna-html-review-navbar/report.html`
- `output/rna-html-review-navbar/nav-desktop.png`
- `output/rna-html-review-navbar/nav-mobile.png`
- `tests/report_navigation.cjs`

未完成原因：当前环境的 Playwright Chromium 无法启动，退出原因为 Crashpad socket 权限错误。没有执行 Quarto 重渲染，因为那会写入报告产物，且本轮明确要求先获得批准。

## 8. 后续重构兼容性约束

后续重构必须保持：

1. 6 个报告页面的 hash 路由和直接 hash 访问。
2. 页面切换时导航链接的 `aria-current` 状态。
3. TOC 按页面过滤，并同步展开当前页面的祖先目录。
4. Quarto `toc-depth: 3` 的层级语义。
5. Plotly 图表显示后的 resize 逻辑。
6. Mermaid 在可见页面中的延迟渲染。
7. ITables 的 Copy、CSV、Excel 和分页配置。
8. 桌面端横向导航与移动端折叠菜单的现有入口。

本轮调查到此结束，未进入代码修改阶段。
