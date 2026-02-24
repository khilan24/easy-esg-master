# ESG 投研报告生成工具

一键生成 ESG（环境、社会、治理）投研**周报**或**日报**，支持 **Gemini** 与 **千问（Qwen）** 两种模型，输出 Word、JSON 与原始文本。

## 功能概览

- **周报 / 日报**：周报研究「上周一至上周日」，日报研究「昨日」
- **模型可选**：Gemini（Deep Research + Gemini 3 Pro）或千问（Qwen Deep Research + qwen3-max-preview 对话）
- **流程**：阶段1 并行研究(E/S/G) → 阶段2 润色 → 阶段3 热点聚焦 → 阶段4 合并 → 阶段5 Word 与 PPT 填充
- **使用方式**：Web 前端（推荐）或命令行；前端可填写 API Key，无需改 config

## 环境与安装

- Python 3.7+
- 依赖：`google-genai`（Gemini）、`dashscope`（千问）、`flask`（Web）

```bash
pip install -r requirements.txt
```

## 配置

1. 复制配置模板并编辑：

```bash
cp config/config.json.example config.json
```

2. **provider**：`"gemini"` 或 `"qwen"`，表示默认使用的模型；不填则默认 Gemini；前端选择会覆盖
3. **gemini**：Gemini 的 API Key（`api_key` 或 `api_keys.E/S/G`）、Deep Research 的 `agent`、对话模型 `model`
4. **qwen**：千问的 `api_key`、对话模型 `model`、深度研究模型 `deep_research_model`；也可在前端/环境变量中提供 Key

配置采用 **gemini / qwen 分组**，避免混在一起；旧版平铺写法仍兼容。

配置示例（`config/config.json.example`）：

```json
{
  "provider": "gemini",
  "gemini": {
    "api_key": "YOUR_GEMINI_API_KEY",
    "api_keys": { "E": "...", "S": "...", "G": "..." },
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

- **provider**：当前默认用哪家；前端选择模型时会覆盖
- **gemini**：仅在使用 Gemini 时生效；`api_keys` 三键可并行研究
- **qwen**：仅在使用千问时生效；`model` 用于润色/热点/合并，`deep_research_model` 用于 E/S/G 深度研究

## 使用方式

### 1. Web 前端（推荐）

```bash
python web/app.py
```

浏览器打开 **http://127.0.0.1:5000**：

- 选择**模型**：Gemini 或千问
- 填写 **API Key**：千问填 1 个；Gemini 填 E、S、G 各 1 个（可选，不填则用 config）
- 选择**报告类型**：周报 / 日报
- 点击「生成报告」，页面会显示研究进展、耗时与运行日志，完成后可下载 Word、PPT、JSON

### 2. 命令行

```bash
# 周报（默认 Gemini）
python main.py
python main.py --mode weekly --provider gemini

# 日报 + 千问
python main.py --mode daily --provider qwen
```

参数说明：

- `--mode` / `-m`：`weekly`（周报）或 `daily`（日报）
- `--provider` / `-p`：`gemini` 或 `qwen`，不传则使用 config 中的 `provider`

### 3. 仅填充（每次输出 txt、json、word、pptx）

若已有 JSON 报告，可只跑模板填充；**每次运行均保证输出四类文件**：`*_原始内容.txt`、`*_报告.json`、`*_最终版.docx`、`*_最终版.pptx`。固定使用 `templates/` 下的国信模板。

```bash
python scripts/fill_template.py --json output/daily/YYYYMMDD_报告.json
python scripts/fill_template.py   # 自动查找最新 JSON，并填充 Word + PPT
```

- `--json`：JSON 路径，不传则自动查找最新 `*_报告.json`

不指定 `--json` 时会在 `output/weekly/`、`output/daily/` 下自动查找最新 `*_报告.json`。若输出目录缺少 `*_原始内容.txt`，脚本会从同类型目录复制或创建占位文件。

## 输出目录与文件

| 类型 | 目录 | 文件名示例 |
|------|------|------------|
| 周报 | `output/weekly/` | `*_原始内容.txt`、`*_报告.json`、`*_最终版.docx`、`*_最终版.pptx` |
| 日报 | `output/daily/` | `*_原始内容.txt`、`*_报告.json`、`*_最终版.docx`、`*_最终版.pptx` |

文件名以日期开头，便于排序与归档。需在 `templates/` 下放置国信模板 `ESG研报模板.docx`、`ESG研报模板.pptx`。

## 项目结构

```
easy-esg-master/
├── main.py                 # 主程序（--mode weekly|daily，--provider gemini|qwen）
├── requirements.txt
├── config/                 # 配置
│   └── config.json.example
├── templates/              # Word/PPT 模板（ESG研报模板.docx、ESG研报模板.pptx）
├── scripts/                # 命令行脚本
│   └── fill_template.py   # Word + PPT 填充（每次输出 txt/json/docx/pptx）
├── core/                   # 核心逻辑
│   ├── gemini_client.py    # Gemini API（Deep Research + 对话）
│   ├── qwen_client.py      # 千问 API（Deep Research + 对话）
│   ├── research_stages.py  # 研究流程（E/S/G 研究、润色、热点、合并）
│   ├── progress.py         # 运行进度写入（供 Web 展示）
│   └── utils.py            # 配置、日期、提示词、打印
├── report/                 # 报告格式化与保存
│   ├── report_formatter.py
│   └── report_saver.py
├── fill/                   # 模板填充（Word + PPT）
│   ├── word_filler.py
│   └── ppt_filler.py
├── prompt/                 # 提示词（占位符按领域与日期替换）
│   ├── 章节研究.txt
│   ├── 章节润色.txt
│   ├── 热点聚焦.txt
│   └── 合并.txt
├── web/                    # Web 前端
│   ├── app.py              # Flask 后端（状态、进度、下载）
│   └── templates/index.html
├── deploy/                 # 阿里云部署
│   ├── README.md           # 部署说明
│   ├── systemd/            # systemd 服务
│   ├── nginx/              # Nginx 配置（8080 端口）
│   └── scripts/            # 更新脚本
├── .cursor/skills/         # Cursor IDE 技能（esg-report、frontend-design）
└── output/
    ├── weekly/             # 周报输出
    └── daily/              # 日报输出
```

- `.cursor/skills/` 为 Cursor IDE 技能与参考，用于 AI 辅助开发，已纳入仓库。

## 部署（阿里云）

若需在阿里云 ECS 上部署 Web 服务（8080 端口），参见 [deploy/README.md](deploy/README.md)。内含 systemd、Nginx 配置与一键更新脚本，版本迭代可通过 GitHub 拉取后执行 `deploy/scripts/update.sh` 完成。

## 注意事项

- `config.json` 含 API Key，已加入 `.gitignore`，勿提交
- Deep Research 阶段耗时较长，请保持网络畅通
- **千问**：Deep Research 默认读超时约 300 秒，若出现 `Read timed out` 可检查网络后重试；若某领域（E/S/G）失败，程序会提示「部分领域研究失败」并尽量用已有结果继续
- 前端运行日志会实时刷新；失败时请查看日志末尾的错误信息（含「响应解析失败」时的 output 结构摘要，便于排查）

## 参考

- [Gemini Interactions API](https://ai.google.dev/gemini-api/docs/interactions)
- [千问 Deep Research（阿里云）](https://help.aliyun.com/zh/model-studio/qwen-deep-research-api)
