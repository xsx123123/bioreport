# HTML 报告图表下载

点击 Plotly 图表右上角的相机按钮，选择文件格式和宽高后下载。中文、英文报告均支持，单文件 HTML 可离线使用。

- 默认格式为 PNG；也可选择 SVG、PDF。
- 宽高单位为像素，默认使用图表的导出尺寸；没有配置时使用 700 × 450。输入值就是文件的实际图像尺寸，不再额外乘以原有 PNG 下载倍率。
- PNG 额外提供分辨率（DPI）设置，默认 600，支持 72–2400；DPI 写入 PNG 的 pHYs 元数据，决定出版软件中的物理打印尺寸，不改变像素数。SVG、PDF 不适用，选择这两个格式时该输入框自动隐藏。
- 交互配色下拉（Palette / Scale）只属于屏幕上的图表：导出时临时移除，PNG/SVG/PDF 文件中均不含这些按钮，导出完成后自动恢复。
- 默认锁定宽高比，修改一边会联动另一边；取消勾选后可分别设置。恢复默认会恢复 PNG、原始尺寸和 600 DPI。
- 每张图表分别记住当前页面内的下载设置。
- 单边尺寸支持 100–16000 像素。PNG、PDF 总像素数最多为 1600 万，超出时会提示缩小尺寸。

SVG 保留 Plotly 生成的矢量内容，并嵌入单文件报告的内置字体。热图、WebGL 等本身包含栅格内容的图层仍为图像。PDF 是单页文档，内嵌白色背景的无损 RGB 图像，图像像素尺寸等于设置值，页面大小按 96 px/in 换算；需要编辑矢量图形时使用 SVG。

验证：

```bash
python -m pytest -q tests/test_plotly_download.py tests/test_render_output.py tests/test_plotly_runtime.py
python tests/verify_plotly_download.py
python tests/verify_plotly_bundle.py
```

浏览器验证需要 Playwright、Chromium、Pillow、numpy 和 pypdf。产物位于 `output/plotly-download-validation/`。

在限制浏览器进程启动的环境中，单测及 Quarto 渲染不能代替实际下载验证。应在可以运行 Chromium 的环境中执行上述两个浏览器脚本；单独查看交互时，也可直接打开生成的 `output/plotly-download-validation/inline.html`，点击图表相机按钮检查默认 PNG、格式选择和宽高设置。
