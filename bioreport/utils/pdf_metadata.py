"""Apply delivery metadata independently of the visible cover/title block."""
import os
from pathlib import Path
import tempfile
import bioreport


def metadata_fields(config):
    report, project = config.get('report', {}), config.get('project', {})
    author = report.get('author', 'BioReport / CygnusX BioOps')
    if isinstance(author, list): author = ', '.join(map(str, author))
    keywords = report.get('keywords') or (['RNA-seq', 'transcriptomics'] if report.get('type') == 'rna-seq' else ['omics']) + ['BioReport', 'reproducible research', 'provenance']
    if isinstance(keywords, str): keywords = [keywords]
    return {
        '/Title': f"{report.get('title', 'Analysis Report')} — {project.get('project_id', '')}",
        '/Author': author,
        '/Subject': report.get('subject', 'RNA-seq transcriptome analysis report' if report.get('type') == 'rna-seq' else 'Omics analysis report'),
        '/Keywords': ', '.join(keywords),
        '/Creator': f'BioReport v{bioreport.__version__}',
    }


def set_pdf_metadata(path, config):
    from pypdf import PdfReader, PdfWriter
    path = Path(path)
    reader = PdfReader(path)
    writer = PdfWriter(clone_from=reader)
    writer.add_metadata(metadata_fields(config))
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.pdf', delete=False) as handle:
            temporary = Path(handle.name)
            writer.write(handle)
        os.replace(temporary, path)
    finally:
        writer.close()
        reader.close()
        if temporary is not None: temporary.unlink(missing_ok=True)
