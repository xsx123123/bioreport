import json
import yaml
import os
from pathlib import Path
from datetime import datetime


def build_default_report_config(client, species, genome, pipeline_version, project_id="DEMO-PROJECT"):
    """构造默认的统一 YAML 配置结构。"""
    today = datetime.now().strftime("%Y-%m-%d")
    return {
        "report": {
            "type": "rna-seq",
            "title": f"{client} RNA-seq Analysis Report",
            "subtitle": "RNA Sequencing Analysis",
            "language": "en",
            "output_format": "html",
            "sections": [
                "index",
                "workflow",
                "qc",
                "results",
                "ai",
                "about"
            ],
            "theme": {
                "light": "./theme/bioreport.scss",
                "dark": "./theme/bioreport.scss"
            },
            "css": [
                "./theme/styles.css",
                "./theme/itables_saas.css"
            ],
            "logo": "/logo/logo.png",
            "logo_href": "https://github.com/xsx123123",
            "navbar_right": [
                {"icon": "github", "href": "https://github.com/xsx123123"},
                {"icon": "wechat", "href": "https://github.com/xsx123123"}
            ],
            "sidebar_title": "RNA-seq Report",
            "announcement": {
                "icon": "info-circle",
                "dismissable": True,
                "content": "**Alert** - this is some information that you should pay attention to",
                "type": "primary",
                "position": "below-navbar"
            }
        },
        "project": {
            "project_id": project_id,
            "client": client,
            "species": species,
            "genome_version": genome,
            "pipeline_version": pipeline_version,
            "analysis_date": today
        },
        "stats": {
            "total_samples": 0,
            "group_count": 0
        },
        "input_files": {
            "data_dir": "/data",
            "qc_file": "index/multiqc_qc_general_stats.txt",
            "mapping_file": "index/multiqc_mapping_general_stats.txt",
            "tpm_file": "index/merge_rsem_tpm.tsv",
            "sample_file": "index/sample.csv",
            "fastp_report_dir": "fastp_trim_report/multiqc_short_read_trim_report_data",
            "fastp_stats_file": "fastp_trim_report/multiqc_general_stats.txt",
            "fastq_screen_r1_dir": "fastq_screen_report/fastq_screen_multiqc_r1/multiqc_r1_fastq_screen_report_data",
            "fastq_screen_r2_dir": "fastq_screen_report/fastq_screen_multiqc_r2/multiqc_r2_fastq_screen_report_data",
            "qualimap_dir": "QualiMap/multiqc_data",
            "contrasts_file": "index/contrasts.csv",
            "deg_dir": "res/DEG",
            "enrichment_dir": "res/Enrichments"
        },
        "analysis": {
            "deg": {
                "log2fc_threshold": 1.0,
                "pvalue_threshold": 0.05
            },
            "enrichment": {
                "p_cutoff": 0.1,
                "top_n": 20
            },
            "heatmap": {
                "top_n": 1000
            }
        },
        "ai": {
            "enabled": True,
            "prompt_file": "/app/bioreport/utils/prompt.txt",
            "model": "doubao-seed-1-6-251015",
            "provider": "volcengine",
            "temperature": 0.7,
            "deg_limit": 20,
            "enrichment_limit": 10
        }
    }


def update_yaml_config(client, species, genome, pipeline_version, output_path, project_id="DEMO-PROJECT"):
    """更新或创建统一的 JSON 报告配置。"""
    default_data = build_default_report_config(client, species, genome, pipeline_version, project_id)

    out_path = Path(output_path)
    if out_path.exists():
        try:
            with open(out_path, 'r', encoding='utf-8') as f:
                existing_data = yaml.safe_load(f) or {}

            # 深度合并：保留现有 input_files/stats/analysis/ai，只更新 project 和 report title
            existing_data.setdefault("report", {})
            existing_data["report"].setdefault("sections", default_data["report"]["sections"])
            existing_data["report"]["title"] = default_data["report"]["title"]
            existing_data["project"] = default_data["project"]

            for key in ("input_files", "stats", "analysis", "ai"):
                if key not in existing_data:
                    existing_data[key] = default_data[key]

            final_data = existing_data
            print(f"Updated existing YAML configuration: {output_path}")
        except Exception as e:
            print(f"Warning: could not read existing YAML; replacing it: {output_path} ({e})")
            final_data = default_data
    else:
        final_data = default_data
        print(f"Created YAML configuration: {output_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(final_data, f, allow_unicode=True, sort_keys=False)


def update_json_config(client, species, genome, pipeline_version, output_path, project_id="DEMO-PROJECT"):
    """更新 data/project_summary.json（旧版兼容）"""
    default_data = {
        "project_meta": {
            "project_id": project_id,
            "client": client,
            "species": species,
            "genome_version": genome,
            "pipeline_version": pipeline_version,
            "analysis_date": datetime.now().strftime("%Y-%m-%d")
        },
        "stats": {
            "total_samples": 0,
            "group_count": 0
        },
        "input_files": {
            "data_dir": "/data",
            "qc_file": "index/multiqc_qc_general_stats.txt",
            "mapping_file": "index/multiqc_mapping_general_stats.txt",
            "tpm_file": "index/merge_rsem_tpm.tsv",
            "sample_file": "index/sample.csv",
            "fastp_report_dir": "fastp_trim_report/multiqc_short_read_trim_report_data",
            "fastp_stats_file": "fastp_trim_report/multiqc_general_stats.txt",
            "fastq_screen_r1_dir": "fastq_screen_report/fastq_screen_multiqc_r1/multiqc_r1_fastq_screen_report_data",
            "fastq_screen_r2_dir": "fastq_screen_report/fastq_screen_multiqc_r2/multiqc_r2_fastq_screen_report_data",
            "qualimap_dir": "QualiMap/multiqc_data",
            "contrasts_file": "index/contrasts.csv",
            "deg_dir": "res/DEG",
            "enrichment_dir": "res/Enrichments"
        }
    }

    if os.path.exists(output_path):
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)

            if "project_meta" not in existing_data:
                existing_data["project_meta"] = {}
            existing_data["project_meta"].update(default_data["project_meta"])

            if "input_files" not in existing_data:
                existing_data["input_files"] = default_data["input_files"]
            else:
                for key, value in default_data["input_files"].items():
                    existing_data["input_files"].setdefault(key, value)

            final_data = existing_data
            print(f"Updated existing JSON configuration: {output_path}")
        except json.JSONDecodeError:
            print(f"Warning: existing JSON is invalid; replacing it: {output_path}")
            final_data = default_data
    else:
        final_data = default_data
        print(f"Created JSON configuration: {output_path}")

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_data, f, indent=2, ensure_ascii=False)


def update_quarto_yaml(title, yaml_path):
    """更新 _quarto.yml 中的标题（直接字符串替换，保留注释）。"""
    if not os.path.exists(yaml_path):
        print(f"Error: _quarto.yml not found: {yaml_path}")
        return

    try:
        with open(yaml_path, 'r', encoding='utf-8') as f:
            content = f.read()

        import re
        new_title_line = f'title: "{title}"'
        pattern = re.compile(r'^title:\s*["\'].*["\']', re.MULTILINE)

        if pattern.search(content):
            new_content = pattern.sub(new_title_line, content)
            if new_content != content:
                with open(yaml_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"Report title updated: {title}")
            else:
                print("Report title unchanged.")
        else:
            print("Warning: no standard title field found in _quarto.yml; skipping update.")

    except Exception as e:
        print(f"Error: failed to update _quarto.yml: {e}")
