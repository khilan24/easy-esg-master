"""
工具函数模块
包含配置加载、提示词加载、日期处理、output 目录规则等通用功能
"""
import os
import json
from datetime import datetime, timedelta
from pathlib import Path
import threading

OUTPUT_BASE = "output"

# 线程锁用于打印
print_lock = threading.Lock()


def safe_print(*args, **kwargs):
    """线程安全的打印函数，默认 flush 以便子进程输出实时进入管道（如 Web 运行日志）。
    自动处理 Windows GBK 编码问题，将 Unicode 特殊字符替换为 ASCII 兼容字符。
    """
    with print_lock:
        kwargs.setdefault("flush", True)
        try:
            print(*args, **kwargs)
        except UnicodeEncodeError:
            # Windows 终端 GBK 编码无法处理某些 Unicode 字符，替换为 ASCII
            safe_args = []
            for arg in args:
                if isinstance(arg, str):
                    safe_args.append(arg.replace("✓", "[完成]").replace("✗", "[失败]"))
                else:
                    safe_args.append(arg)
            print(*safe_args, **kwargs)


def load_config(provider_override=None, api_key_override=None):
    """
    从配置文件加载配置；无 config.json 时仅从环境变量（ESG_RUNTIME_API_KEY 等）构建配置。
    provider_override: 可选 "gemini" | "qwen"，覆盖 config 中的 provider。
    api_key_override: 可选，前端或环境传入的 API Key（ESG_RUNTIME_API_KEY），优先于 config 使用。
    """
    config_path = "config.json"
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        def _g(key, default=None):
            return config.get(key, default)
        _gemini = config.get("gemini") if isinstance(config.get("gemini"), dict) else {}
        _qwen = config.get("qwen") if isinstance(config.get("qwen"), dict) else {}
        config.setdefault("api_key", _gemini.get("api_key") or _g("api_key"))
        config.setdefault("api_keys", _gemini.get("api_keys") or _g("api_keys"))
        config.setdefault("agent", _gemini.get("agent") or _g("agent", "deep-research-pro-preview-12-2025"))
        config.setdefault("model", _gemini.get("model") or _g("model", "gemini-3-pro-preview"))
        config.setdefault("qwen_api_key", _qwen.get("api_key") or _g("qwen_api_key"))
        config.setdefault("qwen_model", _qwen.get("model") or _g("qwen_model", "qwen3-max-preview"))
        config.setdefault("qwen_deep_research_model", _qwen.get("deep_research_model") or _g("qwen_deep_research_model", "qwen-deep-research"))
    else:
        # 无 config.json 时使用默认值，Key 仅从环境变量读取（由前端经 app 传入）
        config = {
            "api_key": None,
            "api_keys": None,
            "agent": "deep-research-pro-preview-12-2025",
            "model": "gemini-3-pro-preview",
            "qwen_api_key": None,
            "qwen_model": "qwen3-max-preview",
            "qwen_deep_research_model": "qwen-deep-research",
        }

    provider = provider_override or config.get("provider", "gemini")
    if provider not in ("gemini", "qwen"):
        provider = "gemini"
    config["provider"] = provider

    # 前端或环境传入的 Key 优先（main 通过 env 传入，此处仅从 env 读取）
    runtime_single = (os.environ.get("ESG_RUNTIME_API_KEY") or "").strip()
    runtime_e = (os.environ.get("ESG_RUNTIME_API_KEY_E") or runtime_single).strip()
    runtime_s = (os.environ.get("ESG_RUNTIME_API_KEY_S") or runtime_single).strip()
    runtime_g = (os.environ.get("ESG_RUNTIME_API_KEY_G") or runtime_single).strip()

    if provider == "qwen":
        qwen_key = runtime_single or config.get("qwen_api_key") or os.environ.get("DASHSCOPE_API_KEY") or ""
        if not qwen_key or str(qwen_key).startswith("YOUR_"):
            raise ValueError("请在前端输入千问 API Key，或在 config.json 的 qwen.api_key 中配置。")
        config["api_keys"] = {"E": qwen_key, "S": qwen_key, "G": qwen_key}
        config["api_key"] = qwen_key
        config["qwen_model"] = config.get("qwen_model", "qwen3-max-preview")
        config["qwen_deep_research_model"] = config.get("qwen_deep_research_model", "qwen-deep-research")
        return config

    # Gemini：支持 E/S/G 三个 Key 或单个 Key
    if runtime_e or runtime_s or runtime_g:
        config["api_keys"] = {
            "E": runtime_e or runtime_s or runtime_g,
            "S": runtime_s or runtime_e or runtime_g,
            "G": runtime_g or runtime_e or runtime_s,
        }
        config["api_key"] = config["api_keys"]["E"]
        return config
    if config.get("api_keys"):
        api_keys = config["api_keys"]
        if not isinstance(api_keys, dict):
            raise ValueError("api_keys 必须是一个字典，包含 E、S、G 三个键")
        for domain in ["E", "S", "G"]:
            if domain not in api_keys or not api_keys[domain] or str(api_keys[domain]).startswith("YOUR_"):
                raise ValueError(f"请在前端输入 Gemini API Key，或在 config.json 的 gemini.api_keys 中配置有效的 {domain}。")
    else:
        if not config.get("api_key") or str(config["api_key"]) == "YOUR_API_KEY_HERE":
            raise ValueError("请在前端输入 Gemini API Key，或在 config.json 的 gemini.api_key 中配置。")
        config["api_keys"] = {
            "E": config["api_key"],
            "S": config["api_key"],
            "G": config["api_key"],
        }
    if not config.get("api_key"):
        config["api_key"] = config["api_keys"]["E"]
    return config


def load_prompt(prompt_file):
    """加载提示词文件"""
    prompt_path = os.path.join("prompt", prompt_file)
    if not os.path.exists(prompt_path):
        raise FileNotFoundError(f"提示词文件 {prompt_path} 不存在")
    
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read()


def get_last_week_date_range():
    """获取上周的日期范围（上周一至上周日）"""
    today = datetime.now()
    days_since_monday = today.weekday()
    last_monday = today - timedelta(days=days_since_monday + 7)
    last_sunday = last_monday + timedelta(days=6)
    return _build_date_info(last_monday, last_sunday, "weekly", "ESG投研周报")


def get_yesterday_date_range():
    """获取昨天的日期范围（研究日为当前日期的前一天）"""
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    return _build_date_info(yesterday, yesterday, "daily", "ESG投研日报")


def _build_date_info(start_dt, end_dt, report_type, report_label):
    """构建统一的日期信息字典，含 report_type / report_label"""
    return {
        "start_date_chinese": start_dt.strftime("%Y年%m月%d日"),
        "end_date_chinese": end_dt.strftime("%Y年%m月%d日"),
        "start_date_iso": start_dt.strftime("%Y-%m-%d"),
        "end_date_iso": end_dt.strftime("%Y-%m-%d"),
        "date_range_chinese": f"{start_dt.strftime('%Y年%m月%d日')} 至 {end_dt.strftime('%Y年%m月%d日')}" if start_dt != end_dt else start_dt.strftime("%Y年%m月%d日"),
        "date_range_iso": f"{start_dt.strftime('%Y-%m-%d')} 至 {end_dt.strftime('%Y-%m-%d')}" if start_dt != end_dt else start_dt.strftime("%Y-%m-%d"),
        "date_range_compact": f"{start_dt.strftime('%Y.%m.%d')}-{end_dt.strftime('%Y.%m.%d')}" if start_dt != end_dt else start_dt.strftime("%Y.%m.%d"),
        "report_type": report_type,
        "report_label": report_label,
    }


def get_date_range_for_mode(mode):
    """根据模式返回日期范围。mode: 'weekly' | 'daily'"""
    if mode == "daily":
        return get_yesterday_date_range()
    return get_last_week_date_range()


def get_output_date_suffix(date_info):
    """
    返回用于文件名的日期部分（放在最前）：周报为 YYYYMMDD_YYYYMMDD，日报为 YYYYMMDD。
    用于 {suffix}_原始内容.txt、{suffix}_报告.json、{suffix}_最终版.docx。
    """
    start_str = date_info["start_date_iso"].replace("-", "")
    end_str = date_info["end_date_iso"].replace("-", "")
    if start_str == end_str:
        return start_str
    return f"{start_str}_{end_str}"


def get_output_subdir(date_info):
    """
    根据 date_info 返回本次报告的 output 目录路径（相对项目根）。
    规则：直接存于 output/weekly/ 或 output/daily/，不再建日期子目录。
    """
    report_type = date_info.get("report_type", "weekly")
    return os.path.join(OUTPUT_BASE, report_type)


def get_latest_output_subdir(base_dir=None):
    """
    在 output 下查找「最近一次生成」的目录：比较 weekly/ 与 daily/ 内文件最新修改时间。
    返回相对 base_dir 的路径 "weekly" 或 "daily"，若无则返回 None。
    """
    base = Path(base_dir or OUTPUT_BASE)
    if not base.exists():
        return None
    best_subdir = None
    best_mtime = 0
    for kind in ("weekly", "daily"):
        kind_dir = base / kind
        if not kind_dir.is_dir():
            continue
        mtime = max((f.stat().st_mtime for f in kind_dir.iterdir() if f.is_file()), default=0)
        if mtime > best_mtime:
            best_mtime = mtime
            best_subdir = kind
    return best_subdir


def find_latest_report_json(base_dir=None):
    """
    查找最新的报告 JSON 文件路径。
    优先查找 output/weekly/*_报告.json、output/daily/*_报告.json（日期在前）；兼容 报告_*.json、报告.json、ESG投研*_*.json。
    返回 Path 或 None。
    """
    base = Path(base_dir or OUTPUT_BASE)
    if not base.exists():
        return None
    candidates = []
    for kind in ("weekly", "daily"):
        for p in (base / kind).glob("*_报告.json"):
            if p.is_file():
                candidates.append(p)
        for p in (base / kind).glob("报告_*.json"):
            if p.is_file():
                candidates.append(p)
        p_legacy = base / kind / "报告.json"
        if p_legacy.is_file():
            candidates.append(p_legacy)
    for p in base.glob("ESG投研*_*.json"):
        if p.is_file():
            candidates.append(p)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def list_output_files_in_subdir(subdir_rel, base_dir=None):
    """
    列出指定目录下的文件，返回相对 base_dir 的路径列表，用于下载等。
    subdir_rel: "weekly" 或 "daily"
    返回: [('最终版.docx', 'weekly/最终版.docx'), ...]
    """
    base = Path(base_dir or OUTPUT_BASE)
    folder = base / subdir_rel if subdir_rel else base
    if not folder.is_dir():
        return []
    out = []
    for f in folder.iterdir():
        if f.is_file() and not f.name.startswith("~$"):
            rel = f.relative_to(base)
            out.append((f.name, str(rel).replace("\\", "/")))
    return out


# 领域占位符映射：E/S/G -> 中文名、示例句
DOMAIN_MAP = {
    "E": {"cn": "环境", "example": "欧盟委员会通过《可持续产品生态设计条例》"},
    "S": {"cn": "社会", "example": "某公司发布员工多元化发展报告"},
    "G": {"cn": "治理", "example": "某公司发布董事会多元化政策"},
}


def replace_domain_placeholders(text, domain):
    """
    替换章节研究/润色提示词中的领域占位符。
    domain: "E" | "S" | "G"
    占位符：{DOMAIN} -> E/S/G, {DOMAIN_CN} -> 环境/社会/治理, {DOMAIN_EXAMPLE} -> 该领域示例句
    """
    if domain not in DOMAIN_MAP:
        return text
    info = DOMAIN_MAP[domain]
    replacements = {
        "{DOMAIN}": domain,
        "{DOMAIN_CN}": info["cn"],
        "{DOMAIN_EXAMPLE}": info["example"],
    }
    result = text
    for placeholder, replacement in replacements.items():
        result = result.replace(placeholder, replacement)
    return result


def replace_date_placeholders(text, date_info):
    """替换文本中的所有日期与报告类型占位符（含周报/日报维度）"""
    report_type = date_info.get("report_type", "weekly")
    is_weekly = report_type == "weekly"
    replacements = {
        # 日期范围
        "上周（具体日期范围由系统自动填充）": date_info["date_range_chinese"],
        "上周": date_info["date_range_chinese"],
        "上周一至上周日": date_info["date_range_chinese"],
        "{上周日期}": date_info["date_range_chinese"],
        "{DATE_RANGE}": date_info["date_range_chinese"],
        "{DATE_RANGE_CHINESE}": date_info["date_range_chinese"],
        "{TIME_SCOPE}": date_info["date_range_chinese"],
        "{START_DATE}": date_info["start_date_chinese"],
        "{END_DATE}": date_info["end_date_chinese"],
        "{START_DATE_CHINESE}": date_info["start_date_chinese"],
        "{END_DATE_CHINESE}": date_info["end_date_chinese"],
        "{START_DATE_ISO}": date_info["start_date_iso"],
        "{END_DATE_ISO}": date_info["end_date_iso"],
        "{DATE_RANGE_ISO}": date_info["date_range_iso"],
        "{DATE_RANGE_COMPACT}": date_info["date_range_compact"],
        # 周报/日报用语（根据 report_type 替换）
        "{REPORT_TYPE_CN}": "周报" if is_weekly else "日报",
        "{PERIOD_PHRASE}": "过去一周" if is_weekly else "当日",
        "{THIS_PERIOD}": "本周" if is_weekly else "当日",
    }
    result = text
    for placeholder, replacement in replacements.items():
        result = result.replace(placeholder, replacement)
    return result
