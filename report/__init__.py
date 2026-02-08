"""
报告处理模块
包含报告格式化和保存功能
"""
from .report_formatter import (
    parse_section_content,
    extract_title_and_hotspot,
    normalize_newlines
)
from .report_saver import save_raw_content, save_formatted_report

__all__ = [
    'parse_section_content',
    'extract_title_and_hotspot',
    'normalize_newlines',
    'save_raw_content',
    'save_formatted_report',
]
