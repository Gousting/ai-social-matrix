#!/usr/bin/env python3
"""
爆款拆解分析脚本 (00_viral_analyzer.py)

功能：
  1. 手动输入或批量导入高赞高收藏帖子
  2. 调用LLM进行结构化拆解分析（标题公式/开头钩子/正文结构/结尾CTA/标签组合）
  3. 生成可复用的爆款模板，保存到模板库
  4. 支持列出、搜索、删除模板
  5. AI改写时自动引用最相关的模板作为参考

用法：
  # 手动输入一篇帖子进行拆解
  python scripts/00_viral_analyzer.py --analyze

  # 从JSON文件批量导入拆解
  python scripts/00_viral_analyzer.py --import data/viral_posts_sample.json

  # 列出模板库中的所有模板
  python scripts/00_viral_analyzer.py --list

  # 按关键词搜索模板
  python scripts/00_viral_analyzer.py --search "AI工具"

  # 查看某个模板的详细内容
  python scripts/00_viral_analyzer.py --show <模板ID>

  # 删除某个模板
  python scripts/00_viral_analyzer.py --delete <模板ID>

  # 生成示例帖子JSON文件
  python scripts/00_viral_analyzer.py --generate-sample
"""
import sys
import os
import json
import argparse
import re
from datetime import datetime
from typing import Dict, List, Optional

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from scripts.utils.config_loader import config
from scripts.utils.api_client import api_client
from scripts.utils.logger import logger


# 模板库目录
TEMPLATE_DIR = os.path.join(PROJECT_ROOT, "data", "viral_templates")
os.makedirs(TEMPLATE_DIR, exist_ok=True)


# ============================================
# 爆款拆解Prompt
# ============================================

VIRAL_ANALYSIS_SYSTEM = """你是一个资深社交媒体内容分析师，擅长拆解爆款帖子的底层逻辑。
你需要对给定的高赞高收藏帖子进行结构化拆解，提取可复用的爆款模板。

分析维度：
1. 标题公式：识别标题使用的公式类型（数字型/痛点型/反常识型/对比型/悬念型/利益型/身份型等），并提取可复用的标题模板
2. 开头钩子：分析前3行如何抓住注意力（痛点共鸣/反常识/数据冲击/场景代入/提问式等），提取开头模板
3. 正文结构：拆解正文的逻辑结构（总分总/步骤式/对比式/清单式/故事式等），分段数量，每段功能
4. 结尾CTA：识别结尾的互动引导话术（收藏/评论/关注/转发等），提取结尾模板
5. 标签组合：分析标签策略（流量标签/精准标签/长尾标签），提取高频标签
6. 语言风格：emoji使用密度、语气、段落长度、字数
7. 爆款原因总结：为什么这篇能爆，核心成功因素是什么

输出必须是严格的JSON格式，不要有任何额外文字。"""

VIRAL_ANALYSIS_USER = """请拆解以下高赞帖子，提取可复用的爆款模板。

帖子信息：
- 平台：{platform}
- 标题：{title}
- 正文：
{content}
- 标签：{tags}
- 点赞数：{likes}
- 收藏数：{favorites}
- 评论数：{comments}

请输出JSON格式的拆解结果，包含以下字段：
{{
  "title_formula": "标题公式类型（如：数字+痛点+解决方案）",
  "title_template": "可复用的标题模板（用[关键词]、[数字]、[痛点]等占位符）",
  "title_analysis": "标题为什么吸引人，具体分析",
  "opening_hook_type": "开头钩子类型（如：痛点共鸣）",
  "opening_template": "可复用的开头模板",
  "opening_analysis": "开头钩子分析",
  "body_structure": "正文结构类型（如：步骤式）",
  "body_segments": [
    {{"segment": 1, "function": "段落功能", "content_summary": "内容摘要"}}
  ],
  "body_template": "可复用的正文结构模板",
  "cta_type": "结尾CTA类型（如：收藏引导）",
  "cta_template": "可复用的结尾CTA模板",
  "tag_strategy": "标签策略分析",
  "high_freq_tags": ["高频标签1", "高频标签2"],
  "language_style": {{
    "emoji_density": "emoji使用密度（高/中/低）",
    "tone": "语气（如：亲切朋友式）",
    "paragraph_length": "平均段落长度",
    "total_words": 字数
  }},
  "viral_reasons": ["爆款原因1", "爆款原因2"],
  "reusable_template": "完整的可复用模板（标题+开头+正文结构+结尾+标签）",
  "applicable_topics": ["适用话题1", "适用话题2"]
}}"""


def analyze_viral_post(post: Dict) -> Optional[Dict]:
    """
    拆解一篇高赞帖子

    Args:
        post: 帖子字典，包含title, content, tags, platform, likes, favorites, comments

    Returns:
        拆解结果字典
    """
    title = post.get("title", "")
    content = post.get("content", "")
    tags = post.get("tags", [])
    platform = post.get("platform", "xiaohongshu")
    likes = post.get("likes", 0)
    favorites = post.get("favorites", 0)
    comments = post.get("comments", 0)

    if isinstance(tags, list):
        tags_str = " ".join(tags)
    else:
        tags_str = str(tags)

    user_prompt = VIRAL_ANALYSIS_USER.format(
        platform=platform,
        title=title,
        content=content,
        tags=tags_str,
        likes=likes,
        favorites=favorites,
        comments=comments
    )

    logger.info(f"开始拆解帖子: {title[:30]}...")

    try:
        response, provider = api_client.chat(
            prompt=user_prompt,
            system_prompt=VIRAL_ANALYSIS_SYSTEM,
            max_tokens=3000,
            temperature=0.3
        )
    except Exception as e:
        logger.error(f"API调用失败: {e}")
        return None

    # 解析JSON响应
    try:
        # 提取JSON部分（可能有markdown代码块包裹）
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            json_str = json_match.group(0)
            analysis = json.loads(json_str)
        else:
            analysis = json.loads(response)
    except Exception as e:
        logger.error(f"JSON解析失败: {e}")
        logger.error(f"原始响应: {response[:500]}")
        # 保存原始响应用于调试
        debug_path = os.path.join(TEMPLATE_DIR, f"debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(response)
        return None

    # 添加元数据
    analysis["_metadata"] = {
        "source_title": title,
        "source_platform": platform,
        "source_likes": likes,
        "source_favorites": favorites,
        "source_comments": comments,
        "analyzed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "provider": provider
    }

    # 生成模板ID
    template_id = f"tpl_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    analysis["_template_id"] = template_id
    analysis["_template_name"] = f"{analysis.get('title_formula', '未知公式')} - {title[:15]}"

    logger.info(f"拆解完成: {analysis.get('title_formula', '未知公式')}")
    return analysis


def save_template(analysis: Dict) -> str:
    """
    保存拆解结果到模板库

    Args:
        analysis: 拆解结果字典

    Returns:
        模板文件路径
    """
    template_id = analysis.get("_template_id", f"tpl_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    filename = f"{template_id}.json"
    filepath = os.path.join(TEMPLATE_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)

    logger.info(f"模板已保存: {filepath}")
    return filepath


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
        # 搜索适用话题
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


def get_template_for_rewrite(keyword: str, top_n: int = 3) -> str:
    """
    获取用于AI改写的模板参考文本

    Args:
        keyword: 内容关键词
        top_n: 返回前N个模板

    Returns:
        格式化的模板参考文本
    """
    templates = search_templates(keyword, top_n)
    if not templates:
        return ""

    reference_text = "\n\n===== 爆款模板参考（从高赞帖子拆解） =====\n"
    for i, tpl in enumerate(templates, 1):
        reference_text += f"\n--- 模板{i}: {tpl.get('_template_name', '未知')} ---\n"
        reference_text += f"标题公式: {tpl.get('title_formula', '未知')}\n"
        reference_text += f"标题模板: {tpl.get('title_template', '无')}\n"
        reference_text += f"开头钩子: {tpl.get('opening_hook_type', '未知')} - {tpl.get('opening_template', '无')}\n"
        reference_text += f"正文结构: {tpl.get('body_structure', '未知')}\n"
        reference_text += f"正文模板: {tpl.get('body_template', '无')}\n"
        reference_text += f"结尾CTA: {tpl.get('cta_type', '未知')} - {tpl.get('cta_template', '无')}\n"
        reference_text += f"高频标签: {', '.join(tpl.get('high_freq_tags', []))}\n"
        reference_text += f"爆款原因: {'; '.join(tpl.get('viral_reasons', []))}\n"
        if tpl.get("reusable_template"):
            reference_text += f"完整模板:\n{tpl.get('reusable_template')}\n"

    reference_text += "\n===== 请参考以上爆款模板的结构和风格进行改写，但必须原创，不要直接复制 =====\n"
    return reference_text


def list_templates():
    """列出所有模板"""
    templates = load_all_templates()
    if not templates:
        print("\n📭 模板库为空，请先使用 --analyze 或 --import 拆解帖子\n")
        return

    print(f"\n{'='*100}")
    print(f"  爆款模板库 ({len(templates)}个)")
    print(f"{'='*100}")
    print(f"{'ID':<22} {'公式':<18} {'平台':<8} {'点赞':<8} {'收藏':<8} 适用话题")
    print(f"{'-'*100}")

    for tpl in templates:
        tid = tpl.get("_template_id", "")[:20]
        formula = tpl.get("title_formula", "未知")[:16]
        platform = tpl.get("_metadata", {}).get("source_platform", "")
        likes = tpl.get("_metadata", {}).get("source_likes", 0)
        favorites = tpl.get("_metadata", {}).get("source_favorites", 0)
        topics = ", ".join(tpl.get("applicable_topics", [])[:3])
        print(f"{tid:<22} {formula:<18} {platform:<8} {likes:<8} {favorites:<8} {topics}")

    print(f"{'='*100}\n")


def show_template(template_id: str):
    """显示模板详细内容"""
    templates = load_all_templates()
    target = None
    for tpl in templates:
        if template_id in tpl.get("_template_id", "") or template_id in tpl.get("_filename", ""):
            target = tpl
            break

    if not target:
        print(f"\n❌ 未找到模板: {template_id}\n")
        return

    print(f"\n{'='*80}")
    print(f"  模板详情: {target.get('_template_name', '未知')}")
    print(f"{'='*80}")
    print(f"模板ID: {target.get('_template_id', '')}")
    print(f"来源平台: {target.get('_metadata', {}).get('source_platform', '')}")
    print(f"来源标题: {target.get('_metadata', {}).get('source_title', '')}")
    print(f"数据: 点赞{target.get('_metadata', {}).get('source_likes', 0)} / 收藏{target.get('_metadata', {}).get('source_favorites', 0)} / 评论{target.get('_metadata', {}).get('source_comments', 0)}")
    print(f"拆解时间: {target.get('_metadata', {}).get('analyzed_at', '')}")
    print(f"{'-'*80}")

    print(f"\n📌 标题公式: {target.get('title_formula', '未知')}")
    print(f"   标题模板: {target.get('title_template', '无')}")
    print(f"   标题分析: {target.get('title_analysis', '无')}")

    print(f"\n🎣 开头钩子: {target.get('opening_hook_type', '未知')}")
    print(f"   开头模板: {target.get('opening_template', '无')}")
    print(f"   钩子分析: {target.get('opening_analysis', '无')}")

    print(f"\n📝 正文结构: {target.get('body_structure', '未知')}")
    segments = target.get("body_segments", [])
    for seg in segments:
        print(f"   段落{seg.get('segment', '?')}: {seg.get('function', '')} - {seg.get('content_summary', '')}")
    print(f"   正文模板: {target.get('body_template', '无')}")

    print(f"\n📢 结尾CTA: {target.get('cta_type', '未知')}")
    print(f"   CTA模板: {target.get('cta_template', '无')}")

    print(f"\n🏷️  标签策略: {target.get('tag_strategy', '无')}")
    print(f"   高频标签: {', '.join(target.get('high_freq_tags', []))}")

    style = target.get("language_style", {})
    print(f"\n💬 语言风格: emoji密度={style.get('emoji_density', '未知')}, 语气={style.get('tone', '未知')}, 字数={style.get('total_words', '未知')}")

    print(f"\n🔥 爆款原因:")
    for reason in target.get("viral_reasons", []):
        print(f"   - {reason}")

    print(f"\n🎯 适用话题: {', '.join(target.get('applicable_topics', []))}")

    if target.get("reusable_template"):
        print(f"\n📋 完整可复用模板:")
        print(f"{target.get('reusable_template')}")

    print(f"\n{'='*80}\n")


def delete_template(template_id: str):
    """删除模板"""
    templates = load_all_templates()
    target_file = None
    for tpl in templates:
        if template_id in tpl.get("_template_id", "") or template_id in tpl.get("_filename", ""):
            target_file = tpl.get("_filename", "")
            break

    if not target_file:
        print(f"\n❌ 未找到模板: {template_id}\n")
        return

    filepath = os.path.join(TEMPLATE_DIR, target_file)
    os.remove(filepath)
    print(f"\n✅ 已删除模板: {template_id}\n")


def generate_sample_file():
    """生成示例帖子JSON文件"""
    sample = [
        {
            "platform": "xiaohongshu",
            "title": "装Codex卡了3天😭这5步真的能成",
            "content": "家人们谁懂啊！装个Codex折腾了我整整3天，各种报错各种坑😭\n\n终于让我摸出了一套保姆级安装流程，5步搞定，小白也能学会！\n\n第一步：下载安装包\n去官网下载最新版，注意区分Windows/Mac版本，别下错了！\n\n第二步：安装依赖\n运行前先装Python和Node.js，版本一定要对，不然各种报错\n\n第三步：配置API密钥\n去OpenAI官网申请API key，填到配置文件里，这步最关键\n\n第四步：安装VS Code插件\n在插件市场搜Codex，安装后重启VS Code\n\n第五步：测试运行\n随便打开一个代码文件，按快捷键试试，能补全就成功了！\n\n亲测有效，收藏起来慢慢看，有问题评论区问我～\n\n#Codex #AI编程 #编程工具 #效率工具 #人工智能 #程序员",
            "tags": ["Codex", "AI编程", "编程工具", "效率工具", "人工智能", "程序员"],
            "likes": 2856,
            "favorites": 1892,
            "comments": 156
        },
        {
            "platform": "xiaohongshu",
            "title": "别再瞎找了！2026最好用的5个AI工具",
            "content": "整理了半个月，把2026年真正好用的AI工具都挑出来了！\n\n每一个都是我亲测用了至少1个月的，不好用你来打我👊\n\n1️⃣ Codex - AI编程助手\n写代码速度提升3倍，自动补全+bug修复，程序员必备\n\n2️⃣ Midjourney - AI绘画\n出图质量天花板，做封面做海报都靠它\n\n3️⃣ Notion AI - 笔记+写作\n整理资料、写文章、做总结，一站式搞定\n\n4️⃣ Runway - AI视频\n文字转视频，做短视频神器\n\n5️⃣ Gamma - AI做PPT\n输入主题自动生成PPT，打工人救星\n\n每个工具都有免费额度，学生党也能用！\n\n收藏这篇，需要的时候直接翻～\n\n#AI工具 #效率工具 #人工智能 #打工人必备 #学生党",
            "tags": ["AI工具", "效率工具", "人工智能", "打工人必备", "学生党"],
            "likes": 5623,
            "favorites": 4231,
            "comments": 289
        }
    ]

    sample_path = os.path.join(PROJECT_ROOT, "data", "viral_posts_sample.json")
    with open(sample_path, "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 示例帖子文件已生成: {sample_path}")
    print(f"   包含 {len(sample)} 篇示例帖子")
    print(f"   使用方法: python scripts/00_viral_analyzer.py --import {sample_path}\n")


def interactive_analyze():
    """交互式输入帖子进行拆解"""
    print("\n" + "="*60)
    print("  爆款帖子拆解 - 交互式输入")
    print("="*60)
    print("\n请输入帖子信息（直接回车使用默认值）：\n")

    platform = input("平台 [xiaohongshu]: ").strip() or "xiaohongshu"
    title = input("标题: ").strip()
    if not title:
        print("\n❌ 标题不能为空\n")
        return

    print("\n正文（输入完成后单独一行输入 . 结束）:")
    content_lines = []
    while True:
        line = input()
        if line.strip() == ".":
            break
        content_lines.append(line)
    content = "\n".join(content_lines)

    tags_input = input("\n标签（用空格分隔）: ").strip()
    tags = tags_input.split() if tags_input else []

    likes = int(input("点赞数 [0]: ").strip() or "0")
    favorites = int(input("收藏数 [0]: ").strip() or "0")
    comments = int(input("评论数 [0]: ").strip() or "0")

    post = {
        "platform": platform,
        "title": title,
        "content": content,
        "tags": tags,
        "likes": likes,
        "favorites": favorites,
        "comments": comments
    }

    print("\n⏳ 正在拆解分析，请稍候...\n")
    analysis = analyze_viral_post(post)

    if analysis:
        filepath = save_template(analysis)
        print(f"\n✅ 拆解完成！")
        print(f"   标题公式: {analysis.get('title_formula', '未知')}")
        print(f"   开头钩子: {analysis.get('opening_hook_type', '未知')}")
        print(f"   正文结构: {analysis.get('body_structure', '未知')}")
        print(f"   结尾CTA: {analysis.get('cta_type', '未知')}")
        print(f"   模板已保存: {filepath}")
        print(f"\n   使用 --show {analysis.get('_template_id', '')} 查看完整拆解结果\n")
    else:
        print("\n❌ 拆解失败，请检查API配置或帖子内容\n")


def import_from_file(filepath: str):
    """从JSON文件批量导入拆解"""
    if not os.path.exists(filepath):
        print(f"\n❌ 文件不存在: {filepath}\n")
        return

    with open(filepath, "r", encoding="utf-8") as f:
        posts = json.load(f)

    if not isinstance(posts, list):
        print("\n❌ JSON文件格式错误，应该是帖子数组\n")
        return

    print(f"\n📥 从 {filepath} 导入 {len(posts)} 篇帖子进行拆解\n")

    success_count = 0
    for i, post in enumerate(posts, 1):
        title = post.get("title", "无标题")[:30]
        print(f"[{i}/{len(posts)}] 拆解: {title}...")
        analysis = analyze_viral_post(post)
        if analysis:
            save_template(analysis)
            success_count += 1
            print(f"  ✅ 完成: {analysis.get('title_formula', '未知公式')}")
        else:
            print(f"  ❌ 失败")

    print(f"\n{'='*60}")
    print(f"  批量拆解完成: 成功{success_count}/{len(posts)}")
    print(f"  使用 --list 查看所有模板")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="爆款拆解分析脚本")
    parser.add_argument("--analyze", action="store_true", help="交互式输入帖子进行拆解")
    parser.add_argument("--import", dest="import_file", type=str, help="从JSON文件批量导入拆解")
    parser.add_argument("--list", action="store_true", help="列出所有模板")
    parser.add_argument("--search", type=str, help="按关键词搜索模板")
    parser.add_argument("--show", type=str, help="显示模板详细内容（模板ID）")
    parser.add_argument("--delete", type=str, help="删除模板（模板ID）")
    parser.add_argument("--generate-sample", action="store_true", help="生成示例帖子JSON文件")

    args = parser.parse_args()

    if args.analyze:
        interactive_analyze()
    elif args.import_file:
        import_from_file(args.import_file)
    elif args.list:
        list_templates()
    elif args.search:
        results = search_templates(args.search, top_n=10)
        if not results:
            print(f"\n❌ 未找到与 '{args.search}' 相关的模板\n")
        else:
            print(f"\n🔍 搜索 '{args.search}' 找到 {len(results)} 个模板:\n")
            for i, tpl in enumerate(results, 1):
                print(f"  {i}. [{tpl.get('_template_id', '')[:20]}] {tpl.get('title_formula', '未知')} - {tpl.get('_metadata', {}).get('source_title', '')[:30]}")
            print()
    elif args.show:
        show_template(args.show)
    elif args.delete:
        delete_template(args.delete)
    elif args.generate_sample:
        generate_sample_file()
    else:
        parser.print_help()
        print("\n💡 快速开始:")
        print("  1. 生成示例帖子: python scripts/00_viral_analyzer.py --generate-sample")
        print("  2. 批量拆解示例: python scripts/00_viral_analyzer.py --import data/viral_posts_sample.json")
        print("  3. 查看模板库:   python scripts/00_viral_analyzer.py --list")
        print()


if __name__ == "__main__":
    main()
