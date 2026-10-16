"""Shared semantic report content and renderer-independent layout policies."""
from .model import (Report, Section, Paragraph, MetricGrid, TableBlock, FigureBlock,
                    FigureGroup, CalloutBlock, MethodBlock, ProvenanceBlock, AppendixBlock)
from .planner import LayoutPlanner
