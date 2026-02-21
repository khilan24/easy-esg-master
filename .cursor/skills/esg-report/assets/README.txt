本目录为 skill 的 assets，供脚本与项目使用。

- ESG研报模板.docx：Word 模板。若缺失，请从项目根目录复制同名文件到此处，或由 run_report.py 在项目内从本 skill 同步到项目根。
- prompts/：章节研究、润色、热点聚焦、合并等提示词（.txt），由 run_report 同步到项目的 prompt/。
- config.json.example：API 配置示例。首次在项目内运行 run_report.py 时若项目无 config.json，会复制为 config.json，需填入 API Key。

脚本说明见 SKILL.md 与 scripts/run_report.py、scripts/fill_word.py。
