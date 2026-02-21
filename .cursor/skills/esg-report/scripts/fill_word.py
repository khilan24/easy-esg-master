#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立 Word 模板填充脚本（无项目依赖）
基于 JSON 格式的投研周报填充 Word 模板中的占位符。
可从 skill 的 assets 或任意路径指定模板与 JSON。
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path


def _skill_assets_dir():
    """Skill 的 assets 目录（脚本在 scripts/ 下时，assets 为 ../assets）"""
    return Path(__file__).resolve().parent.parent / "assets"


def load_json_report(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def unpack_docx(docx_path, output_dir):
    import zipfile
    output_path = Path(output_dir)
    if output_path.exists():
        shutil.rmtree(output_path)
    output_path.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(docx_path, "r") as z:
        z.extractall(output_path)
    return output_path


def pack_docx(input_dir, output_docx):
    import zipfile
    input_path = Path(input_dir)
    output_path = Path(output_docx)
    if output_path.exists():
        output_path.unlink()
    with zipfile.ZipFile(output_docx, "w", zipfile.ZIP_DEFLATED) as z:
        for fp in sorted(input_path.rglob("*")):
            if fp.is_file():
                z.write(fp, fp.relative_to(input_path))
    return output_path


def convert_newlines_to_word_xml(text):
    if not isinstance(text, str):
        text = str(text)
    text = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
    text = re.sub(r"\n+", "\n", text)
    return text.replace("\n", "</w:t><w:br/><w:t>")


def replace_placeholder_in_xml(xml_content, placeholder, replacement):
    rep_xml = convert_newlines_to_word_xml(replacement)
    ph_text = f"{{{{{placeholder}}}}}"
    if ph_text in xml_content:
        return xml_content.replace(ph_text, rep_xml), True
    start_positions = []
    i = 0
    while i < len(xml_content) - 1:
        if xml_content[i : i + 2] == "{{":
            start_positions.append(i)
        i += 1
    for start_pos in reversed(start_positions):
        depth, pos, end_pos = 0, start_pos + 2, -1
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
            ph_content = xml_content[start_pos + 2 : end_pos - 2]
            text_only = re.sub(r"<[^>]+>", "", ph_content)
            if placeholder in text_only:
                xml_content = xml_content[:start_pos] + rep_xml + xml_content[end_pos:]
                return xml_content, True
    return xml_content, False


def build_replacements(report_data, max_news_per_section=8):
    replacements = {}
    replacements["日期范围"] = report_data["report_metadata"]["report_period"]["date_range"]
    replacements["热点聚焦"] = report_data["report_content"]["hotspot_focus"]
    sections = {"环境": "environmental", "社会": "social", "治理": "governance"}
    for section_name_cn, section_key in sections.items():
        section_data = report_data["report_content"][section_key]
        replacements[f"{section_name_cn}章节标题"] = section_data["section_title"]
        news_items = section_data["news_items"]
        for i in range(1, min(len(news_items), max_news_per_section) + 1):
            news = news_items[i - 1]
            replacements[f"{section_name_cn}新闻标题{i}"] = news["title"]
            replacements[f"{section_name_cn}新闻内容{i}"] = news["content"]
    return replacements


def clean_remaining_placeholders(xml_content, used_placeholders):
    start_positions = []
    i = 0
    while i < len(xml_content) - 1:
        if xml_content[i : i + 2] == "{{":
            start_positions.append(i)
        i += 1
    for start_pos in reversed(start_positions):
        depth, pos, end_pos = 0, start_pos + 2, -1
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
            ph_content = xml_content[start_pos + 2 : end_pos - 2]
            text_only = re.sub(r"<[^>]+>", "", ph_content)
            is_used = any(p in text_only for p in used_placeholders)
            if not is_used:
                xml_content = xml_content[:start_pos] + xml_content[end_pos:]
    return xml_content


def fill_word_template(json_path, template_path, output_path, max_news=8):
    json_path = Path(json_path)
    template_path = Path(template_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not template_path.exists():
        print(f"错误：模板不存在 {template_path}", file=sys.stderr)
        return False, None
    if not json_path.exists():
        print(f"错误：JSON 不存在 {json_path}", file=sys.stderr)
        return False, None
    report_data = load_json_report(json_path)
    replacements = build_replacements(report_data, max_news_per_section=max_news)
    temp_dir = unpack_docx(template_path, Path("temp_template_fill_word"))
    doc_xml = temp_dir / "word" / "document.xml"
    xml_content = doc_xml.read_text(encoding="utf-8")
    for ph, rep in replacements.items():
        xml_content, _ = replace_placeholder_in_xml(xml_content, ph, rep)
    xml_content = clean_remaining_placeholders(xml_content, set(replacements.keys()))
    doc_xml.write_text(xml_content, encoding="utf-8")
    pack_docx(temp_dir, output_path)
    shutil.rmtree(temp_dir, ignore_errors=True)
    return True, output_path


def main():
    ap = argparse.ArgumentParser(description="用 JSON 报告填充 Word 模板（无项目依赖）")
    ap.add_argument("--json", "-j", default=None, help="JSON 报告路径（默认自动找 output 下最新）")
    ap.add_argument("--template", "-t", default=None, help="Word 模板路径（默认用 skill assets 或当前目录）")
    ap.add_argument("--output", "-o", default=None, help="输出 docx 路径（默认 output/ESG投研周报_最终版.docx）")
    ap.add_argument("--max-news", type=int, default=8, help="每章最多新闻条数")
    args = ap.parse_args()

    assets = _skill_assets_dir()
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    json_path = args.json
    if not json_path:
        candidates = list(output_dir.glob("ESG投研周报_*.json")) + list(Path(".").glob("ESG投研周报_*.json"))
        if not candidates:
            print("错误：未找到 JSON 报告，请用 --json 指定", file=sys.stderr)
            return 1
        json_path = max(candidates, key=lambda p: p.stat().st_mtime)
        print(f"使用最新 JSON: {json_path}")

    template_path = args.template
    if not template_path:
        if (assets / "ESG研报模板.docx").exists():
            template_path = assets / "ESG研报模板.docx"
        elif Path("ESG研报模板.docx").exists():
            template_path = Path("ESG研报模板.docx")
        else:
            print("错误：未找到模板，请将 ESG研报模板.docx 放到项目根或 skill assets，或用 --template 指定", file=sys.stderr)
            return 1

    output_path = args.output
    if not output_path:
        output_path = output_dir / "ESG投研周报_最终版.docx"
    else:
        output_path = Path(output_path)
        if not output_path.is_absolute() and "output" not in str(output_path):
            output_path = output_dir / output_path.name

    ok, out = fill_word_template(json_path, template_path, output_path, max_news=args.max_news)
    if ok:
        print(f"已生成: {out}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
