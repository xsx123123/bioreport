import argparse
import json
import yaml
import os
from pathlib import Path
from datetime import datetime


def build_default_report_config(client, species, genome, pipeline_version):
    """构造默认的统一 YAML 配置结构。"""
    today = datetime.now().strftime("%Y-%m-%d")
    return {
        "report": {
            "type": "rna-seq",
            "title": f"{client} RNA-seq 分析报告",
            "subtitle": "RNA 转录组测序分析报告",
            "language": "zh",
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
                "light": "./theme/New_Brutalism.scss",
                "dark": "./theme/Dark_New_Brutalism.scss"
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
            "data_dir": "../data/index/",
            "qc_file": "multiqc_qc_general_stats.txt",
            "mapping_file": "multiqc_mapping_general_stats.txt",
            "tpm_file": "merge_rsem_tpm.tsv",
            "sample_file": "sample.csv",
            "fastp_report_dir": "../data/fastp_trim_report/multiqc_short_read_trim_report_data",
            "fastp_stats_file": "../data/fastp_trim_report/multiqc_general_stats.txt",
            "fastq_screen_r1_dir": "../data/fastq_screen_report/fastq_screen_multiqc_r1/multiqc_r1_fastq_screen_report_data",
            "fastq_screen_r2_dir": "../data/fastq_screen_report/fastq_screen_multiqc_r2/multiqc_r2_fastq_screen_report_data",
            "qualimap_dir": "../data/QualiMap/multiqc_data/",
            "contrasts_file": "../data/index/contrasts.csv",
            "deg_dir": "../data/res/DEG",
            "enrichment_dir": "../data/res/Enrichments"
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
            "prompt_file": "/app/rnareport/utils/prompt.txt",
            "model": "doubao-seed-1-6-251015",
            "provider": "volcengine",
            "temperature": 0.7,
            "deg_limit": 20,
            "enrichment_limit": 10
        }
    }


def update_yaml_config(client, species, genome, pipeline_version, output_path):
    """更新或创建统一的 report_config.yaml。"""
    default_data = build_default_report_config(client, species, genome, pipeline_version)

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
            print(f"✅ 已更新现有 YAML 配置: {output_path}")
        except Exception as e:
            print(f"⚠️  读取现有 YAML 失败，覆盖创建: {output_path} ({e})")
            final_data = default_data
    else:
        final_data = default_data
        print(f"✅ 创建新 YAML 配置: {output_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(final_data, f, allow_unicode=True, sort_keys=False)


def update_json_config(client, species, genome, pipeline_version, output_path):
    """更新 data/project_summary.json（旧版兼容）"""
    default_data = {
        "project_meta": {
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
            "data_dir": "../data/index/",
            "qc_file": "multiqc_qc_general_stats.txt",
            "mapping_file": "multiqc_mapping_general_stats.txt",
            "tpm_file": "merge_rsem_tpm.tsv",
            "sample_file": "sample.csv",
            "fastp_report_dir": "../data/fastp_trim_report/multiqc_short_read_trim_report_data",
            "fastp_stats_file": "../data/fastp_trim_report/multiqc_general_stats.txt",
            "fastq_screen_r1_dir": "../data/fastq_screen_report/fastq_screen_multiqc_r1/multiqc_r1_fastq_screen_report_data",
            "fastq_screen_r2_dir": "../data/fastq_screen_report/fastq_screen_multiqc_r2/multiqc_r2_fastq_screen_report_data",
            "qualimap_dir": "../data/QualiMap/multiqc_data/",
            "contrasts_file": "../data/index/contrasts.csv",
            "deg_dir": "../data/res/DEG",
            "enrichment_dir": "../data/res/Enrichments"
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
                existing_data["input_files"].update(default_data["input_files"])

            final_data = existing_data
            print(f"✅ 已更新现有 JSON 配置: {output_path}")
        except json.JSONDecodeError:
            print(f"⚠️  现有 JSON 文件损坏，覆盖创建: {output_path}")
            final_data = default_data
    else:
        final_data = default_data
        print(f"✅ 创建新 JSON 配置: {output_path}")

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_data, f, indent=2, ensure_ascii=False)


def update_quarto_yaml(title, yaml_path):
    """更新 _quarto.yml 中的标题（直接字符串替换，保留注释）。"""
    if not os.path.exists(yaml_path):
        print(f"❌ 找不到 _quarto.yml: {yaml_path}")
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
                print(f"✅ 报告标题已更新为: {title}")
            else:
                print("ℹ️  报告标题未变更")
        else:
            print("⚠️  未在 _quarto.yml 中找到标准 title 字段，跳过更新。")

    except Exception as e:
        print(f"❌ 更新 _quarto.yml 失败: {e}")


def main():
    parser = argparse.ArgumentParser(description="BFP Report Configuration Tool")

    parser.add_argument("--client", help="客户名称", default="未指定客户")
    parser.add_argument("--species", help="物种名称", default="Unknown")
    parser.add_argument("--genome", help="基因组版本", default="Unknown")
    parser.add_argument("--pipeline", help="流程版本", default="RNAFlow v2.x")
    parser.add_argument("--title", help="报告主标题", default=None)

    # 路径参数
    parser.add_argument("--config_out", help="统一 YAML 配置输出路径", default="../../configs/report_config.yaml")
    parser.add_argument("--json_out", help="旧版 JSON 输出路径", default=None)
    parser.add_argument("--yaml_out", help="Quarto YAML 路径", default=None)

    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))

    # 1. 生成/更新统一 YAML 配置
    config_path = os.path.abspath(os.path.join(script_dir, args.config_out))
    update_yaml_config(args.client, args.species, args.genome, args.pipeline, config_path)

    # 2. 如需要，同时生成旧版 JSON
    if args.json_out:
        json_path = os.path.abspath(os.path.join(script_dir, args.json_out))
        update_json_config(args.client, args.species, args.genome, args.pipeline, json_path)

    # 3. 更新 _quarto.yml 标题（如提供 title 且提供 yaml_out）
    if args.title and args.yaml_out:
        yaml_path = os.path.abspath(os.path.join(script_dir, args.yaml_out))
        update_quarto_yaml(args.title, yaml_path)


if __name__ == "__main__":
    main()
