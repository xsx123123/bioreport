"""Conservative page policies; Typst performs final measurements at render time."""
from dataclasses import replace
import math
import unicodedata
from .model import FigureBlock, FigureGroup, TableBlock


def _width(value):
    return sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in str(value))


class LayoutPlanner:
    def __init__(self, page_height=247., page_width=166.):
        self.page_height = page_height
        self.page_width = page_width

    def plan(self, block):
        if isinstance(block, TableBlock):
            # Approximate wrapped cells, including CJK. The renderer also measures
            # the complete table, so a long cell never forces an oversized block.
            weights = [4 if h == "SHA256" else 3 if h in ('Description','通路名称','数据目录内路径','统计口径') else
                       1.8 if h in ('Gene ID','Sample','样本','项目','比较组') else 1
                       for h in block.headers]
            capacities = [max(4, self.page_width*w/sum(weights)/1.7-4) for w in weights]
            height = 12 + sum(4 + 4*max((math.ceil(_width(v)/capacities[i]) for i,v in enumerate(row)), default=1)
                              for row in block.rows)
            split = block.allow_split or height > self.page_height - 20
            return replace(block, preferred_height=height, minimum_height=12,
                           keep_together=not split, allow_split=split)
        if isinstance(block, FigureBlock):
            height = min(self.page_width*block.ratio, self.page_height-45)
            return replace(block, preferred_height=height, minimum_height=min(height, 65.))
        if isinstance(block, FigureGroup):
            figures = [self.plan(f) for f in block.figures]
            return replace(block, figures=figures, tables=[self.plan(t) for t in block.tables])
        return block
