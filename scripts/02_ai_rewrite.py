#!/usr/bin/env python3
"""
AI内容改写脚本 (02_ai_rewrite.py)

功能：
  1. 从选题库读取候选选题
  2. 按平台生成差异化改写版本（小红书/知乎/B站/公众号/视频号）
  3. 调用免费LLM API进行改写
  4. 原创性自检（相似度检测）
  5. 质量检查（字数、结构元素）
  6. 保存为草稿JSON到待审核目录

用法：
  # 改写指定选题（按note_id），生成所有平台版本
  python scripts/02_ai_rewrite.py --note-id sample_001 --platform all

  # 改写Top N选题，生成所有平台版本
  python scripts/02_ai_rewrite.py --top 5 --platform all

  # 只改写小红书版本
  python scripts/02_ai_rewrite.py --note-id sample_001 --platform xiaohongshu

  # 从指定文本改写（不依赖选题库）
  python scripts/02_ai_rewrite.py --text "参考内容..." --title "标题" --platform xiaohongshu

  # 查看待审核草稿列表
  python scripts/02_ai_rewrite.py --list
"""
import sys
import os
import json
import argparse
from datetime import datetime
from typing import Dict, List, Optional

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from scripts.utils.config_loader import config
from scripts.utils.db import db
from scripts.utils.api_client import api_client
from scripts.utils.logger import logger


# ============================================
# 各平台改写Prompt模板
# ============================================

PROMPT_TEMPLATES = {
    "xiaohongshu": {
        "name": "小红书",
        "system": "你是一个小红书AI工具领域的爆款博主，擅长写保姆级教程和干货分享，语气亲切像朋友聊天，喜欢用emoji和分点结构。",
        "user": """请将以下参考内容改写成一篇小红书图文笔记。

要求：
1. 标题控制在20字以内，用数字+emoji吸引点击，制造好奇心或痛点
2. 正文500字左右，分点清晰，每段不超过3行，多用emoji分隔
3. 结构：开头用痛点/场景引入（1-2句）→ 中间给步骤/方法（分点）→ 结尾给总结+互动引导
4. 标签5-8个，包含#AI工具 #效率工具 等相关标签，用空格分隔
5. 语气亲切自然，像朋友分享经验，不要太官方，避免绝对化用语
6. 必须原创改写，不要直接复制原文，加入自己的理解和经验
7. 输出格式：第一行是标题，空一行，然后是正文，最后一行是标签

参考内容标题：{title}
参考内容正文：
{content}

账号定位：{position}
""",
        "max_tokens": 1500,
        "target_length": 500
    },

    "zhihu": {
        "name": "知乎",
        "system": "你是一个知乎AI领域的优质答主，专业、严谨、有深度，擅长写长文教程和深度分析，结构清晰，逻辑严密。",
        "user": """请将以下参考内容改写成一篇知乎长文回答或文章。

要求：
1. 标题用问题式或总结式，20-30字，吸引点击
2. 正文2000-3000字，结构清晰：背景介绍→核心原理/概念→详细步骤→踩坑经验→总结展望
3. 包含代码块（用```包裹）、配置示例、参数说明
4. 语言专业但不晦涩，适合有一定技术基础的读者，避免太口语化
5. 必须原创改写，加入自己的分析和经验，不要简单复制
6. 输出格式：第一行是标题，空一行，然后是正文（支持Markdown格式）

参考内容标题：{title}
参考内容正文：
{content}

账号定位：{position}
""",
        "max_tokens": 4000,
        "target_length": 2500
    },

    "bilibili": {
        "name": "B站专栏",
        "system": "你是一个B站科技区UP主，擅长写专栏教程，风格活泼有趣，步骤详细，适合年轻开发者群体。",
        "user": """请将以下参考内容改写成一篇B站专栏文章。

要求：
1. 标题吸引人，20-50字，可以用悬念或数字
2. 正文1500-2000字，步骤详细，每步配说明
3. 结构：开头引入（为什么学这个）→ 环境准备 → 详细步骤 → 常见问题 → 总结
4. 包含代码块、终端命令截图说明、配置示例
5. 语言活泼有趣，可以适当用网络用语，但不要太水
6. 必须原创改写，加入自己的踩坑经验
7. 输出格式：第一行是标题，空一行，然后是正文（支持Markdown）

参考内容标题：{title}
参考内容正文：
{content}

账号定位：{position}
""",
        "max_tokens": 3000,
        "target_length": 1800
    },

    "wechat_mp": {
        "name": "公众号",
        "system": "你是一个公众号AI领域的深度作者，擅长写体系化的深度长文，有独家观点，逻辑严密，适合私域传播。",
        "user": """请将以下参考内容改写成一篇公众号深度长文。

要求：
1. 标题有吸引力，20-30字，可以用悬念或痛点
2. 正文3000字以上，体系化、有深度，不能只是教程罗列
3. 结构：引言（痛点/背景）→ 核心概念解析 → 完整教程 → 深度分析/对比 → 适用场景 → 未来趋势 → 总结
4. 包含代码示例、配置说明、对比表格
5. 语言正式但不生硬，有自己的观点和判断，避免人云亦云
6. 必须原创改写，加入深度思考和独家观点
7. 输出格式：第一行是标题，空一行，然后是正文（支持Markdown）

参考内容标题：{title}
参考内容正文：
{content}

账号定位：{position}
""",
        "max_tokens": 5000,
        "target_length": 3000
    },

    "wechat_channels": {
        "name": "视频号",
        "system": "你是一个视频号图文创作者，擅长写精简的干货卡片，内容极简，1分钟读完，适合泛用户群体。",
        "user": """请将以下参考内容改写成一篇视频号图文动态（精简卡片版）。

要求：
1. 标题简短有力，15字以内
2. 正文200字以内，极简，只保留最核心的3个要点
3. 结构：一句话引入 → 3个核心要点（用数字编号）→ 一句话总结
4. 标签3-5个，简洁
5. 语言极简，避免废话，每个字都要有信息量
6. 必须原创改写
7. 输出格式：第一行是标题，空一行，然后是正文，最后一行是标签

参考内容标题：{title}
参考内容正文：
{content}

账号定位：{position}
""",
        "max_tokens": 800,
        "target_length": 200
    }
}


def parse_ai_response(response: str, platform: str) -> Dict:
    """
    解析AI返回的内容，提取标题、正文、标签
    """
    lines = response.strip().split("\n")
    result = {
        "title": "",
        "content": "",
        "tags": [],
        "raw": response
    }

    if not lines:
        return result

    # 第一行通常是标题
    result["title"] = lines[0].strip().lstrip("#").strip()

    # 找标签行（通常包含#号）
    content_lines = []
    for line in lines[1:]:
        stripped = line.strip()
        # 检测标签行（以#开头或包含多个#标签）
        if stripped.startswith("#") and len(stripped.split("#")) > 2:
            tags = [t.strip() for t in stripped.split("#") if t.strip()]
            result["tags"] = [f"#{t}" if not t.startswith("#") else t for t in tags]
        elif stripped and not result["tags"]:
            # 检查是否是标签行（行内包含多个#）
            if stripped.count("#") >= 2 and len(stripped) < 100:
                tags = [t.strip() for t in stripped.split("#") if t.strip()]
                result["tags"] = [f"#{t}" if not t.startswith("#") else t for t in tags]
            else:
                content_lines.append(line)

    result["content"] = "\n".join(content_lines).strip()

    # 如果没提取到标签，用默认标签
    if not result["tags"]:
        result["tags"] = ["#AI工具", "#效率工具", "#编程"]

    return result


def check_compliance(content: str, title: str = "") -> Dict:
    """
    v1.5新增：合规检查
    检查内容中是否包含私域引流违禁词、广告法违禁词
    """
    compliance_config = config.settings.get("compliance", {})
    if not compliance_config.get("enabled", True):
        return {"passed": True, "issues": [], "banned_words_found": []}

    private_banned = compliance_config.get("private_traffic_banned_words", [])
    ad_banned = compliance_config.get("ad_law_banned_words", [])

    issues = []
    banned_found = []
    full_text = f"{title}\n{content}"

    # 检查私域引流违禁词
    for word in private_banned:
        if word in full_text:
            banned_found.append(word)
            issues.append(f"私域引流违禁词: '{word}'（违规，会被限流/封号）")

    # 检查广告法违禁词
    for word in ad_banned:
        if word in full_text:
            banned_found.append(word)
            issues.append(f"广告法违禁词: '{word}'（绝对化用语）")

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "banned_words_found": banned_found
    }


def add_ai_content_label(content: str, platform: str) -> str:
    """
    v1.5新增：添加AI内容标识
    2026年平台要求：发布时必须主动标识AI内容，正文标注"人工智能生成"
    """
    label_config = config.settings.get("rewrite", {}).get("ai_content_label", {})
    if not label_config.get("enabled", True):
        return content

    text_label = label_config.get("text_label", "人工智能生成")

    # 在内容末尾添加AI标识
    if text_label not in content:
        content = content.rstrip() + f"\n\n（{text_label}，已人工审核优化）"

    return content


def check_quality(draft: Dict, platform: str) -> Dict:
    """
    质量检查：字数、结构元素
    返回检查结果
    """
    template = PROMPT_TEMPLATES.get(platform, {})
    target_length = template.get("target_length", 500)
    content = draft.get("content", "")
    title = draft.get("title", "")

    issues = []
    passed = True

    # 标题检查
    if not title:
        issues.append("标题为空")
        passed = False
    elif len(title) > 30 and platform in ["xiaohongshu", "wechat_channels"]:
        issues.append(f"标题过长({len(title)}字)，建议{20 if platform=='xiaohongshu' else 15}字以内")

    # 正文字数检查
    content_length = len(content)
    if content_length < target_length * 0.5:
        issues.append(f"正文过短({content_length}字)，目标{target_length}字")
        passed = False
    elif content_length > target_length * 2:
        issues.append(f"正文过长({content_length}字)，目标{target_length}字")

    # 标签检查
    tags = draft.get("tags", [])
    if not tags:
        issues.append("未提取到标签")

    return {
        "passed": passed,
        "issues": issues,
        "content_length": content_length,
        "target_length": target_length,
        "title_length": len(title),
        "tags_count": len(tags)
    }


def rewrite_single(title: str, content: str, platform: str, position: str = "",
                    source_note_id: str = None) -> Dict:
    """
    改写单篇内容为指定平台版本

    Returns:
        草稿字典
    """
    template = PROMPT_TEMPLATES.get(platform)
    if not template:
        logger.error(f"不支持的平台: {platform}")
        return None

    logger.info(f"开始改写: [{template['name']}] {title[:30]}")

    # 构建Prompt
    user_prompt = template["user"].format(
        title=title,
        content=content if content else "（无正文，请根据标题自行创作）",
        position=position if position else "AI工具教程博主"
    )

    # 调用API
    try:
        response, provider = api_client.chat(
            prompt=user_prompt,
            system_prompt=template["system"],
            max_tokens=template.get("max_tokens", 2000),
            temperature=0.7
        )
    except Exception as e:
        logger.error(f"API调用失败: {e}")
        return None

    # 解析响应
    draft = parse_ai_response(response, platform)
    draft["platform"] = platform
    draft["platform_name"] = template["name"]
    draft["provider"] = provider
    draft["source_title"] = title
    draft["source_note_id"] = source_note_id
    draft["position"] = position
    draft["rewrite_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # v1.5：添加AI内容标识（2026年平台要求必须主动标识）
    draft["content"] = add_ai_content_label(draft["content"], platform)
    draft["ai_label_added"] = True

    # v1.5：合规检查（私域引流违禁词、广告法违禁词）
    compliance = check_compliance(draft["content"], draft["title"])
    draft["compliance"] = compliance
    if not compliance["passed"]:
        logger.warning(f"合规检查未通过: {compliance['issues']}")
        draft["quality_warning"] = f"合规问题: {'; '.join(compliance['issues'])}"
    else:
        logger.info("合规检查通过")

    # v1.5：人工修改率提醒（2026年平台要求≥60%）
    human_mod_rate = config.settings.get("rewrite", {}).get("human_modification_rate", 60)
    draft["human_modification_required"] = human_mod_rate
    draft["human_modification_note"] = (
        f"⚠️ 人工修改率必须≥{human_mod_rate}%（2026年平台要求），"
        f"AI直发必被限流。请人工重写开头+加真实细节+验证代码准确性。"
    )

    # 原创性自检
    if content:
        similarity = api_client.check_similarity(content, draft["content"])
        draft["similarity"] = similarity
        threshold = config.rewrite_config.get("similarity_threshold", 60)
        if similarity > threshold:
            logger.warning(f"原创性自检未通过: 相似度{similarity}% > {threshold}%")
            draft["quality_warning"] = f"相似度{similarity}%偏高，建议人工修改"
        else:
            logger.info(f"原创性自检通过: 相似度{similarity}%")
    else:
        draft["similarity"] = 0

    # 质量检查
    quality = check_quality(draft, platform)
    draft["quality"] = quality
    if quality["passed"]:
        logger.info(f"质量检查通过: {quality['content_length']}字 (目标{quality['target_length']}字)")
    else:
        logger.warning(f"质量检查问题: {quality['issues']}")

    return draft


def save_draft(draft: Dict) -> str:
    """
    保存草稿到待审核目录
    返回文件路径
    """
    output_dir = config.get_path("drafted_pending")
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    platform = draft.get("platform", "unknown")
    safe_title = draft.get("title", "untitled")[:20].replace("/", "_").replace("\\", "_")
    filename = f"{timestamp}_{platform}_{safe_title}.json"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)

    logger.info(f"草稿已保存: {filepath}")
    return filepath


def rewrite_from_note(note_id: str, platforms: list, position: str = "") -> list:
    """
    从选题库读取指定选题，改写为多个平台版本
    """
    # 从数据库获取选题
    topics = db.get_top_topics(limit=100)
    note = None
    for t in topics:
        if t.get("note_id") == note_id:
            note = t
            break

    if not note:
        logger.error(f"未找到选题: {note_id}")
        return []

    title = note.get("title", "")
    content = note.get("content", "")
    if not position:
        position = "AI工具教程博主，专注分享AI工具安装使用教程"

    saved_files = []
    for platform in platforms:
        draft = rewrite_single(title, content, platform, position, source_note_id=note_id)
        if draft:
            filepath = save_draft(draft)
            saved_files.append(filepath)
            # 标记选题已使用
            db.mark_note_used(note_id)

    return saved_files


def rewrite_top_n(n: int, platforms: list) -> list:
    """
    改写Top N选题
    """
    topics = db.get_top_topics(limit=n)
    if not topics:
        logger.error("选题库为空，请先导入或采集选题")
        return []

    logger.info(f"开始改写Top {len(topics)}选题，平台: {platforms}")
    saved_files = []
    for i, note in enumerate(topics, 1):
        logger.info(f"[{i}/{len(topics)}] 处理选题: {note.get('title', '')[:30]}")
        title = note.get("title", "")
        content = note.get("content", "")
        note_id = note.get("note_id", "")
        position = "AI工具教程博主，专注分享AI工具安装使用教程"

        for platform in platforms:
            draft = rewrite_single(title, content, platform, position, source_note_id=note_id)
            if draft:
                filepath = save_draft(draft)
                saved_files.append(filepath)

        db.mark_note_used(note_id)

    logger.info(f"Top N改写完成: 共生成{len(saved_files)}篇草稿")
    return saved_files


def list_drafts():
    """列出待审核草稿"""
    draft_dir = config.get_path("drafted_pending")
    if not os.path.exists(draft_dir):
        print("待审核目录为空")
        return

    files = [f for f in os.listdir(draft_dir) if f.endswith(".json")]
    if not files:
        print("待审核目录为空")
        return

    print(f"\n{'='*80}")
    print(f"  待审核草稿列表 ({len(files)}篇)")
    print(f"{'='*80}")
    print(f"{'文件名':<45} {'平台':<10} {'字数':<6} {'相似度':<6} 标题")
    print(f"{'-'*80}")

    for f in sorted(files):
        filepath = os.path.join(draft_dir, f)
        try:
            with open(filepath, "r", encoding="utf-8") as fp:
                draft = json.load(fp)
            title = draft.get("title", "")[:30]
            platform = draft.get("platform_name", draft.get("platform", ""))
            content_len = len(draft.get("content", ""))
            similarity = draft.get("similarity", 0)
            print(f"{f:<45} {platform:<10} {content_len:<6} {similarity:<6.0f}% {title}")
        except Exception as e:
            print(f"{f:<45} 读取失败: {e}")

    print(f"{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(description="AI内容改写脚本")
    parser.add_argument("--note-id", type=str, help="选题库中的note_id")
    parser.add_argument("--top", type=int, help="改写Top N选题")
    parser.add_argument("--text", type=str, help="直接输入参考内容文本")
    parser.add_argument("--title", type=str, help="参考内容标题（配合--text使用）")
    parser.add_argument("--platform", type=str, default="all",
                        help="目标平台: xiaohongshu/zhihu/bilibili/wechat_mp/wechat_channels/all")
    parser.add_argument("--position", type=str, default="", help="账号定位描述")
    parser.add_argument("--list", action="store_true", help="列出待审核草稿")

    args = parser.parse_args()

    # 解析平台列表
    if args.platform == "all":
        platforms = list(PROMPT_TEMPLATES.keys())
    else:
        platforms = [args.platform] if args.platform in PROMPT_TEMPLATES else []
        if not platforms:
            logger.error(f"不支持的平台: {args.platform}")
            return

    if args.list:
        list_drafts()
        return

    if args.text:
        # 从指定文本改写
        title = args.title or "未命名内容"
        saved_files = []
        for platform in platforms:
            draft = rewrite_single(title, args.text, platform, args.position)
            if draft:
                filepath = save_draft(draft)
                saved_files.append(filepath)
        print(f"\n改写完成: 共生成{len(saved_files)}篇草稿")
        return

    if args.note_id:
        saved_files = rewrite_from_note(args.note_id, platforms, args.position)
        print(f"\n改写完成: 共生成{len(saved_files)}篇草稿")
        return

    if args.top:
        saved_files = rewrite_top_n(args.top, platforms)
        print(f"\n改写完成: 共生成{len(saved_files)}篇草稿")
        return

    # 默认显示帮助
    parser.print_help()
    print("\n常用命令:")
    print("  # 从选题库改写指定选题为所有平台版本")
    print("  python scripts/02_ai_rewrite.py --note-id sample_001 --platform all")
    print("  # 改写Top5选题")
    print("  python scripts/02_ai_rewrite.py --top 5 --platform all")
    print("  # 从指定文本改写小红书版本")
    print('  python scripts/02_ai_rewrite.py --text "参考内容" --title "标题" --platform xiaohongshu')
    print("  # 查看待审核草稿")
    print("  python scripts/02_ai_rewrite.py --list")


if __name__ == "__main__":
    main()
