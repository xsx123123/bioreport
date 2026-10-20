"""Bundle trimming must preserve trace coverage and custom module fallback."""
import ast
from pathlib import Path
import plotly.graph_objects as go
from bioreport.utils import plotly_runtime, render_output


def test_static_rna_trace_inventory_fits_official_cartesian_bundle():
    actual=set()
    for path in (Path(__file__).resolve().parents[1]/'omics/rna/analysis').glob('*.py'):
        for call in ast.walk(ast.parse(path.read_text())):
            if not isinstance(call,ast.Call) or not isinstance(call.func,ast.Attribute) or not isinstance(call.func.value,ast.Name):
                continue
            alias,name=call.func.value.id,call.func.attr
            if alias=='go' and name!='Figure':actual.add(name.lower())
            elif alias=='px':actual.update({'heatmap','image'} if name=='imshow' else {name})
    assert {'scatter','bar','violin','heatmap'} <= actual
    assert actual <= plotly_runtime.CARTESIAN_TRACES


def test_unsupported_trace_upgrades_to_full_runtime_without_losing_figures(monkeypatch):
    output=[]
    monkeypatch.delenv('BIOREPORT_SHARED_ASSET_DIR',raising=False)
    monkeypatch.delenv('BIOREPORT_OUTPUT_FORMAT',raising=False)
    monkeypatch.setattr(render_output,'display',output.append)
    monkeypatch.setattr(render_output,'_plotly_loaded',False)
    render_output.show_figure(go.Figure(go.Scatter(x=[1],y=[2])))
    assert render_output._plotly_bundle=='cartesian'
    render_output.show_figure(go.Figure(go.Scatter3d(x=[1],y=[2],z=[3])))
    assert render_output._plotly_bundle=='full'
    render_output.show_figure(go.Figure(go.Bar(x=['A'],y=[1])))
    assert len(output)==5
    assert sum('data-bioreport-dependency="plotly"' in value.data for value in output)==2
    assert sum('class="plotly-graph-div"' in value.data for value in output)==3


def test_changed_plotly_version_uses_matching_full_runtime(monkeypatch):
    monkeypatch.setattr(plotly_runtime,'get_plotlyjs_version',lambda:'99.0.0')
    source,bundle,filename=plotly_runtime.selected_runtime(go.Figure(go.Scatter(x=[1],y=[2])))
    assert source and bundle=='full' and filename=='plotly-99.0.0.min.js'
