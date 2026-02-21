---
name: esg-report
description: This skill enables AI to generate ESG research reports (weekly or daily) matching the quality of the easy-esg-master project. It covers backend implementation only (no frontend), including Deep Research (E/S/G), polishing, hotspot focus, merging, JSON formatting, and Word template filling. Supports both Gemini and Qwen models.
---

# ESG 投研报告生成（周报 / 日报）

## Overview

本 skill 使 AI 能够生成 **ESG 投研周报**（上周一至上周日）或 **ESG 投研日报**（昨日），输出质量与 easy-esg-master 项目同等。包含完整的后端实现流程：Deep Research（E/S/G 并行）→ 润色 → 热点聚焦 → 合并 → JSON 格式化 → Word 填充。支持 **Gemini** 和 **千问（Qwen）** 两种模型。

## When to Use

Use this skill when:

- The user asks to **完成上周ESG研报** or **完成昨日ESG研报** / 生成 ESG 周报或日报，并希望得到 **整理好的 Word 版**
- The user wants to produce reports (JSON and Word) that meet the same delivery standard as easy-esg-master
- The user needs backend implementation guidance for ESG report generation

## 核心流程（5个阶段）

### 阶段1：Deep Research（E/S/G 并行研究）

**目标**：使用 3 个独立的 API Key 并行进行 E、S、G 三个领域的深度研究。

**实现要点**：
- 使用 `ThreadPoolExecutor` 并行执行三个领域的研究
- Gemini：使用 `GeminiClient.call_deep_research()`，传入 Deep Research Agent（默认 `deep-research-pro-preview-12-2025`）
- Qwen：使用 `QwenClient.call_deep_research()`，传入 Qwen Deep Research 模型（默认 `qwen-deep-research`），**必须使用 `stream=True`**
- 提示词模板：`prompt/章节研究.txt`，需替换日期占位符 `{DATE_RANGE}` 和领域占位符 `{DOMAIN}`、`{DOMAIN_NAME}`、`{DOMAIN_EXAMPLE}`
- 每个领域使用独立的 API Key（Gemini 需要 E/S/G 三个 Key，Qwen 可共用同一个 Key）
- 如果某个领域失败，记录错误但继续处理其他领域

**关键代码结构**：
```python
from concurrent.futures import ThreadPoolExecutor, as_completed

# 加载提示词模板并替换占位符
research_template = load_prompt("章节研究.txt")
prompt_E = replace_domain_placeholders(replace_date_placeholders(research_template, date_info), "E")
prompt_S = replace_domain_placeholders(replace_date_placeholders(research_template, date_info), "S")
prompt_G = replace_domain_placeholders(replace_date_placeholders(research_template, date_info), "G")

# 并行执行
with ThreadPoolExecutor(max_workers=3) as executor:
    futures = {
        executor.submit(client_E.call_deep_research, prompt_E, "环境(E)"): "E",
        executor.submit(client_S.call_deep_research, prompt_S, "社会(S)"): "S",
        executor.submit(client_G.call_deep_research, prompt_G, "治理(G)"): "G"
    }
    for future in as_completed(futures):
        domain = futures[future]
        try:
            results[domain] = future.result()
        except Exception as e:
            results[domain] = None  # 记录错误但继续
```

### 阶段2：润色（E/S/G 并行）

**目标**：对三个领域的研究结果进行润色，使其符合报告格式要求。

**实现要点**：
- 并行执行三个领域的润色
- 提示词模板：`prompt/章节润色.txt`，需替换日期和领域占位符
- 使用对话模型（Gemini: `gemini-3-pro-preview`，Qwen: `qwen3-max-preview`）
- 如果润色失败，使用原始研究结果

**关键代码结构**：
```python
polish_template = load_prompt("章节润色.txt")
for domain in ["E", "S", "G"]:
    if research_results.get(domain):
        template = replace_domain_placeholders(replace_date_placeholders(polish_template, date_info), domain)
        prompt = f"{template}\n\n以下是需要润色的内容：\n\n{research_results[domain]}"
        # 并行调用 call_model
```

### 阶段3：热点聚焦

**目标**：基于 E/S/G 三个章节的内容，生成热点聚焦部分。

**实现要点**：
- 提示词模板：`prompt/热点聚焦.txt`
- 输入：完整的 E、S、G 三个章节内容（不截断，保证质量）
- 输出：每个领域 2-4 句话的热点聚焦，用 `\n` 分隔段落
- 使用对话模型

**关键代码结构**：
```python
hotspot_template = load_prompt("热点聚焦.txt")
hotspot_template = replace_date_placeholders(hotspot_template, date_info)
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
hotspot_result = client.call_model(prompt, "热点聚焦")
```

### 阶段4：合并报告

**目标**：将热点聚焦和三个章节合并为最终报告。

**实现要点**：
- 提示词模板：`prompt/合并.txt`
- 输入：完整的热点聚焦和三个章节内容（不截断）
- 输出：符合 OUTPUT_STANDARD.md 规范的最终报告文本
- 使用对话模型

### 阶段5：Word 填充

**目标**：将最终报告解析为结构化 JSON，并填充到 Word 模板。

**实现要点**：
- **报告解析**：使用 `report/report_formatter.py` 中的函数解析最终报告文本
  - `parse_section_content()`: 解析章节内容，提取新闻项
  - `extract_title_and_hotspot()`: 提取标题和热点聚焦
  - `normalize_newlines()`: 规范化换行符
- **JSON 格式化**：生成符合 OUTPUT_STANDARD.md 的 JSON 结构
- **Word 填充**：使用 `word/word_filler.py` 填充 Word 模板
  - 清理多余换行：去除首尾空白，压缩连续换行为单个
  - 替换占位符：`{{日期范围}}`、`{{热点聚焦}}`、`{{环境章节标题}}`、`{{环境新闻标题1}}`、`{{环境新闻内容1}}` 等
  - 清理 XML 中多余的换行标签

## 配置管理

### config.json 结构

支持嵌套结构（推荐）和平铺结构（兼容）：

```json
{
  "provider": "gemini",
  "gemini": {
    "api_key": "YOUR_GEMINI_API_KEY",
    "api_keys": {
      "E": "YOUR_GEMINI_KEY_FOR_E",
      "S": "YOUR_GEMINI_KEY_FOR_S",
      "G": "YOUR_GEMINI_KEY_FOR_G"
    },
    "agent": "deep-research-pro-preview-12-2025",
    "model": "gemini-3-pro-preview"
  },
  "qwen": {
    "api_key": "YOUR_QWEN_API_KEY",
    "model": "qwen3-max-preview",
    "deep_research_model": "qwen-deep-research"
  }
}
```

### 配置加载逻辑（core/utils.py）

- 支持 `provider_override` 参数覆盖默认 provider
- 支持环境变量 `ESG_RUNTIME_API_KEY`、`ESG_RUNTIME_API_KEY_E/S/G` 优先于 config
- Gemini：优先使用 `api_keys.E/S/G`，若无则使用单个 `api_key`
- Qwen：使用单个 `api_key`，Deep Research 使用 `deep_research_model`

## 日期处理

### 周报（weekly）
- 研究区间：上周一 00:00 至上周日 23:59:59
- 输出目录：`output/weekly/`
- 文件名格式：`YYYYMMDD_YYYYMMDD_原始内容.txt`、`YYYYMMDD_YYYYMMDD_报告.json`、`YYYYMMDD_YYYYMMDD_最终版.docx`

### 日报（daily）
- 研究区间：昨日 00:00 至 23:59:59
- 输出目录：`output/daily/`
- 文件名格式：`YYYYMMDD_原始内容.txt`、`YYYYMMDD_报告.json`、`YYYYMMDD_最终版.docx`

## API 客户端实现

### GeminiClient (core/gemini_client.py)

**Deep Research**：
- 使用 `google.genai.Client` 创建 Interaction
- Agent: `deep-research-pro-preview-12-2025`
- 设置 HTTP 超时为 5 分钟（300000ms）
- 轮询 Interaction 状态直到完成

**对话模型**：
- 使用 `client.models.generate_content()`
- Model: `gemini-3-pro-preview`
- 解析响应中的 `text` 字段

### QwenClient (core/qwen_client.py)

**Deep Research**：
- 使用 `dashscope.Generation.call()`，**必须设置 `stream=True`**
- Model: `qwen-deep-research`
- 使用 `_collect_stream_content()` 收集流式响应
- 忽略 `KeepAlive` 阶段，提取 `output.message.content`

**对话模型**：
- 使用 `dashscope.Generation.call()`，`stream=False`
- Model: `qwen3-max-preview`
- 解析响应中的 `output.text` 或 `output.message.content`

## 输出标准（必读）

**完整规范**：参考 `references/OUTPUT_STANDARD.md`，定义：
- JSON 报告结构（report_metadata、report_content、章节结构、新闻项结构）
- Word 占位符列表
- 内容规范（时效性、章节结构、单条新闻结构、热点聚焦、合并与验证）
- 格式与解析约定
- 研究深度要求

**关键要点**：
- 仅使用报告周期内的信息；若无，明确说明
- 省略章节级别的开头总结和结尾总结
- 每条新闻：副标题 + 导语 + 核心细节 + 评论 + 结尾 + **单独一行"资料来源：URL"**
- 热点聚焦：E/S/G 各一段，每段 2-4 句话
- 使用单个换行 `\n` 分隔段落
- 占位符必须匹配 OUTPUT_STANDARD.md

## 错误处理

- **部分领域失败**：记录错误但继续处理其他领域，最终报告中使用可用结果
- **编码问题**：使用 `safe_print()` 处理 Windows GBK 编码问题，将 Unicode 字符替换为 ASCII
- **Qwen 超时**：Deep Research 默认超时约 300 秒，若超时可检查网络后重试
- **Word 填充失败**：记录警告但保留 JSON，可稍后手动填充

## 文件结构

```
easy-esg-master/
├── main.py                 # 主程序入口
├── fill_template.py        # Word 填充命令行入口
├── config.json.example     # 配置模板
├── ESG研报模板.docx        # Word 模板
├── core/
│   ├── __init__.py
│   ├── gemini_client.py    # Gemini API 客户端
│   ├── qwen_client.py      # Qwen API 客户端
│   ├── research_stages.py  # 研究流程（5个阶段）
│   ├── progress.py         # 进度跟踪（可选）
│   └── utils.py            # 配置、日期、提示词加载
├── report/
│   ├── report_formatter.py # 报告解析与格式化
│   └── report_saver.py     # JSON 保存
├── word/
│   └── word_filler.py      # Word 模板填充
└── prompt/                 # 提示词模板
    ├── 章节研究.txt
    ├── 章节润色.txt
    ├── 热点聚焦.txt
    └── 合并.txt
```

## 实现检查清单

生成报告时确保：

- [ ] 配置正确：`config.json` 存在且包含有效的 API Key
- [ ] 提示词完整：`prompt/` 目录包含所有 4 个提示词文件
- [ ] 日期计算正确：周报为上周一至上周日，日报为昨日
- [ ] 并行执行：E/S/G 三个领域的研究和润色都并行执行
- [ ] 内容完整：不截断内容，保证质量优先
- [ ] JSON 格式正确：符合 OUTPUT_STANDARD.md 的结构
- [ ] Word 填充正确：占位符匹配，清理多余换行
- [ ] 错误处理：部分失败时继续处理，记录错误信息

## Resources

- **references/OUTPUT_STANDARD.md**：完整输出与内容标准（JSON 结构、Word 占位符、内容规范、格式与解析、研究深度、精简版提示）。**必须参考**。
- 项目 README：`README.md`（项目根目录）
