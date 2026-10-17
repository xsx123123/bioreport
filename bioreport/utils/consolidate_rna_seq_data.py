#!/usr/bin/env python3
"""Consolidate RNA-seq data and generate AI interpretation reports."""

import os
import csv
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable
from loguru import logger


from bioreport.config import load_config, resolve_path
from bioreport.utils.report_utils import get_comparisons_from_csv, get_file_path

# -----------------------------------------------------------------------------
# Configuration & Constants
# -----------------------------------------------------------------------------

# Dynamic path resolution
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"

# Default paths
DEFAULT_OUTPUT_PATH = DATA_DIR / "consolidated_rna_seq_data.txt"
DEFAULT_PROMPT_PATH = SCRIPT_DIR / "prompt.txt"
PROJECT_SUMMARY_PATH = DATA_DIR / "project_summary.json"
DEFAULT_REPORT_DIR = DATA_DIR / "ai_reports"


# -----------------------------------------------------------------------------
# Logging & Utilities
# -----------------------------------------------------------------------------


def setup_logging(verbose: bool = False):
    """Configure the shared CLI log format for standalone callers."""
    from bioreport.cli import setup_logging as configure

    configure()


def safe_resolve_path(path_str: str, config: Dict[str, Any] = None) -> Optional[Path]:
    """
    Safely resolve path relative to the data directory.
    Handles paths starting with '../data/' by mapping them to DATA_DIR.
    If a unified config is provided, uses resolve_path() from config_loader.
    """
    if not path_str:
        return None
    
    path_str = str(path_str)
    
    # Prefer the new config-aware resolver when a config is available.
    if config is not None:
        resolved = resolve_path(config, path_str)
        logger.debug(f"Resolved path via config: {path_str} -> {resolved}")
        return resolved
    
    # Legacy fallback
    if path_str.startswith('../data/'):
        relative_part = path_str.replace('../data/', '', 1)
        resolved_path = DATA_DIR / relative_part
    else:
        resolved_path = Path(path_str).resolve()
    
    logger.debug(f"Resolved path: {path_str} -> {resolved_path}")
    return resolved_path


def read_file_content(file_path: Path) -> str:
    """Read full content of a text file."""
    if not file_path.exists():
        logger.warning(f"File not found: {file_path}")
        return ""
    try:
        return file_path.read_text(encoding='utf-8')
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
        return ""


def csv_to_markdown_table(
    file_path: Path, 
    delimiter: str = '\t', 
    max_rows: Optional[int] = None,
    exclude_columns: Optional[List[str]] = None,
    filter_rows_func: Optional[Callable[[List[str]], bool]] = None
) -> str:
    """
    Read a CSV/TSV file and convert it to a Markdown table string.
    """
    if not file_path.exists():
        logger.warning(f"File not found for table conversion: {file_path}")
        return ""

    try:
        with open(file_path, 'r', encoding='utf-8', newline='') as f:
            # Auto-detect dialect if possible, otherwise fallback to provided delimiter
            try:
                sample = f.read(1024)
                f.seek(0)
                dialect = csv.Sniffer().sniff(sample, delimiters=[delimiter, ','])
                reader = csv.reader(f, dialect)
            except csv.Error:
                f.seek(0)
                reader = csv.reader(f, delimiter=delimiter)

            rows = list(reader)

        if not rows:
            return "*Empty file*"

        header = rows[0]
        data_rows = rows[1:]

        # 1. Row Filtering (Pre-limit)
        if filter_rows_func:
            data_rows = [row for row in data_rows if filter_rows_func(row)]

        if max_rows is not None:
            data_rows = data_rows[:max_rows]

        # 2. Column Exclusion
        if exclude_columns:
            # Identify indices to keep
            keep_indices = [i for i, col in enumerate(header) if col not in exclude_columns]
            
            # Update header
            header = [header[i] for i in keep_indices]
            
            # Update data rows
            new_data_rows = []
            for row in data_rows:
                # Handle rows that might differ in length, though csv reader handles this mostly
                # We simply grab indices if they exist
                new_row = [row[i] for i in keep_indices if i < len(row)]
                new_data_rows.append(new_row)
            data_rows = new_data_rows

        # Markdown Table Construction
        # 1. Header
        md_lines = []
        md_lines.append("| " + " | ".join(header) + " |")
        # 2. Separator
        md_lines.append("| " + " | ".join(["---"] * len(header)) + " |")
        # 3. Data
        for row in data_rows:
            # Handle rows that might be shorter than header
            padded_row = row + [""] * (len(header) - len(row))
            md_lines.append("| " + " | ".join(padded_row) + " |")

        return "\n".join(md_lines)

    except Exception as e:
        logger.error(f"Error converting {file_path} to markdown: {e}")
        return f"Error reading table: {e}"


# -----------------------------------------------------------------------------
# Subcommand: Generate (Consolidate Data)
# -----------------------------------------------------------------------------

def selected_result_files(config, directory, suffix, comparisons=None, required=False):
    files_map = config.get('files', {})
    if comparisons is None:
        names = {key for key in files_map if key.endswith(suffix)}
        if directory and directory.is_dir():
            names.update(path.name for path in directory.glob(f'*{suffix}'))
        keys = sorted(names)
    else:
        keys = [f'{comparison}{suffix}' for comparison in comparisons]

    if not directory and not any(key in files_map for key in keys):
        return []

    selected = []
    for key in keys:
        path = get_file_path(config, key, local_base_dir=str(directory or ''))
        if path and Path(path).is_file():
            selected.append(Path(path))
        elif key in files_map or required:
            raise FileNotFoundError(f'Result file is missing: {path or key}')
    return selected

def run_generate(
    output_path: Path,
    deg_limit: int,
    enrichment_limit: int,
    prompt_path: Optional[Path],
    project_summary_path: Optional[Path],
    verbose: bool
):
    """
    Consolidate RNA-seq data into a text file.
    """

    logger.info("Starting RNA-seq data consolidation")

    # 1. Load Project Summary (YAML or legacy JSON)
    target_summary_path = project_summary_path if project_summary_path else PROJECT_SUMMARY_PATH

    logger.info("Loading project summary from {}", target_summary_path)
    try:
        project_summary = load_config(target_summary_path)
    except Exception as e:
        logger.error(f"Error parsing project summary: {e}")
        return
        

    # 2. Extract Data
    project_meta = project_summary.get('project', project_summary.get('project_meta', {}))
    stats = project_summary.get('stats', {})

    input_files = project_summary.get('input_files', {})
    config = project_summary

    output_lines = []

    # -- Header --
    output_lines.append("# RNA-seq Analysis Summary\n")

    # -- Project Info --
    output_lines.append("## 1. Project Information\n")
    for key, val in project_meta.items():
        output_lines.append(f"- **{key.replace('_', ' ').title()}**: {val}")
    output_lines.append("\n")
    
    output_lines.append("## 2. Analysis Statistics\n")
    output_lines.append(f"- **Total Samples**: {stats.get('total_samples', 'N/A')}")
    output_lines.append(f"- **Groups**: {stats.get('group_count', 'N/A')}")
    output_lines.append("\n")

    # -- FASTP Stats --
    fastp_path = safe_resolve_path(input_files.get('fastp_stats_file'), config)
    if fastp_path and fastp_path.exists():
        output_lines.append("## 3. QC: FASTP Trimming Statistics\n")
        output_lines.append(csv_to_markdown_table(fastp_path, delimiter='\t', max_rows=10))
        output_lines.append("\n")

    # -- Mapping Stats --
    mapping_path = safe_resolve_path(input_files.get('mapping_file'), config)
    if mapping_path and mapping_path.exists():
        output_lines.append("## 4. QC: Mapping Statistics\n")
        
        # Filter function: Keep only clean sample names (exclude . and _stats)
        def clean_samples_filter(row: List[str]) -> bool:
            if not row:
                return False
            sample_name = row[0]
            return '.' not in sample_name and '_stats' not in sample_name

        output_lines.append(csv_to_markdown_table(
            mapping_path, 
            delimiter='\t', 
            max_rows=10, 
            filter_rows_func=clean_samples_filter
        ))
        output_lines.append("\n")

    # -- Expression (TPM) --
    tpm_path = safe_resolve_path(input_files.get('tpm_file'), config)
    if tpm_path and tpm_path.exists():
        output_lines.append("## 5. Expression Levels (TPM - Preview)\n")
        output_lines.append(csv_to_markdown_table(tpm_path, delimiter='\t', max_rows=10))
        output_lines.append("\n")

    # -- Contrasts --
    contrasts_path = safe_resolve_path(input_files.get('contrasts_file'), config)
    comparisons = get_comparisons_from_csv(contrasts_path) if contrasts_path and contrasts_path.exists() else None
    if contrasts_path and contrasts_path.exists():
        output_lines.append("## 6. Experimental Contrasts\n")
        output_lines.append(csv_to_markdown_table(contrasts_path, delimiter=',')) # Usually CSV
        output_lines.append("\n")

    # -- Differential Expression --
    deg_dir = safe_resolve_path(input_files.get('deg_dir'), config)
    for target_deg in selected_result_files(config, deg_dir, '_DEG.csv', comparisons, required=bool(comparisons)):
        output_lines.append(f"## 7. Differential Expression ({target_deg.stem})\n")
        output_lines.append(f"Showing top {deg_limit} genes:\n")
        output_lines.append(csv_to_markdown_table(target_deg, delimiter=',', max_rows=deg_limit))
        output_lines.append("\n")

    # -- Enrichment --
    enrichment_dir = safe_resolve_path(input_files.get('enrichment_dir'), config)
    enrichment_files = [
        (suffix, selected_result_files(config, enrichment_dir, suffix, comparisons))
        for suffix in ("_UP.csv", "_DOWN.csv")
    ]
    if any(files for _, files in enrichment_files):
        output_lines.append("## 8. Enrichment Analysis (Top Terms)\n")
        
        # Check for UP and DOWN files
        for suffix, files in enrichment_files:
            for f in files:
                direction = "Upregulated" if "UP" in suffix else "Downregulated"
                output_lines.append(f"### {direction} Genes Enrichment ({f.stem})\n")
                output_lines.append(csv_to_markdown_table(
                    f,
                    delimiter=',',
                    max_rows=enrichment_limit,
                    exclude_columns=['geneID']
                ))
                output_lines.append("\n")

    # 3. Write Output
    final_content = []
    
    # Prepend prompt if exists
    target_prompt_path = prompt_path if prompt_path else DEFAULT_PROMPT_PATH
    if target_prompt_path and target_prompt_path.exists():
        prompt_content = read_file_content(target_prompt_path)
        if prompt_content:
            final_content.append(prompt_content)
            final_content.append("\n\n---\n\n")

    final_content.extend(output_lines)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save Consolidated Data
        full_text = "\n".join(final_content)
        output_path.write_text(full_text, encoding='utf-8')
        
        logger.info(f"Consolidated data written to {output_path}")
        
    except Exception as e:
        logger.error(f"Failed to write output: {e}")


# -----------------------------------------------------------------------------
# Subcommand: Report (Generate AI Report)
# -----------------------------------------------------------------------------

def run_report(
    input_path: Path,
    output_dir: Path,
    model: Optional[str],
    temperature: float,
    provider: str,
    verbose: bool,
    config: Optional[Dict[str, Any]] = None,
):
    """
    Generate AI interpretation report from the consolidated text file.
    """

    logger.info("Starting AI Report Generation")

    if not input_path.exists():
        logger.error(f"Error: Input file not found at {input_path}")
        return

    # 1. Read Input
    try:
        input_text = input_path.read_text(encoding='utf-8')
        logger.info(f"Read input file: {input_path} ({len(input_text)} chars)")
    except Exception as e:
        logger.error(f"Error reading input file: {e}")
        return

    # 2. Initialize AI Interpreter (lazy import so `generate` works without AI deps)
    try:
        from bioreport.ai import AIInterpreter
        interpreter_kwargs = {"model": model, "provider": provider}
        if config:
            interpreter_kwargs["config"] = config
        interpreter = AIInterpreter(**interpreter_kwargs) if model else AIInterpreter(provider=provider, **({"config": config} if config else {}))
    except Exception as e:
        logger.error(f"Error initializing AI Interpreter: {e}")
        return

    # 3. Call AI
    logger.info("Sending data to AI model... (This may take a minute)")
    
    try:
        system_prompt = "You are a helpful expert bioinformatics assistant. You are analyzing RNA-seq data."
        user_content = [{"type": "text", "text": input_text}]
        trace_id = f"cli-report-{os.getpid()}"
        
        response = interpreter.execute_inference(
            system_prompt=system_prompt,
            user_content=user_content,
            trace_id=trace_id,
            temperature=temperature
        )
        
        # 4. Save Report
        output_dir.mkdir(parents=True, exist_ok=True)
        report_file = output_dir / "AI_Interpretation_Report.md"
        
        # Verify and extract content (removes XML tags if present)
        final_report_content = interpreter._verify_and_extract_content(response.content)
        
        report_file.write_text(final_report_content, encoding='utf-8')
        
        logger.info(f"AI Report generated: {report_file}")
        
        # Show cost if available
        if hasattr(interpreter, '_calculate_cost'):
             cost = interpreter._calculate_cost(response)
             logger.info(f"Estimated Cost: ¥{cost}")

    except Exception as e:
        logger.error(f"AI Report generation failed: {e}")
