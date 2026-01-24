#!/usr/bin/env python3
"""
Consolidate RNA-seq analysis data from JSON and other sources into a text format for LLM interpretation.
Optimized with rich, argparse, and loguru for better user experience and control.
"""

import json
import os
import argparse
from pathlib import Path
from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel


def setup_logging(verbose: bool = False):
    """Configure loguru logging."""
    logger.remove()  # Remove default handler
    if verbose:
        logger.add(
            "consolidate_rna_seq_data.log",
            level="DEBUG",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
            rotation="10 MB"
        )
        logger.info("Verbose logging enabled")
    else:
        logger.add(
            "consolidate_rna_seq_data.log",
            level="INFO",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
            rotation="10 MB"
        )


def read_prompt_file(prompt_path: str) -> str:
    """Read the prompt file content."""
    if not os.path.exists(prompt_path):
        logger.warning(f"Prompt file not found: {prompt_path}. Skipping prompt prepending.")
        return ""

    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt_content = f.read()
        logger.debug(f"Successfully read prompt file: {prompt_path}")
        return prompt_content
    except Exception as e:
        logger.error(f"Error reading prompt file {prompt_path}: {e}")
        return ""


def read_project_summary(json_path: str) -> dict:
    """Read and return the project summary data."""
    logger.debug(f"Reading project summary from: {json_path}")
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
        logger.success(f"Successfully loaded project summary from {json_path}")
        return data
    except FileNotFoundError:
        logger.error(f"Project summary file not found: {json_path}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in project summary file: {e}")
        raise


def safe_resolve_path(path_str: str, base_dir: str) -> str:
    """Safely resolve path relative to base directory."""
    if not path_str:
        return ""
    
    # Handle relative paths that start with ../data/
    if path_str.startswith('../data/'):
        resolved_path = path_str.replace('../data/', f'{base_dir}/')
    else:
        resolved_path = str(Path(path_str).resolve())
    
    logger.debug(f"Resolved path: {path_str} -> {resolved_path}")
    return resolved_path


def read_file_lines(file_path: str, max_lines: int = None) -> list:
    """Read lines from a file safely with optional line limit."""
    if not os.path.exists(file_path):
        logger.warning(f"File not found: {file_path}")
        return []
    
    try:
        with open(file_path, 'r') as f:
            if max_lines is not None:
                lines = [f.readline().strip() for _ in range(max_lines)]
                # Read remaining lines if we hit the limit
                remaining = f.readlines()
                if remaining:
                    lines.extend(remaining[:max(0, max_lines - len(lines))])
            else:
                lines = [line.strip() for line in f.readlines()]
        
        logger.debug(f"Read {len(lines)} lines from {file_path}")
        return lines
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")
        return []


def consolidate_data(
    output_path: str,
    deg_limit: int = 10,
    enrichment_limit: int = 5,
    verbose: bool = False,
    prompt_path: str = None
):
    """
    Main function to consolidate RNA-seq data.

    Args:
        output_path: Path to write the consolidated output file
        deg_limit: Maximum number of differentially expressed genes to include
        enrichment_limit: Maximum number of enrichment terms to include per category
        verbose: Enable verbose logging
        prompt_path: Path to the prompt file to prepend to output
    """
    console = Console()
    setup_logging(verbose)

    # Base directory for resolving paths
    base_dir = '/home/jzhang/pipeline/RNAFlow/report/templates/RNA_Project/data'
    project_summary_path = f'{base_dir}/project_summary.json'

    logger.info("Starting RNA-seq data consolidation")
    console.print(Panel("[bold blue]RNA-seq Data Consolidation Tool[/bold blue]", expand=False))

    # Read the prompt file if provided
    prompt_content = ""
    if prompt_path:
        prompt_content = read_prompt_file(prompt_path)
    elif os.path.exists("/home/jzhang/pipeline/RNAFlow/report/templates/RNA_Project/scripts/prompt.txt"):
        prompt_content = read_prompt_file("/home/jzhang/pipeline/RNAFlow/report/templates/RNA_Project/scripts/prompt.txt")

    # Read the project summary JSON
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Loading project summary...", total=None)
        project_summary = read_project_summary(project_summary_path)
        progress.update(task, completed=True)
    
    # Extract project metadata
    project_meta = project_summary.get('project_meta', {})
    stats = project_summary.get('stats', {})
    input_files = project_summary.get('input_files', {})
    
    # Create output text
    output_text = []
    output_text.append("RNA-seq Analysis Summary")
    output_text.append("=" * 50)
    output_text.append("")
    
    # Add project metadata
    output_text.append("Project Information:")
    output_text.append(f"- Client: {project_meta.get('client', 'N/A')}")
    output_text.append(f"- Species: {project_meta.get('species', 'N/A')}")
    output_text.append(f"- Genome Version: {project_meta.get('genome_version', 'N/A')}")
    output_text.append(f"- Pipeline Version: {project_meta.get('pipeline_version', 'N/A')}")
    output_text.append(f"- Analysis Date: {project_meta.get('analysis_date', 'N/A')}")
    output_text.append("")
    
    # Add statistics
    output_text.append("Analysis Statistics:")
    output_text.append(f"- Total Samples: {stats.get('total_samples', 'N/A')}")
    output_text.append(f"- Number of Groups: {stats.get('group_count', 'N/A')}")
    output_text.append("")
    
    # Add input files information
    output_text.append("Input Files and Data Sources:")
    for key, value in input_files.items():
        output_text.append(f"- {key}: {value}")
    output_text.append("")
    
    # Read and add FASTP statistics (trimming results)
    fastp_stats_path = safe_resolve_path(input_files.get('fastp_stats_file', ''), base_dir)
    if os.path.exists(fastp_stats_path):
        output_text.append("FASTP Trimming Statistics:")
        output_text.append("-" * 30)
        fastp_lines = read_file_lines(fastp_stats_path, max_lines=8)
        for i, line in enumerate(fastp_lines):
            output_text.append(line)
            if i == 0:  # Add separator after header
                output_text.append("-" * len(line))
        output_text.append("")
    
    # Read and add mapping statistics
    mapping_file_path = safe_resolve_path(input_files.get('mapping_file', ''), base_dir)
    if os.path.exists(mapping_file_path):
        output_text.append("Mapping Statistics:")
        output_text.append("-" * 20)
        mapping_lines = read_file_lines(mapping_file_path, max_lines=8)
        for i, line in enumerate(mapping_lines):
            output_text.append(line)
            if i == 0:  # Add separator after header
                output_text.append("-" * len(line))
        output_text.append("")
    
    # Read and add TPM values for a few genes (to show expression levels)
    tpm_file_path = safe_resolve_path(input_files.get('tpm_file', ''), base_dir)
    if os.path.exists(tpm_file_path):
        output_text.append("Sample Expression Levels (TPM - top 10 genes):")
        output_text.append("-" * 45)
        tpm_lines = read_file_lines(tpm_file_path, max_lines=11)
        for i, line in enumerate(tpm_lines):
            output_text.append(line)
            if i == 0:  # Add separator after header
                output_text.append("-" * min(len(line), 100))
        output_text.append("")
    
    # Read contrasts information
    contrasts_path = safe_resolve_path(input_files.get('contrasts_file', ''), base_dir)
    if os.path.exists(contrasts_path):
        output_text.append("Contrasts (Differential Expression Comparisons):")
        output_text.append("-" * 55)
        contrasts_lines = read_file_lines(contrasts_path)
        for line in contrasts_lines:
            output_text.append(line)
        output_text.append("")
    
    # Read DEG summary with limit
    deg_dir = safe_resolve_path(input_files.get('deg_dir', ''), base_dir)
    deg_file = os.path.join(deg_dir, '2_vs_1_DEG.csv')
    if os.path.exists(deg_file):
        output_text.append(f"Differential Expression Analysis (2_vs_1 contrast) - Top {deg_limit} genes:")
        output_text.append("-" * 55)
        deg_lines = read_file_lines(deg_file, max_lines=deg_limit + 1)  # Header + limited genes
        for i, line in enumerate(deg_lines):
            output_text.append(line)
            if i == 0:  # Add separator after header
                output_text.append("-" * min(len(line), 100))
        output_text.append("")
    
    # Add enrichment analysis info with limits
    enrichment_dir = safe_resolve_path(input_files.get('enrichment_dir', ''), base_dir)
    down_enrichment_file = os.path.join(enrichment_dir, '2_vs_1_DOWN.csv')
    up_enrichment_file = os.path.join(enrichment_dir, '2_vs_1_UP.csv')
    
    if os.path.exists(down_enrichment_file):
        output_text.append(f"Top Enriched Terms (DOWN in Group 2 vs Group 1) - Top {enrichment_limit} terms:")
        output_text.append("-" * 50)
        down_lines = read_file_lines(down_enrichment_file, max_lines=enrichment_limit + 1)
        for i, line in enumerate(down_lines):
            output_text.append(line)
            if i == 0:  # Add separator after header
                output_text.append("-" * min(len(line), 100))
        output_text.append("")
    
    if os.path.exists(up_enrichment_file):
        output_text.append(f"Top Enriched Terms (UP in Group 2 vs Group 1) - Top {enrichment_limit} terms:")
        output_text.append("-" * 50)
        up_lines = read_file_lines(up_enrichment_file, max_lines=enrichment_limit + 1)
        for i, line in enumerate(up_lines):
            output_text.append(line)
            if i == 0:  # Add separator after header
                output_text.append("-" * min(len(line), 100))
        output_text.append("")
    
    # Write consolidated data to output file (with prompt prepended if available)
    try:
        final_content = []
        if prompt_content:
            final_content.append(prompt_content)
            final_content.append("\n" + "="*50 + "\n")  # Separator between prompt and data

        final_content.extend(output_text)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(final_content))

        logger.success(f"Consolidated RNA-seq data written to {output_path}")
        console.print(f"[green]✓[/green] Consolidated RNA-seq data written to [bold]{output_path}[/bold]")
        if prompt_content:
            console.print(f"[blue]📝[/blue] Prompt content prepended to output")
        console.print(f"[blue]📊[/blue] Total lines in output: {len(final_content)}")
        console.print(f"[blue]🧬[/blue] DEG limit: {deg_limit} genes")
        console.print(f"[blue]📈[/blue] Enrichment limit: {enrichment_limit} terms per category")
    except Exception as e:
        logger.error(f"Error writing output file: {e}")
        console.print(f"[red]✗ Error writing output file: {e}[/red]")
        raise


def main():
    """Parse command line arguments and run the consolidation."""
    parser = argparse.ArgumentParser(
        description="Consolidate RNA-seq analysis data for LLM interpretation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --deg-limit 20 --enrichment-limit 10
  %(prog)s --output /path/to/custom_output.txt --verbose
  %(prog)s --deg-limit 5 --enrichment-limit 3 --verbose
  %(prog)s --prompt-path /path/to/custom_prompt.txt
        """
    )

    parser.add_argument(
        '--output',
        '-o',
        default='/home/jzhang/pipeline/RNAFlow/report/templates/RNA_Project/data/consolidated_rna_seq_data.txt',
        help='Output file path (default: consolidated_rna_seq_data.txt in data directory)'
    )

    parser.add_argument(
        '--deg-limit',
        '-d',
        type=int,
        default=10,
        help='Maximum number of differentially expressed genes to include (default: 10)'
    )

    parser.add_argument(
        '--enrichment-limit',
        '-e',
        type=int,
        default=5,
        help='Maximum number of enrichment terms per category to include (default: 5)'
    )

    parser.add_argument(
        '--prompt-path',
        '-p',
        help='Path to custom prompt file to prepend to output (default: scripts/prompt.txt)'
    )

    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Enable verbose logging to file'
    )

    args = parser.parse_args()

    # Validate arguments
    if args.deg_limit <= 0:
        parser.error("--deg-limit must be a positive integer")
    if args.enrichment_limit <= 0:
        parser.error("--enrichment-limit must be a positive integer")

    consolidate_data(
        output_path=args.output,
        deg_limit=args.deg_limit,
        enrichment_limit=args.enrichment_limit,
        verbose=args.verbose,
        prompt_path=args.prompt_path
    )


if __name__ == "__main__":
    main()