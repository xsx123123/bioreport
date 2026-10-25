"""Comparison tab search: threshold switch and the meta tag the theme script reads."""
from bioreport.utils.comparisons_ui import (
    DEFAULT_SEARCH_THRESHOLD, search_threshold, search_threshold_meta)


def test_threshold_defaults_and_config():
    assert DEFAULT_SEARCH_THRESHOLD == 10
    assert search_threshold() == 10
    assert search_threshold({'report': {'comparison_search_threshold': 3}}) == 3
    assert search_threshold({'report': {'comparison_search_threshold': '7'}}) == 7
    assert search_threshold({'report': {'comparison_search_threshold': None,
                                        'comparison_fold_threshold': 5}}) == 10
    assert search_threshold({'report': {'comparison_search_threshold': 'x'}}) == 10


def test_retired_fold_threshold_still_honored():
    assert search_threshold({'report': {'comparison_fold_threshold': 20}}) == 20
    assert search_threshold({'report': {'comparison_fold_threshold': 'x'}}) == 10


def test_threshold_meta_tag():
    assert search_threshold_meta() == (
        '<meta name="report-comparison-search-threshold" content="10">')
    assert 'content="4"' in search_threshold_meta({'report': {'comparison_search_threshold': 4}})
    # 0 or negative disables the search button but stays a valid integer payload
    assert 'content="0"' in search_threshold_meta({'report': {'comparison_search_threshold': 0}})
