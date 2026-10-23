"""Declarative GWAS module definitions (GWASFlow upstream contract)."""

from pathlib import Path

from bioreport.registry import Module


_ROOT = str(Path(__file__).resolve().parent)
MODULES = [
    Module("gwas.index", "qmd/index.qmd", "项目概况", "index",
           required_inputs=("project_summary_file", "qc_final_stats_file"),
           package_root=_ROOT, icon="house"),
    Module("gwas.workflow", "qmd/workflow.qmd", "分析流程", "workflow",
           required_inputs=("software_versions_file",),
           package_root=_ROOT, icon="signpost-split"),
    Module("gwas.qc", "qmd/qc.qmd", "基因型质控", "qc",
           required_inputs=("qc_audit_file", "qc_final_stats_file"),
           package_root=_ROOT, icon="clipboard2-check"),
    Module("gwas.results", "qmd/results.qmd", "关联分析结果", "results",
           required_inputs=("gwas_dir", "chromosome_table_file"),
           package_root=_ROOT, icon="bar-chart"),
    Module("gwas.results.manhattan", "qmd/modules/results/manhattan.qmd", "曼哈顿与 QQ 图", "results",
           required_inputs=("gwas_dir", "chromosome_table_file"),
           package_root=_ROOT, parent="gwas.results",
           setup_qmd="qmd/modules/results/setup.qmd"),
    Module("gwas.results.significant", "qmd/modules/results/significant.qmd", "显著位点与候选区域", "results",
           required_inputs=("gwas_dir", "loci_dir"),
           package_root=_ROOT, parent="gwas.results",
           setup_qmd="qmd/modules/results/setup.qmd"),
    Module("gwas.results.structure", "qmd/modules/results/structure.qmd", "群体结构", "results",
           required_inputs=("pca_eigenvec_file", "kinship_matrix_file"),
           package_root=_ROOT, parent="gwas.results",
           setup_qmd="qmd/modules/results/setup.qmd", skip_if_missing_inputs=True),
]


def register(registry) -> None:
    registry.register_omics(
        "gwas",
        MODULES,
        aliases={
            "index": "gwas.index",
            "workflow": "gwas.workflow",
            "qc": "gwas.qc",
            "results": "gwas.results",
            "results.manhattan": "gwas.results.manhattan",
            "results.significant": "gwas.results.significant",
            "results.structure": "gwas.results.structure",
        },
        defaults=("gwas.index", "gwas.workflow", "gwas.qc", "gwas.results"),
    )
