# BioReport Quarto 官方文档辅助指南

## 页面布局、HTML 主题、资源打包、案例参考与可访问性

-   **项目：** BioReport RNA-seq HTML 报告
-   **用途：** 为 BioReport 的 Quarto HTML 报告 UI/UX
    升级提供官方技术依据
-   **文档性质：** 辅助参考文档，不是对现有仓库实施完成情况的断言
-   **整理日期：** 2026-10-19
-   **适用原则：**
    先调查当前实现，再把官方能力映射到现有报告；不得直接用示例覆盖现有配置

------------------------------------------------------------------------

## 1. 文档目的与使用方式

本文将五份 Quarto 官方资料整理成面向 BioReport 工程实施的参考指南：

1.  [Page Layout ---
    页面布局](https://quarto.org/docs/output-formats/page-layout.html)
2.  [HTML Theming --- HTML
    主题](https://quarto.org/docs/output-formats/html-themes.html)
3.  [HTML Basics --- HTML
    基础功能](https://quarto.org/docs/output-formats/html-basics.html)
4.  [Quarto Gallery --- 官方示例集](https://quarto.org/docs/gallery/)
5.  [HTML Accessibility Checks --- HTML
    可访问性检查](https://quarto.org/docs/output-formats/html-accessibility.html)

这五份资料解决的是不同层级的问题：

  -------------------------------------------------------------------------------------------------------------------------
  资料                    主要解决的问题                                 在 BioReport 中的用途
  ----------------------- ---------------------------------------------- --------------------------------------------------
  Page Layout             页面采用什么布局、正文/边栏/目录如何分配宽度   优先解决正文过窄、图表空间不足、导航挤占内容区域

  HTML Theming            如何选择 Bootstrap/Bootswatch 主题，如何使用   建立统一的颜色、字体、标题和基础组件规范
                          SCSS 定制主题                                  

  HTML Basics             如何设置目录、附加 CSS、标签页、锚点及自包含   保留现有导航能力，并确保报告按现有方式交付
                          HTML                                           

  Quarto Gallery          官方报告、复杂布局和 Dashboard 的实例          作为布局和组件的设计参考，而不是直接复制整个案例

  HTML Accessibility      如何使用 axe-core 检查 HTML 可访问性问题       验证颜色对比度、语义结构及部分交互可访问性问题
  Checks                                                                 
  -------------------------------------------------------------------------------------------------------------------------

**推荐阅读与实施顺序：** Page Layout → HTML Theming → HTML Basics →
Gallery →
Accessibility。实际工程顺序仍然应先调查仓库现状，再决定哪些配置值得采用。

## 2. Page Layout：页面布局与宽度控制

官方链接：<https://quarto.org/docs/output-formats/page-layout.html>

### 2.1 Quarto 的默认布局为什么可能不适合 BioReport

Quarto 的 HTML
文档默认采用偏向文章阅读的布局。官方文档说明，默认正文区域通常约为
600--900px，适合传统文章，但对宽图表、数据矩阵、分析结果仪表区等内容可能不够宽。

BioReport 的实际页面包含：

-   顶部品牌导航；
-   左侧章节导航；
-   项目与质量控制统计卡片；
-   PCA、表达量分布等图表；
-   样本 × 基因的宽表达矩阵；
-   可能包含大量字段的分析结果表格。

这类报告不应把所有内容都限制在传统文章的窄阅读宽度内。但也不应该让每一段正文无限拉宽。因此，正确方案是建立**分层宽度**：正文保持可读，图表与数据表格按需使用更宽区域。

### 2.2 三种页面布局选项

Quarto 提供三种高层布局选项。

#### `page-layout: article`

适合具有正文阅读区域、边栏和页边内容的文章式布局。若报告的左侧目录和正文关系已经合理，只是正文略窄，可以先保留文章式布局，再调整网格宽度。

#### `page-layout: full`

使用文章布局的网格系统，但在侧栏或页边区域没有内容占用时，会自动扩展内容区域。这适合需要更多水平空间的内容，例如数据分析结果页、索引页和图表密集型页面。

对 BioReport
来说，它是值得测试的候选方案，但**不是无需验证即可直接启用的最终结论**。如果现有导航、目录或自定义侧栏占用了网格区域，启用后实际宽度与导航表现需要重新检查。

#### `page-layout: custom`

提供不带默认网格、内边距或外边距的简单 HTML
内容容器。它更适合需要完全自定义布局的页面。

本次不建议默认选择 `custom`。除非现有布局确实无法通过 `article` / `full`
和网格参数实现，否则优先利用 Quarto
的原生响应式布局，减少自建布局的维护成本。

### 2.3 页面网格的四个宽度参数

官方文档给出的默认基础值如下：

  参数                 默认值 作用
  ----------------- --------- ------------------------
  `sidebar-width`     `250px` 左侧侧栏区域的基础宽度
  `body-width`        `800px` 正文区域的基础宽度
  `margin-width`      `250px` 右侧页边区域的基础宽度
  `gutter-width`      `1.5em` 各布局区域之间的间距

重要说明：

-   这些值是布局计算使用的基础/最大值，不等同于每个视口下最终显示的固定像素宽度。
-   Quarto 会根据布局类型、屏幕尺寸及是否有边栏或页边内容调整区域尺寸。
-   `sidebar-width`、`body-width`、`margin-width` 应以像素值设置。
-   `gutter-width` 可以使用像素、`em` 或 `rem` 等单位。
-   页面整体可用宽度还受浏览器视口、目录、导航及其他布局内容影响。

### 2.4 BioReport 的初始宽度建议

建议将以下值作为**初始测试目标**，通过截图和实际渲染进行调整：

  内容类型     初始目标
  ------------ ----------------------------------
  普通正文     约 1100--1200px 的最大阅读区域
  统计卡片     与正文主区域协调，桌面端优先三列
  PCA 等图表   可使用比普通正文更宽的区域
  宽表达矩阵   在可用容器内横向滚动，不静默裁切
  移动端       按视口收缩，避免页面整体横向溢出

这些数值是设计目标，不是 Quarto 官方强制推荐值，也不能直接视为最终配置。

### 2.5 官方支持的 YAML 网格配置

可以在现有配置上合并类似设置：

``` yaml
format:
  html:
    page-layout: full
    grid:
      body-width: 1150px
      margin-width: 220px
      gutter-width: 1.5rem
```

注意事项：

1.  先确认现有 `page-layout`、目录和侧栏配置，再决定是否启用 `full`。
2.  如果现有导航需要占用左侧区域，应测试导航是否被压缩、覆盖或移动。
3.  不要仅为了增宽图表而把所有正文设置成 100% 宽度。
4.  对于宽表格，通常还需要表格容器自身的横向滚动和列宽策略，不能只依赖页面变宽。
5.  如果 `body-width` 修改后仍然不生效，应检查主题的 `max-width`、项目级
    YAML、文档级 YAML 和现有 CSS 是否共同限制了宽度。

### 2.6 网格参数与 `max-width` 的区别

两者不能简单视为同一个设置：

-   `grid.body-width` 控制 Quarto 页面网格中正文区域的基础宽度。
-   `max-width` 是 HTML
    主题选项之一，限制页面内容可占用的最大宽度。官方文档指出，Bootstrap
    主题默认值为 1400px，Pandoc 主题默认值为 `36em`。
-   自定义 CSS
    还可能对某个正文容器、图表容器或表格容器设置额外宽度限制。

当正文仍然偏窄时，应同时检查这三层，而不是反复盲目提高一个参数。

### 2.7 BioReport 的实际实施建议

按以下顺序排查：

1.  找到生成当前 HTML 的 QMD/模板入口。
2.  找到项目级 `_quarto.yml` 和文档级 YAML。
3.  确认是否使用 `page-layout`、`grid`、`max-width`。
4.  确认左侧导航是 Quarto TOC、网站 sidebar，还是项目自定义组件。
5.  记录当前页面在 1440px 和 1920px 视口下的正文宽度。
6.  一次只调整一组布局参数，重新渲染并对比截图。
7.  在宽度确定后再调整图表和表格的内部布局。

------------------------------------------------------------------------

## 3. HTML Theming：Bootstrap、Bootswatch 与 SCSS

官方链接：<https://quarto.org/docs/output-formats/html-themes.html>

### 3.1 Quarto 的主题基础

Quarto HTML 默认使用 Bootstrap 5 主题体系。官方还提供多种 Bootswatch
主题，包括
`cosmo`、`flatly`、`litera`、`lumen`、`minty`、`pulse`、`sandstone`、`spacelab`、`yeti`、`zephyr`
等。

主题选项示例：

``` yaml
format:
  html:
    theme: cosmo
```

可选的基础方式包括：

-   `default`：Bootstrap 默认主题；
-   `cosmo` 等 Bootswatch 主题：预设的配色和组件风格；
-   `pandoc`：Pandoc 默认 HTML 样式；
-   `none`：不附加 Quarto 标准主题 CSS。

对 BioReport 来说，除非有明确的技术原因，不建议直接切换到
`none`。这可能导致当前导航、目录、表单和其他 Bootstrap
相关组件失去基础样式。

### 3.2 如何选择基础主题

建议将主题分为两层：

1.  **基础主题：** 提供 Bootstrap 组件的基本视觉风格。
2.  **BioReport 自定义主题：**
    统一品牌颜色、字体、标题、间距和必要的组件样式。

可优先比较 `cosmo`、`flatly`、`litera`
等明亮、克制的主题，但不要仅凭主题名称决定。应使用同一份代表性报告实际渲染，比较导航、表格、图表、统计卡片和提示框的表现。

本次升级不要求一定更换当前基础主题。如果当前主题已经与 BioReport
品牌协调，可以保留原主题，仅叠加自定义 SCSS/CSS。

### 3.3 主题选项与 CSS 的职责区别

Quarto 官方建议：

-   简单样式调整可以通过 `css` 引入 CSS 文件；
-   更深入的主题定制可以通过 SCSS 主题文件完成。

建议采用以下职责划分：

  -----------------------------------------------------------------------------------------------
  层级                    主要职责                           BioReport 示例
  ----------------------- ---------------------------------- ------------------------------------
  Quarto YAML             选择主题、设置布局、引用样式文件   `theme`、`css`、`page-layout`

  SCSS 主题               修改 Bootstrap/Bootswatch 的变量   主色、字体、标题字重、主题基础颜色

  CSS 组件样式            定义具体页面与组件外观             表格间距、图表容器、卡片、提示框

  组件原生配置            处理交互与行为                     表格排序/分页、Plotly 响应式布局
  -----------------------------------------------------------------------------------------------

不要用大量 CSS 覆盖来代替所有主题变量调整，也不要试图用 SCSS
变量完成所有组件级布局。

### 3.4 通过 SCSS 扩展基础主题

官方支持在主题列表中同时使用基础主题和自定义 SCSS 文件：

``` yaml
format:
  html:
    theme:
      - cosmo
      - styles/report-theme.scss
```

这里的 `cosmo`
只是示例。实际项目应保留现有基础主题，并在确认兼容后添加自定义文件。

SCSS 文件可使用 Quarto 约定的区域标记：

``` scss
/*-- scss:defaults --*/

// 放置 Bootstrap / 主题变量覆盖。
// 例如字体、标题字重和基础颜色变量。

/*-- scss:rules --*/

// 放置主题层面的自定义规则。
// 具体报告组件样式也可以保存在独立 CSS 文件中。
```

`scss:defaults` 用于变量等默认值；`scss:rules` 用于 CSS 规则。Quarto
会按主题处理规则对文件进行编译和合并。

### 3.5 建议的 BioReport 设计变量

可以在项目中建立统一的品牌变量，例如：

  变量                   建议值      用途
  ---------------------- ----------- ----------------------------
  `--br-primary`         `#2563EB`   主要强调色、链接和激活状态
  `--br-primary-dark`    `#203A5F`   标题和重要文字
  `--br-text`            `#334155`   正文
  `--br-muted`           `#64748B`   辅助文字
  `--br-border`          `#E2E8F0`   边框和分隔线
  `--br-surface`         `#FFFFFF`   主背景
  `--br-surface-soft`    `#F8FAFC`   辅助背景和表格交替行
  `--br-surface-hover`   `#EFF6FF`   轻量悬停状态

这些是 BioReport 的设计建议，不是 Quarto 内置变量。CSS
自定义属性可以在组件样式中使用；若需要修改 Bootstrap 的 Sass
变量，则应使用对应的 Sass 变量名和 SCSS 区域。

### 3.6 字体、字号和行高

HTML Theming 官方提供的常用选项包括：

-   `mainfont`：文档主要字体；
-   `fontsize`：基础字号；
-   `fontcolor`：默认文本颜色；
-   `linkcolor`：链接颜色；
-   `monofont`：代码字体；
-   `monobackgroundcolor`：代码背景颜色；
-   `linestretch`：行高；
-   `backgroundcolor`：文档背景色；
-   `margin-left`、`margin-right`、`margin-top`、`margin-bottom`：文档边距。

例如：

``` yaml
format:
  html:
    theme: cosmo
    fontsize: 1rem
    linestretch: 1.5
```

应注意：

1.  先确认当前字体设置和主题默认值，避免重复覆盖。
2.  不要将所有正文、表格和辅助文本强制设置成同一个字号。
3.  基因 ID、样本 ID
    等字段可使用适当的等宽字体，但普通表格不应全部采用等宽字体。
4.  字体调整必须检查中英文混排、数字和长标识符的显示效果。

### 3.7 主题升级的建议策略

BioReport 不宜直接大规模重写 Bootstrap 样式。推荐：

1.  保留当前主题和导航。
2.  先建立少量、清晰的主题变量。
3.  通过 SCSS 调整全局字体、颜色和标题体系。
4.  通过 CSS 调整表格、图表、卡片等局部组件。
5.  对每一轮修改重新渲染实际报告。
6.  避免重复定义多个相互覆盖的主题文件。

官方补充资料：[More About Quarto
Themes](https://quarto.org/docs/output-formats/html-themes-more)。

------------------------------------------------------------------------

## 4. HTML Basics：目录、CSS 与独立 HTML 资源

官方链接：<https://quarto.org/docs/output-formats/html-basics.html>

### 4.1 自动目录与章节导航

Quarto HTML 支持通过 `toc` 生成自动目录：

``` yaml
format:
  html:
    toc: true
    toc-depth: 3
    toc-title: "导航目录"
```

相关选项：

-   `toc`：是否生成目录；
-   `toc-depth`：目录包含的标题层级，默认深度为 3；
-   `toc-expand`：初始展开层级或全部展开/折叠；
-   `toc-title`：目录标题；
-   `toc-location`：目录位置。

`toc-location` 可选择 `left`、`right` 或 `body` 等位置。默认 HTML
主题下，浮动目录会在滚动时突出当前章节，并在视口过窄时隐藏。具体表现取决于使用的布局和主题。

需要特别注意：`toc-location` 在 `theme: none` 或 `theme: pandoc`
等禁用标准 HTML 主题的情况下不可用。

### 4.2 BioReport 的导航建议

当前报告已有顶部导航与左侧"导航目录"。实施前必须确认这两个导航的来源：

-   如果顶部导航属于项目自定义模板，保留它的结构与交互；
-   如果左侧目录来自 Quarto TOC，应优先调整 Quarto 原生选项；
-   如果左侧目录由自定义 JavaScript 或 HTML
    生成，应避免同时启用另一个重复目录；
-   如果两套导航分别承担全报告章节切换和当前页面内部导航，应清楚区分它们的层级与功能。

不要只因为 Quarto 提供 `toc`
就重复生成一个目录。导航的数量和行为应以实际用户需求为准。

### 4.3 引入自定义 CSS

Quarto 官方支持：

``` yaml
format:
  html:
    css: styles/report.css
```

如果需要多个样式文件，可使用列表：

``` yaml
format:
  html:
    css:
      - styles/report.css
      - styles/tables.css
```

CSS 适合处理：

-   正文宽度和组件间距；
-   表格的颜色、边框、行高和滚动容器；
-   图表容器和图注；
-   卡片、提示框和导航的局部视觉样式；
-   小屏幕下的响应式调整。

CSS 不适合单独承担所有功能逻辑。表格排序、分页、搜索和 Plotly
图表自适应等行为仍应使用现有组件的原生能力或配置。

### 4.4 自包含 HTML：`embed-resources`

BioReport
的报告可能需要作为独立文件交付给用户。因此，必须在升级前确认资源打包方式。

官方选项：

``` yaml
format:
  html:
    embed-resources: true
```

该选项可以将适用的 CSS、JavaScript、图片和视频等资源嵌入
HTML，使文档尽可能自包含，适合脱离项目目录分享。

但需要注意：

-   自包含文件可能明显变大。
-   资源是否能够嵌入取决于资源类型和引用方式。
-   绝对 URL 资源与相对 URL 资源的处理方式不同。
-   被标记为外部资源的内容可能不会嵌入。
-   MathJax/KaTeX 等数学库默认不一定随资源一起嵌入；如确实需要，可调查
    `self-contained-math` 等相关选项。
-   自包含 HTML
    的实际离线能力必须通过断网或隔离环境打开文件验证，不能仅凭 YAML
    设置判断。

### 4.5 对 BioReport 的交付要求

样式升级后应确认：

1.  自定义 CSS 是否在重新渲染后生效。
2.  样式文件是否按预期嵌入或被正确引用。
3.  Plotly 图表是否仍可交互。
4.  表格的 JavaScript 是否仍能初始化。
5.  图片和其他资源是否正常显示。
6.  HTML 文件是否可以按照现有交付流程独立打开。
7.  报告文件大小变化是否可接受。

如果当前采用单文件 HTML 交付方式，不要为了方便开发而直接把最终 CSS
改成只在本地路径下有效的外部引用，除非交付策略也同步调整。

### 4.6 官方参考

-   [HTML
    Basics](https://quarto.org/docs/output-formats/html-basics.html)
-   [HTML Options
    Reference](https://quarto.org/docs/reference/formats/html.html)
-   [Publishing HTML / Standalone
    HTML](https://quarto.org/docs/output-formats/html-publishing.html)

------------------------------------------------------------------------

## 5. Quarto Gallery：如何参考官方示例

官方链接：<https://quarto.org/docs/gallery/>

Gallery
是官方案例集合，不是一个单独的主题或前端框架。其价值在于比较不同报告和
Dashboard 的布局方式，并选择适合 BioReport 的设计模式。

### 5.1 优先浏览的案例类别

#### Articles & Reports

适合观察：

-   传统报告的标题和正文层级；
-   图表与正文之间的关系；
-   目录与章节组织；
-   单个 Markdown/QMD 文件生成 HTML 报告的方式。

#### HTML with advanced layout

适合观察：

-   全宽图表与正文区域的组合；
-   多栏布局；
-   边栏说明；
-   内容块之间的空间分配。

#### Dashboards

适合观察：

-   统计卡片；
-   多列图表；
-   指标与图表的组合；
-   交互式图表的布局；
-   响应式布局在宽屏与移动端之间的变化。

### 5.2 可优先查看的 Dashboard 示例

官方 Gallery 包含多种可交互案例，例如：

-   [Stock Explorer](https://jjallaire.github.io/stock-explorer/)
-   [Gapminder](https://jjallaire.github.io/gapminder/)
-   [Customer
    Churn](https://jjallaire.github.io/customer-churn-dashboard/)
-   [NFL Injuries](https://jjallaire.github.io/nfl-injuries-dashboard/)

这些案例可用于观察信息密度、KPI
卡片、图表排布和交互控件。实际链接和可用状态应以官方 Gallery
当前页面为准。

### 5.3 BioReport 应借鉴什么

  BioReport 组件     借鉴方向
  ------------------ ----------------------------------------------
  项目概述页         Dashboard 中 KPI 与辅助说明的组织方式
  PCA / 表达量图表   多列图表布局、图注和响应式调整
  表达矩阵           数据表格的可读性、操作区和页面空间管理
  质量控制页         将关键指标与解释文本结合，而不是只堆叠图表
  溯源信息页         清晰的字段分组和元数据层级
  全局导航           统一导航层级，避免报告内部出现多个竞争性导航

### 5.4 不应该直接复制什么

不要直接复制某个 Dashboard 的整个项目结构或样式，原因包括：

-   Dashboard 与长篇科研报告的阅读模式不同；
-   案例使用的语言、库和依赖可能不同；
-   案例中的交互行为不一定适用于静态独立 HTML；
-   直接复制 CSS 可能覆盖当前 Quarto/Bootstrap 组件；
-   直接复制 JavaScript 可能与现有表格或 Plotly 运行时冲突。

正确流程是：先从案例中识别一个设计模式，再用现有 Quarto 配置、CSS/SCSS
和组件实现该模式。

------------------------------------------------------------------------

## 6. HTML Accessibility：可访问性检查

官方链接：<https://quarto.org/docs/output-formats/html-accessibility.html>

### 6.1 为什么 BioReport 也需要可访问性检查

科研报告可能包含大量颜色编码、细小辅助文字、交互式表格、图表图例和导航链接。视觉美化不能以降低可读性为代价。

可访问性检查可帮助发现部分问题，例如：

-   文本与背景对比度不足；
-   部分交互控件缺少可识别名称；
-   某些语义结构或交互状态不符合检查规则；
-   部分元素在辅助技术或键盘操作场景下存在问题。

自动化工具只能发现其规则覆盖范围内的问题，不能替代人工检查。

### 6.2 启用 axe 检查

Quarto 集成了 axe-core 检查能力。可在 HTML 格式中启用：

``` yaml
format:
  html:
    axe: true
```

渲染后在浏览器中打开报告，并检查开发者工具中的控制台信息。

官方提供的输出方式包括：

-   `console`：在控制台显示结果；
-   `document`：将检查结果展示在页面上；
-   `json`：以 JSON 形式输出结果，适合与浏览器自动化测试集成。

例如：

``` yaml
format:
  html:
    axe:
      output: json
```

如需将检查限制到某个标准，可使用 `standard`，例如：

``` yaml
format:
  html:
    axe:
      standard: wcag21aa
```

若需要同时检查最佳实践规则，可在相应配置中设置 `best-practice: true`。

### 6.3 建议将检查放在开发或验收阶段

不建议不加区分地把开发诊断报告放进每一份最终交付的科研 HTML 中。

建议：

1.  在开发配置或测试 profile 中开启 `axe`。
2.  打开实际渲染页面并检查结果。
3.  修复真实的对比度、标签、语义和交互问题。
4.  在最终验收时再次执行检查。
5.  确认生产交付是否应该关闭诊断输出，避免将调试报告误带给最终用户。

如果希望将检查集成到 Playwright/Puppeteer 等自动化测试中，可以研究
`output: json` 的结果形式，但需要实际验证运行环境和报告的脚本执行方式。

### 6.4 BioReport 的人工检查清单

-   [ ] 正文、辅助文本、链接和表格文字具有足够对比度。
-   [ ] 不仅通过颜色表达通过/失败或显著/不显著。
-   [ ] 所有重要链接具有清晰的可读文本。
-   [ ] 表格标题、列标题与数据单元格结构合理。
-   [ ] 键盘焦点清晰可见。
-   [ ] 表格搜索框、分页按钮和下拉选择器可以辨识。
-   [ ] 图表有清晰的标题或说明；必要时提供文字解释。
-   [ ] 图片具有适当的替代文本。
-   [ ] 放大页面或缩小视口后，内容仍可阅读。
-   [ ] 折叠导航、标签页和交互组件不会遮挡关键内容。
-   [ ] 自动化检查发现的问题均有记录与处理结论。

官方页面：[HTML Accessibility
Checks](https://quarto.org/docs/output-formats/html-accessibility.html)。

------------------------------------------------------------------------

## 7. 将五份官方资料映射到 BioReport 的实施任务

  ------------------------------------------------------------------------------------------------------
  阶段              参考资料          工程任务                                      验收证据
  ----------------- ----------------- --------------------------------------------- --------------------
  0\. 现状调查      全部五份资料      定位                                          调查记录与基线截图
                                      YAML、模板、主题、CSS、表格库和资源打包方式   

  1\. 布局修复      Page Layout       调整正文网格，验证                            不同视口的前后截图
                                      article/full，协调目录与正文                  

  2\. 主题统一      HTML Theming      选择/保留基础主题，建立品牌变量和 SCSS        主题文件、渲染截图

  3\. 目录与交付    HTML Basics       保留正确的目录行为，验证 CSS 与独立 HTML 资源 独立 HTML 打开测试

  4\. 视觉参考      Gallery           对照案例优化 KPI、图表和信息布局              组件级对比截图

  5\. 质量验收      Accessibility     开启 axe 检查，人工检查交互与对比度           检查报告和缺陷清单
  ------------------------------------------------------------------------------------------------------

### 7.1 建议的工程执行顺序

1.  不修改代码，先完成仓库现状调查。
2.  优先处理正文宽度和表格溢出。
3.  调整导航、目录和正文的空间关系。
4.  建立基础主题与组件 CSS。
5.  统一统计卡片、图表和提示框。
6.  验证自包含 HTML 与离线交付。
7.  执行响应式和可访问性检查。
8.  记录前后对比与遗留问题。

------------------------------------------------------------------------

## 8. 推荐的配置参考模板

以下示例展示多个官方能力如何组合。**它不是可直接覆盖当前项目的完整配置。**
应将需要的字段合并到现有
YAML，并保留原有标题、目录、主题、资源打包及其他必要设置。

``` yaml
format:
  html:
    # 先验证现有报告适合 article 还是 full
    page-layout: full

    # 保留现有基础主题；cosmo 仅为示例
    theme:
      - cosmo
      - styles/report-theme.scss

    # 报告级组件样式
    css:
      - styles/report.css

    # 仅作为初始测试值
    grid:
      body-width: 1150px
      margin-width: 220px
      gutter-width: 1.5rem

    # 目录设置需与现有导航机制协调
    toc: true
    toc-depth: 3
    toc-location: left

    # 只有当前交付要求单文件 HTML 时才启用/保留
    embed-resources: true

    # 开发或验收阶段启用，最终交付前按策略关闭
    # axe: true
```

### 8.1 使用前必须检查的事项

-   当前是否已经使用 `theme` 或自定义 SCSS；
-   `page-layout: full` 是否与左侧导航、目录和自定义布局兼容；
-   `toc` 是否会生成重复的导航目录；
-   `grid.body-width` 是否与 `max-width` 或自定义容器宽度相冲突；
-   自定义 CSS 是否会覆盖 Bootstrap 或表格渲染器的行为；
-   `embed-resources` 是否符合最终交付要求；
-   `axe` 是否只在测试环境开启。

------------------------------------------------------------------------

## 9. 实施时的常见误区

### 误区一：直接把 `page-layout` 改成 `full`

`full`
可能帮助释放水平空间，但如果导航和目录占用布局区域，最终效果仍需检查。先对比
`article` 与 `full`，再决定是否采用。

### 误区二：只增大 `body-width`

页面最大宽度、主题限制、侧栏宽度、正文容器和图表内部尺寸可能共同影响最终表现。应同时调查
Quarto 网格、主题和实际 DOM。

### 误区三：用全局 CSS 强行覆盖所有表格

当前表格可能来自 ITables、DataTables、Quarto
原生表格或其他组件。必须先识别真实渲染器，再限定选择器和样式范围。

### 误区四：把主题切换等同于完成美化

Bootswatch
可以提供基础风格，但不会自动解决宽表达矩阵、图表布局、列名截断、分页工具栏和特定统计卡片的问题。

### 误区五：只在当前生成的 HTML 上修改样式

最终样式必须写入可维护的源码和模板，并通过真实渲染命令重新生成。不能把临时修改已生成
HTML 的结果当成工程实现。

### 误区六：将 `embed-resources: true` 当作绝对离线保证

必须实际打开生成文件，检查脚本、样式、图片和图表能否正常加载。文件大小、外部
URL 和未嵌入资源都需要纳入验证。

### 误区七：只看 axe 自动化结果

自动化检查不覆盖全部视觉与交互问题。仍需检查移动端、键盘操作、长表格、图表可读性和实际科研内容。

------------------------------------------------------------------------

## 10. 可直接交给 Codex 的辅助执行指令

请先阅读本文件及以下 Quarto 官方资料，再调查当前 BioReport
仓库。不要直接根据文档示例覆盖现有配置。

官方资料：

1.  https://quarto.org/docs/output-formats/page-layout.html
2.  https://quarto.org/docs/output-formats/html-themes.html
3.  https://quarto.org/docs/output-formats/html-basics.html
4.  https://quarto.org/docs/gallery/
5.  https://quarto.org/docs/output-formats/html-accessibility.html

### 第一步：调查

只读检查：

-   当前 Quarto 版本；
-   实际报告入口与渲染命令；
-   项目级和文档级 YAML；
-   当前基础主题、SCSS、CSS；
-   目录与顶部导航来源；
-   表格渲染器及版本；
-   Plotly 图表布局方式；
-   `embed-resources` 等资源打包设置；
-   现有 HTML 的文件大小、DOM 结构和交互状态。

### 第二步：给出技术决策

明确回答：

1.  当前正文宽度由哪些配置或 CSS 限制？
2.  当前最合适的是 `article`、`full` 还是保留现有布局？
3.  当前主题应该保留还是调整？为什么？
4.  表格列名截断的根因是什么？
5.  如何保留导航、目录、Plotly、表格交互和独立 HTML 交付？
6.  哪些改动只需要 CSS，哪些需要 YAML/SCSS，哪些需要修改组件配置？

### 第三步：实施

在确认方案后：

-   先修复正文布局与表格问题；
-   再建立统一主题；
-   然后优化图表、卡片和响应式行为；
-   最后执行可访问性和交付兼容性验证。

不要无理由更换表格库、图表库或前端框架。

### 第四步：验证

至少验证：

-   1440×900 桌面视口；
-   1920×1080 大屏视口；
-   768×1024 平板视口；
-   390×844 手机视口。

检查正文宽度、导航、目录、表格横向滚动、分页搜索、图表交互、资源加载和浏览器控制台错误。开发阶段启用
axe 检查，并记录问题的修复状态。

### 第五步：交付

输出：

-   现状调查记录；
-   设计与技术决策；
-   修改文件清单；
-   实际渲染结果；
-   修改前后截图；
-   功能回归清单；
-   可访问性检查结果；
-   HTML 文件体积与性能变化；
-   未解决问题和后续建议。

**核心原则：**
以官方文档为技术依据，以当前仓库的真实结构为实施依据。先定位原因，再做最小且可验证的修改。不得只添加一份
CSS 就宣称完成报告 UI/UX 升级。

------------------------------------------------------------------------

## 11. 官方参考链接总表

1.  **Page Layout** --- 页面布局与网格宽度\
    https://quarto.org/docs/output-formats/page-layout.html

2.  **HTML Theming** --- Bootstrap、Bootswatch 与主题定制\
    https://quarto.org/docs/output-formats/html-themes.html

3.  **More About Quarto Themes** --- SCSS 主题文件与变量/规则组织\
    https://quarto.org/docs/output-formats/html-themes-more

4.  **HTML Basics** --- 目录、CSS、锚点与自包含 HTML\
    https://quarto.org/docs/output-formats/html-basics.html

5.  **HTML Options Reference** --- HTML 格式选项\
    https://quarto.org/docs/reference/formats/html.html

6.  **Quarto Gallery** --- 官方报告与 Dashboard 案例\
    https://quarto.org/docs/gallery/

7.  **HTML Accessibility Checks** --- axe-core 可访问性检查\
    https://quarto.org/docs/output-formats/html-accessibility.html

8.  **Publishing HTML** --- HTML 发布与独立文件交付\
    https://quarto.org/docs/output-formats/html-publishing.html

------------------------------------------------------------------------

## 12. 最终建议

针对当前
BioReport，最有价值的不是立即更换一个主题，而是把官方能力按正确层级组合起来：

1.  **Page Layout** 解决正文和图表区域的空间分配；
2.  **HTML Theming** 建立统一、可维护的品牌主题；
3.  **HTML Basics** 保障目录、CSS 引用和独立 HTML 交付；
4.  **Gallery** 提供布局与数据展示的参考案例；
5.  **Accessibility Checks** 为最终视觉升级增加可验证的质量门槛。

完成这些工作后，BioReport
可以形成可复用的报告主题与组件规范。后续其他组学报告能够共享布局、卡片、表格、图表和导航样式，而不必为每一份新报告重新进行一次独立的视觉改造。
