"""Declarative RNA module definitions."""

from pathlib import Path

from bioreport.registry import Module


_ROOT = str(Path(__file__).resolve().parent)
MODULES = [
    Module("rna.workflow", "qmd/workflow.qmd", "分析流程", "workflow", required_inputs=("software_versions_file",), package_root=_ROOT, icon="signpost-split"),
    Module("rna.qc", "qmd/qc.qmd", "质量控制", "qc", ("fastp_stats_file", "fastp_report_dir", "fastq_screen_r1_dir", "fastq_screen_r2_dir", "qualimap_dir"), package_root=_ROOT, icon="clipboard2-check", skip_if_missing_inputs=True),
    Module("rna.qc.fastp", "qmd/modules/qc/fastp.qmd", "fastp 质控", "qc", ("fastp_stats_file", "fastp_report_dir"), package_root=_ROOT, parent="rna.qc", setup_qmd="qmd/modules/qc/setup.qmd", skip_if_missing_inputs=True),
    Module("rna.qc.screen", "qmd/modules/qc/screen.qmd", "污染检测", "qc", ("fastq_screen_r1_dir", "fastq_screen_r2_dir"), package_root=_ROOT, parent="rna.qc", setup_qmd="qmd/modules/qc/setup.qmd", skip_if_missing_inputs=True),
    Module("rna.qc.qualimap", "qmd/modules/qc/qualimap.qmd", "QualiMap 比对质控", "qc", ("qualimap_dir",), package_root=_ROOT, parent="rna.qc", setup_qmd="qmd/modules/qc/setup.qmd", skip_if_missing_inputs=True),
    Module("rna.qc.star", "qmd/modules/qc/star.qmd", "STAR 比对结果", "qc", ("qualimap_dir",), package_root=_ROOT, parent="rna.qc", setup_qmd="qmd/modules/qc/setup.qmd", skip_if_missing_inputs=True),
    Module("rna.results", "qmd/results.qmd", "分析结果", "results", ("tpm_file", "sample_file", "contrasts_file", "deg_dir", "enrichment_dir"), package_root=_ROOT, icon="bar-chart"),
    Module("rna.results.samples", "qmd/modules/results/samples.qmd", "样本关系与表达分布", "results", ("tpm_file", "sample_file"), package_root=_ROOT, parent="rna.results", setup_qmd="qmd/modules/results/setup.qmd"),
    Module("rna.results.matrix", "qmd/modules/results/matrix.qmd", "基因表达矩阵", "results", ("tpm_file",), package_root=_ROOT, parent="rna.results", setup_qmd="qmd/modules/results/setup.qmd"),
    Module("rna.results.heatmap", "qmd/modules/results/heatmap.qmd", "基因表达热图", "results", ("tpm_file", "sample_file"), package_root=_ROOT, parent="rna.results", setup_qmd="qmd/modules/results/setup.qmd"),
    Module("rna.results.deg", "qmd/modules/results/deg.qmd", "差异表达分析", "results", ("contrasts_file", "deg_dir"), package_root=_ROOT, parent="rna.results", setup_qmd="qmd/modules/results/setup.qmd"),
    Module("rna.results.enrichment", "qmd/modules/results/enrichment.qmd", "富集分析结果", "results", ("contrasts_file", "enrichment_dir"), package_root=_ROOT, parent="rna.results", setup_qmd="qmd/modules/results/setup.qmd"),
    Module("rna.index", "qmd/index.qmd", "项目概况", "index", ("qc_file", "mapping_file", "tpm_file", "sample_file"), package_root=_ROOT, icon="house"),
]


def register(registry) -> None:
    registry.register_omics(
        "rna",
        MODULES,
        aliases={
            "index": "rna.index",
            "workflow": "rna.workflow",
            "qc": "rna.qc",
            "results": "rna.results",
            "qc.fastp": "rna.qc.fastp",
            "qc.screen": "rna.qc.screen",
            "qc.qualimap": "rna.qc.qualimap",
            "qc.star": "rna.qc.star",
            "results.samples": "rna.results.samples",
            "results.matrix": "rna.results.matrix",
            "results.heatmap": "rna.results.heatmap",
            "results.deg": "rna.results.deg",
            "results.enrichment": "rna.results.enrichment",
        },
        defaults=("rna.index", "rna.workflow", "rna.qc", "rna.results"),
    )
