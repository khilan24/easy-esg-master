"""
报告格式化模块
包含解析章节内容、提取标题和热点聚焦等功能
"""
import re


def normalize_newlines(text):
    """规范化换行符：将所有多个连续的换行符统一为单个换行符
    """
    if not text:
        return text
    
    # 将所有多个连续的换行符统一为单个换行符
    normalized = re.sub(r'\n+', '\n', text)
    
    # 清理开头和结尾的多余换行符
    normalized = normalized.strip()
    
    return normalized


def is_source_line(text):
    """判断是否是资料来源行"""
    text_lower = text.lower()
    # 检查各种资料来源格式
    return (
        text.startswith(('Sources', 'Source:', '资料来源', '[资料来源]', '[cite:')) or
        'vertexaisearch.cloud.google.com' in text or
        'grounding-api-redirect' in text or
        re.search(r'\[cite:\s*\d+', text) is not None  # [cite: 1, 2, 3] 格式
    )


def format_source_line(source_text):
    """格式化资料来源行为统一格式：资料来源：原文链接"""
    source_text = source_text.strip()
    
    # 处理 [cite: 1, 2, 3] 格式（没有实际链接，留空）
    if source_text.startswith('[cite:'):
        return "资料来源："
    
    # 处理 [资料来源](链接) 格式
    match = re.search(r'\[资料来源\]\((https?://[^\)]+)\)', source_text)
    if match:
        return f"资料来源：{match.group(1)}"
    
    # 处理 Source: [网站](链接) 格式
    match = re.search(r'Source:\s*\[([^\]]+)\]\((https?://[^\)]+)\)', source_text)
    if match:
        return f"资料来源：{match.group(2)}"
    
    # 处理包含链接的其他格式
    match = re.search(r'(https?://[^\s\)]+)', source_text)
    if match:
        return f"资料来源：{match.group(1)}"
    
    # 如果没有找到链接，返回原文本（去掉Markdown格式）
    cleaned = source_text.replace('[资料来源]', '').replace('Source:', '').strip()
    if cleaned:
        return f"资料来源：{cleaned}"
    
    return "资料来源："


def extract_source_from_text(text):
    """从文本中提取资料来源并格式化为统一格式"""
    lines = text.split('\n')
    sources = []
    
    for line in lines:
        line_stripped = line.strip()
        if is_source_line(line_stripped):
            formatted_source = format_source_line(line_stripped)
            if formatted_source and formatted_source not in sources:
                sources.append(formatted_source)
    
    return '\n'.join(sources) if sources else None


def parse_section_content(section_text, domain_name):
    """解析章节内容，提取每条新闻的标题和内容
    一条新闻 = 一个标题 + 所有相关内容段落（直到下一个标题出现）
    确保每条新闻的content末尾都包含资料来源
    """
    if not section_text or section_text.strip() == "":
        return []
    
    news_items = []
    
    # 按单个换行符分割段落（统一使用单个换行符）
    paragraphs = [p.strip() for p in section_text.split('\n') if p.strip()]
    
    if not paragraphs:
        return []
    
    current_title = None
    current_content_parts = []
    pending_source = None  # 暂存的资料来源（可能在下一个段落）
    
    for i, para in enumerate(paragraphs):
        para_lines = [l.strip() for l in para.split('\n') if l.strip()]
        if not para_lines:
            continue
        
        first_line = para_lines[0]
        
        # 跳过章节标题行（必须同时包含"动态"或"章节"关键词）
        # 避免误跳过包含"环境"、"社会"、"治理"等词汇的新闻标题
        if any(kw in first_line for kw in ['# 环境', '# 社会', '# 治理', '环境（E）', '社会（S）', '治理（G）', '公司治理（G）']):
            if any(kw in first_line for kw in ['动态', '章节']):
                continue
        # 额外检查：如果是章节标题格式（如"# 投研周报：环境（E）"），也要跳过
        if first_line.startswith('#') and ('投研周报' in first_line or '周报' in first_line):
            if any(kw in first_line for kw in ['环境', '社会', '治理']):
                continue
        
        # 移除Markdown格式标记
        clean_first = re.sub(r'^#+\s*', '', first_line)  # 移除 ### 或 ##
        clean_first = clean_first.replace('**', '').replace('*', '').strip()
        
        # 检查是否是资料来源行
        if is_source_line(clean_first):
            # 如果当前有新闻，将资料来源添加到内容末尾
            if current_title:
                # 资料来源应该添加到当前新闻的内容末尾
                if current_content_parts:
                    # 检查最后一部分是否已经是资料来源
                    last_part = current_content_parts[-1]
                    if not is_source_line(last_part):
                        current_content_parts.append(para)
                else:
                    current_content_parts.append(para)
            else:
                # 没有当前新闻，暂存资料来源
                pending_source = para
            continue
        
        # 判断是否是新闻标题的特征：
        # 1. 是Markdown标题格式（###、## 或 # 开头）
        # 2. 或者长度较短（小于100字符）且不包含句号
        # 3. 不是以内容性词汇开头
        is_markdown_title = first_line.startswith(('###', '##', '#'))
        
        is_plain_title = (
            len(clean_first) < 100 and
            not clean_first.endswith('。') and
            not clean_first.endswith('.') and
            not clean_first.startswith(('在', '根据', '该', '这', '其', '文件', '此次', '此事', '从', 'Sources', '资料来源', '[资料来源]', '工业和信息化部', '美国', '晶科', '中国天楹'))
        )
        
        if (is_markdown_title or is_plain_title) and len(clean_first) > 5:
            # 遇到新标题，保存之前的新闻
            if current_title and current_content_parts:
                content = '\n'.join(current_content_parts).strip()
                
                # 检查内容末尾是否已有资料来源
                if content:
                    # 检查最后几行是否有资料来源
                    content_lines = content.split('\n')
                    has_source_at_end = False
                    if len(content_lines) >= 1:
                        last_few_lines = '\n'.join(content_lines[-3:])  # 检查最后3行
                        if is_source_line(last_few_lines):
                            has_source_at_end = True
                    
                    # 如果没有资料来源，尝试从内容中提取
                    if not has_source_at_end:
                        extracted_source = extract_source_from_text(content)
                        if extracted_source:
                            # 从内容中移除资料来源，然后添加到末尾
                            content_lines_clean = []
                            for line in content_lines:
                                if not is_source_line(line):
                                    content_lines_clean.append(line)
                            content = '\n'.join(content_lines_clean).strip()
                            if content:
                                content = f"{content}\n{extracted_source}"
                        elif pending_source:
                            # 使用暂存的资料来源
                            content = f"{content}\n{pending_source}"
                            pending_source = None
                    
                    if content:  # 确保有内容
                        news_items.append({
                            "title": current_title,
                            "content": content
                        })
            
            # 开始新新闻
            current_title = clean_first
            # 如果标题后面还有内容（同一段落内）
            if len(para_lines) > 1:
                remaining_lines = para_lines[1:]
                # 检查剩余内容是否也是标题的一部分
                second_line = remaining_lines[0] if remaining_lines else ""
                if len(second_line) < 100 and not second_line.endswith('。') and not second_line.endswith('.'):
                    # 可能是标题的延续
                    current_title = f"{current_title} {second_line}"
                    if len(remaining_lines) > 1:
                        remaining_content = '\n'.join(remaining_lines[1:])
                        # 检查剩余内容中是否有资料来源
                        if is_source_line(remaining_content):
                            pending_source = remaining_content
                            current_content_parts = []
                        else:
                            current_content_parts = [remaining_content]
                    else:
                        current_content_parts = []
                else:
                    remaining_content = '\n'.join(remaining_lines)
                    # 检查剩余内容中是否有资料来源
                    if is_source_line(remaining_content):
                        pending_source = remaining_content
                        current_content_parts = []
                    else:
                        current_content_parts = [remaining_content]
            else:
                current_content_parts = []
        else:
            # 这是内容段落，添加到当前新闻
            if current_title:
                # 检查这个段落是否是资料来源
                if is_source_line(para):
                    # 如果当前内容为空，暂存资料来源
                    if not current_content_parts:
                        pending_source = para
                    else:
                        # 检查最后一部分是否已经是资料来源
                        if not is_source_line(current_content_parts[-1]):
                            current_content_parts.append(para)
                else:
                    current_content_parts.append(para)
            else:
                # 没有标题，尝试从第一行提取标题
                # 如果第一行很长，可能是导语，提取前部分作为标题
                if len(clean_first) > 80:
                    # 尝试找到第一个句号或逗号
                    title_end = clean_first.find('。')
                    if title_end == -1:
                        title_end = clean_first.find('，')
                    if title_end == -1 or title_end < 20:
                        title_end = min(60, len(clean_first))
                    
                    current_title = clean_first[:title_end].strip()
                    if len(clean_first) > title_end:
                        remaining = clean_first[title_end:].strip()
                        if not is_source_line(remaining):
                            current_content_parts.append(remaining)
                    if len(para_lines) > 1:
                        remaining_lines = '\n'.join(para_lines[1:])
                        if not is_source_line(remaining_lines):
                            current_content_parts.append(remaining_lines)
                        else:
                            pending_source = remaining_lines
                else:
                    # 使用第一行作为标题
                    current_title = clean_first
                    if len(para_lines) > 1:
                        remaining_lines = '\n'.join(para_lines[1:])
                        if not is_source_line(remaining_lines):
                            current_content_parts.append(remaining_lines)
                        else:
                            pending_source = remaining_lines
    
    # 保存最后一条新闻
    if current_title and current_content_parts:
        content = '\n'.join(current_content_parts).strip()
        
        # 检查内容末尾是否已有资料来源
        if content:
            content_lines = content.split('\n')
            has_source_at_end = False
            if len(content_lines) >= 1:
                last_few_lines = '\n'.join(content_lines[-3:])
                if is_source_line(last_few_lines):
                    has_source_at_end = True
            
            # 如果没有资料来源，尝试添加
            if not has_source_at_end:
                extracted_source = extract_source_from_text(content)
                if extracted_source:
                    content_lines_clean = [line for line in content_lines if not is_source_line(line)]
                    content = '\n'.join(content_lines_clean).strip()
                    if content:
                        content = f"{content}\n{extracted_source}"
                elif pending_source:
                    content = f"{content}\n{pending_source}"
        
        if content:
            news_items.append({
                "title": current_title,
                "content": content
            })
    
    # 过滤掉明显无效的新闻项，并确保每条新闻的content末尾都有资料来源
    filtered_items = []
    for item in news_items:
        title = item['title'].strip()
        content = item['content'].strip()
        
        # 跳过无效项
        if (len(title) < 5 or 
            title == content or 
            title.startswith('#') or
            any(kw in title for kw in ['环境（E）', '社会（S）', '治理（G）', '公司治理']) or
            len(content) < 20):  # 内容太短也跳过
            continue
        
        # 确保内容末尾有资料来源
        content_lines = content.split('\n')
        
        # 分离内容行和资料来源行
        content_lines_clean = []
        source_lines = []
        
        for line in content_lines:
            line_stripped = line.strip()
            if is_source_line(line_stripped):
                source_lines.append(line_stripped)
            else:
                content_lines_clean.append(line)
        
        # 重新组合：先内容，后资料来源
        clean_content = '\n'.join(content_lines_clean).strip()
        
        # 格式化资料来源
        formatted_sources = []
        if source_lines:
            for source_line in source_lines:
                formatted = format_source_line(source_line)
                if formatted and formatted not in formatted_sources:
                    formatted_sources.append(formatted)
        
        # 如果没有找到资料来源，尝试从整个文本中提取
        if not formatted_sources:
            extracted_source = extract_source_from_text(content)
            if extracted_source:
                formatted_sources.append(extracted_source)
        
        # 组合最终内容：先内容，后资料来源（单独成行）
        if formatted_sources:
            source_text = '\n'.join(formatted_sources)
            final_content = f"{clean_content}\n{source_text}" if clean_content else source_text
        else:
            # 如果确实没有资料来源，保留原内容（但这种情况应该很少）
            final_content = clean_content if clean_content else content
        
        # 规范化换行符：清理多余的换行符
        final_content = normalize_newlines(final_content)
        
        filtered_items.append({
            "title": title,
            "content": final_content
        })
    
    return filtered_items


def extract_title_and_hotspot(final_report_text, date_info):
    """从最终报告中提取标题和热点聚焦"""
    title = None
    hotspot = None
    
    lines = final_report_text.split('\n')
    
    # 查找标题（通常在开头，可能包含日期）
    for i, line in enumerate(lines[:15]):  # 检查前15行
        line_stripped = line.strip()
        # 移除Markdown格式
        clean_line = line_stripped.replace('#', '').replace('*', '').strip()
        
        if 'ESG周报' in clean_line or 'ESG投研日报' in clean_line or ('ESG' in clean_line and ('周报' in clean_line or '日报' in clean_line)):
            title = clean_line
            break

    if not title:
        report_label = date_info.get("report_label", "ESG投研周报")
        title = f"{report_label}（{date_info['date_range_chinese']}）"
    
    # 查找热点聚焦部分
    hotspot_start = None
    hotspot_end = None
    
    for i, line in enumerate(lines):
        line_lower = line.lower()
        # 查找热点聚焦的开始标记（跳过标题行）
        if any(keyword in line_lower for keyword in ['热点聚焦', '核心摘要', '摘要', '周报开篇']):
            # 跳过标题行，找到实际内容开始
            hotspot_start = i + 1
            # 跳过可能的空行和分隔线
            while hotspot_start < len(lines) and (lines[hotspot_start].strip() == '' or lines[hotspot_start].strip().startswith('---')):
                hotspot_start += 1
            break
    
    if hotspot_start:
        # 查找下一个章节标题作为结束点（如【环境（E）章节】或### **【环境（E）动态】**）
        for i in range(hotspot_start, len(lines)):
            line_stripped = lines[i].strip()
            # 查找章节标题标记
            if (line_stripped.startswith('【') and any(kw in line_stripped for kw in ['环境', '社会', '治理', '公司治理', '章节'])) or \
               (line_stripped.startswith('###') and any(kw in line_stripped for kw in ['环境', '社会', '治理', '动态'])):
                hotspot_end = i
                break
        
        if hotspot_end:
            hotspot_lines = lines[hotspot_start:hotspot_end]
        else:
            # 如果没有找到结束点，尝试查找包含"环境（E）"、"社会（S）"、"治理（G）"的完整段落
            # 热点聚焦通常包含E、S、G三个段落
            hotspot_end = hotspot_start
            e_found = False
            s_found = False
            g_found = False
            
            for i in range(hotspot_start, len(lines)):
                line_stripped = lines[i].strip()
                # 检查是否包含E、S、G段落标记
                if '环境（E）' in line_stripped or '【环境（E）' in line_stripped:
                    e_found = True
                if '社会（S）' in line_stripped or '【社会（S）' in line_stripped:
                    s_found = True
                if '治理（G）' in line_stripped or '【治理（G）' in line_stripped or '【公司治理（G）' in line_stripped:
                    g_found = True
                
                # 如果找到了E、S、G三个段落，且遇到空行或下一个章节，则结束
                if e_found and s_found and g_found:
                    # 继续查找，直到遇到空行或下一个章节标题
                    if line_stripped == '' or line_stripped.startswith('【') or line_stripped.startswith('###'):
                        hotspot_end = i
                        break
                    hotspot_end = i + 1
                else:
                    hotspot_end = i + 1
            
            # 如果没找到完整的三段，至少提取到第一个明显的章节分隔
            if hotspot_end == hotspot_start:
                for i in range(hotspot_start, min(hotspot_start + 50, len(lines))):
                    line_stripped = lines[i].strip()
                    if line_stripped.startswith('【') or (line_stripped.startswith('###') and '动态' in line_stripped):
                        hotspot_end = i
                        break
                    hotspot_end = i + 1
        
        hotspot_lines = lines[hotspot_start:hotspot_end]
        hotspot = '\n'.join([l.strip() for l in hotspot_lines if l.strip()]).strip()
        # 规范化换行符
        hotspot = normalize_newlines(hotspot)
    
    return title, hotspot
