"""Fold large comparison groups into searchable collapse cards.

Tab strips stop being navigable once a study has dozens of DEG contrasts
(231 comparison tabs render as a wall of links). When the comparison count
exceeds a threshold, modules render each comparison as a collapsed Quarto
callout card with a shared search box instead of a `.panel-tabset`; small
studies keep the native tabbed layout and the PDF flow is untouched.
"""
from html import escape

DEFAULT_FOLD_THRESHOLD = 12


def fold_threshold(config=None) -> int:
    """Report-level switch: report.comparison_fold_threshold (0 or negative disables folding)."""
    settings = (config or {}).get('report', {})
    try:
        return int(settings.get('comparison_fold_threshold', DEFAULT_FOLD_THRESHOLD))
    except (TypeError, ValueError):
        return DEFAULT_FOLD_THRESHOLD


def fold_comparisons(count, config=None) -> bool:
    threshold = fold_threshold(config)
    return threshold > 0 and count > threshold


def comparison_search_markup(total, english=False) -> str:
    """Search box rendered above a folded comparison card list.

    All boxes inside one routed page stay in sync: typing filters every
    folded card list on that page, so the table section and the volcano
    section locate the same comparison together.
    """
    placeholder = 'Search comparison groups' if english else '搜索比较组'
    empty = 'No matching comparison group' if english else '没有匹配的比较组'
    hint = ('Enter opens the first match' if english else '回车打开第一个匹配')
    return (
        '<div class="report-comparison-search" role="search">'
        f'<input type="search" placeholder="{escape(placeholder, quote=True)}" '
        'aria-label="' + escape(placeholder, quote=True) + '" autocomplete="off" '
        f'data-empty-text="{escape(empty, quote=True)}">'
        f'<span class="report-comparison-count" data-total="{total}" role="status"></span>'
        f'<span class="report-comparison-hint">{escape(hint)}</span>'
        '</div>')


def cards_open() -> str:
    # Blank-line guards: Quarto concatenates consecutive as-is markdown
    # outputs, where an unseparated heading would fuse into a paragraph.
    return '\n\n::::: {.report-comparison-cards}\n\n'


def cards_close() -> str:
    return '\n\n:::::\n\n'


def card_open(title) -> str:
    """A collapsed card; four-colon fences leave room for the inner tabset."""
    return (f'\n\n:::: {{.callout-note appearance="minimal" icon=false collapse="true" '
            f'.report-comparison-card}}\n\n## {title}\n\n')


def card_close() -> str:
    return '\n\n::::\n\n'
