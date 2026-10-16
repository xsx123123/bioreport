"""Small semantic vocabulary shared by omics modules and output formats."""
from dataclasses import dataclass, field
from typing import Any, ClassVar


@dataclass(kw_only=True)
class Block:
    id: str
    content: Any = None
    keep_with_next: bool = False
    keep_together: bool = True
    preferred_height: float | None = None  # millimetres
    minimum_height: float | None = None
    page_break_before: bool = False
    page_break_after: bool = False
    layout_priority: int = 0
    type: ClassVar[str] = 'block'


@dataclass(kw_only=True)
class Report(Block):
    type: ClassVar[str] = 'report'


@dataclass(kw_only=True)
class Section(Block):
    keep_with_next: bool = True
    type: ClassVar[str] = 'section'


@dataclass(kw_only=True)
class Paragraph(Block):
    keep_together: bool = False
    type: ClassVar[str] = 'paragraph'


@dataclass(kw_only=True)
class MetricGrid(Block):
    type: ClassVar[str] = 'metric_grid'


@dataclass(kw_only=True)
class TableBlock(Block):
    caption: str = "数据概览"
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    numeric: list[bool] = field(default_factory=list)
    allow_split: bool = False
    repeat_header: bool = True
    continuation: bool = True
    type: ClassVar[str] = 'table'


@dataclass(kw_only=True)
class FigureBlock(Block):
    path: str
    caption: str
    ratio: float
    type: ClassVar[str] = 'figure'


@dataclass(kw_only=True)
class FigureGroup(Block):
    figures: list[FigureBlock] = field(default_factory=list)
    tables: list[TableBlock] = field(default_factory=list)
    columns: int = 1
    type: ClassVar[str] = 'figure_group'

    def __post_init__(self):
        if not (self.figures or self.tables) or self.columns < 1:
            raise ValueError('FigureGroup requires figures or tables and positive columns')


@dataclass(kw_only=True)
class CalloutBlock(Block):
    type: ClassVar[str] = 'callout'


@dataclass(kw_only=True)
class MethodBlock(Block):
    type: ClassVar[str] = 'method'


@dataclass(kw_only=True)
class ProvenanceBlock(Block):
    type: ClassVar[str] = 'provenance'


@dataclass(kw_only=True)
class AppendixBlock(Block):
    type: ClassVar[str] = 'appendix'
