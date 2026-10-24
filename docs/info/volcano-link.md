# 差异基因表与火山图联动

在 HTML 报告的差异基因表中搜索基因 ID 或名称，点击基因旁的“定位”。报告会打开对应比较组的火山图，以橙色圆圈和标签标出该基因，并显示 log2FC 与原始 P 值。若当前缩放范围遮住目标，会恢复图表范围。

“返回基因表”保留原来的搜索、排序和页码；“清除标记”移除定位图层。缺少有效绘图坐标的基因会显示提示。相同 ID 对应多个有效点时一并标出，多个基因共用同一 Symbol 时则按基因 ID 分别定位。

匹配使用比较组与稳定基因 ID，优先选取 ENSEMBL、GeneID、gene_id，其次为 Symbol 等名称列。没有这些列时使用源数据的行位置。源数据和统计阈值不变，定位使用图中已有坐标；复制与 CSV 导出保留原始值。

中文、英文 RNA 模板均已接入。下载的图表会包含当前定位标记，如需原图请先清除标记。PDF 报告为静态页面，不提供表格点击联动。

自定义页面可使用：

```python
display_gene_expression_table(df_deg, volcano_comparison=comparison)
fig = plot_volcano_pvalue(
    df_deg, title=f'{comparison} Volcano',
    col_logfc='log2FoldChange', col_pval='pvalue',
    comparison=comparison,
)
show_figure(fig)
```

两端应传入相同比较组名称，并使用相同的源数据行顺序。不要在没有稳定 ID 的情况下仅向表格传入经过重新排序的子集。

脚本 `bioreport/assets/js/volcano-link.js` 随图表运行库打包一次，支持离线单文件 HTML 与共享本地资源的网站报告。已生成的 HTML 需要重新生成或更新内嵌内容后才会出现联动按钮。

验证命令：

```bash
python -m pytest tests/test_volcano_link.py tests/test_html_table_presentation.py tests/test_html_expression_table.py tests/test_pdf_print_contract.py
BIOREPORT_TEST_BROWSER=firefox python tests/verify_volcano_link.py
```

浏览器验证覆盖搜索、不同组的同 ID、同名 Symbol、缺失坐标、排序分页、导出原始值与清除标记，产物保存到 `output/volcano-link-validation/`。
