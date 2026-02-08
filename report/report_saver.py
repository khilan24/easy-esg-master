"""
报告保存模块
包含保存原始内容和格式化内容的功能
"""
import os
import json
from datetime import datetime
from .report_formatter import parse_section_content, extract_title_and_hotspot, normalize_newlines
from core.utils import safe_print, get_output_subdir, get_output_date_suffix


def save_raw_content(final_content, hotspot_content, polished_results, date_info):
    """保存AI生成的原始内容。直接存入 output/weekly/ 或 output/daily/，文件名为 原始内容_日期.txt。"""
    output_dir = get_output_subdir(date_info)
    os.makedirs(output_dir, exist_ok=True)
    suffix = get_output_date_suffix(date_info)
    filename = os.path.join(output_dir, f"{suffix}_原始内容.txt")

    report_label = date_info.get("report_label", "ESG投研周报")
    content_parts = []
    content_parts.append("=" * 80)
    content_parts.append(f"{report_label} - 原始内容")
    content_parts.append(f"研究期间：{date_info['date_range_chinese']}")
    content_parts.append(f"生成时间：{datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}")
    content_parts.append("=" * 80)
    content_parts.append("")
    
    # 最终合并报告
    content_parts.append("【最终合并报告】")
    content_parts.append("-" * 80)
    content_parts.append(final_content)
    content_parts.append("")
    content_parts.append("")
    
    # 热点聚焦
    content_parts.append("【热点聚焦】")
    content_parts.append("-" * 80)
    content_parts.append(hotspot_content)
    content_parts.append("")
    content_parts.append("")
    
    # E、S、G章节
    for domain, domain_name in [("E", "环境（E）"), ("S", "社会（S）"), ("G", "公司治理（G）")]:
        content_parts.append(f"【{domain_name}章节】")
        content_parts.append("-" * 80)
        content_parts.append(polished_results.get(domain, "无内容"))
        content_parts.append("")
        content_parts.append("")
    
    # 保存文件
    with open(filename, 'w', encoding='utf-8') as f:
        f.write('\n'.join(content_parts))
    
    safe_print(f"\n原始内容已保存至：{filename}")
    return filename


def save_formatted_report(final_content, hotspot_content, polished_results, date_info, agent, model):
    """保存格式化后的报告到 JSON。直接存入 output/weekly/ 或 output/daily/，文件名为 报告_日期.json。"""
    output_dir = get_output_subdir(date_info)
    os.makedirs(output_dir, exist_ok=True)
    suffix = get_output_date_suffix(date_info)
    filename = os.path.join(output_dir, f"{suffix}_报告.json")
    report_label = date_info.get("report_label", "ESG投研周报")

    title, _ = extract_title_and_hotspot(final_content, date_info)
    if not title:
        title = f"{report_label}（{date_info['date_range_chinese']}）"
    
    # 优先使用传入的hotspot_content，如果为空或太短，尝试从final_content中提取
    extracted_hotspot = hotspot_content.strip() if hotspot_content and len(hotspot_content.strip()) > 50 else ""
    if not extracted_hotspot:
        _, extracted_hotspot = extract_title_and_hotspot(final_content, date_info)
    if not extracted_hotspot or len(extracted_hotspot) < 50:
        extracted_hotspot = hotspot_content  # 最后使用传入的参数
    
    # 清理热点聚焦内容：移除标题行和Markdown格式标记
    if extracted_hotspot:
        lines = extracted_hotspot.split('\n')
        cleaned_lines = []
        skip_title = True
        for line in lines:
            line_stripped = line.strip()
            # 跳过标题行和分隔线
            if skip_title and (line_stripped.startswith('#') or line_stripped.startswith('###') or 
                              '热点聚焦' in line_stripped or line_stripped.startswith('---') or 
                              line_stripped == ''):
                continue
            skip_title = False
            # 移除Markdown格式标记，但保留内容
            cleaned_line = line_stripped.replace('###', '').replace('**', '').strip()
            if cleaned_line:
                cleaned_lines.append(cleaned_line)
        extracted_hotspot = '\n'.join(cleaned_lines).strip()
        # 规范化换行符：清理多余的换行符
        extracted_hotspot = normalize_newlines(extracted_hotspot)
    
    # 解析各个章节的新闻
    section_E = parse_section_content(polished_results.get("E", ""), "E")
    section_S = parse_section_content(polished_results.get("S", ""), "S")
    section_G = parse_section_content(polished_results.get("G", ""), "G")
    
    report_data = {
        "report_metadata": {
            "title": report_label,
            "report_type": date_info.get("report_type", "weekly"),
            "report_period": {
                "start_date": date_info["start_date_chinese"],
                "end_date": date_info["end_date_chinese"],
                "start_date_iso": date_info["start_date_iso"],
                "end_date_iso": date_info["end_date_iso"],
                "date_range": date_info["date_range_chinese"]
            },
            "generation_time": datetime.now().strftime('%Y年%m月%d日 %H:%M:%S'),
            "generation_time_iso": datetime.now().isoformat(),
            "agent": agent,
            "model": model
        },
        "report_content": {
            "title": title,
            "hotspot_focus": extracted_hotspot,
            "environmental": {
                "section_title": "环境（E）动态",
                "news_items": section_E
            },
            "social": {
                "section_title": "社会（S）动态",
                "news_items": section_S
            },
            "governance": {
                "section_title": "公司治理（G）动态",
                "news_items": section_G
            }
        }
    }
    
    # 保存为 JSON 文件
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
    
    safe_print(f"\n格式化报告已保存至：{filename}")
    return filename
