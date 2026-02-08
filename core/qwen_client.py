#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
千问（DashScope）API 客户端模块
封装 Qwen-Deep-Research 与 Qwen 对话模型的调用。
官方说明：qwen-deep-research 仅支持流式输出（stream=True），见
https://help.aliyun.com/zh/model-studio/qwen-deep-research
"""
import dashscope
from .utils import safe_print

DEFAULT_DEEP_RESEARCH_MODEL = "qwen-deep-research"
DEFAULT_CHAT_MODEL = "qwen3-max-preview"


def _collect_stream_content(responses, domain_name):
    """
    按官方文档解析 qwen-deep-research 流式响应：
    response.output.message.content 为每块内容，phase=KeepAlive 可忽略。
    返回累积的文本；若遇非 200 则抛错。
    """
    full_content = []
    for response in responses:
        if getattr(response, "status_code", None) and response.status_code != 200:
            msg = getattr(response, "message", None) or ""
            code = getattr(response, "code", None) or ""
            raise ValueError(f"API 错误 status={response.status_code}, code={code}, message={msg}")
        output = getattr(response, "output", None) or (response.get("output") if isinstance(response, dict) else None)
        if not output:
            continue
        msg = output.get("message", {}) if isinstance(output, dict) else getattr(output, "message", None)
        if not msg:
            continue
        phase = msg.get("phase") if isinstance(msg, dict) else getattr(msg, "phase", None)
        if phase == "KeepAlive":
            continue
        content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", None)
        if content:
            full_content.append(str(content))
    return "".join(full_content).strip() or None


class QwenClient:
    """千问 API 客户端，接口与 GeminiClient 对齐：call_deep_research、call_model"""

    def __init__(self, api_key, model=None, deep_research_model=None):
        self.api_key = api_key
        self.model = model or DEFAULT_CHAT_MODEL
        self.deep_research_model = deep_research_model or DEFAULT_DEEP_RESEARCH_MODEL

    def call_deep_research(self, prompt, domain_name):
        """
        调用 Qwen-Deep-Research：两阶段（反问确认 → 深入研究），返回最终研究报告。
        必须使用流式输出（stream=True），否则会因长连接导致超时。
        """
        safe_print(f"\n[{domain_name}] 开始 Qwen Deep Research（流式）...")
        # 第一阶段：模型反问确认（官方仅支持 stream=True）
        messages_step1 = [{"role": "user", "content": prompt}]
        responses1 = dashscope.Generation.call(
            api_key=self.api_key,
            model=self.deep_research_model,
            messages=messages_step1,
            stream=True,
        )
        step1_content = _collect_stream_content(responses1, domain_name)
        if not step1_content:
            step1_content = "请直接进行深入研究。"
        safe_print(f"[{domain_name}] 第一阶段完成，进入深入研究...")

        # 第二阶段：深入研究，输出完整报告
        messages_step2 = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": step1_content},
            {"role": "user", "content": "请直接基于上述研究主题进行深入研究，输出完整的研究报告内容，无需再追问。"},
        ]
        responses2 = dashscope.Generation.call(
            api_key=self.api_key,
            model=self.deep_research_model,
            messages=messages_step2,
            stream=True,
        )
        result = _collect_stream_content(responses2, domain_name)
        if result:
            safe_print(f"[{domain_name}] [完成] 研究完成！")
            return result
        raise Exception("无法获取研究结果")

    def call_model(self, prompt, domain_name=None):
        """调用千问对话模型（如 qwen3-max-preview）进行润色/热点/合并等。"""
        if domain_name:
            safe_print(f"\n[{domain_name}] 开始处理...")
        messages = [{"role": "user", "content": prompt}]
        resp = dashscope.Generation.call(
            api_key=self.api_key,
            model=self.model,
            messages=messages,
            stream=False,
        )
        result = _get_message_content(resp)
        if result is None:
            raise ValueError("模型未返回有效内容")
        if domain_name:
            safe_print(f"[{domain_name}] [完成] 处理完成！")
        return result


def _get_message_content(response, domain_name=None):
    """从 DashScope Generation 响应中提取 assistant 文本。兼容 dict 与对象及多种返回格式。"""
    if not response:
        return None
    status = getattr(response, "status_code", None) or (response.get("status_code") if isinstance(response, dict) else None)
    if status != 200:
        msg = getattr(response, "message", None) or (response.get("message") if isinstance(response, dict) else None)
        code = getattr(response, "code", None) or (response.get("code") if isinstance(response, dict) else None)
        raise ValueError(f"API 错误 status={status}, code={code}, message={msg}")
    output = getattr(response, "output", None) if not isinstance(response, dict) else response.get("output")
    if not output:
        _log_parse_fail(domain_name, "output 为空")
        return None

    def _str_content(x):
        if x is None:
            return None
        s = str(x).strip()
        return s if s else None

    def _get(obj, *keys):
        if obj is None:
            return None
        for k in keys:
            if isinstance(obj, dict):
                obj = obj.get(k)
            else:
                obj = getattr(obj, k, None)
            if obj is None:
                return None
        return _str_content(obj) if isinstance(obj, (str, int, float)) else None

    # 1. output.text（部分接口）
    text = _get(output, "text") or (getattr(output, "text", None) and _str_content(getattr(output, "text")))
    if text:
        return text

    # 2. output.message -> content / text（Deep Research 等可能返回 message 对象或列表）
    msg = output.get("message") if isinstance(output, dict) else getattr(output, "message", None)
    if msg is not None:
        if isinstance(msg, str) and msg.strip():
            return msg.strip()
        content = _get(msg, "content") or _get(msg, "text") or _get(msg, "body")
        if content:
            return content
        if isinstance(msg, dict):
            for key in ("content", "text", "body"):
                v = msg.get(key)
                if v is not None and (isinstance(v, str) or (isinstance(v, list) and v)):
                    if isinstance(v, str):
                        return _str_content(v)
                    if isinstance(v, list):
                        for part in v:
                            if isinstance(part, dict) and part.get("type") == "text":
                                t = part.get("text")
                                if t:
                                    return _str_content(t)
                            if isinstance(part, str) and part.strip():
                                return part.strip()
        if hasattr(msg, "content"):
            c = getattr(msg, "content", None)
            if c:
                return _str_content(c)
        if hasattr(msg, "text"):
            t = getattr(msg, "text", None)
            if t:
                return _str_content(t)

    # 3. output.choices[0].message.content（OpenAI 兼容格式）
    choices = output.get("choices") if isinstance(output, dict) else getattr(output, "choices", None)
    if choices and len(choices) > 0:
        first = choices[0] if isinstance(choices, list) else (choices[0] if hasattr(choices, "__getitem__") else None)
        if first is not None:
            msg = first.get("message") if isinstance(first, dict) else getattr(first, "message", None)
            if msg is not None:
                content = _get(msg, "content") or _get(msg, "text")
                if content:
                    return content
            # choices[0].text 直接
            direct = first.get("text") if isinstance(first, dict) else getattr(first, "text", None)
            if direct:
                return _str_content(direct)
            direct = first.get("content") if isinstance(first, dict) else getattr(first, "content", None)
            if direct:
                return _str_content(direct)

    # 4. output.result / output.body
    for key in ("result", "body"):
        val = output.get(key) if isinstance(output, dict) else getattr(output, key, None)
        if val and _str_content(val):
            return _str_content(val)

    _log_parse_fail(domain_name, "无有效 content/text")
    return None


def _log_parse_fail(domain_name, reason):
    """解析失败时只打一行核心信息。"""
    prefix = f"[{domain_name}] " if domain_name else ""
    safe_print(f"{prefix}解析失败：{reason}，请检查 API 返回格式或模型可用性。")
