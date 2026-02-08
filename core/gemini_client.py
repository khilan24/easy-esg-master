#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gemini API 客户端模块
封装与 Google Gemini API 的交互功能
"""
import time
from google import genai
from google.genai import types
from .utils import safe_print

# 长请求超时（毫秒），避免热点聚焦/合并等长 prompt 触发 SDK 默认约 60s 超时
HTTP_TIMEOUT_MS = 300000  # 5 分钟


class GeminiClient:
    """Gemini API 客户端封装类"""
    
    def __init__(self, api_key, agent=None, model=None):
        """
        初始化客户端
        
        Args:
            api_key: API Key
            agent: Deep Research Agent 名称（可选）
            model: 模型名称（可选）
        """
        self.api_key = api_key
        self.agent = agent or "deep-research-pro-preview-12-2025"
        self.model = model or "gemini-3-pro-preview"
        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=HTTP_TIMEOUT_MS),
        )
    
    def call_deep_research(self, prompt, domain_name):
        """
        调用 Deep Research Agent 进行研究
        
        Args:
            prompt: 研究提示词
            domain_name: 领域名称（如"环境(E)"）
        
        Returns:
            研究结果文本
        """
        safe_print(f"\n[{domain_name}] 开始 Deep Research...")
        
        try:
            initial_interaction = self.client.interactions.create(
                input=prompt,
                agent=self.agent,
                background=True
            )
            
            interaction_id = initial_interaction.id
            safe_print(f"[{domain_name}] 研究任务已启动，Interaction ID: {interaction_id}")
            
            # 轮询结果
            poll_count = 0
            last_step_count = 0
            
            while True:
                poll_count += 1
                interaction = self.client.interactions.get(interaction_id)
                status = interaction.status
                
                # 尝试获取迭代次数信息（仅用于显示）
                current_step_count = None
                if hasattr(interaction, 'steps') and interaction.steps:
                    current_step_count = len(interaction.steps)
                elif hasattr(interaction, 'step_count'):
                    current_step_count = interaction.step_count
                elif hasattr(interaction, 'metadata') and interaction.metadata:
                    if isinstance(interaction.metadata, dict):
                        current_step_count = interaction.metadata.get('step_count') or interaction.metadata.get('steps')
                
                # 记录迭代次数变化
                if current_step_count is not None and current_step_count != last_step_count:
                    last_step_count = current_step_count
                    safe_print(f"[{domain_name}] [轮询 {poll_count}] 迭代次数: {current_step_count}, 状态: {status}")
                elif poll_count % 3 == 0:  # 每3次轮询打印一次状态
                    if current_step_count is not None:
                        safe_print(f"[{domain_name}] [轮询 {poll_count}] 迭代次数: {current_step_count}, 状态: {status}")
                    else:
                        safe_print(f"[{domain_name}] [轮询 {poll_count}] 状态: {status}")
                
                if status == "completed":
                    final_step_count = current_step_count if current_step_count is not None else last_step_count
                    if final_step_count is not None:
                        safe_print(f"[{domain_name}] [完成] 研究完成！最终迭代次数: {final_step_count}")
                    else:
                        safe_print(f"[{domain_name}] [完成] 研究完成！")
                    
                    # 获取最终报告
                    result = None
                    if interaction.outputs and len(interaction.outputs) > 0:
                        text_output = None
                        for output in interaction.outputs:
                            if hasattr(output, 'type') and output.type == "text":
                                text_output = output
                                break
                            elif hasattr(output, 'text'):
                                text_output = output
                                break
                        
                        if text_output:
                            if hasattr(text_output, 'text'):
                                result = text_output.text
                            else:
                                result = str(text_output)
                        else:
                            last_output = interaction.outputs[-1]
                            if hasattr(last_output, 'text'):
                                result = last_output.text
                            else:
                                result = str(last_output)
                    else:
                        result = str(interaction)
                    
                    if result is not None:
                        return result
                    else:
                        raise Exception(f"[{domain_name}] 无法获取研究结果")
                        
                elif status in ["failed", "cancelled"]:
                    error_msg = f"[{domain_name}] [失败] 任务失败，状态: {status}"
                    if hasattr(interaction, 'error'):
                        error_msg += f"，错误信息: {interaction.error}"
                    raise Exception(error_msg)
                
                time.sleep(10)  # 每10秒轮询一次
                
        except Exception as e:
            safe_print(f"[{domain_name}] 错误：{str(e)}")
            raise
    
    def call_model(self, prompt, domain_name=None):
        """
        调用 Gemini 模型（非 Deep Research）
        
        Args:
            prompt: 提示词
            domain_name: 领域名称（可选，用于日志）
        
        Returns:
            模型输出文本
        """
        if domain_name:
            safe_print(f"\n[{domain_name}] 开始处理...")
        last_error = None
        for attempt in range(2):
            try:
                interaction = self.client.interactions.create(
                    model=self.model,
                    input=prompt
                )
                if interaction.outputs and len(interaction.outputs) > 0:
                    text_output = None
                    for output in interaction.outputs:
                        if hasattr(output, 'type') and output.type == "text":
                            text_output = output
                            break
                        elif hasattr(output, 'text'):
                            text_output = output
                            break
                    if text_output:
                        result = text_output.text if hasattr(text_output, 'text') else str(text_output)
                    else:
                        last_output = interaction.outputs[-1]
                        result = last_output.text if hasattr(last_output, 'text') else str(last_output)
                    if domain_name:
                        safe_print(f"[{domain_name}] [完成] 处理完成！")
                    return result
                return str(interaction)
            except Exception as e:
                last_error = e
                is_timeout = "timeout" in str(e).lower() or "timed out" in str(e).lower() or "disconnect" in str(e).lower()
                if attempt == 0 and is_timeout:
                    safe_print(f"[{domain_name or 'API'}] 请求超时或断开，3 秒后重试一次…")
                    time.sleep(3)
                    continue
                if domain_name:
                    safe_print(f"[{domain_name}] 错误：{str(e)}")
                raise last_error
