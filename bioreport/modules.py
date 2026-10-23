"""Compose report documents from reusable Quarto content modules."""

from pathlib import Path
import json
import hashlib
import re
import shutil
from html import escape
from collections.abc import Mapping

import bioreport
import yaml
from jinja2 import Template

from .registry import get_registry


MODULES = {
    "ai": ("AI.qmd", "AI 解读"),
    "about": ("about.qmd", "关于"),
    "faq": ("faq.qmd", "常见问题"),
    "license": ("license.qmd", "许可"),
    "trademark": ("trademark.qmd", "商标"),
    "provenance": ("provenance.qmd", "溯源信息"),
}

# Bootstrap icons (without the bi- prefix) shown before each navbar entry.
# Built-in pages ship with the core engine; omics modules declare their own
# icon on the Module contract, with category fallbacks below.
BUILTIN_PAGE_ICONS = {
    "about": "info-circle",
    "ai": "stars",
    "faq": "question-circle",
    "license": "file-earmark-text",
    "trademark": "award",
    "provenance": "shield-lock",
}
CATEGORY_PAGE_ICONS = {
    "index": "house",
    "workflow": "signpost-split",
    "qc": "clipboard2-check",
    "results": "bar-chart",
}
DEFAULT_PAGE_ICON = "file-text"


def _page_icon(chapter_id: str, registered: dict) -> str:
    module = registered.get(chapter_id)
    if module is not None:
        if module.icon:
            return module.icon
        if module.category in CATEGORY_PAGE_ICONS:
            return CATEGORY_PAGE_ICONS[module.category]
    return BUILTIN_PAGE_ICONS.get(chapter_id, DEFAULT_PAGE_ICON)

def _canonical(module_id: str) -> str:
    return get_registry().canonical(module_id)


def _report_footer(template_dir: Path, english: bool = False) -> str:
    """构建真实 HTML 页脚元素，内容取自自动生成的溯源信息。

    provenance.json 缺失时回退到引擎当前版本，保证旧流程不受影响。
    """
    version = bioreport.__version__
    generated_at = ""
    provenance_path = template_dir / "qmd" / "provenance.json"
    try:
        data = json.loads(provenance_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            version = data.get("bioreport_version") or version
            generated_at = data.get("generated_at") or ""
    except Exception:
        pass
    text = f"Powered by BioReport v{version}"
    if generated_at:
        text += f" · {'Generated at' if english else '生成于'} {generated_at}"
    return (
        '```{=html}\n'
        f'<footer class="report-footer">{escape(text)}</footer>\n'
        '```\n'
    )


def output_formats(config: dict) -> list[str]:
    requested = config.get("report", {}).get("output_format", "html")
    formats = [requested] if isinstance(requested, str) else requested
    if not isinstance(formats, list) or not formats or any(
        value not in ("html", "pdf") for value in formats
    ):
        raise ValueError("report.output_format must be html, pdf, or a list of them")
    return list(dict.fromkeys(formats))


def select_report_omics(config: dict, requested: str | None = None) -> str | None:
    """Resolve one template package and scope module aliases before validation."""
    registry = get_registry()
    registered = registry.modules
    report = config.setdefault("report", {})
    modules = report.get("modules", report.get("sections"))
    custom = report.get("module_definitions", {})
    if not isinstance(custom, dict):
        raise ValueError("report.module_definitions must be an object")
    if "modules" in report or "sections" in report:
        if not isinstance(modules, list) or not modules:
            raise ValueError("report.modules must be a nonempty list of module IDs")
        if any(not isinstance(module, str) for module in modules):
            raise ValueError("report.modules must contain string module IDs")
    shared_modules = MODULES

    hints = set()
    if requested:
        hints.add(requested)
    report_type = {"rna-seq": "rna", "rna": "rna", "gwas": "gwas"}.get(report.get("type"))
    if report_type:
        hints.add(report_type)
    for module_id in modules or ():
        if module_id in shared_modules or module_id in custom:
            continue
        if module_id in registered:
            hints.add(module_id.split(".", 1)[0])
        else:
            # A unique short name (e.g. results.manhattan) also identifies
            # its package; common names like index need the report context.
            owners = {name.split(".", 1)[0] for name in registered
                      if name.split(".", 1)[1] == module_id}
            if len(owners) == 1:
                hints.update(owners)
    if len(hints) > 1:
        raise ValueError(
            "Conflicting omics selection: " + ", ".join(sorted(hints))
            + ". --omics, report.type, and report.modules/sections must select the same omics; "
            "mixed-omics reports are not supported."
        )
    # A report containing only shared/custom pages needs no omics overlay.
    if not hints and modules is not None and all(
        module in shared_modules or module in custom for module in modules
    ):
        return None
    omics_name = next(iter(hints), "rna")
    if modules is None:
        modules = [module for module in registry.default_modules
                   if module.startswith(f"{omics_name}.")]
        modules += ["provenance", "about"]
    report["modules"] = [
        module if module in registered or module in shared_modules or module in custom
        else f"{omics_name}.{module}"
        for module in modules
    ]
    return omics_name


def selected_modules(config: dict) -> list[str]:
    report = config.get("report", {})
    custom = report.get("module_definitions", {})
    if not isinstance(custom, dict):
        raise ValueError("report.module_definitions must be an object")
    collisions = custom.keys() & MODULES.keys()
    if collisions:
        raise ValueError(f"Custom module IDs conflict with built-in modules: {', '.join(sorted(collisions))}")
    registry = get_registry()
    # Use the same scoped aliases/defaults in CLI and in Quarto workers that
    # reload the original config. Keep legacy return IDs for compatibility.
    effective = {"report": dict(report)}
    select_report_omics(effective)
    validation_modules = effective["report"].get("modules", report.get("sections", []))
    if config.get("_legacy_format"):
        modules = report.get("modules", report.get("sections", [
            "index", "workflow", "qc", "results", "provenance", "about",
        ]))
    else:
        modules = validation_modules
    if len(validation_modules) != len(set(validation_modules)):
        raise ValueError("report.modules contains duplicate module IDs")
    registered = registry.modules
    parents = {module_id: module.parent for module_id, module in registered.items()}
    for parent in {value for value in parents.values() if value}:
        if parent in validation_modules and any(parents.get(module) == parent for module in validation_modules):
            raise ValueError(f"Use either {parent} or individual child modules")
    if report.get("layout") == "website" and any(parents.get(module) or module in custom for module in validation_modules):
        raise ValueError("Individual and custom modules require report.layout: single")
    if report.get("layout") == "website" and not any(
        module in registered and registered[module].category == "index" for module in validation_modules
    ):
        raise ValueError("Website reports require the index module")
    unknown = set(validation_modules) - MODULES.keys() - registered.keys() - custom.keys()
    if unknown:
        raise ValueError(f"Unknown report modules: {', '.join(sorted(unknown))}")
    for module in validation_modules:
        if module not in MODULES and module not in custom and module not in registered:
            raise ValueError(f"Module is not registered: {module}")
    ai_settings = config.get("ai", {})
    if ai_settings.get("scope", "results") != "global":
        modules = [module for module in modules if module != "ai"]
    if not ai_settings.get("enabled", True):
        modules = [module for module in modules if module != "ai"]
        if not modules:
            raise ValueError("No report modules remain after disabling AI")
    input_files = config.get("input_files", {})
    required_inputs = []
    optional_inputs = []
    for module in validation_modules:
        if module in custom:
            required_inputs.extend(custom[module].get("required_inputs", ()))
        elif module in MODULES:
            required_inputs.extend(())
        else:
            definition = registered[module]
            if not definition.skip_if_missing_inputs:
                required_inputs.extend(definition.required_inputs)
            optional_inputs.extend(definition.optional_inputs)
    from .software import software_records
    alternatives = set()
    if 'software_versions' in config and 'software_versions_file' in required_inputs:
        software_records(config)
        alternatives.add('software_versions_file')
    if config.get('enrichment'):
        alternatives.add('enrichment_dir')
    missing = sorted({key for key in required_inputs if not input_files.get(key) and key not in alternatives})
    optional_inputs = [key for key in optional_inputs if key in input_files]
    if missing:
        raise ValueError(f"Selected modules require input_files: {', '.join(missing)}")
    return modules


def skipped_modules(config: dict, module_ids: list[str] | None = None) -> dict[str, list[str]]:
    """Return missing inputs for selected, skippable leaf modules.

    Composite modules keep their available children and replace only missing
    children with a notice. Paths have already been resolved by load_config.
    """
    registry = get_registry()
    selected = {registry.canonical(m) for m in (
        selected_modules(config) if module_ids is None else module_ids
    )}
    registered = registry.modules
    parents = {m.parent for m in registered.values() if m.parent}
    inputs = config.get("input_files", {})
    base = Path(config.get("_path_base") or inputs.get("data_dir") or ".")
    skipped = {}
    for module in registered.values():
        if not module.skip_if_missing_inputs or module.id in parents:
            continue
        if module.id not in selected and module.parent not in selected:
            continue
        missing = [key for key in module.required_inputs
                   if not inputs.get(key) or not (base / inputs[key]).exists()]
        if missing:
            skipped[module.id] = missing
    return skipped


def _missing_input_notice(missing: list[str], english: bool) -> str:
    keys = ", ".join(f"`{key}`" for key in missing)
    text = (f"Input data is missing; this section was skipped. Missing inputs: {keys}."
            if english else f"输入数据缺失，已跳过本节。缺失输入：{keys}。")
    return f"::: {{.callout-note}}\n{text}\n:::\n"


def _read_module(path: Path) -> tuple[dict, str]:
    source = path.read_text(encoding="utf-8")
    if not source.startswith("---\n"):
        return {}, source
    header, separator, body = source[4:].partition("\n---\n")
    if not separator:
        raise ValueError(f"Unclosed YAML front matter in {path}")
    metadata = yaml.safe_load(header) or {}
    if not isinstance(metadata, dict):
        raise ValueError(f"Invalid YAML front matter in {path}")
    return metadata, body


INCLUDE = re.compile(r"\{\{<\s*include\s+([^\s>]+)\s*>\}\}")


def _expand_includes(
    body: str, qmd_dir: Path, root: Path | None = None, stack: tuple[Path, ...] = (),
    replacements: Mapping[Path, str] | None = None,
) -> str:
    root = root or qmd_dir.resolve()

    def replace(match: re.Match) -> str:
        source = (qmd_dir / match.group(1)).resolve()
        if not source.is_relative_to(root):
            raise ValueError(f"Include escapes the QMD directory: {match.group(1)}")
        if source in stack:
            chain = " -> ".join(str(path) for path in (*stack, source))
            raise ValueError(f"Circular QMD include: {chain}")
        if replacements and source in replacements:
            return replacements[source]
        return _expand_includes(source.read_text(encoding="utf-8"), source.parent, root,
                                (*stack, source), replacements)

    return INCLUDE.sub(replace, body)


def _custom_source(config: dict, module_id: str) -> Path:
    definition = config["report"]["module_definitions"][module_id]
    source = Path(definition["path"])
    if not source.is_absolute():
        base = Path(config["_config_path"]).resolve().parent if "_config_path" in config else Path.cwd()
        source = base / source
    source = source.resolve()
    if source.suffix.lower() != ".qmd" or not source.is_file():
        raise ValueError(f"Custom module {module_id} must refer to an existing .qmd file: {source}")
    return source


def _stage_custom_metadata(metadata: dict, source: Path, template_dir: Path, module_id: str) -> dict:
    staged = metadata.copy()
    target_dir = template_dir / "reference"
    for key in ("bibliography", "csl"):
        if key not in staged:
            continue
        values = staged[key] if isinstance(staged[key], list) else [staged[key]]
        outputs = []
        for value in values:
            original = (source.parent / value).resolve()
            if not original.is_file():
                raise ValueError(f"Custom module {module_id} references missing {key}: {original}")
            target_dir.mkdir(parents=True, exist_ok=True)
            name = re.sub(r"[^A-Za-z0-9.-]", "-", f"{module_id}-{original.name}")
            target = target_dir / name
            shutil.copyfile(original, target)
            outputs.append(f"../reference/{name}")
        staged[key] = outputs if isinstance(staged[key], list) else outputs[0]
    return staged


def _namespace_chunk_labels(body: str, module_id: str, position: int) -> str:
    prefix = f"{re.sub(r'[^A-Za-z0-9-]', '-', module_id)}-{position}"
    labels = {}

    def rename(match: re.Match) -> str:
        label = match.group(3)
        kind, separator, remainder = label.partition("-")
        if separator and kind in {"fig", "tbl", "eq", "lst", "sec"}:
            renamed = f"{kind}-{prefix}-{remainder}"
        else:
            renamed = f"{prefix}-{label}"
        labels[label] = renamed
        return f"{match.group(1)}{match.group(2)}{renamed}{match.group(2)}{match.group(4)}"

    body = re.sub(
        r"(?m)^([ \t]*#\|[ \t]*label:[ \t]*)(['\"]?)([A-Za-z0-9_-]+)\2([ \t]*)$",
        rename,
        body,
    )
    for original, renamed in labels.items():
        body = re.sub(rf"(?<![\w-])@{re.escape(original)}(?![\w-])", f"@{renamed}", body)
    return body


def _module_ai_slot(module_id: str, english: bool = False) -> str:
    """Add a safe no-op-unless-present module interpretation slot to QMD."""
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "-", module_id)
    edition = "/en" if english else ""
    return f'''\n\n```{{python}}\n#| echo: false\n#| warning: false\nfrom pathlib import Path as _BioReportPath\nfrom IPython.display import Markdown as _BioReportMarkdown, display as _BioReportDisplay\n_ai_root = _BioReportPath("../data/ai_interpretations{edition}")\n_ai_files = sorted(_ai_root.glob("{safe_id}__*.md")) + ([_ai_root / "{safe_id}.md"] if (_ai_root / "{safe_id}.md").is_file() else [])\nfor _ai_file in _ai_files:\n    if _ai_file.is_file() and not _ai_file.is_symlink():\n        _BioReportDisplay(_BioReportMarkdown(_ai_file.read_text(encoding="utf-8")))\n```\n'''


def stage_module_interpretations(
    template_dir: Path,
    interpretations: Mapping[str, str] | None,
    *,
    max_bytes: int = 2 * 1024 * 1024,
    execution_id: str | None = None,
    language: str = "zh",
) -> list[Path]:
    """Write optional module Markdown into the Quarto staging tree.

    The writer accepts logical module IDs only; it never treats a caller value
    as a path. Existing symlinks are rejected so a staging configuration cannot
    redirect Quarto to an arbitrary file.
    """
    if interpretations is None:
        interpretations = {}
    if not isinstance(interpretations, Mapping):
        raise ValueError("ai.module_interpretations must be an object")
    data_dir = Path(template_dir) / "data"
    target_dir = data_dir / "ai_interpretations"
    if language not in ("zh", "en"):
        raise ValueError("Invalid interpretation language")
    if target_dir.is_symlink():
        raise ValueError("AI_INTERPRETATION_DIR_SYMLINK")
    if language == "en":
        target_dir = target_dir / "en"
    if any(candidate.is_symlink() for candidate in (data_dir, target_dir)):
        raise ValueError("AI_INTERPRETATION_DIR_SYMLINK")
    target_dir.mkdir(parents=True, exist_ok=True)
    # The directory is owned by this staging writer. Remove only generated
    # Markdown files so a reused staging tree cannot render a previous run's
    # interpretation when the current run has no module output.
    for stale in target_dir.glob("*.md"):
        if stale.is_symlink():
            raise ValueError("AI_INTERPRETATION_FILE_SYMLINK")
        if stale.is_file():
            stale.unlink()
    written: list[Path] = []
    safe_ids: set[str] = set()
    for module_id, content in interpretations.items():
        if not isinstance(module_id, str) or not isinstance(content, str):
            raise ValueError("ai.module_interpretations keys and values must be strings")
        if "\x00" in module_id or "\x00" in content:
            raise ValueError("AI_INTERPRETATION_NUL")
        if re.search(r"<\s*script\b|\{\{<|```\s*\{", content, flags=re.IGNORECASE):
            raise ValueError("AI_INTERPRETATION_UNSAFE_MARKUP")
        safe_id = re.sub(r"[^A-Za-z0-9_.-]", "-", module_id).strip(".")
        if not safe_id:
            raise ValueError("AI_INTERPRETATION_MODULE_ID_INVALID")
        if safe_id in safe_ids:
            raise ValueError("AI_INTERPRETATION_MODULE_ID_COLLISION")
        safe_ids.add(safe_id)
        encoded = content.encode("utf-8")
        if len(encoded) > max_bytes:
            raise ValueError("AI_INTERPRETATION_TOO_LARGE")
        destination = target_dir / f"{safe_id}.md"
        if destination.exists() and destination.is_symlink():
            raise ValueError("AI_INTERPRETATION_FILE_SYMLINK")
        destination.write_bytes(encoded)
        written.append(destination)
    manifest_dir = Path(template_dir) / "data" / "ai_reports"
    if manifest_dir.exists() and manifest_dir.is_symlink():
        raise ValueError("AI_INTERPRETATION_MANIFEST_DIR_SYMLINK")
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = manifest_dir / ("ai-interpretation-manifest.en.json" if language == "en" else "ai-interpretation-manifest.json")
    if manifest.is_symlink():
        raise ValueError("AI_INTERPRETATION_MANIFEST_SYMLINK")
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "execution_id": execution_id,
                "artifacts": [
                    {
                        "module_id": path.stem,
                        "path": str(path.relative_to(Path(template_dir) / "data")),
                        "size": path.stat().st_size,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                    for path in written
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return written


def _cover_provenance(template_dir: Path) -> dict:
    """Read the staged provenance so the cover can show the generation date and
    verification state; a missing file degrades to an empty mapping."""
    try:
        data = json.loads((template_dir / "qmd" / "provenance.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _cover_comparisons(config: dict) -> list[str]:
    """Control→Treat 形式的比较组名称；对照表缺失时返回空列表。"""
    path = config.get("input_files", {}).get("contrasts_file")
    if not path:
        return []
    try:
        from .utils.report_utils import get_comparisons_from_csv
        return get_comparisons_from_csv(path)
    except Exception:
        return []


def _cover_pills(config: dict) -> list[str]:
    """实验规模速览胶囊：仅显示样本数与分组数，研究及溯源信息留给面板。

    任一依据缺失时跳过该胶囊，绝不填充示例值。
    """
    pills = []
    sample_file = config.get("input_files", {}).get("sample_file")
    if sample_file:
        try:
            import pandas as pd
            samples = pd.read_csv(sample_file)
            pills.append(f"{len(samples)} Samples")
            group_col = next((c for c in samples if c.lower() == 'group'), None)
            if group_col:
                pills.append(f"{samples[group_col].nunique()} Groups")
        except Exception:
            pass
    return pills


def compose_report(config: dict, template_dir: Path, pdf: bool = False, website: bool = False) -> Path | list[dict]:
    """Compose selected chapters as one document or separate website pages."""
    from .i18n import language, translate
    report = config.get("report", {})
    english = language(config) == "en"
    tr = lambda value: translate(value, language(config))
    metadata = {
        "title": report.get("title", "Report"),
        "lang": report.get("language", "en"),
        "date": "last-modified",
        "execute": {"echo": False, "warning": False},
    }
    sections = []
    cover_block = ""
    from .report.composition import ReportComposition
    composition = ReportComposition()
    language_prelude = "```{python}\n#| label: report-language\nimport os\nos.environ[\"BIOREPORT_LANGUAGE\"] = " + repr("en" if english else "zh") + "\n```\n\n"
    if website:
        language_prelude += "```{python}\nfrom pathlib import Path as _ReportPath\nos.environ['BIOREPORT_SHARED_ASSET_DIR'] = str((_ReportPath.cwd().parent / 'assets').resolve())\nos.environ['BIOREPORT_SHARED_ASSET_URL'] = '../assets'\n```\n\n"
    pages = []
    website_pages = []
    module_ids = selected_modules(config)
    setup_added = set()
    registered = get_registry().modules
    has_rna = any(_canonical(module).startswith("rna.") for module in module_ids)
    has_gwas = any(_canonical(module).startswith("gwas.") for module in module_ids)
    if pdf:
        metadata["filters"] = ["../pdf/layout.lua"]
        from .utils.fonts import MONO_STACK, font_families
        fonts = tuple(report.get('pdf', {}).get('fonts') or font_families())
        style_dir = template_dir / "pdf"
        style_dir.mkdir(exist_ok=True)
        project = config.get("project", {})
        short_name = project.get('short_name') or project.get('project_id') or report.get('title', 'BioReport')
        # Context and shared print helpers also serve custom, non-RNA modules.
        context = '#let report-fonts = (' + ''.join(json.dumps(f, ensure_ascii=False)+',' for f in fonts) + ')\n'
        context += '#let report-mono-fonts = (' + ''.join(
            json.dumps(f, ensure_ascii=False)+',' for f in report.get('pdf', {}).get('mono_fonts') or MONO_STACK
        ) + ')\n'
        context += '#let report-language = ' + json.dumps('en' if english else 'zh') + '\n'
        context += '#let report-project = ' + json.dumps(str(short_name), ensure_ascii=False) + '\n'
        (style_dir / 'print-context.typ').write_text(context, encoding='utf-8')
        metadata['format'] = {'typst': {
            'keep-typ': True,
            'papersize': 'a4', 'fontsize': '10.5pt', 'mainfont': fonts[0],
            'margin': {'x': '20mm', 'y': '22mm'},
            'include-in-header': ['../pdf/print-context.typ', '../pdf/print-style.typ'],
            'include-before-body': '../pdf/print-body.typ',
            'include-after-body': '../pdf/print-observations.typ',
        }}
    if pdf and has_rna:
        metadata["format"]["typst"].update({
            "papersize": "a4", "toc": False, "toc-depth": 2,
            "number-sections": True,
            "section-numbering": "1.1.1",
            "margin": {"x": "20mm", "y": "22mm"},
            "include-in-header": ['../pdf/print-context.typ', '../pdf/print-style.typ', '../pdf/rna-style.typ'],
            "include-before-body": '../pdf/print-body.typ',
        })
        style_dir = template_dir / "pdf"
        style_dir.mkdir(exist_ok=True)
        project = config.get("project", {})
        lines = [report.get("title", "RNA-seq 分析报告"),
                 project.get("client", ""), project.get("species", ""),
                 project.get("genome_version", project.get("genome", "")),
                 project.get("pipeline_version", project.get("software", ""))]
        title = str(lines[0]).replace('PDF', '').strip()
        # 封面在 build_provenance 之后渲染，直接读取溯源结果以保证日期与校验状态就绪。
        provenance = _cover_provenance(template_dir)
        # Presentation only: checksum collection is not trusted hash verification.
        # Keep evidence generation and validation unchanged.
        def clean(value):
            if value is None:
                return ""
            text = str(value).strip()
            return "" if text.lower() in {"none", "null", "undefined"} else text

        pipeline = clean(lines[4])
        report_date = clean(project.get('report_date') or project.get('date'))
        if not report_date and provenance.get('generated_at'):
            report_date = str(provenance['generated_at']).split('T')[0]
        comparisons = _cover_comparisons(config)
        def comparison_name(identifier):
            parts = identifier.split('_vs_', 1)
            if len(parts) != 2:
                return identifier
            return ' vs '.join(f"Group {p}" if p.isdigit() else p for p in parts)

        comparison_text = ("; " if english else "；").join(map(comparison_name, comparisons[:3]))
        if len(comparisons) > 3 or len(comparison_text) > 150:
            examples = comparison_text[:150] + ('…' if len(comparison_text) > 150 else '')
            comparison_text = (
                f"{len(comparisons)} comparisons; examples: {examples}. Full list in the report."
                if english else f"共 {len(comparisons)} 个比较组；示例：{examples}。完整列表见正文。"
            )

        checksums = provenance.get('input_checksums') or {}
        integrity = (f"已记录 SHA-256 指纹（{len(checksums)} 个输入文件）"
                     if checksums else "未提供校验结果")
        study = [
            ("委托单位", clean(lines[1]), False),
            ("研究物种", clean(lines[2]), True),
            ("参考基因组", clean(lines[3]), False),
            ("核心比较组", comparison_text, False),
        ]
        analysis = [
            ("项目编号", clean(project.get('project_id') or project.get('id')), False),
            ("RNAFlow 流程版本", pipeline, False),
            ("BioReport 报告引擎版本", f"BioReport v{bioreport.__version__}", False),
            ("数据完整性校验状态", integrity, False),
        ]
        def quoted_fields(pairs):
            return [(json.dumps(tr(label), ensure_ascii=False),
                     json.dumps((tr(value) if label == "数据完整性校验状态" else value) or tr("未提供"), ensure_ascii=False), italic)
                    for label, value, italic in pairs]
        cover = Template((style_dir / ("rna-cover.en.typ.j2" if english else "rna-cover.typ.j2")).read_text(encoding="utf-8")).render(
            title=json.dumps(title, ensure_ascii=False),
            study_fields=quoted_fields(study), analysis_fields=quoted_fields(analysis),
            report_date=json.dumps(tr(report_date or "未提供"), ensure_ascii=False),
            pills=[json.dumps(text, ensure_ascii=False) for text in _cover_pills(config)],
            project_id=json.dumps(
                f"ProjectID: {project.get('project_id', project.get('id')) or short_name}",
                ensure_ascii=False),
            bioreport_version_label=json.dumps(f"BioReport: v{bioreport.__version__}", ensure_ascii=False),
            pipeline_version_label=json.dumps(f"FlowVersion: {pipeline or 'RNAFlow'}", ensure_ascii=False),
            english_subtitle=json.dumps(
                report.get('english_subtitle')
                or 'Standardized Transcriptome Sequencing Analysis & Data Lineage Report',
                ensure_ascii=False),
        )
        metadata.pop("title", None)
        metadata.pop("date", None)
        cover_block = f"```{{=typst}}\n{cover}\n```\n\n"
        (style_dir / "rna-cover.typ").write_text(cover, encoding="utf-8")
    elif pdf and has_gwas:
        metadata["format"]["typst"].update({
            "papersize": "a4", "toc": False, "toc-depth": 2,
            "number-sections": True,
            "section-numbering": "1.1.1",
            "margin": {"x": "20mm", "y": "22mm"},
            "include-in-header": ['../pdf/print-context.typ', '../pdf/print-style.typ', '../pdf/gwas-style.typ'],
            "include-before-body": '../pdf/print-body.typ',
        })
        style_dir = template_dir / "pdf"
        style_dir.mkdir(exist_ok=True)
        project = config.get("project", {})
        lines = [report.get("title", "GWAS 全基因组关联分析报告"),
                 project.get("client", ""), project.get("species", ""),
                 project.get("genome_version", project.get("genome", "")),
                 project.get("pipeline_version", project.get("software", ""))]
        title = str(lines[0]).replace('PDF', '').strip()
        provenance = _cover_provenance(template_dir)
        def clean(value):
            if value is None:
                return ""
            text = str(value).strip()
            return "" if text.lower() in {"none", "null", "undefined"} else text

        pipeline = clean(lines[4])
        report_date = clean(project.get('report_date') or project.get('date'))
        if not report_date and provenance.get('generated_at'):
            report_date = str(provenance['generated_at']).split('T')[0]
        traits = [str(t) for t in (config.get('analysis', {}).get('gwas', {}).get('traits') or [])]
        trait_text = ("; " if english else "；").join(traits[:4])
        if len(traits) > 4:
            trait_text = (
                f"{len(traits)} traits; examples: {trait_text}. Full list in the report."
                if english else f"共 {len(traits)} 个性状；示例：{trait_text}。完整列表见正文。"
            )
        elif not trait_text:
            trait_text = tr("未提供")
        checksums = provenance.get('input_checksums') or {}
        integrity = (f"已记录 SHA-256 指纹（{len(checksums)} 个输入文件）"
                     if checksums else "未提供校验结果")
        study = [
            ("委托单位", clean(lines[1]), False),
            ("研究物种", clean(lines[2]), True),
            ("参考基因组", clean(lines[3]), False),
            ("分析性状", trait_text, False),
        ]
        analysis = [
            ("项目编号", clean(project.get('project_id') or project.get('id')), False),
            ("GWASFlow 流程版本", pipeline, False),
            ("BioReport 报告引擎版本", f"BioReport v{bioreport.__version__}", False),
            ("数据完整性校验状态", integrity, False),
        ]
        def quoted_fields(pairs):
            return [(json.dumps(tr(label), ensure_ascii=False),
                     json.dumps((tr(value) if label == "数据完整性校验状态" else value) or tr("未提供"), ensure_ascii=False), italic)
                    for label, value, italic in pairs]
        cover = Template((style_dir / ("gwas-cover.en.typ.j2" if english else "gwas-cover.typ.j2")).read_text(encoding="utf-8")).render(
            title=json.dumps(title, ensure_ascii=False),
            study_fields=quoted_fields(study), analysis_fields=quoted_fields(analysis),
            report_date=json.dumps(tr(report_date or "未提供"), ensure_ascii=False),
            pills=[json.dumps(text, ensure_ascii=False) for text in _cover_pills(config)],
            project_id=json.dumps(
                f"ProjectID: {project.get('project_id', project.get('id')) or short_name}",
                ensure_ascii=False),
            bioreport_version_label=json.dumps(f"BioReport: v{bioreport.__version__}", ensure_ascii=False),
            pipeline_version_label=json.dumps(f"FlowVersion: {pipeline or 'GWASFlow'}", ensure_ascii=False),
            english_subtitle=json.dumps(
                report.get('english_subtitle')
                or 'Genome-Wide Association Study & Data Lineage Report',
                ensure_ascii=False),
        )
        metadata.pop("title", None)
        metadata.pop("date", None)
        cover_block = f"```{{=typst}}\n{cover}\n```\n\n"
        (style_dir / "gwas-cover.typ").write_text(cover, encoding="utf-8")
    content_root = template_dir / "qmd" / "en" if english and (has_rna or has_gwas) else template_dir / "qmd"
    skipped = skipped_modules(config, module_ids)
    replacements = {}
    for module_id, missing in skipped.items():
        filename = registered[module_id].qmd.removeprefix("qmd/")
        if pdf:
            filename = "pdf/" + filename
        # Retain the existing section heading in each language/format while
        # excluding all executable cells and result descriptions for this input.
        _, original = _read_module(content_root / filename)
        heading = re.search(r"(?m)^#{2,6} [^\n]+", original)
        replacements[(content_root / filename).resolve()] = (
            (heading.group(0) + "\n\n" if heading else "")
            + _missing_input_notice(missing, english)
        )
    if pdf and has_rna and any(_canonical(m) == 'rna.index' for m in module_ids):
        summary = (content_root / 'pdf/summary.qmd').read_text(encoding='utf-8')
        sections.append(composition.section(
            'executive-summary', tr('摘要'), summary, pdf=True, unnumbered_pdf=True,
        ))
    methods_appendix_added = False
    for position, module_id in enumerate(module_ids, start=1):
        canonical = _canonical(module_id)
        if (pdf and canonical in ('provenance','about') and not methods_appendix_added
                and any(_canonical(m)=='rna.workflow' for m in module_ids[:position-1])):
            appendix = '```{python}\n#| label: detailed-methods-appendix\n#| output: asis\nfor detail in method_details:\n    display(Markdown(detail))\n```'
            sections.append(composition.section('methods-appendix',tr('详细分析方法（附录）'),appendix,pdf=True,page_break=True))
            methods_appendix_added = True
        if module_id in MODULES:
            filename, heading = MODULES[module_id]
            if pdf and has_rna and module_id in ("about", "provenance"):
                filename = f"pdf/{module_id}.qmd"
            module_meta, body = _read_module(content_root / filename)
            definition = None
        elif canonical in registered:
            definition = registered[canonical]
            filename, heading = definition.qmd.removeprefix("qmd/"), definition.title
            if pdf:
                filename = "pdf/" + filename
            module_meta, body = _read_module(content_root / filename)
        else:
            source = _custom_source(config, module_id)
            definition = report["module_definitions"][module_id]
            heading = definition.get("title", module_id)
            module_meta, body = _read_module(source)
            module_meta = _stage_custom_metadata(module_meta, source, template_dir, module_id)
            body = _expand_includes(body, source.parent, stack=(source,))
            body = _namespace_chunk_labels(body, module_id, position)
            if "params" in definition:
                context = json.dumps({"id": module_id, "params": definition["params"]}, ensure_ascii=True)
                body = (
                    "```{python}\n#| echo: false\n"
                    f"import json as _bioreport_json\nreport_module = _bioreport_json.loads({context!r})\n"
                    "```\n\n" + body
                )
        if canonical in skipped:
            body = _missing_input_notice(skipped[canonical], english)
        if canonical in registered and registered[canonical].parent:
            definition = registered[canonical]
            parent = registered[definition.parent]
            parent_filename = parent.qmd.removeprefix("qmd/")
            if pdf:
                parent_filename = "pdf/" + parent_filename
            module_meta, _ = _read_module(content_root / parent_filename)
            if canonical not in skipped and definition.parent not in setup_added:
                setup_filename = definition.setup_qmd.removeprefix("qmd/")
                if pdf:
                    setup_filename = "pdf/" + setup_filename
                body = (content_root / setup_filename).read_text(encoding="utf-8") + "\n" + body
                setup_added.add(definition.parent)
            if pdf:
                # The selected child is already a chapter: avoid repeating its
                # title as a second-level heading immediately below the setup.
                body = re.sub(r'(?m)^## [^\n]+\n\n', '', body, count=1)
        if (canonical in registered) or (module_id in MODULES and module_id != "ai"):
            body = _expand_includes(body, content_root, stack=(content_root / filename,),
                                    replacements=replacements)
        if not pdf and canonical in {'rna.workflow', 'about'}:
            from .utils.mermaid_static import inline_static_mermaid
            body, _ = inline_static_mermaid(body, template_dir/'qmd/assets',
                                            f'{module_id}-{language(config)}', language(config))
        for key in ("bibliography", "csl"):
            if key in module_meta and not website:
                value = module_meta[key]
                if key == "bibliography" and key in metadata:
                    previous = metadata[key] if isinstance(metadata[key], list) else [metadata[key]]
                    additional = value if isinstance(value, list) else [value]
                    metadata[key] = list(dict.fromkeys(previous + additional))
                elif key in metadata and metadata[key] != value:
                    raise ValueError(f"Conflicting {key} metadata in module {module_id}")
                else:
                    metadata[key] = value
        if pdf:
            if canonical == "rna.workflow":
                # Quarto's browser-based Mermaid PNG conversion can return no
                # SVG. Use the bundled vector diagram for the PDF workflow.
                body = re.sub(
                    r"```\{mermaid\}\n.*?\n```",
                    ('![RNA-seq Analysis Workflow]' if english else '![RNA-seq 分析流程]') + '(assets/rna-workflow.svg){#fig-pipeline-clean width="100%"}',
                    body,
                    flags=re.DOTALL,
                )
            # Quarto's Typst callouts import a remote fontawesome package.
            body = re.sub(r"(?m)^:::\s*\{\.callout-[^\n]*\}", "::: {.report-note}", body)
            # Typst otherwise treats CJK text directly after a citation as part of its label.
            body = re.sub(r"(\[@[A-Za-z0-9_:-]+\])(?=[\u4e00-\u9fff])", r"\1 ", body)
        # Module interpretations are staged as data files by the deterministic
        # writer. The slot is a no-op when AI is disabled or unavailable, so
        # legacy reports keep their original structure.
        if config.get("ai", {}).get("enabled", True) and config.get("ai", {}).get("scope", "results") == "global" and canonical == "ai":
            body += _module_ai_slot(canonical, english)
        elif config.get("ai", {}).get("enabled", True) and config.get("ai", {}).get("scope", "results") == "module" and canonical in registered and canonical not in {"provenance", "about"} and canonical not in skipped:
            body += _module_ai_slot(canonical, english)
        chapters = [(canonical, heading, body)]
        if canonical == "rna.index":
            sample_heading = r"^## Sample Information(?: \{[^}\n]+\})?$" if english else r"^## 样本信息\s*[（(]Sample Info[）)](?: \{[^}\n]+\})?$"
            parts = re.split(sample_heading, body, maxsplit=1, flags=re.MULTILINE)
            if len(parts) == 2:
                overview, samples = parts
                chapters = [
                    (canonical, "项目概述", overview),
                    ("rna.sample-info", "样本信息", samples),
                ]
        elif canonical == "rna.workflow":
            chapters = [(canonical, "分析方法与软件版本" if pdf else "分析概述", body)]
        for chapter_id, title, content in chapters:
            title = tr(title)
            content_heading = tr(module_meta.get("title", title) if chapter_id == "about" else title)
            if website:
                # Separate documents execute in separate kernels. The sample
                # page needs the same data-loading cell as the project overview.
                if chapter_id == "rna.sample-info":
                    setup = re.search(r"```\{python\}\n.*?\n```", overview, re.DOTALL)
                    if setup:
                        content = setup.group(0) + "\n\n" + content
                page_name = chapter_id.removeprefix("rna.").replace(".", "-")
                page_path = template_dir / "qmd" / f"site-{language(config)}-{page_name}.qmd"
                page_meta = {
                    "lang": "en" if english else "zh-Hans",
                    "execute": {"echo": False, "warning": False},
                    **module_meta,
                    "title": content_heading,
                }
                if canonical == "rna.qc" and any(_canonical(module) == "rna.workflow" for module in module_ids):
                    page_meta.pop("bibliography", None)
                    page_meta.pop("csl", None)
                    content = re.sub(
                        r"\[@([A-Za-z0-9_:-]+)\]",
                        lambda match: f"[{'References' if english else '参考文献'}](site-{language(config)}-workflow.qmd#ref-{'FastQ_Screen' if match.group(1) == 'wingett2018fastq' else match.group(1)})",
                        content,
                    )
                page_frontmatter = yaml.safe_dump(page_meta, allow_unicode=True, sort_keys=False)
                page_path.write_text(
                    f"---\n{page_frontmatter}---\n\n" + language_prelude + f"{content.strip()}\n\n" + _report_footer(template_dir, english),
                    encoding="utf-8",
                )
                website_pages.append({"href": f"qmd/{page_path.name}", "id": chapter_id.replace(".", "-"), "title": title, "icon": _page_icon(chapter_id, registered)})
            elif pdf:
                sections.append(composition.section(chapter_id, content_heading, content, pdf=True, page_break=has_rna))
            else:
                page_id = f"report-page-{len(pages) + 1}"
                pages.append((page_id, title))
                sections.append(
                    f"::: {{.report-page{' .about-project' if chapter_id == 'about' else ''} #{page_id}}}\n\n"
                    f"# {content_heading}\n\n{content.strip()}\n\n:::\n"
                )

    if pdf and not methods_appendix_added and any(_canonical(m)=='rna.workflow' for m in module_ids):
        appendix = '```{python}\n#| label: detailed-methods-appendix\n#| output: asis\nfor detail in method_details:\n    display(Markdown(detail))\n```'
        sections.append(composition.section('methods-appendix',tr('详细分析方法（附录）'),appendix,pdf=True,page_break=True))
    if website:
        nav_pages = [(Path(page["href"]).name.replace(".qmd", ".html"), page["title"]) for page in website_pages]
        navigation = _report_navigation(nav_pages, tr)
        navigation = navigation.replace('href="#site-', 'href="site-')
        navigation = navigation.replace('href="#report-page-1"', 'href="' + nav_pages[0][0] + '"')
        for page in website_pages:
            path = template_dir / page['href']
            text = path.read_text(encoding='utf-8')
            boundary = text.index('\n---\n', 4) + 5
            path.write_text(text[:boundary] + '\n' + navigation + text[boundary:], encoding='utf-8')
        return website_pages

    if pdf and "bibliography" in metadata:
        bibliography = metadata["bibliography"]
        sources = bibliography if isinstance(bibliography, list) else [bibliography]
        aliases = []
        for source in sources:
            source_path = (template_dir / "qmd" / source).resolve()
            alias_path = source_path.with_name(source_path.name.replace("_", "-"))
            if alias_path != source_path:
                shutil.copyfile(source_path, alias_path)
            aliases.append(str(Path(source).with_name(alias_path.name)))
        metadata["bibliography"] = aliases if isinstance(bibliography, list) else aliases[0]

    if pdf:
        composition.write(template_dir / "qmd/report-plan.json")
    target = template_dir / "qmd" / ("report_pdf.qmd" if pdf else "report.qmd")
    navigation = ""
    if not pdf:
        metadata["format"] = {"html": {"number-sections": False, "format-links": False}}
        navigation = _report_navigation(pages, tr)
    frontmatter = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False)
    prelude = '```{python}\n#| label: report-language\nimport os\nos.environ["BIOREPORT_LANGUAGE"] = __REPORT_EDITION__\n```\n\n'.replace("__REPORT_EDITION__", repr("en" if english else "zh"))
    target.write_text(
        f"---\n{frontmatter}---\n\n" + prelude + navigation + cover_block + "\n".join(sections)
        + ("" if pdf else "\n" + _report_footer(template_dir, english)),
        encoding="utf-8",
    )
    return target


def _report_navigation(pages, tr):
    page_links = [
        f'<a href="#{page_id}" aria-controls="{page_id}" class="nav-link">{escape(title)}</a>'
        for page_id, title in pages
    ]
    menu_links = "\n".join(page_links)
    navigation = (
        '```{=html}\n<nav class="navbar report-navbar" aria-label="Report navigation">\n'
        '<div class="report-brand">'
        '<a href="https://github.com/xsx123123/bioreport" target="_blank" rel="noopener noreferrer" aria-label="BioReport GitHub 仓库">'
        '<img src="../logo/logo.png" alt="BioReport logo"></a>'
        '<a href="#report-page-1" aria-controls="report-page-1" class="report-brand-link"><span class="report-brand-name">BioReport</span><span class="report-brand-context">RNA-seq report</span></a></div>\n'
        '<button class="report-nav-toggle" type="button" aria-label="Toggle navigation" aria-expanded="false" aria-controls="report-menu">'
        '<span class="report-nav-toggle-bar"></span>'
        '<span class="report-nav-toggle-bar"></span>'
        '<span class="report-nav-toggle-bar"></span>'
        '</button>\n'
        f'<div class="report-menu" id="report-menu">\n{menu_links}\n</div>\n'
        '<div class="report-menu-right">\n'
        '<button class="report-control report-language-control" type="button" data-report-language aria-label="Switch report language">English</button>'
        '<button class="report-control report-theme-control" type="button" data-report-theme aria-label="Switch to dark mode" title="Switch to dark mode">'
        '<svg class="report-theme-icon report-theme-icon-dark" viewBox="0 0 24 24" aria-hidden="true"><path d="M20.2 15.4A8.4 8.4 0 0 1 8.6 3.8 8.5 8.5 0 1 0 20.2 15.4Z"/></svg>'
        '<svg class="report-theme-icon report-theme-icon-light" viewBox="0 0 24 24" aria-hidden="true" hidden><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42"/></svg>'
        '</button>'
        '<a href="https://www.hzau.edu.cn/" target="_blank" rel="noopener noreferrer" aria-label="Huazhong Agricultural University website">'
        '<img src="../logo/Huazhong_Agricultural_University_logo.svg" alt="Huazhong Agricultural University"></a></div>\n'
        '</nav>\n```\n\n'
    )
    return navigation
