"""Format-aware display helpers shared by report modules."""

import os

from IPython.display import HTML, Image, Markdown, display
from itables import init_notebook_mode, show as show_interactive_table
from plotly.offline import get_plotlyjs


_plotly_loaded = False
_itables_loaded = False


def is_pdf() -> bool:
    return os.environ.get("BIOREPORT_OUTPUT_FORMAT") == "pdf"


def show_figure(figure, config=None) -> None:
    global _plotly_loaded
    if is_pdf():
        display(Image(data=figure.to_image(format="png", scale=2)))
    else:
        if not _plotly_loaded:
            # Quarto promotes the output containing plotly.js to a dependency.
            # Emit the library separately so no chart is moved before the report.
            display(HTML(f'<script data-bioreport-dependency="plotly">{get_plotlyjs()}</script>'))
            _plotly_loaded = True
        display(HTML(figure.to_html(full_html=False, include_plotlyjs=False, config=config)))


def show_table(table, **kwargs) -> None:
    global _itables_loaded
    if is_pdf():
        frame = table.data if hasattr(table, "data") else table
        display(Markdown(frame.head(30).to_markdown(index=False)))
    else:
        if not _itables_loaded:
            init_notebook_mode(all_interactive=False, connected=False)
            _itables_loaded = True
        show_interactive_table(table, connected=False, **kwargs)
