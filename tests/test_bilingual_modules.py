"""Chinese and English qmd modules must stay content-aligned.

Every module under ``omics/rna/qmd/modules`` has an English twin under
``omics/rna/qmd/en/modules``. Intro prose and figure/table callout notes
must exist in both languages with the same structure (same callout count),
otherwise the English report silently loses captions added to the Chinese
one (regression fixed on 2026-10-25).
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / 'omics/rna/qmd'
ZH = ROOT / 'modules'
EN = ROOT / 'en/modules'

CALLOUT = '::: {.callout'
SETUP = 'setup.qmd'


def module_pairs():
    zh_files = sorted(path.relative_to(ZH) for path in ZH.glob('**/*.qmd') if path.name != SETUP)
    en_files = sorted(path.relative_to(EN) for path in EN.glob('**/*.qmd') if path.name != SETUP)
    return zh_files, en_files


def callout_count(path):
    return path.read_text(encoding='utf-8').count(CALLOUT)


def test_module_file_sets_match():
    zh_files, en_files = module_pairs()
    assert zh_files == en_files, (
        f'qmd modules exist in only one language: '
        f'zh-only={sorted(set(zh_files) - set(en_files))}, '
        f'en-only={sorted(set(en_files) - set(zh_files))}')


@pytest.mark.parametrize('relative', [str(path) for path in ZH.glob('**/*.qmd') if path.name != SETUP],
                         ids=lambda value: value)
def test_callout_notes_are_translated_for_every_module(relative):
    zh_path = ZH / relative
    en_path = EN / relative
    assert en_path.is_file(), f'missing English twin: {en_path}'
    zh_notes, en_notes = callout_count(zh_path), callout_count(en_path)
    assert zh_notes == en_notes, (
        f'{relative}: Chinese version has {zh_notes} callout note(s) but English has {en_notes}; '
        f'figure/table captions must be added to both languages in the same change')
    assert zh_notes > 0, f'{relative}: expected at least one figure/table callout note in the Chinese module'


def test_figure_note_colors_match_actual_chart_style():
    """Caption color swatches must track the real volcano palette (#e41749/#41b6e6/#c7c7c7)."""
    deg_zh = (ZH / 'results/deg.qmd').read_text(encoding='utf-8')
    deg_en = (EN / 'results/deg.qmd').read_text(encoding='utf-8')
    for color in ('#e41749', '#41b6e6', '#c7c7c7'):
        assert color in deg_zh, f'Chinese volcano caption lost swatch {color}'
        assert color in deg_en, f'English volcano caption lost swatch {color}'