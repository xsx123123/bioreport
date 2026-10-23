#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 分析流程封装模块。
"""

import os
import shutil
import inspect
import re
import subprocess
import pandas as pd
from pathlib import Path
from typing import Any, Dict

from loguru import logger


def _clean_ai_markdown(content: str) -> str:
    """Keep model output embeddable inside an existing QMD document."""
    content = content.strip()
    # Some providers emit the requested XML wrapper only partially.  An
    # unmatched raw HTML tag makes Pandoc/Typst treat the rest of the runtime
    # Markdown output as HTML, which leaves the visible card with no body.
    content = re.sub(r"</?bio_report>", "", content, flags=re.IGNORECASE)
    # Remove any other raw HTML wrapper emitted by a provider.  Such tags are
    # interpreted by Pandoc as literal HTML and can hide following Markdown.
    content = re.sub(r"<\/?[A-Za-z][^>]*>", "", content)
    # A model can also return a nested callout.  Its closing fence terminates
    # the card created by BioReport and hides the remaining text in PDF.
    content = re.sub(r"(?m)^\s*:::\s*(?:\{[^\n]*\})?\s*$", "", content)
    content = content.strip()
    # Models sometimes add a document-level YAML header. It is invalid when
    # inserted in the middle of the composed report and makes Pandoc fail.
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end >= 0:
            content = content[end + len("\n---"):].lstrip()
    # Card headings must not become document-level PDF bookmarks. Models may
    # emit emoji or heading text whose Unicode form differs after Typst
    # extraction, which makes navigation validation fail.
    content = re.sub(r"(?m)^#{1,6}\s+(.+?)\s*$", r"**\1**", content)
    return content


def run_generate(*args, **kwargs):
    """Lazy-load RNA data consolidation so the core CLI stays lightweight."""
    from .utils.consolidate_rna_seq_data import run_generate as implementation

    return implementation(*args, **kwargs)


def run_report(*args, config=None, **kwargs):
    """Lazy-load AI reporting and its optional scientific dependencies."""
    from .utils.consolidate_rna_seq_data import run_report as implementation

    if config is not None:
        kwargs["config"] = config
    return implementation(*args, **kwargs)


def run_ai_pipeline(
    config: Dict[str, Any],
    config_path: str,
    output_dir: str,
    template_dir: Path,
    execution_id: str | None = None,
    visual_mode: bool = False,
) -> None:
    """
    在 Quarto 渲染前执行数据整合与 AI 解读。

    Args:
        config: 统一配置字典。
        config_path: 配置文件路径（传给数据整合业务函数）。
        output_dir: 报告输出目录（仅用于日志/展示）。
    """
    ai_config = config.get("ai", {})
    if not ai_config.get("enabled", True):
        logger.info("AI interpretation is disabled; skipping the AI workflow.")
        return

    logger.info("Starting AI analysis...")

    # Optional prevalidated module Markdown can be staged for the Quarto
    # module slots. The default configuration has no entries and is unchanged.
    from .modules import stage_module_interpretations
    stage_module_interpretations(
        template_dir,
        ai_config.get("module_interpretations"),
        execution_id=execution_id,
    )

    # Stage per-result interpretations. Each table is sent independently so
    # the resulting note can be rendered directly under that result.
    deg_limit = ai_config.get("deg_limit")
    enrichment_limit = ai_config.get("enrichment_limit")
    prompt_file = ai_config.get("prompt_file")
    if prompt_file:
        if not Path(prompt_file).is_file():
            raise FileNotFoundError(f"AI prompt file is missing: {prompt_file}")
    model = ai_config.get("model")
    provider = ai_config.get("provider", "volcengine")
    if provider != "volcengine" and not model:
        raise ValueError(f"ai.model is required when ai.provider is {provider}")
    if ai_config.get("scope", "results") == "global":
        _run_global_interpretation(config, config_path, template_dir, ai_config, model, provider, deg_limit, enrichment_limit, prompt_file)
    else:
        _run_result_interpretations(config, config_path, template_dir, ai_config, model, provider,
                                    output_dir=Path(output_dir), visual_mode=visual_mode)

    from .i18n import is_rna
    if is_rna(config):
        _stage_english_interpretations(config, template_dir, model, provider)

    logger.info("AI analysis complete.")


def _run_global_interpretation(config, config_path, template_dir, ai_config, model, provider, deg_limit, enrichment_limit, prompt_file):
    """Legacy combined chapter, available only with ai.scope=global."""
    consolidated_file = template_dir / "data" / "consolidated_rna_seq_data.txt"
    run_generate(consolidated_file, int(deg_limit) if deg_limit is not None else 20,
                 int(enrichment_limit) if enrichment_limit is not None else 10,
                 Path(prompt_file) if prompt_file else None, Path(config_path), True)
    if not consolidated_file.exists():
        raise RuntimeError("AI data consolidation completed without producing its text output")
    ai_output_dir = template_dir / "data" / "ai_reports"
    report_args = (consolidated_file, ai_output_dir, str(model) if model else None,
                   float(ai_config.get("temperature", 0.7)), provider, True)
    if "config" in inspect.signature(run_report).parameters:
        run_report(*report_args, config=ai_config)
    else:
        run_report(*report_args)
    generated_report = ai_output_dir / "AI_Interpretation_Report.md"
    if not generated_report.exists():
        raise RuntimeError("AI report command completed without producing its Markdown report")
    shutil.copyfile(generated_report, template_dir / "data" / "consolidated_rna_seq_report.md")


def _run_result_interpretations(config, config_path, template_dir, ai_config, model, provider,
                                *, output_dir: Path | None = None, visual_mode: bool = False):
    """Generate one bounded interpretation for each available DEG/enrichment result."""
    from .ai import AIInterpreter
    from .modules import skipped_modules, stage_module_interpretations

    inputs = config.get("input_files", {})
    data_dir = Path(inputs.get("data_dir") or Path(config_path).resolve().parent)
    def input_path(key):
        value = inputs.get(key)
        if not value:
            return None
        path = Path(value)
        return path if path.is_absolute() else data_dir / path

    results = []
    visual_files = _visual_result_files(output_dir, template_dir) if visual_mode else {}
    # Fixed report blocks use the exact same evidence files as their tables
    # and figures. They receive independent cards just like comparisons.
    fixed_inputs = [
        ("rna.qc.fastp__table", "fastp 过滤前后统计表", "fastp_stats_file"),
        ("rna.qc.fastp__figure", "fastp 质控汇总图", "fastp_report_dir"),
        ("rna.qc.screen__R1", "FastQ Screen R1", "fastq_screen_r1_dir"),
        ("rna.qc.screen__R2", "FastQ Screen R2", "fastq_screen_r2_dir"),
        ("rna.qc.qualimap__figure", "QualiMap 比对质控", "qualimap_dir"),
        ("rna.qc.star__figure", "STAR 比对统计", "qualimap_dir"),
        ("rna.results.samples__pca", "样本 PCA 图", "tpm_file"),
        ("rna.results.samples__distribution", "样本表达分布图", "tpm_file"),
        ("rna.results.matrix__table", "基因表达矩阵预览", "tpm_file"),
        ("rna.results.heatmap__figure", "基因表达热图", "tpm_file"),
    ]
    skipped = skipped_modules(config, [item[0].split("__", 1)[0] for item in fixed_inputs])
    for logical_id, label, input_key in fixed_inputs:
        if logical_id.split("__", 1)[0] in skipped:
            continue
        source = input_path(input_key)
        if not source:
            continue
        paths = sorted(source.rglob("*") if source.is_dir() else [source])
        chunks = []
        for item in paths:
            if item.is_file() and not item.is_symlink():
                try:
                    chunks.append(f"### {item.name}\n{item.read_text(encoding='utf-8', errors='replace')[:12000]}")
                except OSError:
                    pass
            if sum(len(chunk) for chunk in chunks) >= 24000:
                break
        if chunks:
            results.append((logical_id, label, label, None, "\n\n".join(chunks)[:24000], visual_files.get(logical_id)))
    for key, suffix, kind in (("deg_dir", "_DEG.csv", "DEG"),):
        root = input_path(key)
        if not root or not root.is_dir():
            continue
        for path in sorted(root.glob(f"*{suffix}")):
            name = path.name[:-len(suffix)]
            comparison, direction = name, None
            logical_id = f"rna.results.deg__{comparison}"
            try:
                frame = pd.read_csv(path, sep=None, engine="python")
            except Exception as exc:
                logger.warning("Skipping unreadable AI result {}: {}", path, exc)
                continue
            limit = int(ai_config.get("result_rows", 30 if kind == "DEG" else 20))
            evidence = frame.head(max(1, min(limit, 100))).to_csv(index=False)
            results.append((logical_id, kind, comparison, direction, evidence, visual_files.get(logical_id)))
    from .enrichment import enrichment_results
    for result in enrichment_results(config):
        if result.status != 'available':
            continue
        frame = result.frame(validate=False)
        limit = max(1, min(int(ai_config.get('result_rows', 20)), 100))
        evidence = frame.head(limit).to_csv(index=False)
        results.append((result.result_id, f'{result.database} 富集'.strip(), result.comparison,
                        result.direction, evidence, visual_files.get(result.result_id)))
    # Result cards should be short factual annotations. Disable expensive
    # reasoning by default and cap output unless the user explicitly opts out.
    result_ai_config = dict(ai_config)
    result_ai_config.setdefault("max_output_tokens", 800)
    interpreter = AIInterpreter(model=model, provider=provider, config=result_ai_config)
    prompt_file = ai_config.get("prompt_file")
    if prompt_file:
        system_prompt = Path(prompt_file).read_text(encoding="utf-8")
    else:
        system_prompt = (
            "你是严谨的 RNA-seq 生物信息学分析助手。只根据给定结果解读，区分统计证据与假设；"
            "不得声称因果或临床意义，指出阈值/字段限制。输出简洁中文 Markdown，作为结果下方的 AI 解读卡片。"
            "只输出正文，不要输出 <bio_report>、HTML 标签、::: Callout、JSON、代码块或文档级 YAML。"
        )
    interpretations = {}
    for logical_id, kind, comparison, direction, evidence, visual_file in results:
        label = f"{kind}: {comparison}" + (f" {direction}" if direction else "")
        user_content = []
        if visual_file:
            encoded = interpreter._encode_file(str(visual_file))
            if encoded:
                user_content.append({"type": "image_url", "image_url": {"url": encoded}})
        user_content.append({"type": "text", "text": f"结果类型：{label}\n请结合图像（如已提供）和以下结构化证据，概述主要发现、证据及限制：\n\n{evidence}"})
        response = interpreter.execute_inference(
            system_prompt=system_prompt,
            user_content=user_content,
            trace_id=f"result-{re.sub(r'[^A-Za-z0-9_-]', '-', logical_id)}",
            thinking=False,
            temperature=float(ai_config.get("temperature", 0.3)),
        )
        raw_content = response.content or ""
        if "<bio_report>" in raw_content and "</bio_report>" in raw_content:
            raw_content = interpreter._verify_and_extract_content(raw_content)
        content = _clean_ai_markdown(raw_content)
        visible_content = re.sub(r"[\s`*_#:\-]", "", content)
        if not visible_content:
            # Keep the card useful even when a provider returns only wrapper
            # tags or an empty vision response.  The evidence is deterministic
            # and clearly labeled as fallback, so it is not mistaken for an
            # AI-generated conclusion.
            fallback = re.sub(r"\s+", " ", evidence).strip()
            content = (
                "模型未返回可显示的 AI 正文。以下为本结果的结构化证据摘要：\n\n"
                + fallback[:1600]
            )
        logger.debug(
            "[{}] AI content sanitized | raw_chars={} final_chars={}",
            logical_id,
            len(raw_content),
            len(content),
        )
        interpretations[logical_id] = f'::: {{.callout-note .ai-result-card appearance="minimal"}}\n\n**AI 解读**\n\n{content}\n\n:::'
    stage_module_interpretations(template_dir, interpretations, execution_id=config.get("execution_id"))


def _visual_result_files(output_dir: Path | None, template_dir: Path) -> dict[str, Path]:
    """Map rendered PDF figure artifacts to result IDs using block captions."""
    if output_dir is None:
        return {}
    manifest = output_dir / "report-blocks-pdf.jsonl"
    if not manifest.is_file():
        logger.warning("Skipping visual AI: PDF block manifest is missing: %s", manifest)
        return {}
    try:
        import json
        blocks = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception as exc:
        logger.warning("Skipping visual AI: could not read PDF block manifest: %s", exc)
        return {}
    figures = []
    for block in blocks:
        if block.get("type") == "figure":
            figures.append(block)
        elif block.get("type") == "figure_group":
            figures.extend(block.get("figures", []))
    candidates = {}
    for figure in figures:
        raw = figure.get("path")
        if not raw:
            continue
        paths = [template_dir / "qmd" / raw, template_dir / raw, output_dir / raw, output_dir / "supplementary" / Path(raw).name]
        source = next((path for path in paths if path.is_file() and not path.is_symlink()), None)
        if source is None:
            continue
        evidence = figure.get('content') or {}
        if evidence.get('kind') == 'enrichment':
            database = evidence.get('database', '')
            prefix = f'{database}__' if database else ''
            logical_id = f"rna.results.enrichment__{prefix}{evidence['comparison']}_{evidence['direction']}"
            candidates.setdefault('by_id', {})[logical_id] = source
        caption = str(figure.get("caption", ""))
        candidates.setdefault("all", []).append((caption, source))
    def first(match):
        return next((path for caption, path in candidates.get("all", []) if match(caption)), None)
    mapped = {
        "rna.qc.fastp__figure": first(lambda c: "Fastp:" in c),
        "rna.qc.qualimap__figure": first(lambda c: "QualiMap:" in c),
        "rna.results.samples__pca": first(lambda c: "PCA" in c),
        "rna.results.samples__distribution": first(lambda c: "表达分布" in c),
        "rna.results.heatmap__figure": first(lambda c: "热图" in c),
    }
    screen = [item[1] for item in candidates.get("all", []) if "FastQ Screen:" in item[0]]
    if screen:
        mapped["rna.qc.screen__R1"], mapped["rna.qc.screen__R2"] = screen[:2]
    for caption, path in candidates.get("all", []):
        if "差异表达火山图" in caption:
            match = re.search(r"([A-Za-z0-9.-]+_vs_[A-Za-z0-9.-]+)", caption)
            if match:
                mapped[f"rna.results.deg__{match.group(1)}"] = path
        if "富集分析" in caption:
            match = re.search(r"([A-Za-z0-9.-]+_vs_[A-Za-z0-9.-]+)\s+(上调|下调)", caption)
            if match:
                direction = "UP" if match.group(2) == "上调" else "DOWN"
                mapped[f"rna.results.enrichment__{match.group(1)}_{direction}"] = path
    mapped.update(candidates.get('by_id', {}))
    resolved = {}
    png_dir = template_dir / "data" / "ai_visuals"
    for key, source in mapped.items():
        if source is None:
            continue
        if source.suffix.lower() != ".svg":
            resolved[key] = source
            continue
        png_dir.mkdir(parents=True, exist_ok=True)
        target = png_dir / f"{source.stem}.png"
        try:
            subprocess.run(["convert", "-background", "white", str(source), str(target)],
                           check=True, capture_output=True, text=True, timeout=10)
            resolved[key] = target
            logger.debug("Visual AI image prepared: {} -> {}", source, target)
        except subprocess.TimeoutExpired as exc:
            logger.warning("Visual AI image conversion timed out after {} seconds: {}; using structured evidence", 10, source)
        except (OSError, subprocess.SubprocessError) as exc:
            detail = (exc.stderr or str(exc)).strip() if hasattr(exc, "stderr") else str(exc)
            logger.warning("Visual AI could not convert image {}: {}; using structured evidence", source, detail)
    return resolved


def _stage_english_interpretations(config, template_dir, model, provider):
    """Translate reviewed source notes once; keep the same evidence and claims."""
    from .ai import AIInterpreter
    from .modules import stage_module_interpretations
    data = template_dir / "data"
    sources = [(p, None) for p in sorted((data / "ai_interpretations").glob("*.md"))]
    for name in ("consolidated_rna_seq_report", "module_interpretations"):
        path = data / (name + ".md")
        if path.is_file():
            sources.append((path, data / (name + ".en.md")))
    translated = {}
    interpreter = None
    for source, destination in sources:
        if source.is_symlink():
            raise ValueError("AI_INTERPRETATION_FILE_SYMLINK")
        content = source.read_text(encoding="utf-8")
        if re.search(r"[\u4e00-\u9fff]", content):
            if interpreter is None:
                options = dict(config.get("ai", {}))
                options.setdefault("max_output_tokens", 4000)
                interpreter = AIInterpreter(model=model, provider=provider, config=options)
            response = interpreter.execute_inference(
                system_prompt="Translate the supplied RNA-seq interpretation into English. Preserve all numbers, gene and sample identifiers, comparisons, uncertainty, limitations and Markdown structure. Do not add analysis or claims. Return only Markdown; no HTML, code fences or document YAML.",
                user_content=[{"type": "text", "text": content}],
                trace_id="translation-en-" + source.stem, thinking=False, temperature=0,
            )
            content = _clean_ai_markdown(response.content or "")
            if not content:
                raise RuntimeError("Empty English AI translation: " + source.name)
            if destination is None:
                content = '::: {.callout-note .ai-result-card appearance="minimal"}\n\n' + content + '\n\n:::'
        if destination is None:
            translated[source.stem] = content
        else:
            if destination.is_symlink():
                raise ValueError("AI_INTERPRETATION_FILE_SYMLINK")
            destination.write_text(content, encoding="utf-8")
    stage_module_interpretations(template_dir, translated, execution_id=config.get("execution_id"), language="en")
