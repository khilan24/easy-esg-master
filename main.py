#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ESG 投研报告生成 - 主程序
支持周报（上周）与日报（昨日），一键完成：研究 → 润色 → 合并 → Word 填充
"""
import argparse
import json
import os
import sys
import traceback

from core import (
    load_config,
    get_date_range_for_mode,
    get_output_subdir,
    get_output_date_suffix,
    safe_print,
    ResearchPipeline,
)
from core.progress import (
    start_total,
    write_progress,
    start_stage,
    end_stage,
    write_progress_done,
    write_progress_error,
)
from report import save_raw_content, save_formatted_report
from word import fill_word_template


def main():
    parser = argparse.ArgumentParser(description="生成 ESG 投研周报或日报")
    parser.add_argument(
        "--mode", "-m",
        choices=["weekly", "daily"],
        default="weekly",
        help="周报（上周一至上周日）或日报（昨日），默认 weekly",
    )
    parser.add_argument(
        "--provider", "-p",
        choices=["gemini", "qwen"],
        default=None,
        help="模型服务：gemini 或 qwen，不传则使用 config.json 中的 provider",
    )
    args = parser.parse_args()
    mode = args.mode
    provider = args.provider

    report_label = "ESG投研日报" if mode == "daily" else "ESG投研周报"
    print("=" * 60)
    print(f"ESG 投研报告生成 - {report_label}")
    try:
        config = load_config(provider_override=provider)
    except Exception as e:
        print(f"配置错误：{e}")
        sys.exit(1)
    provider = config.get("provider", "gemini")
    print("使用 " + ("千问 Deep Research + " + config.get("qwen_model", "qwen3-max-preview") if provider == "qwen" else "Gemini Deep Research Agent + Gemini 3 Pro"))
    print("=" * 60)
    print()

    completed_stages = []
    current_stage_id, current_stage_label = "stage1", "Deep Research（E/S/G）"
    try:
        date_info = get_date_range_for_mode(mode)
        safe_print(f"研究期间：{date_info['date_range_chinese']}")
        safe_print(f"日期范围（ISO）：{date_info['date_range_iso']}\n")

        start_total()
        pipeline = ResearchPipeline(config)
        research_results = pipeline.stage1_research_parallel(date_info)
        if not all(research_results.values()):
            safe_print("\n警告：部分领域的研究失败，将使用可用结果继续处理")
        completed_stages = end_stage("stage1", "Deep Research（E/S/G）", completed_stages)
        write_progress("stage2", "润色（E/S/G）", completed_stages)
        start_stage("stage2", "润色（E/S/G）")

        current_stage_id, current_stage_label = "stage2", "润色（E/S/G）"
        polished_results = pipeline.stage2_polish_parallel(research_results, date_info)
        completed_stages = end_stage("stage2", "润色（E/S/G）", completed_stages)
        write_progress("stage3", "热点聚焦", completed_stages)
        start_stage("stage3", "热点聚焦")

        current_stage_id, current_stage_label = "stage3", "热点聚焦"
        hotspot_result = pipeline.stage3_hotspot_focus(polished_results, date_info)
        completed_stages = end_stage("stage3", "热点聚焦", completed_stages)
        write_progress("stage4", "合并报告", completed_stages)
        start_stage("stage4", "合并报告")

        current_stage_id, current_stage_label = "stage4", "合并报告"
        final_result = pipeline.stage4_merge(polished_results, hotspot_result, date_info)
        completed_stages = end_stage("stage4", "合并报告", completed_stages)
        write_progress("stage5", "Word 填充", completed_stages)
        start_stage("stage5", "Word 填充")

        raw_filename = save_raw_content(final_result, hotspot_result, polished_results, date_info)
        agent = "qwen-deep-research" if provider == "qwen" else config.get("agent", "deep-research-pro-preview-12-2025")
        model = config.get("qwen_model", "qwen3-max-preview") if provider == "qwen" else config.get("model", "gemini-3-pro-preview")
        formatted_filename = save_formatted_report(
            final_result,
            hotspot_result,
            polished_results,
            date_info,
            agent,
            model,
        )

        safe_print("\n" + "=" * 60)
        safe_print("报告预览（前500字）：")
        safe_print("=" * 60)
        safe_print(final_result[:500] + "..." if len(final_result) > 500 else final_result)
        safe_print("\n" + "=" * 60)
        safe_print(f"原始内容：{raw_filename}")
        safe_print(f"JSON 报告：{formatted_filename}")

        try:
            with open(formatted_filename, "r", encoding="utf-8") as f:
                report_json = json.load(f)
            safe_print("\n报告元数据：")
            safe_print(json.dumps(report_json["report_metadata"], ensure_ascii=False, indent=2))
        except Exception as e:
            safe_print(f"\n读取 JSON 出错：{e}")

        word_output_dir = get_output_subdir(date_info)
        date_suffix = get_output_date_suffix(date_info)
        os.makedirs(word_output_dir, exist_ok=True)
        safe_print("\n" + "=" * 60)
        safe_print("阶段5：填充 Word 模板")
        safe_print("=" * 60)
        try:
            fill_success, word_output = fill_word_template(
                json_path=formatted_filename,
                template_path="ESG研报模板.docx",
                output_path=os.path.join(word_output_dir, f"{date_suffix}_最终版.docx"),
            )
            if fill_success:
                completed_stages = end_stage("stage5", "Word 填充", completed_stages)
                write_progress_done(completed_stages)
                safe_print(f"\n[成功] Word 文档：{word_output}")
                safe_print("\n" + "=" * 60)
                safe_print("全部流程完成！")
                safe_print("=" * 60)
                safe_print(f"[完成] 原始内容: {raw_filename}")
                safe_print(f"[完成] JSON 报告: {formatted_filename}")
                safe_print(f"[完成] Word 文档: {word_output}")
            else:
                completed_stages = end_stage("stage5", "Word 填充", completed_stages)
                write_progress_done(completed_stages)
                safe_print("\n[警告] Word 填充失败，JSON 已生成")
                safe_print(f"可手动运行: python fill_template.py --json {formatted_filename}")
        except Exception as e:
            completed_stages = end_stage("stage5", "Word 填充", completed_stages)
            write_progress_error(completed_stages, "stage5", "Word 填充")
            safe_print(f"\n[警告] Word 填充出错: {e}")
            safe_print("JSON 已生成，可稍后运行 fill_template.py 填充")
            print(traceback.format_exc(), flush=True)

    except Exception as e:
        err_msg = traceback.format_exc()
        print(err_msg, flush=True)
        safe_print(f"\n生成报告时发生错误：{str(e)}")
        safe_print("\n请确认：config.json 有效、prompt/ 完整、网络正常，且已安装对应 SDK（Gemini 或千问 dashscope）")
        write_progress_error(completed_stages, current_stage_id, current_stage_label)
        sys.exit(1)


if __name__ == "__main__":
    main()
