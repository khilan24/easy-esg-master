#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ESG 投研报告 - Web 前端后端
支持周报（上周）与日报（昨日），一键生成、状态查询、结果下载。
支持多任务并行（最多 MAX_CONCURRENT 个），每人按 job_id 查看自己的状态与下载。
"""
import json
import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"

try:
    from core.utils import get_latest_output_subdir, list_output_files_in_subdir
except ImportError:
    get_latest_output_subdir = None
    list_output_files_in_subdir = None

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB

MAX_CONCURRENT = 3
_jobs = {}  # job_id -> { status, message, log_tail, output_files, last_report_label, _proc?, cancelled? }
_jobs_lock = threading.Lock()
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


def _run_pipeline(mode="weekly", provider=None, api_key=None, api_keys=None, job_id=None):
    report_label = REPORT_LABEL_BY_MODE.get(mode, "ESG投研周报")
    job_output_dir = (OUTPUT_DIR / job_id) if job_id else OUTPUT_DIR
    progress_file = job_output_dir / ".progress.json"
    with _jobs_lock:
        if job_id not in _jobs:
            return
        j = _jobs[job_id]
        j["status"] = "running"
        j["message"] = f"正在生成{report_label}（全网深度检索 → 核心观点提炼 → 市场热点聚焦 → 综合研报汇总 → 文档排版生成）…"
        j["log_tail"] = []
        j["output_files"] = []
        j["last_report_label"] = report_label
    try:
        job_output_dir.mkdir(parents=True, exist_ok=True)
        if progress_file.exists():
            progress_file.unlink()
    except Exception:
        pass

    cmd = [sys.executable, "main.py", "--mode", mode]
    if provider in ("gemini", "qwen"):
        cmd.extend(["--provider", provider])
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if job_id:
        env["ESG_JOB_ID"] = job_id
    if provider == "qwen" and api_key and isinstance(api_key, str) and api_key.strip():
        env["ESG_RUNTIME_API_KEY"] = api_key.strip()
    if provider == "gemini" and api_keys and isinstance(api_keys, dict):
        for k in ("E", "S", "G"):
            v = (api_keys.get(k) or "").strip()
            if v:
                env["ESG_RUNTIME_API_KEY_" + k] = v
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
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]["_proc"] = proc
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                line = _clean_log_line(line)
            log_lines.append(line)
            if len(log_lines) > _log_max_lines:
                log_lines.pop(0)
            with _jobs_lock:
                if job_id in _jobs:
                    _jobs[job_id]["log_tail"] = log_lines[-_log_tail_size:]

        proc.wait()
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]["_proc"] = None
            j = _jobs.get(job_id)
        if not j:
            return
        if j.get("cancelled"):
            with _jobs_lock:
                if job_id in _jobs:
                    _jobs[job_id]["status"] = "idle"
                    _jobs[job_id]["message"] = "已取消生成"
                    _jobs[job_id]["log_tail"] = log_lines[-_log_tail_size:]
                    _jobs[job_id].pop("cancelled", None)
            try:
                if progress_file.exists():
                    progress_file.unlink()
            except Exception:
                pass
            return
        if proc.returncode != 0:
            with _jobs_lock:
                if job_id in _jobs:
                    _jobs[job_id]["status"] = "error"
                    _jobs[job_id]["message"] = f"生成失败，退出码 {proc.returncode}。请查看下方运行日志中的错误信息。"
                    _jobs[job_id]["log_tail"] = log_lines[-_log_tail_size:]
            try:
                if progress_file.exists():
                    progress_file.unlink()
            except Exception:
                pass
            return
    except Exception as e:
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]["_proc"] = None
                _jobs[job_id]["status"] = "error"
                _jobs[job_id]["message"] = str(e)
                _jobs[job_id]["log_tail"] = (log_lines[-_log_tail_size:] if log_lines else _jobs[job_id].get("log_tail", []))[-_log_tail_size:]
        try:
            if progress_file.exists():
                progress_file.unlink()
        except Exception:
            pass
        return

    files = []
    base_dir = job_output_dir
    if base_dir.exists() and get_latest_output_subdir and list_output_files_in_subdir:
        subdir = get_latest_output_subdir(base_dir)
        if subdir:
            for name, rel_path in list_output_files_in_subdir(subdir, base_dir):
                is_docx = (name.endswith("_最终版.docx") or (name.startswith("最终版") and name.endswith(".docx")))
                is_json = (name.endswith("_报告.json") or (name.startswith("报告") and name.endswith(".json")) or (name.endswith(".json") and "_报告" in name))
                is_txt = (name.endswith("_原始内容.txt") or (name.startswith("原始内容") and name.endswith(".txt")) or (name.endswith(".txt") and "_原始内容" in name))
                if is_docx or is_json or is_txt:
                    # 下载路径：带 job_id 前缀，便于 /api/download 解析
                    path_for_download = f"{job_id}/{rel_path}" if job_id else rel_path
                    files.append({"name": name, "path": path_for_download})
        if not files:
            for subdir_name in ["weekly", "daily"]:
                subdir_path = base_dir / subdir_name
                if subdir_path.exists() and subdir_path.is_dir():
                    for pattern, check_func in [
                        ("*_最终版.docx", lambda n: n.endswith("_最终版.docx") or (n.startswith("最终版") and n.endswith(".docx"))),
                        ("*_报告.json", lambda n: n.endswith("_报告.json") or (n.startswith("报告") and n.endswith(".json")) or ("_报告" in n and n.endswith(".json"))),
                        ("*_原始内容.txt", lambda n: n.endswith("_原始内容.txt") or (n.startswith("原始内容") and n.endswith(".txt")) or ("_原始内容" in n and n.endswith(".txt"))),
                    ]:
                        for p in sorted(subdir_path.glob(pattern), key=lambda x: x.stat().st_mtime, reverse=True)[:1]:
                            if check_func(p.name):
                                rel_path = f"{subdir_name}/{p.name}"
                                path_for_download = f"{job_id}/{rel_path}" if job_id else rel_path
                                files.append({"name": p.name, "path": path_for_download})
        if not files:
            with _jobs_lock:
                j = _jobs.get(job_id, {})
            label = j.get("last_report_label") if j else None
            if label:
                for subdir_name in ["weekly", "daily"]:
                    subdir_path = base_dir / subdir_name
                    if not subdir_path.is_dir():
                        continue
                    for suffix in ["_最终版.docx", "_报告.json", "_原始内容.txt"]:
                        for p in sorted(subdir_path.glob(f"*{suffix}"), key=lambda x: x.stat().st_mtime, reverse=True)[:1]:
                            if p.is_file():
                                rel_path = f"{subdir_name}/{p.name}"
                                path_for_download = f"{job_id}/{rel_path}" if job_id else rel_path
                                files.append({"name": p.name, "path": path_for_download})
                                break

    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["_proc"] = None
            _jobs[job_id]["status"] = "done"
            _jobs[job_id]["message"] = f"报告已生成，可选择下载 TXT、JSON、Word 文件（共 {len(files)} 个文件）。" if files else "报告已生成，但未找到输出文件。请检查 output 目录。"
            _jobs[job_id]["output_files"] = files
            _jobs[job_id]["log_tail"] = log_lines[-_log_tail_size:]
    try:
        if progress_file.exists():
            progress_file.unlink()
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
        return False, "请在下方输入 API Key", {}
    return True, "", {"available_providers": available}


@app.route("/")
def index():
    return render_template("index.html")


def _read_progress(job_id):
    """读取指定 job 的进度信息"""
    if not job_id:
        return None
    try:
        progress_file = (OUTPUT_DIR / job_id / ".progress.json") if job_id else (OUTPUT_DIR / ".progress.json")
        if progress_file.exists():
            with open(progress_file, "r", encoding="utf-8") as f:
                progress = json.load(f)
            with _jobs_lock:
                j = _jobs.get(job_id)
                if j and j.get("status") == "idle":
                    return None
            return progress
    except Exception:
        pass
    return None


@app.route("/api/status")
def api_status():
    job_id = request.args.get("job_id")
    if not job_id:
        return jsonify({"ok": False, "message": "缺少 job_id"}), 400
    with _jobs_lock:
        if job_id not in _jobs:
            return jsonify({"ok": False, "message": "任务不存在或已过期"}), 404
        j = _jobs[job_id].copy()
    for key in ("_proc", "cancelled"):
        j.pop(key, None)
    progress = _read_progress(job_id)
    if progress:
        j["progress"] = progress
    return jsonify(j)


@app.route("/api/run", methods=["POST"])
def api_run():
    running_count = 0
    with _jobs_lock:
        for j in _jobs.values():
            if j.get("status") == "running":
                running_count += 1
    if running_count >= MAX_CONCURRENT:
        return jsonify({"ok": False, "message": f"当前并发已满（最多 {MAX_CONCURRENT} 个任务），请稍后再试"}), 503
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
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "running",
            "message": "",
            "log_tail": [],
            "output_files": [],
            "last_report_label": None,
        }
    thread = threading.Thread(target=_run_pipeline, args=(mode, provider, api_key, api_keys, job_id))
    thread.daemon = True
    thread.start()
    label = REPORT_LABEL_BY_MODE.get(mode, "ESG投研周报")
    return jsonify({"ok": True, "job_id": job_id, "message": f"已开始生成{label}", "provider": provider})


@app.route("/api/cancel", methods=["POST"])
def api_cancel():
    """中止指定 job 的生成任务"""
    job_id = request.args.get("job_id") or (request.get_json(silent=True) or {}).get("job_id")
    if not job_id:
        return jsonify({"ok": False, "message": "缺少 job_id"}), 400
    with _jobs_lock:
        if job_id not in _jobs:
            return jsonify({"ok": False, "message": "任务不存在或已结束"}), 404
        j = _jobs[job_id]
        proc = j.get("_proc")
        if proc is None:
            return jsonify({"ok": False, "message": "当前任务未在运行"}), 400
        try:
            proc.terminate()
        except Exception:
            pass
        j["cancelled"] = True
        j["_proc"] = None
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
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
