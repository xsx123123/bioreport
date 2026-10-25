"""Scrollable comparison tab strips with an optional search control.

Comparison groups always render as pill tab sets (`.panel-tabset`). The strip
scrolls horizontally once tabs overflow; when the tab count exceeds a
threshold the theme script (templates/theme/comparisons-tabs.html) adds a
search button that filters groups and jumps to the match. The threshold is
report-configurable and reaches the script through a meta tag emitted into
the page.
"""

DEFAULT_SEARCH_THRESHOLD = 10


def search_threshold(config=None) -> int:
    """Report-level switch: report.comparison_search_threshold.

    Falls back to the retired report.comparison_fold_threshold; 0 or a
    negative value disables the search button (the strip still scrolls).
    """
    settings = (config or {}).get('report', {})
    value = settings.get('comparison_search_threshold',
                         settings.get('comparison_fold_threshold', DEFAULT_SEARCH_THRESHOLD))
    try:
        return int(value)
    except (TypeError, ValueError):
        return DEFAULT_SEARCH_THRESHOLD


def search_threshold_meta(config=None) -> str:
    """Meta tag the theme script reads for the search-button threshold."""
    return ('<meta name="report-comparison-search-threshold" '
            f'content="{search_threshold(config)}">')
