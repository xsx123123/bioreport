"""Compose report documents from reusable Quarto content modules."""

from pathlib import Path
import json
import re
import shutil

import yaml

from .registry import get_registry


MODULES = {
    "ai": ("AI.qmd", "AI 解读"),
    "about": ("about.qmd", "关于"),
    "faq": ("faq.qmd", "常见问题"),
    "license": ("license.qmd", "许可"),
    "trademark": ("trademark.qmd", "商标"),
}

def _canonical(module_id: str) -> str:
    return get_registry().canonical(module_id)


def selected_modules(config: dict) -> list[str]:
    report = config.get("report", {})
    custom = report.get("module_definitions", {})
    if not isinstance(custom, dict):
        raise ValueError("report.module_definitions must be an object")
    collisions = custom.keys() & MODULES.keys()
    if collisions:
        raise ValueError(f"Custom module IDs conflict with built-in modules: {', '.join(sorted(collisions))}")
    registry = get_registry()
    default_modules = (
        ("index", "workflow", "qc", "results", "about")
        if config.get("_legacy_format")
        else (*registry.default_modules, "about")
    )
    modules = report.get("modules", report.get("sections", list(default_modules)))
    if not isinstance(modules, list) or not modules:
        raise ValueError("report.modules must be a nonempty list of module IDs")
    if any(not isinstance(module, str) for module in modules):
        raise ValueError("report.modules must contain string module IDs")
    if not config.get("_legacy_format"):
        modules = [_canonical(module) for module in modules]
    validation_modules = [_canonical(module) for module in modules]
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
    if not config.get("ai", {}).get("enabled", True):
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
            required_inputs.extend(definition.required_inputs)
            optional_inputs.extend(definition.optional_inputs)
    missing = sorted({key for key in required_inputs if not input_files.get(key)})
    optional_inputs = [key for key in optional_inputs if key in input_files]
    if missing:
        raise ValueError(f"Selected modules require input_files: {', '.join(missing)}")
    return modules


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
    body: str, qmd_dir: Path, root: Path | None = None, stack: tuple[Path, ...] = ()
) -> str:
    root = root or qmd_dir.resolve()

    def replace(match: re.Match) -> str:
        source = (qmd_dir / match.group(1)).resolve()
        if not source.is_relative_to(root):
            raise ValueError(f"Include escapes the QMD directory: {match.group(1)}")
        if source in stack:
            chain = " -> ".join(str(path) for path in (*stack, source))
            raise ValueError(f"Circular QMD include: {chain}")
        return _expand_includes(source.read_text(encoding="utf-8"), source.parent, root, (*stack, source))

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


def compose_report(config: dict, template_dir: Path, pdf: bool = False) -> Path:
    """Assemble one Quarto document from selected chapter modules."""
    report = config.get("report", {})
    metadata = {
        "title": report.get("title", "Report"),
        "lang": report.get("language", "zh"),
        "date": "last-modified",
        "execute": {"echo": False, "warning": False},
    }
    sections = []
    setup_added = set()
    registered = get_registry().modules
    for position, module_id in enumerate(selected_modules(config), start=1):
        canonical = _canonical(module_id)
        if module_id in MODULES:
            filename, heading = MODULES[module_id]
            module_meta, body = _read_module(template_dir / "qmd" / filename)
            definition = None
        elif canonical in registered:
            definition = registered[canonical]
            filename, heading = definition.qmd.removeprefix("qmd/"), definition.title
            module_meta, body = _read_module(template_dir / "qmd" / filename)
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
        if canonical in registered and registered[canonical].parent:
            definition = registered[canonical]
            parent = registered[definition.parent]
            parent_filename = parent.qmd.removeprefix("qmd/")
            module_meta, _ = _read_module(template_dir / "qmd" / parent_filename)
            if definition.parent not in setup_added:
                setup_filename = definition.setup_qmd.removeprefix("qmd/")
                body = (template_dir / "qmd" / setup_filename).read_text(encoding="utf-8") + "\n" + body
                setup_added.add(definition.parent)
        elif module_id in MODULES and module_id != "ai":
            body = _expand_includes(body, template_dir / "qmd", stack=(template_dir / "qmd" / filename,))
        for key in ("bibliography", "csl"):
            if key in module_meta:
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
            # Quarto's Typst callouts import a remote fontawesome package.
            body = re.sub(r"(?m)^:::\s*\{\.callout-[^\n]*\}", "::: {.report-note}", body)
            # Typst otherwise treats CJK text directly after a citation as part of its label.
            body = re.sub(r"(\[@[A-Za-z0-9_:-]+\])(?=[\u4e00-\u9fff])", r"\1 ", body)
        sections.append(f"# {heading}\n\n{body.strip()}\n")

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

    target = template_dir / "qmd" / ("report_pdf.qmd" if pdf else "report.qmd")
    frontmatter = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False)
    target.write_text(f"---\n{frontmatter}---\n\n" + "\n".join(sections), encoding="utf-8")
    return target
