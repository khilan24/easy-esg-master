#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ESG 投研报告 - Web 前端后端
支持周报（上周）与日报（昨日），一键生成、状态查询、结果下载。
"""
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
PROGRESS_FILE = OUTPUT_DIR / ".progress.json"

try:
    from core.utils import get_latest_output_subdir, list_output_files_in_subdir
except ImportError:
    get_latest_output_subdir = None
    list_output_files_in_subdir = None

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB

_state = {"status": "idle", "message": "", "log_tail": [], "output_files": [], "last_report_label": None}
_state_lock = threading.Lock()
_log_max_lines = 200
_log_tail_size = 80

REPORT_LABEL_BY_MODE = {"weekly": "ESG投研周报", "daily": "ESG投研日报"}


def _clean_log_line(line):
    """清理日志行中的乱码字符"""
    if not line:
        return line
    import re
    # 移除明显的乱码模式（连续的替换字符或无法显示的字符）
    # 替换字符 � 通常表示编码错误
    if '�' in line:
        # 如果替换字符过多，可能是编码问题，尝试清理
        line = re.sub(r'�+', '[编码错误]', line)
    # 移除其他无法正确显示的字符（保留常见的中文、英文、数字、标点）
    # 这里不做太激进的清理，只处理明显的乱码
    return line


def _run_pipeline(mode="weekly", provider=None, api_key=None, api_keys=None):
    global _state
    report_label = REPORT_LABEL_BY_MODE.get(mode, "ESG投研周报")
    with _state_lock:
        _state["status"] = "running"
        _state["message"] = f"正在生成{report_label}（Deep Research → 润色 → 合并 → Word）…"
        _state["log_tail"] = []
        _state["output_files"] = []
        _state["last_report_label"] = report_label
    try:
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()
    except Exception:
        pass

    cmd = [sys.executable, "main.py", "--mode", mode]
    if provider in ("gemini", "qwen"):
        cmd.extend(["--provider", provider])
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    # 强制使用UTF-8编码，避免Windows终端GBK编码导致的乱码
    env["PYTHONIOENCODING"] = "utf-8"
    if provider == "qwen" and api_key and isinstance(api_key, str) and api_key.strip():
        env["ESG_RUNTIME_API_KEY"] = api_key.strip()
    if provider == "gemini" and api_keys and isinstance(api_keys, dict):
        for k in ("E", "S", "G"):
            v = (api_keys.get(k) or "").strip()
            if v:
                env["ESG_RUNTIME_API_KEY_" + k] = v
        # 若只填了一个通用 Key（前端兼容）
        single = (api_key or "").strip() if isinstance(api_key, str) else ""
        if single and not any(env.get("ESG_RUNTIME_API_KEY_" + k) for k in ("E", "S", "G")):
            env["ESG_RUNTIME_API_KEY"] = single
    log_lines = []
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        with _state_lock:
            _state["_proc"] = proc
        for line in proc.stdout:
            line = line.rstrip()
            # 清理可能的乱码字符（替换无法正确显示的字符）
            if line:
                # 尝试检测并清理明显的乱码模式（如连续的替换字符）
                line = _clean_log_line(line)
            log_lines.append(line)
            if len(log_lines) > _log_max_lines:
                log_lines.pop(0)
            with _state_lock:
                _state["log_tail"] = log_lines[-_log_tail_size:]

        proc.wait()
        with _state_lock:
            _state["_proc"] = None
            if _state.get("cancelled"):
                _state["status"] = "idle"
                _state["message"] = "已取消生成"
                _state["log_tail"] = log_lines[-_log_tail_size:]
                del _state["cancelled"]
                try:
                    if PROGRESS_FILE.exists():
                        PROGRESS_FILE.unlink()
                except Exception:
                    pass
                return
            if proc.returncode != 0:
                _state["status"] = "error"
                _state["message"] = f"生成失败，退出码 {proc.returncode}。请查看下方运行日志中的错误信息。"
                _state["log_tail"] = log_lines[-_log_tail_size:]
                try:
                    if PROGRESS_FILE.exists():
                        PROGRESS_FILE.unlink()
                except Exception:
                    pass
                return
    except Exception as e:
        with _state_lock:
            _state["_proc"] = None
            _state["status"] = "error"
            _state["message"] = str(e)
            _state["log_tail"] = (log_lines[-_log_tail_size:] if log_lines else _state.get("log_tail", []))[-_log_tail_size:]
        try:
            if PROGRESS_FILE.exists():
                PROGRESS_FILE.unlink()
        except Exception:
            pass
        return

    files = []
    if OUTPUT_DIR.exists():
        if get_latest_output_subdir and list_output_files_in_subdir:
            subdir = get_latest_output_subdir(OUTPUT_DIR)
            if subdir:
                # 从子目录收集文件
                for name, rel_path in list_output_files_in_subdir(subdir, OUTPUT_DIR):
                    # 匹配 Word 文件：*_最终版.docx 或 最终版*.docx
                    is_docx = (name.endswith("_最终版.docx") or 
                              (name.startswith("最终版") and name.endswith(".docx")))
                    # 匹配 JSON 文件：*_报告.json 或 报告*.json
                    is_json = (name.endswith("_报告.json") or 
                              (name.startswith("报告") and name.endswith(".json")) or
                              (name.endswith(".json") and "_报告" in name))
                    # 匹配 TXT 文件：*_原始内容.txt 或 原始内容*.txt
                    is_txt = (name.endswith("_原始内容.txt") or 
                             (name.startswith("原始内容") and name.endswith(".txt")) or
                             (name.endswith(".txt") and "_原始内容" in name))
                    
                    if is_docx or is_json or is_txt:
                        files.append({"name": name, "path": rel_path})
        
        # 如果子目录收集失败，尝试从最新子目录直接查找
        if not files:
            for subdir_name in ["weekly", "daily"]:
                subdir_path = OUTPUT_DIR / subdir_name
                if subdir_path.exists() and subdir_path.is_dir():
                    # 查找最新的三个文件类型
                    for pattern, check_func in [
                        ("*_最终版.docx", lambda n: n.endswith("_最终版.docx") or (n.startswith("最终版") and n.endswith(".docx"))),
                        ("*_报告.json", lambda n: n.endswith("_报告.json") or (n.startswith("报告") and n.endswith(".json")) or ("_报告" in n and n.endswith(".json"))),
                        ("*_原始内容.txt", lambda n: n.endswith("_原始内容.txt") or (n.startswith("原始内容") and n.endswith(".txt")) or ("_原始内容" in n and n.endswith(".txt"))),
                    ]:
                        for p in sorted(subdir_path.glob(pattern), key=lambda x: x.stat().st_mtime, reverse=True)[:1]:
                            if check_func(p.name):
                                rel_path = f"{subdir_name}/{p.name}"
                                files.append({"name": p.name, "path": rel_path})
        
        # 兼容：无子目录时仍从 output 根目录按 label 收集
        if not files and _state.get("last_report_label"):
            label = _state["last_report_label"]
            # 收集 Word 文件
            docx_path = OUTPUT_DIR / f"{label}_最终版.docx"
            if docx_path.exists():
                files.append({"name": docx_path.name, "path": docx_path.name})
            # 收集 JSON 文件
            for p in sorted(OUTPUT_DIR.glob(f"{label}_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:3]:
                files.append({"name": p.name, "path": p.name})
            # 收集 TXT 文件
            for p in sorted(OUTPUT_DIR.glob(f"{label}_*.txt"), key=lambda x: x.stat().st_mtime, reverse=True)[:3]:
                if "_原始内容" in p.name or p.name.startswith("原始内容"):
                    files.append({"name": p.name, "path": p.name})

    with _state_lock:
        _state["_proc"] = None
        _state["status"] = "done"
        if files:
            _state["message"] = f"报告已生成，可选择下载 TXT、JSON、Word 文件（共 {len(files)} 个文件）。"
        else:
            _state["message"] = "报告已生成，但未找到输出文件。请检查 output 目录。"
        _state["output_files"] = files
        _state["log_tail"] = log_lines[-_log_tail_size:]

    # 任务完成后，清除进度文件，下次启动时不会显示上次的运行时长
    try:
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()
    except Exception:
        pass


def _check_config(provider=None, api_key_override=None, api_keys_override=None):
    """
    校验配置。provider 为 None 时检查是否至少有一种可用。
    api_key_override: 前端传入的单个 API Key（千问或 Gemini 通用）。
    api_keys_override: 前端传入的 Gemini E/S/G 三个 Key，dict {"E","S","G"}。
    返回 (ok, message, extra)。extra 可含 provider、available_providers。
    无 config.json 时仅根据前端传入的 Key 校验，有则合并文件与前端 Key。
    """
    cfg = PROJECT_ROOT / "config.json"
    available = []

    if cfg.exists():
        try:
            with open(cfg, "r", encoding="utf-8") as f:
                data = json.load(f)
            gemini_block = data.get("gemini") if isinstance(data.get("gemini"), dict) else {}
            qwen_block = data.get("qwen") if isinstance(data.get("qwen"), dict) else {}
            api_key = data.get("api_key") or gemini_block.get("api_key") or (data.get("api_keys") or gemini_block.get("api_keys") or {}).get("E")
            if api_key and str(api_key).strip() and not str(api_key).startswith("YOUR_"):
                available.append("gemini")
            qwen_key = data.get("qwen_api_key") or qwen_block.get("api_key") or os.environ.get("DASHSCOPE_API_KEY") or ""
            if qwen_key and str(qwen_key).strip() and not str(qwen_key).startswith("YOUR_"):
                available.append("qwen")
        except Exception as e:
            return False, str(e), {}

    # 前端传入的 Key 视为已配置（无 config 时也仅靠此处构建 available）
    if api_key_override and str(api_key_override).strip() and "qwen" not in available:
        available.append("qwen")
    if api_keys_override and isinstance(api_keys_override, dict):
        e, s, g = (api_keys_override.get("E") or "").strip(), (api_keys_override.get("S") or "").strip(), (api_keys_override.get("G") or "").strip()
        if e and s and g and "gemini" not in available:
            available.append("gemini")

    if provider == "gemini":
        if "gemini" not in available:
            return False, "请在上方输入 Gemini 的 E、S、G 三个 API Key，或在 config.json 中配置。", {"available_providers": available}
        return True, "", {"provider": "gemini", "available_providers": available}
    if provider == "qwen":
        if "qwen" not in available:
            return False, "请在上方输入千问 API Key，或在 config.json 中配置 qwen_api_key。", {"available_providers": available}
        return True, "", {"provider": "qwen", "available_providers": available}
    if provider is not None:
        return False, "不支持的 provider，请使用 gemini 或 qwen。", {}
    if not available:
        return False, "请在上方输入 API Key，或至少在 config.json 中配置 Gemini / 千问 之一。", {}
    return True, "", {"available_providers": available}


@app.route("/")
def index():
    return render_template("index.html")


def _read_progress():
    """读取进度信息"""
    try:
        if PROGRESS_FILE.exists():
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                progress = json.load(f)
            # 如果后端状态为idle，不返回进度信息，让前端清零显示
            with _state_lock:
                if _state.get("status") == "idle":
                    return None
            return progress
    except Exception:
        pass
    return None


@app.route("/api/status")
def api_status():
    progress = _read_progress()
    with _state_lock:
        payload = {
            "status": _state["status"],
            "message": _state["message"],
            "log_tail": _state.get("log_tail", []),
            "output_files": _state.get("output_files", []),
            "last_report_label": _state.get("last_report_label"),
        }
        if progress:
            payload["progress"] = progress
        return jsonify(payload)


@app.route("/api/run", methods=["POST"])
def api_run():
    with _state_lock:
        if _state["status"] == "running":
            return jsonify({"ok": False, "message": "已有任务在运行中"}), 409
    mode = "weekly"
    provider = None
    api_key = None
    api_keys = None
    try:
        data = request.get_json(silent=True) or {}
        mode = data.get("mode", "weekly")
        if mode not in ("weekly", "daily"):
            mode = "weekly"
        provider = data.get("provider")
        if provider not in ("gemini", "qwen"):
            provider = None
        api_key = data.get("api_key") or ""
        api_keys = data.get("api_keys")
        if not isinstance(api_keys, dict):
            api_keys = None
    except Exception:
        pass
    ok, err, extra = _check_config(provider, api_key_override=api_key, api_keys_override=api_keys)
    if not ok:
        return jsonify({"ok": False, "message": err}), 400
    if provider is None and extra.get("available_providers"):
        provider = extra["available_providers"][0]
    thread = threading.Thread(target=_run_pipeline, args=(mode, provider, api_key, api_keys))
    thread.daemon = True
    thread.start()
    label = REPORT_LABEL_BY_MODE.get(mode, "ESG投研周报")
    return jsonify({"ok": True, "message": f"已开始生成{label}", "provider": provider})


@app.route("/api/cancel", methods=["POST"])
def api_cancel():
    """中止当前正在运行的生成任务"""
    with _state_lock:
        proc = _state.get("_proc")
        if proc is None:
            return jsonify({"ok": False, "message": "当前没有正在运行的任务"}), 400
        try:
            proc.terminate()
        except Exception:
            pass
        _state["cancelled"] = True
        _state["_proc"] = None
    return jsonify({"ok": True, "message": "已中止生成"})


@app.route("/api/config-check")
def api_config_check():
    provider = request.args.get("provider")
    if provider not in ("gemini", "qwen"):
        provider = None
    ok, message, extra = _check_config(provider)
    return jsonify({"ok": ok, "message": message, **extra})


@app.route("/api/download/<path:filename>")
def api_download(filename):
    if ".." in filename or filename.startswith("/") or "\\" in filename:
        return "Invalid path", 400
    path = (OUTPUT_DIR / filename).resolve()
    try:
        path.relative_to(OUTPUT_DIR.resolve())
    except ValueError:
        return "Invalid path", 400
    if not path.exists() or not path.is_file():
        return "Not found", 404
    return send_file(
        str(path),
        as_attachment=True,
        download_name=path.name,
        mimetype="application/octet-stream",
    )


if __name__ == "__main__":
    os.chdir(PROJECT_ROOT)
    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / "weekly").mkdir(exist_ok=True)
    (OUTPUT_DIR / "daily").mkdir(exist_ok=True)
    # 启动时清除进度文件，确保每次启动前端时运行时长清零
    try:
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()
    except Exception:
        pass
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
