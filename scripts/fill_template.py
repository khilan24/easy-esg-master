#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
填充国信模板（Word + PPT）
每次输出均包含：txt、json、word、pptx。固定使用 templates/ 下的国信模板。
"""
import os
import sys
import shutil
from pathlib import Path

# 保证从项目根目录可导入 core、fill，且工作目录为项目根
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
try:
    os.chdir(_project_root)
except Exception:
    pass

from core.utils import get_template_path, find_latest_report_json
from fill import fill_word_template, fill_ppt_template


def _date_part_from_json_path(json_path):
    """从 JSON 路径推断日期前缀"""
    stem = Path(json_path).stem
    if stem.endswith("_报告"):
        return stem[:-3]
    if stem.startswith("报告_"):
        return stem[3:]
    return stem


def _ensure_txt_in_output(output_dir, date_part):
    """确保输出目录存在 {date_part}_原始内容.txt"""
    output_dir = Path(output_dir)
    txt_name = f"{date_part}_原始内容.txt"
    txt_path = output_dir / txt_name
    if txt_path.exists():
        return
    for kind in ("weekly", "daily"):
        candidate = Path("output") / kind / txt_name
        if candidate.exists():
            shutil.copy2(candidate, txt_path)
            print(f"[补齐] 已复制原始内容: {txt_path}")
            return
    txt_path.write_text("", encoding="utf-8")
    print(f"[补齐] 已创建占位文件: {txt_path}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="填充国信模板，每次输出 txt、json、word、pptx")
    parser.add_argument("--json", "-j", default=None, help="JSON 报告路径（默认自动查找最新 *_报告.json）")
    args = parser.parse_args()

    resolved_json = args.json
    if resolved_json:
        resolved_json = str(_project_root / resolved_json) if not Path(resolved_json).is_absolute() else resolved_json
        if not Path(resolved_json).exists() and (Path.cwd() / args.json).exists():
            resolved_json = str(Path.cwd() / args.json)

    if not resolved_json:
        jp = find_latest_report_json()
        resolved_json = str(jp) if jp else None

    if not resolved_json or not Path(resolved_json).exists():
        print("错误：未找到 JSON 报告文件")
        return False

    word_tpl = get_template_path("docx")
    ppt_tpl = get_template_path("pptx")
    if not Path(word_tpl).exists():
        print(f"错误：Word 模板不存在: {word_tpl}")
        return False
    if not Path(ppt_tpl).exists():
        print(f"错误：PPT 模板不存在: {ppt_tpl}")
        return False

    ok_word, word_out = fill_word_template(json_path=resolved_json, template_path=word_tpl, output_path=None)
    if not ok_word:
        return False

    ok_ppt, ppt_out = fill_ppt_template(json_path=resolved_json, template_path=ppt_tpl, output_path=None)
    if ok_ppt:
        print(f"[PPT] 已填充: {ppt_out}")

    out_dir = Path(resolved_json).parent
    date_part = _date_part_from_json_path(resolved_json)
    _ensure_txt_in_output(out_dir, date_part)
    return True


if __name__ == "__main__":
    try:
        sys.exit(0 if main() else 1)
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
