# HTML 报告图表下载

点击 Plotly 图表右上角的相机按钮，选择文件格式和宽高后下载。中文、英文报告均支持，单文件 HTML 可离线使用。

- 默认格式为 PNG；也可选择 SVG、PDF。
- 宽高为图表布局尺寸（96 px/英寸），默认使用图表的导出尺寸；没有配置时使用 700 × 450。下载框会显示实际输出像素尺寸。
- PNG 默认以 1000 DPI 将矢量图渲染为高清位图，输出宽高为输入值乘以 `1000 / 96` 后四舍五入，并写入 1000 DPI 的 pHYs 元数据。例如 800 × 500 的布局输出 8333 × 5208 像素，打印尺寸约为 8.33 × 5.21 英寸。字体、线条随图表等比例放大。SVG、PDF 保持原有导出尺寸。
- 交互配色下拉（Palette / Scale）只属于屏幕上的图表：导出时临时移除，PNG/SVG/PDF 文件中均不含这些按钮，导出完成后自动恢复。
- 默认锁定宽高比，修改一边会联动另一边；取消勾选后可分别设置。恢复默认会恢复 PNG、原始布局尺寸和宽高比锁定，PNG 固定为 1000 DPI。
- 每张图表分别记住当前页面内的下载设置。
- 布局单边尺寸支持 100–16000 像素。PNG 实际输出单边最多 16000 像素、总计最多 1.28 亿像素。超出时提示缩小尺寸或使用 SVG，不会静默降低 PNG 分辨率。高清 PNG 的导出时间和内存占用会增加。矢量 PDF 不受 PNG 总像素数限制。

SVG、PDF 保留 Plotly 生成的矢量线条和文字。PDF 直接从 SVG 转换，支持文字检索，并嵌入随图表准备的 Source Sans 3 / HarmonyOS Sans SC TrueType 字体子集，避免浏览器转换 WOFF2 时丢失字形；页面大小按 96 px/in 换算，例如 800 × 500 布局对应 600 × 375 pt。热图、WebGL 等原本包含栅格内容的图层仍为图像，坐标轴和标题保持矢量。

PDF 使用仓库内置的 pdfmake 0.2.7 浏览器包（包含 PDFKit / SVG-to-PDFKit），单文件报告内嵌一次，网站报告使用共享本地资源，下载时无需访问 CDN 或服务器。版本、校验值及构建方法见 `bioreport/assets/js/pdfmake-manifest.json`，许可证见同目录 `pdfmake-LICENSE.txt`。

转换库通过专用全局对象 `BioReportPdfMake` 加载，跳过匿名 AMD 注册，兼容 Quarto/Jupyter 表格依赖引入的 RequireJS；否则图表下载会因转换库未初始化而提示导出失败，即使使用默认尺寸也无法下载。

修改后需要重新生成报告；已经生成的单文件 HTML 中内嵌的下载脚本不会自动更新。

验证：

```bash
python -m pytest -q tests/test_plotly_download.py tests/test_render_output.py tests/test_plotly_runtime.py
python tests/verify_plotly_download.py
python tests/verify_plotly_bundle.py
```

浏览器验证需要 Playwright、Chromium、Pillow、numpy、pypdf 和 pypdfium2。验证 PDF 的矢量路径、可检索中文及渲染外观，产物位于 `output/plotly-download-validation/`。

在限制浏览器进程启动的环境中，单测及 Quarto 渲染不能代替实际下载验证。应在可以运行 Chromium 的环境中执行上述两个浏览器脚本；单独查看交互时，也可直接打开生成的 `output/plotly-download-validation/inline.html`，点击图表相机按钮检查默认 PNG、格式选择和宽高设置。
