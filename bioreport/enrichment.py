"""Shared GO/KEGG result contract for renderers, validation and interpretation."""
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EnrichmentResult:
    database: str
    comparison: str
    direction: str
    status: str
    path: str | None = None
    full_table: str | None = None
    terms: list = field(default_factory=list)
    messages: list = field(default_factory=list)
    cutoff: float = .1

    @property
    def result_id(self):
        database = f'{self.database}__' if self.database else ''
        return f'rna.results.enrichment__{database}{self.comparison}_{self.direction}'

    @property
    def identity(self):
        return (self.comparison, self.database, self.direction)

    def frame(self, *, validate=True):
        import pandas as pd
        if self.status != 'available':
            return pd.DataFrame(columns=['ID','Description','GeneRatio','Count','p.adjust'])
        if self.path:
            frame = pd.read_csv(self.path, sep=None, engine='python')
        else:
            frame = pd.DataFrame(self.terms)
        required = {'Description','GeneRatio','Count','p.adjust'}
        if validate and required - set(frame):
            raise ValueError(f'Missing enrichment columns: {sorted(required-set(frame))} in {self.path or self.result_id}')
        return frame


def enrichment_results(config, comparisons=None):
    """Explicit per-database records take precedence over legacy filenames."""
    inputs = config.get('input_files', {})
    base = Path(config.get('_path_base') or inputs.get('data_dir') or '.')
    settings = config.get('analysis', {}).get('enrichment', {})
    explicit = config.get('enrichment')
    if explicit:
        for database, definition in explicit.items():
            if not definition.get('enabled', True):
                continue
            records = definition.get('contrasts', {})
            names = comparisons if comparisons is not None else list(records)
            cutoff = settings.get('p_cutoff', definition.get('parameters', {}).get('cutoff', .1))
            for comparison in names:
                for direction in ('UP','DOWN'):
                    record = records.get(comparison, {}).get(direction, {})
                    def resolved(key):
                        value = record.get(key)
                        return str((base / value).resolve()) if value else None
                    yield EnrichmentResult(database.upper(), comparison, direction,
                        record.get('status','unavailable'), resolved('table'), resolved('full_table'),
                        record.get('terms', []), record.get('messages', []), cutoff)
        return
    from bioreport.utils.report_utils import get_comparisons_from_csv, get_file_path
    root = inputs.get('enrichment_dir')
    if root:
        root = str((base / root).resolve())
    if comparisons is None:
        contrasts = inputs.get('contrasts_file')
        comparisons = get_comparisons_from_csv(base / contrasts) if contrasts else sorted({
            p.stem.rsplit('_', 1)[0] for p in Path(root).glob('*.csv')
            if p.stem.endswith(('_UP','_DOWN'))
        }) if root else []
    for comparison in comparisons:
        for direction in ('UP','DOWN'):
            path = get_file_path(config, f'{comparison}_{direction}.csv', root) if root else None
            yield EnrichmentResult('',comparison,direction,'available' if path and Path(path).is_file() else 'unavailable',
                                   path=path, cutoff=settings.get('p_cutoff', .1))


def validate_enrichment_inputs(config):
    """Validate declared sources, even when their names are nonstandard."""
    if not config.get('enrichment'):
        return
    for result in enrichment_results(config):
        for path in (result.path, result.full_table):
            if path and not Path(path).is_file():
                raise FileNotFoundError(f'Enrichment source missing: {path}')
        if result.status == 'available':
            if not result.path and not result.terms:
                raise ValueError(f'Available enrichment needs table or terms: {result.result_id}')
            frame = result.frame()
            record = config['enrichment'][result.database.lower()]['contrasts'][result.comparison][result.direction]
            if 'term_count' in record and record['term_count'] != len(frame):
                raise ValueError(f'Enrichment term_count differs from table: {result.result_id}')


def select_enrichment_terms(frame, cutoff, top_n):
    """Shared stable selection for interactive and prepared PDF results."""
    import pandas as pd
    from omics.rna.analysis.enrichment_plotly import parse_gene_ratios
    filtered = frame[pd.to_numeric(frame['p.adjust'], errors='coerce') < cutoff].sort_values(
        'p.adjust', kind='stable')
    valid = parse_gene_ratios(filtered['GeneRatio']).notna() & pd.to_numeric(
        filtered['Count'], errors='coerce').ge(0)
    chosen = filtered[valid].head(top_n).copy()
    chosen['Count'] = pd.to_numeric(chosen['Count'])
    return filtered, chosen
