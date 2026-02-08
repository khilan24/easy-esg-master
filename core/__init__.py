"""
核心功能模块
包含 Gemini API 客户端、研究流程和工具函数
"""
from .gemini_client import GeminiClient
from .research_stages import ResearchPipeline
from .utils import (
    load_config,
    load_prompt,
    get_last_week_date_range,
    get_yesterday_date_range,
    get_date_range_for_mode,
    get_output_subdir,
    get_output_date_suffix,
    get_latest_output_subdir,
    find_latest_report_json,
    list_output_files_in_subdir,
    replace_date_placeholders,
    replace_domain_placeholders,
    safe_print,
)

__all__ = [
    "GeminiClient",
    "ResearchPipeline",
    "load_config",
    "load_prompt",
    "get_last_week_date_range",
    "get_yesterday_date_range",
    "get_date_range_for_mode",
    "get_output_subdir",
    "get_output_date_suffix",
    "get_latest_output_subdir",
    "find_latest_report_json",
    "list_output_files_in_subdir",
    "replace_date_placeholders",
    "replace_domain_placeholders",
    "safe_print",
]
