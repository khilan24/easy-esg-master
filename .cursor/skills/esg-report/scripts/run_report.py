#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ESG 投研报告全流程入口（在项目根目录运行）
1. 从 skill 的 assets 同步模板、提示词、config 示例到项目（若缺失）
2. 运行项目 main.py：Deep Research(E/S/G) → 润色 → 热点聚焦 → 合并 → 保存 JSON → 填充 Word
支持 --mode weekly（周报，上周）或 --mode daily（日报，昨日）。默认 weekly。
若不在项目根目录，会提示在 easy-esg-master 根目录运行或单独使用 fill_word.py。
"""
import argparse
import os
import shutil
import sys
from pathlib import Path


def _skill_root():
    """Skill 根目录（scripts 的上级）"""
    return Path(__file__).resolve().parent.parent


def _assets_dir():
    return _skill_root() / "assets"


def _sync_assets_to_project(project_dir):
    """将 skill 的 assets 同步到项目：prompts、模板、config.example。不覆盖已有文件。"""
    project_dir = Path(project_dir)
    assets = _assets_dir()
    synced = []

    # 提示词目录
    src_prompts = assets / "prompts"
    dst_prompt = project_dir / "prompt"
    if src_prompts.exists():
        dst_prompt.mkdir(parents=True, exist_ok=True)
        for f in src_prompts.glob("*.txt"):
            dst = dst_prompt / f.name
            if not dst.exists() or dst.stat().st_mtime < f.stat().st_mtime:
                shutil.copy2(f, dst)
                synced.append(f"prompt/{f.name}")

    # Word 模板
    src_tpl = assets / "ESG研报模板.docx"
    dst_tpl = project_dir / "ESG研报模板.docx"
    if src_tpl.exists() and (not dst_tpl.exists() or dst_tpl.stat().st_mtime < src_tpl.stat().st_mtime):
        shutil.copy2(src_tpl, dst_tpl)
        synced.append("ESG研报模板.docx")

    # config 示例（仅当项目无 config.json 时复制为 config.json 占位）
    src_cfg = assets / "config.json.example"
    dst_cfg = project_dir / "config.json"
    if src_cfg.exists() and not dst_cfg.exists():
        shutil.copy2(src_cfg, dst_cfg)
        synced.append("config.json（请填入 API Key）")

    return synced


def _is_project_root(project_dir):
    """判断是否为 easy-esg-master 项目根（有 main.py 和 core/）"""
    d = Path(project_dir)
    return (d / "main.py").exists() and (d / "core").is_dir()


def main():
    parser = argparse.ArgumentParser(description="ESG 投研报告全流程（周报/日报）")
    parser.add_argument("--mode", choices=("weekly", "daily"), default="weekly", help="周报(上周) 或 日报(昨日)，默认 weekly")
    args = parser.parse_args()

    cwd = Path.cwd()
    if not _is_project_root(cwd):
        print("当前目录不是 easy-esg-master 项目根（缺少 main.py 或 core/）。", file=sys.stderr)
        print("请：", file=sys.stderr)
        print("  1. 在项目根目录下运行本脚本：python .cursor/skills/esg-report/scripts/run_report.py [--mode weekly|daily]", file=sys.stderr)
        print("  2. 或先运行 main.py 生成 JSON，再用 scripts/fill_word.py 填充 Word。", file=sys.stderr)
        return 1

    synced = _sync_assets_to_project(cwd)
    if synced:
        print("已从 skill 同步到项目：", ", ".join(synced))
        if "config.json" in " ".join(synced):
            print("请编辑 config.json 填入 API Key 后重新运行。")
            return 0

    # 将 --mode 传给 main.py（插入到 argv 中，main.py 会解析）
    argv_orig = sys.argv
    sys.argv = [argv_orig[0], "--mode", args.mode]

    sys.path.insert(0, str(cwd))
    os.chdir(cwd)
    try:
        import main as main_mod
        main_mod.main()
        return 0
    except Exception as e:
        print(f"运行 main.py 出错: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
