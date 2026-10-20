# BioReport 报告样式优化验收记录

日期：2026-10-21。依据：同目录《BioReport报告样式优化实现计划.md》。

HTML 实现复用已加载的 templates/theme/styles.css；当前表格使用 Python DataTables，通过列名配置宽度，不依赖 R 或 nth-child 列索引。

- 比较组：中英文 DEG 模板增加 results-comparisons 类；富集复用 enrichment-comparisons。轨道底色、10px 圆角、选中阴影和主色文字仅作用于结果标签页。
- UP/DOWN：enrichment-directions 使用 13px 字号和较轻的底部选中线，与一级比较组区分。
- Description：按列名设置 380px 原生列宽，CSS 最小宽度 360px；浏览器实测 406px，negative regulation of endopeptidase activity 为一行。数字列约 105px、右对齐，ID 不换行；完整搜索与导出数据保留。
- 暗色：适配 data-report-theme、data-bs-theme、quarto-dark。轨道使用 #212529、选中背景 #2b3035。
- 窄屏：小于 768px 时不换行，允许标签轨道横向滚动。

验证：241 项测试通过、3 项跳过；Chromium 实测中英文浅色/深色、1440px 与 390px，检查全部七个导航页面无横向页面溢出。自动验收结果为 output/rnaflow-paths-report/style-review/verification.json，截图在同目录。

最终双语 HTML：output/rnaflow-paths-report/X101SC26098749-Z01-J001_report.html。

同时修复前序 PDF 问题：print-style.typ 测量最长指标名称后统一卡片标签区高度与数值位置；补齐四至六级标题 sticky 规则；富集图前增加来源与筛选说明，避免图后汇总被当作标题后的首段。真实完整项目中英文 PDF 的版面、内容和最终溯源校验均为 PASS。摘要预览：output/rnaflow-pdf-fix/rendered/summary-fixed.png。

pypdf 的 Object count exceeds defined trailer size 警告仍可出现于克隆 PDF 对象的元数据写入过程；本次未屏蔽该警告。原失败原因是 11 处 orphan_heading，修复后为零；不能把警告本身解释为版面校验失败。
