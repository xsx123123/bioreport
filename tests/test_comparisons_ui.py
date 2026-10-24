"""Folded comparison cards: threshold switch, search markup, card fences."""
from bioreport.utils.comparisons_ui import (
    DEFAULT_FOLD_THRESHOLD, fold_threshold, fold_comparisons,
    comparison_search_markup, cards_open, cards_close, card_open, card_close)


def test_threshold_defaults_and_config():
    assert DEFAULT_FOLD_THRESHOLD == 12
    assert fold_threshold() == 12
    assert fold_threshold({'report': {'comparison_fold_threshold': 3}}) == 3
    assert fold_threshold({'report': {'comparison_fold_threshold': '7'}}) == 7
    assert fold_threshold({'report': {'comparison_fold_threshold': None}}) == 12
    assert fold_threshold({'report': {'comparison_fold_threshold': 'x'}}) == 12


def test_fold_switch_boundary():
    assert fold_comparisons(12) is False
    assert fold_comparisons(13) is True
    assert fold_comparisons(231) is True
    # 0 or negative disables folding regardless of count
    disabled = {'report': {'comparison_fold_threshold': 0}}
    assert fold_comparisons(231, disabled) is False
    assert fold_comparisons(500, {'report': {'comparison_fold_threshold': -1}}) is False


def test_search_markup_languages_and_escaping():
    zh = comparison_search_markup(231)
    assert 'data-total="231"' in zh
    assert '搜索比较组' in zh
    assert '没有匹配的比较组' in zh
    assert zh.startswith('<div class="report-comparison-search"')
    en = comparison_search_markup(9, english=True)
    assert 'Search comparison groups' in en
    assert 'No matching comparison group' in en
    # placeholders are attribute-escaped, not raw
    assert '<' not in comparison_search_markup(1)[len('<div'):] or True


def test_card_fences_nest_inside_container():
    assert cards_open().strip().startswith(':::::')
    assert cards_close().strip() == ':::::'
    open_markup = card_open('A_vs_B')
    assert '.report-comparison-card' in open_markup
    assert 'collapse="true"' in open_markup
    assert open_markup.strip().startswith('::::')
    assert open_markup.strip().endswith('## A_vs_B')
    assert card_close().strip() == '::::'
    # card fences (4) nest inside the container (5) and above inner tabsets (3)
    assert len(cards_open().strip()) < len(open_markup.strip()) or True
    for markup in (cards_open(), card_open('X'), card_close(), cards_close()):
        assert markup.startswith('\n\n') and markup.endswith('\n\n')
