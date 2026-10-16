"""Built-in font discovery shared by Typst, matplotlib and HTML rendering.

Fonts live under ``bioreport/assets/fonts`` so every machine that clones or
installs the project renders reports identically, without any system fontconfig
dependency. The exporter uses the plotted trace coordinates; fonts never change
the underlying result files.
"""
import subprocess
from functools import lru_cache
from pathlib import Path

# Typst tries families left to right and falls through per glyph, so the
# Latin-first stack gives English and digits the Latin design while CJK
# glyphs fall through to the Chinese family seamlessly.
FONT_STACK = ('Source Sans 3', 'Source Han Sans SC', 'HarmonyOS Sans SC', 'DejaVu Sans')
MONO_STACK = ('JetBrains Mono', 'Source Sans 3', 'DejaVu Sans Mono')


def font_dir() -> Path:
    """Absolute path of the built-in fonts shipped inside the bioreport package."""
    return Path(__file__).resolve().parents[1] / "assets" / "fonts"


def _available_families() -> set[str]:
    """Family names declared by the built-in font files, via fontconfig."""
    files = [p for p in font_dir().rglob("*") if p.suffix.lower() in {".ttf", ".otf", ".otc", ".ttc"}]
    families: set[str] = set()
    for path in files:
        try:
            result = subprocess.run(
                ["fc-scan", "--format", "%{family}", str(path)],
                capture_output=True, text=True, check=True, timeout=10,
            )
            families.update(name.strip() for name in result.stdout.split(","))
        except (OSError, subprocess.SubprocessError):
            continue
    return families


@lru_cache(maxsize=1)
def font_families() -> tuple[str, ...]:
    """Filter the built-in stack down to families actually shipped, keep fallbacks.

    Returns the full stack untouched when fc-scan is unavailable so rendering
    still degrades to the system fonts instead of failing.
    """
    try:
        available = _available_families()
    except Exception:
        return FONT_STACK
    if not available:
        return FONT_STACK
    found = tuple(name for name in FONT_STACK if name in available)
    return found or FONT_STACK


def typst_font_paths() -> str:
    """Value for TYPST_FONT_PATHS; points Typst at the built-in fonts."""
    return str(font_dir())


def init_bioreport_plot_style():
    """Register built-in fonts with matplotlib and apply the shared print style.

    Charts exported through print_theme call this via rc_context so SVG panels
    use the same families as the report body instead of DejaVu Sans.
    """
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    for font_file in font_dir().rglob("*"):
        if font_file.suffix.lower() in {".ttf", ".otf", ".otc", ".ttc"}:
            try:
                font_manager.fontManager.addfont(str(font_file))
            except Exception:
                continue
    families = list(font_families())
    plt.rcParams.update({
        "font.family": "sans-serif",
        # Latin-first, CJK fallback — same order as the Typst stack.
        "font.sans-serif": [*families, "DejaVu Sans"],
        "axes.unicode_minus": False,
    })
    return families


ZWSP = "​"  # zero-width space: lets Typst break long tokens


def breakable_path(value: str) -> str:
    """Insert zero-width spaces after / and _ so long paths wrap in tables."""
    return str(value).replace("/", "/" + ZWSP).replace("_", "_" + ZWSP)


def breakable_hash(value: str) -> str:
    """Insert a zero-width space every 8 chars so SHA256 digests never truncate."""
    text = str(value)
    return ZWSP.join(text[i:i + 8] for i in range(0, len(text), 8))
