"""Keep the PDF workflow graph consistent with its HTML Mermaid source."""

from pathlib import Path
import re
import xml.etree.ElementTree as ET


def test_pdf_workflow_preserves_mermaid_nodes_and_connections():
    qmd = Path(__file__).resolve().parents[1] / "omics/rna/qmd"
    source = (qmd / "workflow.qmd").read_text(encoding="utf-8")
    diagram = re.search(r"```\{mermaid\}\n(.*?)\n```", source, re.DOTALL).group(1)
    svg = ET.parse(qmd / "assets/rna-workflow.svg").getroot()
    ns = {"svg": "http://www.w3.org/2000/svg"}
    definitions = re.findall(r'\b(\w+)(?:\["?([^\]\n]+?)"?\]|\{([^}]+)\}|\(([^)]+)\)):::', diagram)
    expected_nodes = {identifier: next(value for value in values if value).strip('"') for identifier, *values in definitions}
    actual_nodes = {
        group.attrib["id"].removeprefix("node-"): group.find("svg:text", ns).text
        for group in svg.findall("svg:g", ns)
    }
    assert actual_nodes == expected_nodes
    expected_edges = set()
    for line in diagram.splitlines():
        if "-->" not in line and "-.->" not in line:
            continue
        left, arrow, right = re.split(r"(-->|-\.->)", line.strip())
        src = re.match(r"\w+", left).group()
        dst = re.match(r"\w+", right.strip()).group()
        expected_edges.add((src, dst, arrow == "-.->"))
    actual_edges = {
        (path.attrib["data-source"], path.attrib["data-target"], "stroke-dasharray" in path.attrib)
        for path in svg.findall("svg:path", ns)
    }
    assert actual_edges == expected_edges
