#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Word 模板填充模块
基于 JSON 格式的投研周报，填充 Word 模板中的格式化字符串
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


def load_json_report(json_path):
    """加载 JSON 格式的投研周报"""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def unpack_docx(docx_path, output_dir):
    """解压 docx 文件"""
    output_path = Path(output_dir)
    if output_path.exists():
        shutil.rmtree(output_path)
    output_path.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(docx_path, 'r') as zip_ref:
        zip_ref.extractall(output_path)
    return output_path


def pack_docx(input_dir, output_docx):
    """打包目录为 docx 文件"""
    input_path = Path(input_dir)
    output_path = Path(output_docx)
    if output_path.exists():
        output_path.unlink()
    
    with zipfile.ZipFile(output_docx, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
        for file_path in sorted(input_path.rglob('*')):
            if file_path.is_file():
                arcname = file_path.relative_to(input_path)
                zip_ref.write(file_path, arcname)


def convert_newlines_to_word_xml(text):
    """将文本中的换行符转换为 Word XML 格式
    在 Word XML 中，<w:br/> 和 <w:t> 是同级元素，都在 <w:r> 内
    结构：<w:r><w:t>文本1</w:t><w:br/><w:t>文本2</w:t></w:r>
    
    处理规则：
    - 去除开头和结尾的所有换行符和空白，避免章节间多余空行
    - 将多个连续换行符（2个或更多）压缩为单个换行符（段落之间）
    - 确保章节之间没有多余的换行
    """
    if not isinstance(text, str):
        text = str(text)
    
    # 先转义 XML 特殊字符
    text = (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&apos;'))
    
    # 去除开头和结尾的所有换行符、回车符和空白字符
    text = text.strip('\n\r \t')
    
    # 将多个连续换行符（2个或更多）压缩为单个换行符
    # 这样可以避免段落之间有多余的空行，同时保留必要的段落分隔
    text = re.sub(r'\n{2,}', '\n', text)
    
    # 将单个换行符转换为 Word XML 格式
    # 由于占位符在 <w:t> 标签内，我们需要：
    # 1. 关闭当前的 <w:t> 标签
    # 2. 添加 <w:br/> 换行
    # 3. 重新打开 <w:t> 标签
    # 格式：</w:t><w:br/><w:t>
    
    # 将单个 \n 替换为 </w:t><w:br/><w:t>
    result = text.replace('\n', '</w:t><w:br/><w:t>')
    
    return result


def replace_placeholder_in_xml(xml_content, placeholder, replacement):
    """在 XML 中替换占位符，处理可能被标签分割的情况
    同时处理换行符转换为 Word XML 格式
    """
    # 将换行符转换为 Word XML 格式
    replacement_xml = convert_newlines_to_word_xml(replacement)
    placeholder_text = f"{{{{{placeholder}}}}}"
    
    # 方法1: 直接替换（最简单的情况）
    if placeholder_text in xml_content:
        return xml_content.replace(placeholder_text, replacement_xml), True
    
    # 方法2: 处理被 XML 标签分割的情况
    # 使用平衡括号匹配，找到所有 {{ ... }} 模式，然后检查去除标签后的文本
    
    # 先找到所有可能的 {{ 位置
    start_positions = []
    i = 0
    while i < len(xml_content) - 1:
        if xml_content[i:i+2] == '{{':
            start_positions.append(i)
        i += 1
    
    # 从后往前处理，避免位置偏移
    for start_pos in reversed(start_positions):
        # 找到对应的 }}
        depth = 0
        pos = start_pos + 2
        end_pos = -1
        
        while pos < len(xml_content) - 1:
            if xml_content[pos:pos+2] == '}}':
                if depth == 0:
                    end_pos = pos + 2
                    break
                depth -= 1
            elif xml_content[pos:pos+2] == '{{':
                depth += 1
            pos += 1
        
        if end_pos > 0:
            # 提取占位符内容
            placeholder_content = xml_content[start_pos+2:end_pos-2]
            # 移除 XML 标签，只保留文本
            text_only = re.sub(r'<[^>]+>', '', placeholder_content)
            # 检查是否包含占位符
            if placeholder in text_only:
                # 替换整个占位符区域
                xml_content = xml_content[:start_pos] + replacement_xml + xml_content[end_pos:]
                return xml_content, True
    
    return xml_content, False


def build_replacements(report_data, max_news_per_section=8):
    """构建替换字典
    max_news_per_section: 每个章节的最大新闻数量（模板中准备的占位符数量）
    """
    replacements = {}
    
    def clean_text(text):
        """清理文本：去除首尾空白和换行，压缩连续换行"""
        if not text:
            return ""
        text = str(text).strip('\n\r \t')
        # 压缩多个连续换行为单个换行
        text = re.sub(r'\n{2,}', '\n', text)
        return text
    
    # 1. 日期范围（去除首尾空白和换行）
    date_range = report_data['report_metadata']['report_period']['date_range']
    replacements['日期范围'] = clean_text(date_range)
    
    # 2. 热点聚焦（去除首尾空白和换行）
    hotspot_focus = report_data['report_content']['hotspot_focus']
    replacements['热点聚焦'] = clean_text(hotspot_focus)
    
    # 3. 各章节内容
    sections = {
        '环境': 'environmental',
        '社会': 'social',
        '治理': 'governance'
    }
    
    for section_name_cn, section_key in sections.items():
        section_data = report_data['report_content'][section_key]
        
        # 章节标题（去除首尾空白和换行）
        replacements[f'{section_name_cn}章节标题'] = clean_text(section_data.get('section_title'))
        
        # 新闻项（只填充实际存在的新闻，最多 max_news_per_section 个）
        news_items = section_data['news_items']
        actual_count = len(news_items)
        
        # 只填充实际存在的新闻
        for i in range(1, min(actual_count, max_news_per_section) + 1):
            news = news_items[i - 1]
            replacements[f'{section_name_cn}新闻标题{i}'] = clean_text(news.get('title'))
            replacements[f'{section_name_cn}新闻内容{i}'] = clean_text(news.get('content'))
        
        # 对于超出实际新闻数量的占位符，不添加到 replacements 中
        # 它们会在后续的清理步骤中被删除
    
    return replacements


def clean_remaining_placeholders(xml_content, used_placeholders):
    """清理剩余的占位符，处理被 XML 标签分割的情况
    used_placeholders: 已使用的占位符集合
    """
    # 找到所有 {{ 位置
    start_positions = []
    i = 0
    while i < len(xml_content) - 1:
        if xml_content[i:i+2] == '{{':
            start_positions.append(i)
        i += 1
    
    # 从后往前处理，避免位置偏移
    for start_pos in reversed(start_positions):
        # 找到对应的 }}
        depth = 0
        pos = start_pos + 2
        end_pos = -1
        
        while pos < len(xml_content) - 1:
            if xml_content[pos:pos+2] == '}}':
                if depth == 0:
                    end_pos = pos + 2
                    break
                depth -= 1
            elif xml_content[pos:pos+2] == '{{':
                depth += 1
            pos += 1
        
        if end_pos > 0:
            # 提取占位符内容
            placeholder_content = xml_content[start_pos+2:end_pos-2]
            # 移除 XML 标签，只保留文本
            text_only = re.sub(r'<[^>]+>', '', placeholder_content)
            
            # 检查这个占位符是否在已使用的列表中
            # 如果不在，说明是多余的占位符，需要删除
            is_used = False
            for used_placeholder in used_placeholders:
                if used_placeholder in text_only:
                    is_used = True
                    break
            
            if not is_used:
                # 删除整个占位符区域（包括周围的 XML 结构）
                # 需要找到包含这个占位符的段落，如果段落只包含占位符，则删除整个段落
                # 这里先简单删除占位符本身
                xml_content = xml_content[:start_pos] + xml_content[end_pos:]
    
    return xml_content


def fill_word_template(json_path=None, template_path=None, output_path=None):
    """
    填充 Word 模板的函数
    
    参数：
        json_path: JSON 报告路径，如果为 None，则自动查找最新的 JSON 文件
        template_path: Word 模板路径，默认为 'ESG研报模板.docx'
        output_path: 输出文件路径，默认为 'ESG投研周报_最终版.docx'
    
    返回：
        (success: bool, output_file: Path)
    """
    if template_path is None:
        template_path = Path('ESG研报模板.docx')
    else:
        template_path = Path(template_path)
    
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    if json_path is None:
        if find_latest_report_json:
            json_path = find_latest_report_json(output_dir)
        else:
            json_files = list(output_dir.glob("ESG投研*_*.json")) or list(Path(".").glob("ESG投研*_*.json"))
            json_path = max(json_files, key=lambda p: p.stat().st_mtime) if json_files else None
        if not json_path or not json_path.exists():
            print("错误：未找到 JSON 报告文件（output/weekly|daily/报告_*.json 或旧版 output/*.json）")
            return False, None
        json_path = Path(json_path)
        print(f"自动使用最新的 JSON 文件: {json_path}")
    else:
        json_path = Path(json_path)

    if output_path is None:
        # 与 JSON 同目录输出：20260119_20260125_报告.json -> 20260119_20260125_最终版.docx；兼容 报告_*.json
        stem = json_path.stem
        if stem.endswith("_报告"):
            date_part = stem[:-3]
            output_path = json_path.parent / f"{date_part}_最终版.docx"
        elif stem.startswith("报告_"):
            date_part = stem[3:]
            output_path = json_path.parent / f"{date_part}_最终版.docx"
        else:
            output_path = json_path.parent / "最终版.docx"
    else:
        output_path = Path(output_path)
        if not output_path.is_absolute() and "output" not in str(output_path):
            output_path = output_dir / output_path.name
    
    print("=" * 60)
    print("开始处理 Word 模板")
    print("=" * 60)
    
    # 检查文件
    if not template_path.exists():
        print(f"错误：模板文件不存在: {template_path}")
        return False, None
    
    if not json_path.exists():
        print(f"错误：JSON 文件不存在: {json_path}")
        return False, None
    
    # 加载 JSON
    print(f"\n1. 加载 JSON 报告: {json_path}")
    report_data = load_json_report(json_path)
    
    # 构建替换字典（每个章节最多8个新闻）
    print(f"2. 构建替换字典...")
    replacements = build_replacements(report_data, max_news_per_section=8)
    print(f"   共 {len(replacements)} 个替换项")
    
    # 解压模板
    print(f"\n3. 解压 Word 模板: {template_path}")
    temp_dir = unpack_docx(template_path, "temp_template_unpacked")
    
    # 读取 document.xml
    document_xml_path = temp_dir / "word" / "document.xml"
    print(f"4. 读取 document.xml...")
    with open(document_xml_path, 'r', encoding='utf-8') as f:
        xml_content = f.read()
    
    # 执行替换
    print(f"\n5. 执行替换...")
    replaced_count = 0
    for placeholder, replacement in replacements.items():
        xml_content, success = replace_placeholder_in_xml(xml_content, placeholder, replacement)
        if success:
            replaced_count += 1
            print(f"   [OK] {{{{ {placeholder} }}}}")
    
    print(f"\n   共替换了 {replaced_count}/{len(replacements)} 个占位符")
    
    # 清理多余的换行：移除连续的 <w:br/> 标签（保留单个）
    print(f"\n6. 清理多余的换行...")
    # 匹配连续的 </w:t><w:br/><w:t></w:t><w:br/><w:t> 模式，压缩为单个
    # 注意：需要匹配完整的模式，包括可能的空文本标签
    xml_content = re.sub(r'(</w:t><w:br/><w:t>){2,}', '</w:t><w:br/><w:t>', xml_content)
    # 清理空文本标签之间的换行：<w:t></w:t><w:br/><w:t></w:t> -> 删除
    xml_content = re.sub(r'<w:t></w:t><w:br/><w:t></w:t>', '', xml_content)
    # 清理开头和结尾的换行标签（如果前面或后面是空文本标签）
    xml_content = re.sub(r'^(</w:t><w:br/><w:t>)+', '', xml_content)
    xml_content = re.sub(r'(</w:t><w:br/><w:t>)+$', '', xml_content)
    
    # 清理剩余的占位符（未使用的占位符）
    print(f"\n7. 清理剩余的占位符...")
    used_placeholders = set(replacements.keys())
    xml_content = clean_remaining_placeholders(xml_content, used_placeholders)
    
    # 保存 XML
    print(f"8. 保存 document.xml...")
    with open(document_xml_path, 'w', encoding='utf-8') as f:
        f.write(xml_content)
    
    # 打包
    print(f"\n9. 打包 Word 文件: {output_path}")
    pack_docx(temp_dir, output_path)
    
    # 清理
    print(f"10. 清理临时文件...")
    shutil.rmtree(temp_dir)
    
    print(f"\n" + "=" * 60)
    print(f"完成！输出文件: {output_path}")
    print("=" * 60)
    return True, output_path
