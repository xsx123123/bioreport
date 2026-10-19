#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
报告溯源信息（Provenance）构建模块。

自动记录报告的生成引擎版本、生成时间、渲染模块、输出布局/格式、
分析流程版本以及输入文件 SHA256 指纹，服务科研可复现与合规审计。
所有字段均为运行时自动采集，禁止手填。
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import bioreport

# 大文件分块读取的块大小（64 KiB），避免整文件载入内存。
_CHUNK_SIZE = 64 * 1024


def _sha256_file(path: Path) -> str:
    """分块读取文件并计算 SHA256，避免大文件占用过多内存。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def input_checksums(config: dict) -> dict:
    """对 input_files 中真实存在的文件计算 SHA256 指纹。

    返回 {逻辑字段名: sha256}；目录（如 *_dir 结尾的键）与缺失文件自动跳过。
    """
    checksums = {}
    input_files = config.get("input_files", {})
    data_dir = input_files.get("data_dir")
    for key, value in input_files.items():
        if key == "data_dir" or not isinstance(value, str):
            continue
        path = Path(value)
        if not path.is_file() and data_dir and not path.is_absolute():
            # 未经过 load_config 解析的相对路径，回退到 data_dir 定位。
            candidate = Path(data_dir) / value
            if candidate.is_file():
                path = candidate
        if path.is_file():
            checksums[key] = _sha256_file(path)
    return checksums


def build_provenance(config: dict, sections: list) -> dict:
    """组装报告溯源信息字典，字段全部自动生成。"""
    report = config.get("report", {})
    project = config.get("project", {})

    output_format = report.get("output_format", "html")
    if isinstance(output_format, str):
        output_format = [output_format]

    provenance = {
        "project_id": project["project_id"],
        "bioreport_version": bioreport.__version__,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "rendered_modules": list(sections),
        "layout": report.get("layout", "single"),
        "output_format": list(output_format),
        "input_checksums": input_checksums(config),
        "input_manifest": input_manifest(config),
    }
    pipeline_version = project.get("pipeline_version")
    if pipeline_version:
        provenance["pipeline_version"] = pipeline_version
    return provenance


def write_provenance(provenance: dict, qmd_dir: Path) -> Path:
    """将溯源信息写入临时项目的 qmd/provenance.json，供 QMD 页面读取。"""
    qmd_dir.mkdir(parents=True, exist_ok=True)
    target = qmd_dir / "provenance.json"
    target.write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return target


def artifact_record(path, role, display=None):
    path = Path(path)
    return {'artifact':path.name, 'role':role, 'path':str(display if display is not None else path),
            'sha256':_sha256_file(path), 'size':path.stat().st_size}


def input_manifest(config):
    """Unique configured files, including contents of declared result directories."""
    from bioreport.config import display_path
    data_dir = Path(config.get('input_files', {}).get('data_dir', '.'))
    entries = {}
    for role, value in config.get('input_files', {}).items():
        if role == 'data_dir' or not isinstance(value, str): continue
        path = Path(value)
        if not path.is_absolute(): path = data_dir / path
        candidates = sorted(path.rglob('*')) if path.is_dir() else [path]
        for candidate in candidates:
            if candidate.is_file():
                identity = str(candidate.resolve())
                if identity not in entries:
                    entries[identity] = artifact_record(candidate, role, display_path(str(candidate), config))
    return list(entries.values())


def expected_report_paths(config):
    """Paths required by the requested formats and RNA language editions."""
    from bioreport.i18n import languages
    from bioreport.modules import output_formats
    from bioreport.config import report_artifact_name
    website = config.get('report', {}).get('layout') == 'website'
    paths = []
    for fmt in output_formats(config):
        if fmt == 'html' and not website:
            paths.append(report_artifact_name(config, fmt))
            continue
        paths.extend(('en/index.html' if lang == 'en' else 'index.html') if website
                     else report_artifact_name(config, fmt, lang)
                     for lang in languages(config))
    return list(dict.fromkeys(paths))


def write_delivery_manifests(config, provenance, output_dir):
    """External report hashes avoid the self-referential hash of an embedded PDF."""
    import platform
    import shlex
    import subprocess
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    from bioreport.i18n import is_rna
    paths = [directory / name for name in expected_report_paths(config)] if is_rna(config) else sorted(directory.glob('*_report*.*'))
    reports = [artifact_record(p, 'report', str(p.relative_to(directory))) for p in paths
               if p.is_file() and p.suffix in ('.pdf', '.html')]
    for record in reports:
        record['language'] = ('zh+en' if record['path'].endswith('_report.html') and is_rna(config)
                              else 'en' if '.en.' in record['path'] or record['path'].startswith('en/') else 'zh')
    artifacts = [artifact_record(p, 'supplementary', str(p.relative_to(directory)))
                 for p in sorted((directory/'supplementary').rglob('*')) if p.is_file()]
    for name, role in [('report-plan.json','semantic_report'),('report-blocks-pdf.jsonl','rendered_blocks'),
                       ('layout-observations.json','layout_observations'),('pdf-validation.json','pdf_validation'),
                       ('content-validation.json','content_validation')]:
        path=directory/name
        if path.is_file():artifacts.append(artifact_record(path,role,name))
    for lang in ('zh', 'en'):
        for stem in ('report-plan', 'report-blocks-pdf', 'layout-observations', 'pdf-validation', 'content-validation'):
            suffix = '.jsonl' if stem == 'report-blocks-pdf' else '.json'
            path = directory / (stem + '.' + lang + suffix)
            if path.is_file():
                artifacts.append(artifact_record(path, stem, path.name))
    config_path = config.get('_config_path')
    reproduction = []
    config_path = config.get('_config_path')
    if config_path and Path(config_path).is_file():
        import shutil
        backup = directory / ('run_config_backup'+Path(config_path).suffix)
        shutil.copyfile(config_path, backup)
        reproduction.append(artifact_record(backup, 'original_configuration', backup.name))
        resolved = directory/'reproduction-config.json'
        resolved.write_text(json.dumps({k:v for k,v in config.items() if not k.startswith('_')},ensure_ascii=False,indent=2))
        reproduction.append(artifact_record(resolved, 'resolved_configuration', resolved.name))
    try:
        quarto = subprocess.run(['quarto','--version'], capture_output=True, text=True,
                                timeout=10, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError): quarto = 'unavailable'
    from importlib.metadata import version, PackageNotFoundError
    packages={}
    for package in ('pandas','numpy','scipy','scikit-learn','plotly','matplotlib','pypdf','multiqc','jinja2'):
        try:packages[package]=version(package)
        except PackageNotFoundError:pass
    try:
        typst_result=subprocess.run(['quarto','typst','--version'],capture_output=True,text=True,timeout=10)
        typst=(typst_result.stdout or typst_result.stderr).strip() if typst_result.returncode==0 else 'unavailable'
    except (OSError, subprocess.SubprocessError):typst='unavailable'
    manifests = {
        'report-manifest': {'project_id':provenance['project_id'], 'generated_at':provenance['generated_at'],
                            'report_version':provenance['bioreport_version'], 'artifacts':reports},
        'input-manifest': {'artifacts':provenance.get('input_manifest', [])},
        'artifact-manifest': {'artifacts':artifacts},
        'reproduction-manifest': {'artifacts':reproduction, 'python':platform.python_version(),
            'quarto':quarto, 'typst':typst, 'packages':packages, 'bioreport':bioreport.__version__,
            'command': 'bioreport run -c reproduction-config.json -o reproduced',
            'note':'Resolved config runs against the recorded input paths on this host. On another host restore the inputs and update their root paths; verify Input Manifest hashes before rendering.'},
    }
    for name, value in manifests.items():
        (directory/f'{name}.json').write_text(json.dumps(value,ensure_ascii=False,indent=2), encoding='utf-8')


def validate_delivery_manifests(config, output_dir):
    """Rehash every delivery record and compare configured input coverage."""
    output = Path(output_dir)
    errors = []
    checked = 0
    input_expected = {r['path'] for r in input_manifest(config)}
    for name in ('report','input','artifact','reproduction'):
        path = output/f'{name}-manifest.json'
        if not path.is_file():
            errors.append({'manifest':name,'error':'missing_manifest'});continue
        manifest = json.loads(path.read_text())
        records = manifest.get('artifacts',[])
        if name=='input' and {r['path'] for r in records} != input_expected:
            errors.append({'manifest':name,'error':'input_coverage'})
        if name=='report':
            from bioreport.i18n import is_rna
            if is_rna(config) and {r['path'] for r in records} != set(expected_report_paths(config)):
                errors.append({'manifest': name, 'error': 'report_language_coverage', 'expected': expected_report_paths(config)})
            if not manifest.get('generated_at') or not manifest.get('report_version'):
                errors.append({'manifest':name,'error':'missing_generation_metadata'})
        for record in records:
            if not all(record.get(k) for k in ('artifact','role','path','sha256')):
                errors.append({'manifest':name,'error':'incomplete_record'});continue
            candidate = Path(record['path'])
            if not candidate.is_absolute():
                if name=='input':candidate=Path(config['input_files'].get('data_dir','.'))/candidate
                else:candidate=output/candidate
            if not candidate.is_file() or _sha256_file(candidate)!=record['sha256']:
                errors.append({'manifest':name,'error':'sha256','path':record['path']})
            elif candidate.stat().st_size!=record.get('size'):
                errors.append({'manifest':name,'error':'size','path':record['path']})
            checked+=1
    result={'status':'FAIL' if errors else 'PASS','checked_artifacts':checked,'errors':errors}
    (output/'provenance-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result
