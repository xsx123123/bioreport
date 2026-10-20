"""Choose a package-local official bundle; preserve custom trace compatibility."""
from functools import lru_cache
from pathlib import Path

from loguru import logger
from plotly.offline import get_plotlyjs, get_plotlyjs_version

BUNDLE_VERSION = '3.4.0'
CARTESIAN_TRACES = frozenset({'bar','box','contour','heatmap','histogram','histogram2d',
                            'histogram2dcontour','image','pie','scatter','scatterternary','violin'})


def supports_cartesian(figure):
    return {trace.type for trace in figure.data} <= CARTESIAN_TRACES


@lru_cache(maxsize=1)
def _cartesian_source():
    path = Path(__file__).resolve().parents[1]/'assets/js'/f'plotly-cartesian-{BUNDLE_VERSION}.min.js'
    return path.read_text(encoding='utf-8') if path.is_file() else None


def selected_runtime(figure, force_full=False):
    version = get_plotlyjs_version()
    if not force_full and version == BUNDLE_VERSION and supports_cartesian(figure):
        source = _cartesian_source()
        if source:
            logger.info('Plotly runtime: local Cartesian {}; trace types: {}; {} bytes', version,
                        ', '.join(sorted({trace.type for trace in figure.data})),len(source.encode()))
            return source, 'cartesian', f'plotly-cartesian-{version}.min.js'
    logger.info('Plotly runtime: full {}; preserving trace/version compatibility for {}',
                version, ', '.join(sorted({trace.type for trace in figure.data})))
    return get_plotlyjs(), 'full', f'plotly-{version}.min.js'
