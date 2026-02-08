#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
研究阶段模块
封装 ESG 报告生成的各个研究阶段
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from .gemini_client import GeminiClient
from .qwen_client import QwenClient
from .utils import load_prompt, replace_date_placeholders, replace_domain_placeholders, safe_print


class ResearchPipeline:
    """研究流程管道类，支持 Gemini 或千问（Qwen）"""
    
    def __init__(self, config):
        """
        初始化研究流程
        
        Args:
            config: 配置字典，含 provider("gemini"|"qwen")、api_keys、api_key、agent、model、qwen_model、qwen_deep_research_model 等
        """
        self.api_keys = config["api_keys"]
        self.api_key = config["api_key"]
        provider = config.get("provider", "gemini")
        
        if provider == "qwen":
            qwen_model = config.get("qwen_model", "qwen3-max-preview")
            qwen_dr_model = config.get("qwen_deep_research_model", "qwen-deep-research")
            self.clients = {
                "E": QwenClient(self.api_keys["E"], deep_research_model=qwen_dr_model),
                "S": QwenClient(self.api_keys["S"], deep_research_model=qwen_dr_model),
                "G": QwenClient(self.api_keys["G"], deep_research_model=qwen_dr_model),
            }
            self.default_client = QwenClient(self.api_key, model=qwen_model, deep_research_model=qwen_dr_model)
        else:
            self.agent = config.get("agent", "deep-research-pro-preview-12-2025")
            self.model = config.get("model", "gemini-3-pro-preview")
            self.clients = {
                "E": GeminiClient(self.api_keys["E"], agent=self.agent),
                "S": GeminiClient(self.api_keys["S"], agent=self.agent),
                "G": GeminiClient(self.api_keys["G"], agent=self.agent),
            }
            self.default_client = GeminiClient(self.api_key, model=self.model)
    
    def stage1_research_parallel(self, date_info):
        """
        阶段1：使用3个不同的API Key并行进行 E、S、G 三个领域的 Deep Research
        
        Args:
            date_info: 日期信息字典
        
        Returns:
            研究结果字典，键为 "E", "S", "G"
        """
        safe_print("\n" + "=" * 60)
        safe_print("阶段1：Deep Research（使用3个API Key并行进行 E、S、G 三个领域）")
        safe_print(f"研究期间：{date_info['date_range_chinese']}")
        safe_print("=" * 60)
        
        # 加载统一提示词模板，按领域与日期替换占位符
        research_template = load_prompt("章节研究.txt")
        prompt_E = replace_domain_placeholders(replace_date_placeholders(research_template, date_info), "E")
        prompt_S = replace_domain_placeholders(replace_date_placeholders(research_template, date_info), "S")
        prompt_G = replace_domain_placeholders(replace_date_placeholders(research_template, date_info), "G")
        
        results = {}
        
        # 使用3个不同的API Key并行执行三个领域的研究
        safe_print("\n并行进行 E、S、G 三个领域的 Deep Research（每个领域使用独立的API Key）")
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(self.clients["E"].call_deep_research, prompt_E, "环境(E)"): "E",
                executor.submit(self.clients["S"].call_deep_research, prompt_S, "社会(S)"): "S",
                executor.submit(self.clients["G"].call_deep_research, prompt_G, "治理(G)"): "G"
            }
            
            for future in as_completed(futures):
                domain = futures[future]
                try:
                    results[domain] = future.result()
                except Exception as e:
                    safe_print(f"[{domain}] 研究失败：{str(e)}")
                    results[domain] = None
        
        return results
    
    def stage2_polish_parallel(self, research_results, date_info):
        """
        阶段2：并行对三个领域的研究结果进行润色
        
        Args:
            research_results: 阶段1的研究结果
            date_info: 日期信息字典
        
        Returns:
            润色后的结果字典
        """
        safe_print("\n" + "=" * 60)
        safe_print("阶段2：并行对 E、S、G 三个领域的研究结果进行润色")
        safe_print(f"研究期间：{date_info['date_range_chinese']}")
        safe_print("=" * 60)
        
        # 加载统一润色提示词模板，按领域与日期替换占位符
        polish_template = load_prompt("章节润色.txt")
        polish_prompts = {}
        for domain in ["E", "S", "G"]:
            if research_results.get(domain):
                template = replace_domain_placeholders(replace_date_placeholders(polish_template, date_info), domain)
                polish_prompts[domain] = f"{template}\n\n以下是需要润色的内容：\n\n{research_results[domain]}"
            else:
                polish_prompts[domain] = None
        
        # 并行执行润色
        polished_results = {}
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {}
            for domain in ["E", "S", "G"]:
                if polish_prompts[domain]:
                    futures[executor.submit(
                        self.default_client.call_model, 
                        polish_prompts[domain], 
                        f"润色-{domain}"
                    )] = domain
            
            for future in as_completed(futures):
                domain = futures[future]
                try:
                    polished_results[domain] = future.result()
                except Exception as e:
                    safe_print(f"[润色-{domain}] 失败：{str(e)}")
                    polished_results[domain] = research_results.get(domain)  # 使用原始结果
        
        return polished_results
    
    def stage3_hotspot_focus(self, polished_results, date_info):
        """
        阶段3：生成热点聚焦部分
        
        Args:
            polished_results: 阶段2的润色结果
            date_info: 日期信息字典
        
        Returns:
            热点聚焦文本
        """
        safe_print("\n" + "=" * 60)
        safe_print("阶段3：生成热点聚焦部分")
        safe_print(f"研究期间：{date_info['date_range_chinese']}")
        safe_print("=" * 60)
        
        hotspot_template = load_prompt("热点聚焦.txt")
        
        # 替换日期占位符
        hotspot_template = replace_date_placeholders(hotspot_template, date_info)
        
        # 构建输入内容（完整内容，不截断，保证质量）
        input_content = f"""
以下是E、S、G三个章节的研究内容：

【环境（E）章节】
{polished_results.get('E', '无内容')}

【社会（S）章节】
{polished_results.get('S', '无内容')}

【治理（G）章节】
{polished_results.get('G', '无内容')}
"""
        
        prompt = f"{hotspot_template}\n\n{input_content}"
        
        hotspot_result = self.default_client.call_model(prompt, "热点聚焦")
        return hotspot_result
    
    def stage4_merge(self, polished_results, hotspot_result, date_info):
        """
        阶段4：合并生成最终报告
        
        Args:
            polished_results: 阶段2的润色结果
            hotspot_result: 阶段3的热点聚焦结果
            date_info: 日期信息字典
        
        Returns:
            最终合并报告文本
        """
        safe_print("\n" + "=" * 60)
        safe_print("阶段4：合并生成最终报告")
        safe_print(f"研究期间：{date_info['date_range_chinese']}")
        safe_print("=" * 60)
        
        merge_template = load_prompt("合并.txt")
        
        # 替换日期占位符
        merge_template = replace_date_placeholders(merge_template, date_info)
        
        # 构建输入内容（完整内容，不截断，保证质量）
        input_content = f"""
【热点聚焦部分】
{hotspot_result}

【环境（E）章节】
{polished_results.get('E', '无内容')}

【社会（S）章节】
{polished_results.get('S', '无内容')}

【治理（G）章节】
{polished_results.get('G', '无内容')}
"""
        
        prompt = f"{merge_template}\n\n{input_content}"
        
        final_result = self.default_client.call_model(prompt, "合并")
        return final_result
