#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运行进度写入模块，供 Web 前端读取并展示阶段与耗时。
"""
import json
import os
import time
from pathlib import Path

PROGRESS_FILE = os.path.join("output", ".progress.json")

_START_TIMES = {}  # stage_id -> start time


def _ensure_output():
    Path("output").mkdir(parents=True, exist_ok=True)


def write_progress(current_stage_id, current_stage_label, completed_stages=None):
    """
    写入当前阶段。completed_stages: [{"id": "stage1", "label": "...", "duration_sec": 120}, ...]
    """
    _ensure_output()
    total_started = _START_TIMES.get("total")
    data = {
        "total_started_at": total_started,
        "current_stage": current_stage_id,
        "current_stage_label": current_stage_label,
        "completed_stages": completed_stages or [],
        "status": "running",
    }
    if total_started:
        data["total_elapsed_sec"] = round(time.time() - total_started, 1)
    try:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=0)
    except Exception:
        pass


def start_total():
    """记录总开始时间，并写入阶段1 开始."""
    _START_TIMES["total"] = time.time()
    _START_TIMES["stage1"] = time.time()
    _ensure_output()
    write_progress("stage1", "Deep Research（E/S/G）", [])


def start_stage(stage_id, stage_label):
    """记录某阶段开始时间."""
    _START_TIMES[stage_id] = time.time()


def end_stage(stage_id, stage_label, completed_stages):
    """结束某阶段，计算耗时并写入下一阶段."""
    elapsed = time.time() - _START_TIMES.get(stage_id, time.time())
    completed_stages.append({
        "id": stage_id,
        "label": stage_label,
        "duration_sec": round(elapsed, 1),
    })
    return completed_stages


def write_progress_done(completed_stages):
    """写入完成状态."""
    _ensure_output()
    total_started = _START_TIMES.get("total")
    data = {
        "total_started_at": total_started,
        "current_stage": "done",
        "current_stage_label": "全部完成",
        "completed_stages": completed_stages,
        "status": "done",
    }
    if total_started:
        data["total_elapsed_sec"] = round(time.time() - total_started, 1)
    try:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=0)
    except Exception:
        pass


def write_progress_error(completed_stages, current_stage_id, current_stage_label):
    """写入错误状态."""
    _ensure_output()
    total_started = _START_TIMES.get("total")
    data = {
        "total_started_at": total_started,
        "current_stage": current_stage_id,
        "current_stage_label": current_stage_label,
        "completed_stages": completed_stages or [],
        "status": "error",
    }
    if total_started:
        data["total_elapsed_sec"] = round(time.time() - total_started, 1)
    try:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=0)
    except Exception:
        pass
