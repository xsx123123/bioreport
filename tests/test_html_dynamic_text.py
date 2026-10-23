"""Report narrative must follow project metadata and actual configured cutoffs."""
import json
from pathlib import Path
import re

import pytest

from bioreport.config import load_project_metadata
from bioreport.software import version_label
from render_report_inprocess import execute_qmd_in_order


ROOT = Path(__file__).resolve().parents[1]
QMD = ROOT / 'omics/rna/qmd'


def render_inline(text, namespace):
    return re.sub(r'`\{python\}\s+([^`]+)`', lambda match: str(eval(match[1], namespace)), text)


@pytest.mark.parametrize('genome', ['ITAG4.1', 'Custom-Assembly-v9'])
def test_sample_description_uses_json_genome_and_current_stats(tmp_path, genome):
    config = json.loads((ROOT / 'tests/report.rna.html.json').read_text())
    config['input_files']['data_dir'] = str(ROOT / 'examples/rna-seq/data')
    config['project']['genome_version'] = genome
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(config))
    metadata = load_project_metadata(str(path))
    namespace = {'project_info': metadata, 'total_samples_count': 17, 'avg_q30': 76.24,
                 'qc_status_text': '数据质量一般'}
    for language in ('zh', 'en'):
        source = (QMD / ('index.qmd' if language == 'zh' else 'en/index.qmd')).read_text()
        section = source.split('## 样本信息（Sample Info）' if language == 'zh' else '## Sample Information', 1)[1].split('```', 1)[0]
        rendered = render_inline(section, namespace)
        assert genome in rendered and '17' in rendered and '76.2' in rendered
        assert 'GRCm39' not in rendered and '95.9' not in rendered


def test_legends_use_nondefault_cutoffs_without_recalculating_statistics():
    namespace = {'deg_settings': {'pvalue_threshold': .012, 'log2fc_threshold': 2.5},
                 'distribution_settings': {'threshold': 3.5}}
    for prefix in ('', 'en/'):
        source = (QMD / f'{prefix}modules/results/deg.qmd').read_text()
        rendered = render_inline(re.sub(r'```.*?```', '', source, flags=re.S), namespace)
        assert '0.012' in rendered and '2.5' in rendered
        source = (QMD / f'{prefix}modules/results/samples.qmd').read_text()
        rendered = render_inline(re.sub(r'```.*?```', '', source, flags=re.S), namespace)
        assert '3.5' in rendered


def test_software_version_labels_match_supplied_names():
    versions = {'fastp': '1.0.1', 'FastQ Screen': '0.16.0', 'QualiMap': '2.3'}
    assert version_label(versions, 'Fastp') == '1.0.1'
    assert version_label(versions, 'Fastq Screen') == '0.16.0'
    assert version_label(versions, 'Qualimap') == '2.3'
    assert version_label(versions, 'STAR', 'Not supplied') == 'Not supplied'


def test_inprocess_verifier_matches_quarto_inline_execution_order():
    namespace = {}
    source = '''```{python}
value = 1
```
Before: `{python} value`
```{python}
value = 2
```
After: `{python} value`
```text
`{python} undefined_example`
```
'''
    actual = execute_qmd_in_order(source, namespace, lambda code: exec(code, namespace) or '')
    assert 'Before: 1' in actual and 'After: 2' in actual
    assert '`{python} undefined_example`' in actual
    # This reproduces the reported failure; a later assignment must not mask it.
    with pytest.raises(NameError, match='workflow_config'):
        execute_qmd_in_order("`{python} workflow_config['genome']`\n```{python}\nworkflow_config = {}\n```",
                             {}, lambda code: '')


@pytest.mark.parametrize('language', ['zh', 'en'])
def test_workflow_defines_metadata_before_first_inline_use(monkeypatch, language):
    from bioreport.utils import report_utils

    monkeypatch.setenv('REPORT_CONFIG', str(ROOT / 'examples/X101SC26098749-Z01-J001_UPDATE/report.paths.json'))
    monkeypatch.setattr(report_utils, 'software_version_table',
                        lambda frame, source: dict(zip(frame.Software, frame.Version)))
    source = (QMD / ('en/workflow.qmd' if language == 'en' else 'workflow.qmd')).read_text()
    namespace = {}
    rendered = execute_qmd_in_order(source, namespace, lambda code: exec(code, namespace) or '')
    assert namespace['workflow_config']['genome'] == 'ITAG4.1'
    assert 'ITAG4.1' in rendered
    assert '`{python}' not in rendered
