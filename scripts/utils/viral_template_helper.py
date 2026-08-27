"""
爆款模板参考工具 (viral_template_helper.py)

为AI改写提供爆款模板参考，从模板库中匹配最相关的模板。
"""
import os
import sys
import json
from typing import List, Dict

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from scripts.utils.logger import logger


# 模板库目录
TEMPLATE_DIR = os.path.join(PROJECT_ROOT, "data", "viral_templates")


def load_all_templates() -> List[Dict]:
    """加载模板库中的所有模板"""
    templates = []
    if not os.path.exists(TEMPLATE_DIR):
        return templates

    for filename in os.listdir(TEMPLATE_DIR):
        if not filename.endswith(".json") or filename.startswith("debug_"):
            continue
        filepath = os.path.join(TEMPLATE_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                template = json.load(f)
            template["_filename"] = filename
            templates.append(template)
        except Exception as e:
            logger.warning(f"加载模板失败 {filename}: {e}")

    return templates


def search_templates(keyword: str, top_n: int = 5) -> List[Dict]:
    """
    按关键词搜索模板

    Args:
        keyword: 搜索关键词
        top_n: 返回前N个结果

    Returns:
        匹配的模板列表
    """
    templates = load_all_templates()
    if not templates:
        return []

    keyword_lower = keyword.lower()
    scored = []

    for tpl in templates:
        score = 0
        # 搜索适用话题（权重最高）
        for topic in tpl.get("applicable_topics", []):
            if keyword_lower in topic.lower():
                score += 10
        # 搜索标题公式
        if keyword_lower in tpl.get("title_formula", "").lower():
            score += 5
        # 搜索高频标签
        for tag in tpl.get("high_freq_tags", []):
            if keyword_lower in tag.lower():
                score += 3
        # 搜索源标题
        if keyword_lower in tpl.get("_metadata", {}).get("source_title", "").lower():
            score += 2
        # 搜索完整模板
        if keyword_lower in tpl.get("reusable_template", "").lower():
            score += 1

        if score > 0:
            scored.append((score, tpl))

    # 按分数排序
    scored.sort(key=lambda x: x[0], reverse=True)
    return [tpl for _, tpl in scored[:top_n]]


def extract_keywords(text: str) -> List[str]:
    """
    从文本中提取关键词（简单实现，提取长度>=2的中文词和英文词）

    Args:
        text: 输入文本

    Returns:
        关键词列表
    """
    import re
    # 提取中文词（2-4个字）
    chinese_words = re.findall(r'[\u4e00-\u9fa5]{2,4}', text)
    # 提取英文词
    english_words = re.findall(r'[a-zA-Z]{2,}', text)
    # 合并并去重，保留顺序
    seen = set()
    keywords = []
    for w in chinese_words + english_words:
        w_lower = w.lower()
        if w_lower not in seen and len(w) >= 2:
            seen.add(w_lower)
            keywords.append(w)
    return keywords[:5]  # 取前5个关键词


def get_template_reference(title: str, top_n: int = 2) -> str:
    """
    获取用于AI改写的模板参考文本

    Args:
        title: 内容标题（用于匹配关键词）
        top_n: 返回前N个模板

    Returns:
        格式化的模板参考文本，如果没有匹配的模板则返回空字符串
    """
    # 从标题中提取关键词
    keywords = extract_keywords(title)
    if not keywords:
        return ""

    # 用第一个关键词搜索
    matched = []
    for kw in keywords[:3]:  # 尝试前3个关键词
        results = search_templates(kw, top_n=top_n)
        for tpl in results:
            if tpl.get("_template_id") not in [m.get("_template_id") for m in matched]:
                matched.append(tpl)
        if len(matched) >= top_n:
            break

    if not matched:
        return ""

    # 格式化参考文本
    reference_text = "\n\n===== 爆款模板参考（从高赞帖子拆解） =====\n"
    for i, tpl in enumerate(matched[:top_n], 1):
        reference_text += f"\n--- 模板{i}: {tpl.get('_template_name', '未知')} ---\n"
        reference_text += f"标题公式: {tpl.get('title_formula', '未知')}\n"
        reference_text += f"标题模板: {tpl.get('title_template', '无')}\n"
        reference_text += f"开头钩子: {tpl.get('opening_hook_type', '未知')}\n"
        if tpl.get("opening_template"):
            reference_text += f"开头模板: {tpl.get('opening_template')}\n"
        reference_text += f"正文结构: {tpl.get('body_structure', '未知')}\n"
        if tpl.get("body_template"):
            reference_text += f"正文模板: {tpl.get('body_template')}\n"
        reference_text += f"结尾CTA: {tpl.get('cta_type', '未知')}\n"
        if tpl.get("cta_template"):
            reference_text += f"CTA模板: {tpl.get('cta_template')}\n"
        if tpl.get("high_freq_tags"):
            reference_text += f"高频标签: {', '.join(tpl.get('high_freq_tags', []))}\n"
        if tpl.get("viral_reasons"):
            reference_text += f"爆款原因: {'; '.join(tpl.get('viral_reasons', [])[:3])}\n"

    reference_text += "\n===== 请参考以上爆款模板的结构和风格进行改写，但必须原创，不要直接复制 =====\n"
    return reference_text
