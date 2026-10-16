"""Compose shared semantic sections through the existing QMD renderer."""
from pathlib import Path
import json
from .model import Report, Section, Paragraph, MethodBlock, ProvenanceBlock, AppendixBlock, CalloutBlock
from .planner import LayoutPlanner
from .recording import serialize


class ReportComposition:
    def __init__(self, identity='report'):
        self.report = Report(id=identity, content=[])
        self.planner = LayoutPlanner()

    def section(self, identity, title, body, *, pdf=False, page_break=False):
        kind = MethodBlock if identity=='rna.workflow' else ProvenanceBlock if identity=='provenance' else AppendixBlock if identity in ('about','methods-appendix') else CalloutBlock if identity=='ai' else Paragraph
        content = kind(id=identity+'-content', content=body)
        section = self.planner.plan(Section(id=identity, content={"title":title,"blocks":[content]}, page_break_before=page_break))
        self.report.content.append(section)
        prefix = '```{=typst}\n#pagebreak(weak: true)\n```\n\n' if pdf and section.page_break_before else ''
        return prefix+f'# {title}\n\n{content.content.strip()}\n'

    def write(self, path):
        Path(path).write_text(json.dumps(serialize(self.report),ensure_ascii=False,indent=2),encoding='utf-8')
