import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from bioreport.config import load_config, load_project_metadata
from bioreport.enrichment import enrichment_results, validate_enrichment_inputs
from bioreport.modules import selected_modules
from bioreport.software import software_records


def delivery(tmp_path):
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data/contrasts.csv').write_text('Control,Treat\nA,B\n')
    row = {'ID':'GO:1','Description':'GO term','GeneRatio':'2/10','Count':2,'p.adjust':.01}
    pd.DataFrame([row]).to_csv(tmp_path / 'data/go.csv', index=False)
    kegg = {**row, 'ID':'sly00001', 'Description':'KEGG pathway'}
    pd.DataFrame([kegg]).to_csv(tmp_path / 'data/kegg.csv', index=False)
    config = {
        'schema_version':'2.0.0', 'path_base':'.',
        'project_meta':{'project_id':'TEST-RNAFLOW'},
        'report':{'modules':['rna.workflow','rna.results.enrichment']},
        'input_files':{'data_dir':'data','contrasts_file':'data/contrasts.csv'},
        'software_versions':[{'Software':'MultiQC','Version':'1.31'}],
        'enrichment':{database:{'enabled':True,'parameters':{'cutoff':.05},'contrasts':{
            'B_vs_A':{
                'UP':{'status':'available','table':f'data/{database}.csv','term_count':1},
                'DOWN':{'status':'no_results','term_count':0,'terms':[], 'messages':['No significant enrichment']}
            }}} for database in ('go','kegg')}
    }
    path = tmp_path / 'project_summary.json'
    path.write_text(json.dumps(config))
    return path, config


def test_delivery_paths_and_inline_versions_without_external_inputs(tmp_path):
    path, _ = delivery(tmp_path)
    config = load_config(path)
    assert config['input_files']['contrasts_file'] == str(tmp_path / 'data/contrasts.csv')
    assert selected_modules(config) == ['rna.workflow','rna.results.enrichment']
    assert software_records(config).to_dict('records') == [{'Software':'MultiQC','Version':'1.31'}]
    metadata = load_project_metadata(str(path))
    assert metadata['software_versions'] == config['software_versions']
    assert metadata['enrichment'] == config['enrichment']
    results = list(enrichment_results(config))
    assert len(results) == 4
    assert len({r.result_id for r in results}) == 4
    assert [r.frame().Description.iloc[0] for r in results if r.status == 'available'] == ['GO term','KEGG pathway']
    assert all(r.cutoff == .05 for r in results)
    assert all(r.frame().empty for r in results if r.status == 'no_results')
    validate_enrichment_inputs(config)


def test_missing_explicit_enrichment_source_fails(tmp_path):
    path, _ = delivery(tmp_path)
    config = load_config(path)
    (tmp_path / 'data/go.csv').unlink()
    with pytest.raises(FileNotFoundError, match='Enrichment source missing'):
        validate_enrichment_inputs(config)


@pytest.mark.parametrize('change', ['empty_versions','bad_status','bad_path_base'])
def test_contract_rejects_invalid_input(tmp_path, change):
    path, config = delivery(tmp_path)
    if change == 'empty_versions': config['software_versions'] = []
    elif change == 'bad_status': config['enrichment']['go']['contrasts']['B_vs_A']['UP']['status'] = 'unknown'
    else: config['path_base'] = 3
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError): load_config(path)


def test_html_renders_both_databases_and_no_results(tmp_path, monkeypatch):
    import IPython.display
    from bioreport.enrichment_views import render_enrichment
    path, _ = delivery(tmp_path)
    config = load_config(path)
    outputs, tables, figures, notes = [], [], [], []
    monkeypatch.setattr(IPython.display, 'display', lambda item:outputs.append(item.data))
    monkeypatch.setattr('bioreport.utils.visualize_utils.display_gene_expression_table', lambda frame:tables.append(frame))
    monkeypatch.setattr('bioreport.utils.render_output.show_figure', lambda fig, **kw:figures.append(kw))
    render_enrichment(config, ['B_vs_A'], notes.append)
    text = '\n'.join(outputs)
    assert '### GO' in text and '### KEGG' in text
    assert text.count('无显著富集结果') == 2
    assert [frame.Description.iloc[0] for frame in tables] == ['GO term','KEGG pathway']
    assert {kw['evidence']['database'] for kw in figures} == {'GO','KEGG'}
    assert len(set(notes)) == 2


def test_legacy_external_versions_and_filenames_remain_supported(tmp_path):
    path, config = delivery(tmp_path)
    config.pop('enrichment');config.pop('software_versions');config.pop('path_base')
    config['input_files'] = {'data_dir':'data','contrasts_file':'contrasts.csv','enrichment_dir':'.',
                             'software_versions_file':'software.json'}
    (tmp_path / 'data/software.json').write_text('[{"Software":"Samtools","Version":"1.22.1"}]')
    (tmp_path / 'data/go.csv').rename(tmp_path / 'data/B_vs_A_UP.csv')
    path.write_text(json.dumps(config))
    loaded = load_config(path)
    assert software_records(loaded).Version.iloc[0] == '1.22.1'
    assert selected_modules(loaded)
    results = list(enrichment_results(loaded))
    assert results[0].result_id == 'rna.results.enrichment__B_vs_A_UP'
    assert results[0].frame().Description.iloc[0] == 'GO term'


def test_consecutive_enrichment_outputs_keep_nested_tabset_boundaries(tmp_path, monkeypatch):
    import shutil
    import subprocess
    import IPython.display
    from bioreport.enrichment_views import render_enrichment
    if not shutil.which('quarto'): pytest.skip('Quarto Pandoc checks emitted Markdown')
    path, data = delivery(tmp_path)
    for database in data['enrichment'].values():
        database['contrasts']['C_vs_A'] = copy.deepcopy(database['contrasts']['B_vs_A'])
    path.write_text(json.dumps(data))
    outputs = []
    monkeypatch.setattr(IPython.display, 'display', lambda item:outputs.append(item.data))
    monkeypatch.setattr('bioreport.utils.visualize_utils.display_gene_expression_table',
                        lambda frame:outputs.append('<div>Table</div>'))
    monkeypatch.setattr('bioreport.utils.render_output.show_figure',
                        lambda fig, **kw:outputs.append('<div>Figure</div>'))
    render_enrichment(load_config(path), ['B_vs_A','C_vs_A'], lambda _:None)
    # Reproduce Jupyter as-is concatenation, including adjacent prose/headers.
    document = ''.join(outputs)
    result = subprocess.run(['quarto','pandoc','--from=markdown','--to=json'],
                            input=document,text=True,capture_output=True,check=True)
    ast = json.loads(result.stdout)
    headers, tabsets = [], []
    def visit(value):
        if isinstance(value,dict):
            if value.get('t') == 'Header': headers.append(value['c'][0])
            if value.get('t') == 'Div' and 'panel-tabset' in value['c'][0][1]:
                tabsets.append(value['c'][0][1])
            for child in value.values(): visit(child)
        elif isinstance(value,list):
            for child in value: visit(child)
    visit(ast)
    assert headers.count(3) == 2
    assert headers.count(4) == 4
    assert headers.count(5) == 8
    assert sum('enrichment-comparisons' in classes for classes in tabsets) == 2
    assert sum('enrichment-directions' in classes for classes in tabsets) == 4


def test_real_delivery_contract_reads_every_database_direction():
    path = Path('examples/X101SC26098749-Z01-J001_UPDATE/project_summary.json')
    if not path.exists(): pytest.skip('Local delivery fixture is not installed')
    loaded = load_config(path)
    results = list(enrichment_results(loaded))
    assert len(results) == 24
    assert sum(r.status == 'available' for r in results) == 23
    assert {r.database for r in results} == {'GO','KEGG'}
    validate_enrichment_inputs(loaded)


def test_upstream_path_only_examples_match_standalone_schema():
    from jsonschema import Draft202012Validator, FormatChecker
    schema = json.loads(Path('configs/rnaflow.delivery.schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    example = json.loads(Path('configs/report.rnaflow.example.json').read_text())
    validator.validate(example)
    actual = Path('examples/X101SC26098749-Z01-J001_UPDATE/report.paths.json')
    if actual.exists():
        data = json.loads(actual.read_text())
        validator.validate(data)
        assert all('terms' not in record for db in data['enrichment'].values()
                   for directions in db['contrasts'].values() for record in directions.values())


@pytest.mark.parametrize('change', ['terms', 'missing_table', 'null_available_table', 'absolute',
                                  'parent', 'windows', 'url', 'wrong_no_results_count'])
def test_upstream_schema_rejects_nonportable_or_large_payloads(change):
    from jsonschema import Draft202012Validator
    schema = json.loads(Path('configs/rnaflow.delivery.schema.json').read_text())
    data = json.loads(Path('configs/report.rnaflow.example.json').read_text())
    directions = next(iter(data['enrichment']['go']['contrasts'].values()))
    record = directions['UP']
    if change == 'terms': record['terms'] = []
    elif change == 'missing_table': record.pop('table')
    elif change == 'null_available_table': record['table'] = None
    elif change == 'wrong_no_results_count': record.update(status='no_results', term_count=1)
    else:
        record['table'] = {'absolute':'/data/go.csv', 'parent':'data/../go.csv',
                           'windows':'data' + chr(92) + 'go.csv', 'url':'https://example.org/go.csv'}[change]
    assert list(Draft202012Validator(schema).iter_errors(data))
