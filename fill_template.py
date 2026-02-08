#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
填充 Word 模板（命令行接口）
支持周报/日报 JSON，自动查找最新或指定 JSON 并填充 Word。
"""
import sys
from word.word_filler import fill_word_template


def main():
    import argparse

    parser = argparse.ArgumentParser(description="填充 Word 模板（周报/日报 JSON）")
    parser.add_argument("--template", "-t", default="ESG研报模板.docx", help="Word 模板路径")
    parser.add_argument("--json", "-j", default=None, help="JSON 报告路径（默认自动查找最新 ESG投研*_*.json）")
    parser.add_argument("--output", "-o", default=None, help="输出 docx 路径（默认根据 JSON 推断）")
    args = parser.parse_args()

    success, _ = fill_word_template(
        json_path=args.json,
        template_path=args.template,
        output_path=args.output,
    )
    return success


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
