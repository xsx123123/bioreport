"""Exercise the installed distribution, browser exporter and RNA delivery."""
import argparse
import importlib
import json
import subprocess
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--examples', type=Path, default=Path('/app/examples'))
    args = parser.parse_args()
    for module in ('pandas', 'numpy', 'scipy', 'sklearn', 'plotly', 'itables',
                   'jupyter_core', 'ipykernel', 'multiqc', 'rich_argparse',
                   'openai', 'pypdf', 'pikepdf', 'pypdfium2'):
        importlib.import_module(module)

    from bioreport.registry import get_registry
    from bioreport.utils.provenance import validate_delivery_manifests
    from bioreport.config import load_config
    from plotly import graph_objects as go

    # Fail during image construction if Chromium/Kaleido cannot export.
    image = go.Figure(go.Scatter(x=[1, 2], y=[1, 4])).to_image(format='svg')
    assert b'<svg' in image, 'Kaleido did not return SVG'
    for module in get_registry().modules.values():
        assert get_registry().qmd_path(module).is_file(), module.id

    with tempfile.TemporaryDirectory(prefix='bioreport-smoke-') as temp:
        root = Path(temp)
        config = {
            'project': {'project_id': 'IMAGE-SMOKE', 'client': 'Image validation',
                        'species': 'Mus musculus', 'genome_version': 'GRCm39'},
            'report': {'type': 'rna-seq', 'layout': 'single',
                       'modules': ['rna.index', 'rna.workflow', 'rna.qc',
                                   'rna.results', 'provenance', 'about'],
                       'output_format': ['html', 'pdf']},
            'ai': {'enabled': False},
            'input_files': {
                'data_dir': str((args.examples / 'rna-seq/data').resolve()),
                'qc_file': 'index/multiqc_qc_general_stats.txt',
                'mapping_file': 'index/multiqc_mapping_general_stats.txt',
                'tpm_file': 'index/merge_rsem_tpm.tsv',
                'sample_file': 'index/sample.csv',
                'contrasts_file': 'index/contrasts.csv',
                'gene_annotation_file': 'gene_annotation.tsv',
                'software_versions_file': 'software_versions.yaml',
                'fastp_stats_file': 'fastp_trim_report/multiqc_general_stats.txt',
                'fastp_report_dir': 'fastp_trim_report/multiqc_short_read_trim_report_data',
                'fastq_screen_r1_dir': 'fastq_screen_report/fastq_screen_multiqc_r1/multiqc_r1_fastq_screen_report_data',
                'fastq_screen_r2_dir': 'fastq_screen_report/fastq_screen_multiqc_r2/multiqc_r2_fastq_screen_report_data',
                'qualimap_dir': 'QualiMap/multiqc_data',
                'deg_dir': 'res/DEG', 'enrichment_dir': 'res/Enrichments',
            },
        }
        config_path = root / 'report.json'
        config_path.write_text(json.dumps(config), encoding='utf-8')
        output = root / 'output'
        subprocess.run(['bioreport', 'validate', '-c', str(config_path)], check=True, timeout=60)
        subprocess.run(['bioreport', 'run', '-c', str(config_path), '-o', str(output)],
                       check=True, timeout=900)
        html = (output / 'IMAGE-SMOKE_report.html').read_text(encoding='utf-8')
        assert 'plotly-graph-div' in html, 'RNA charts missing'
        assert (output / 'IMAGE-SMOKE_report.pdf').read_bytes().startswith(b'%PDF-')
        pdf_checks = json.loads((output / 'pdf-validation.json').read_text())
        assert pdf_checks['status'] == 'PASS', pdf_checks
        delivery = validate_delivery_manifests(load_config(config_path), str(output))
        assert not delivery['errors'], delivery
    print('Installed package, Kaleido, RNA HTML/PDF and delivery validation passed.')


if __name__ == '__main__':
    main()
