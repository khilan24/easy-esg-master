#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PPT 模板填充模块
基于 JSON 格式的投研周报，填充 PPT 模板中的 {{占位符}}，与 Word 使用相同占位符，另增 {{报告日期}}
"""
import json
import re
import zipfile
import shutil
from pathlib import Path

try:
    from core.utils import find_latest_report_json
except ImportError:
    find_latest_report_json = None

from .word_filler import load_json_report, build_replacements


def _build_ppt_replacements(report_data, max_news_per_section=8):
    """构建 PPT 替换字典，在 Word 基础上增加 {{报告日期}}"""
    replacements = build_replacements(report_data, max_news_per_section)
    gen_time = report_data.get("report_metadata", {}).get("generation_time", "")
    if gen_time:
        replacements["报告日期"] = gen_time.split()[0] if " " in gen_time else gen_time
    return replacements


def _escape_xml(text):
    """转义 XML 特殊字符"""
    if not isinstance(text, str):
        text = str(text)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _convert_newlines_to_pptx_xml(text):
    """将换行符转换为 PPTX DrawingML 格式"""
    if not isinstance(text, str):
        text = str(text)
    text = text.strip("\n\r \t")
    text = re.sub(r"\n{2,}", "\n", text)
    return text.replace("\n", "</a:t><a:br/><a:t>")


def _replace_placeholder_in_xml(xml_content, placeholder, replacement):
    """在 XML 中替换占位符"""
    replacement_xml = _convert_newlines_to_pptx_xml(replacement)
    placeholder_text = f"{{{{{placeholder}}}}}"

    if placeholder_text in xml_content:
        return xml_content.replace(placeholder_text, replacement_xml), True

    start_positions = []
    i = 0
    while i < len(xml_content) - 1:
        if xml_content[i : i + 2] == "{{":
            start_positions.append(i)
        i += 1

    for start_pos in reversed(start_positions):
        depth = 0
        pos = start_pos + 2
        end_pos = -1
        while pos < len(xml_content) - 1:
            if xml_content[pos : pos + 2] == "}}":
                if depth == 0:
                    end_pos = pos + 2
                    break
                depth -= 1
            elif xml_content[pos : pos + 2] == "{{":
                depth += 1
            pos += 1
        if end_pos > 0:
            placeholder_content = xml_content[start_pos + 2 : end_pos - 2]
            text_only = re.sub(r"<[^>]+>", "", placeholder_content)
            if placeholder in text_only:
                xml_content = xml_content[:start_pos] + replacement_xml + xml_content[end_pos:]
                return xml_content, True
    return xml_content, False


def _clean_remaining_placeholders(xml_content, used_placeholders):
    """清理剩余的占位符"""
    start_positions = []
    i = 0
    while i < len(xml_content) - 1:
        if xml_content[i : i + 2] == "{{":
            start_positions.append(i)
        i += 1

    for start_pos in reversed(start_positions):
        depth = 0
        pos = start_pos + 2
        end_pos = -1
        while pos < len(xml_content) - 1:
            if xml_content[pos : pos + 2] == "}}":
                if depth == 0:
                    end_pos = pos + 2
                    break
                depth -= 1
            elif xml_content[pos : pos + 2] == "{{":
                depth += 1
            pos += 1
        if end_pos > 0:
            placeholder_content = xml_content[start_pos + 2 : end_pos - 2]
            text_only = re.sub(r"<[^>]+>", "", placeholder_content)
            is_used = any(used in text_only for used in used_placeholders)
            if not is_used:
                xml_content = xml_content[:start_pos] + xml_content[end_pos:]
    return xml_content


def fill_ppt_template(json_path=None, template_path=None, output_path=None):
    """
    填充 PPT 模板

    参数：
        json_path: JSON 报告路径，若为 None 则自动查找最新
        template_path: PPT 模板路径，默认为 templates/ESG研报模板.pptx 或根目录
        output_path: 输出文件路径

    返回：
        (success: bool, output_file: Path)
    """
    if template_path is None:
        p = Path("templates/ESG研报模板.pptx")
        template_path = p if p.exists() else Path("ESG研报模板.pptx")
    else:
        template_path = Path(template_path)

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    if json_path is None:
        if find_latest_report_json:
            json_path = find_latest_report_json(output_dir)
        else:
            json_files = list(output_dir.glob("**/*_报告.json")) or list(Path(".").glob("**/*_报告.json"))
            json_path = max(json_files, key=lambda p: p.stat().st_mtime) if json_files else None
        if not json_path or not json_path.exists():
            print("错误：未找到 JSON 报告文件")
            return False, None
        json_path = Path(json_path)
    else:
        json_path = Path(json_path)

    if output_path is None:
        stem = json_path.stem
        if stem.endswith("_报告"):
            date_part = stem[:-3]
        elif stem.startswith("报告_"):
            date_part = stem[3:]
        else:
            date_part = stem
        output_path = json_path.parent / f"{date_part}_最终版.pptx"
    else:
        output_path = Path(output_path)

    if not template_path.exists():
        print(f"错误：PPT 模板不存在: {template_path}")
        return False, None
    if not json_path.exists():
        print(f"错误：JSON 文件不存在: {json_path}")
        return False, None

    report_data = load_json_report(json_path)
    replacements = _build_ppt_replacements(report_data, max_news_per_section=8)

    temp_dir = Path("temp_ppt_unpacked")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    with zipfile.ZipFile(template_path, "r") as zf:
        zf.extractall(temp_dir)

    replaced_count = 0
    for xml_file in temp_dir.rglob("*.xml"):
        try:
            with open(xml_file, "r", encoding="utf-8") as f:
                xml_content = f.read()
        except Exception:
            continue

        file_changed = False
        for placeholder, replacement in replacements.items():
            xml_content, success = _replace_placeholder_in_xml(xml_content, placeholder, replacement)
            if success:
                replaced_count += 1
                file_changed = True

        if file_changed:
            xml_content = _clean_remaining_placeholders(xml_content, set(replacements.keys()))
            with open(xml_file, "w", encoding="utf-8") as f:
                f.write(xml_content)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(temp_dir.rglob("*")):
            if f.is_file():
                arcname = f.relative_to(temp_dir)
                zf.write(f, arcname)

    shutil.rmtree(temp_dir)
    return True, output_path
