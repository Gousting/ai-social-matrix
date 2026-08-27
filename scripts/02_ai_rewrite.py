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
        "system": "你是一个小红书AI工具领域的真实博主，有3年使用AI工具的经验，踩过无数坑，擅长写保姆级教程。你的文字像跟朋友聊天一样自然，有温度，有个人真实感受，绝对不会有AI味。你写的教程参考了大量高赞爆款帖子的结构：短段落、分点清晰、emoji分隔、关键词堆叠、避坑提醒，每篇都控制在1000字左右，小白能快速读完照着做。",
        "user": """请将以下参考内容改写成一篇小红书图文笔记。

【核心定位】
你是一个真实的AI工具博主，不是AI！写出来的内容必须像真人写的，有个人真实感受、踩坑经历、口语化表达，绝对不能有AI味。

【字数控制 - 非常重要】
正文控制在800-1200字！不要写太长，小白没耐心读完！长教程可以分成上下两篇，这篇只写核心步骤。

【去AI味严格要求 - 必须遵守】
1. 必须有个人真实感受和踩坑经历，比如"我之前踩过这个坑"、"我当时折腾了半天"
2. 观点要有取舍，不要中立无取舍
3. 结构不要太规整，重要的步骤展开写，不重要的一笔带过
4. 避免连接词密集（首先、其次、最后、综上所述、总而言之）
5. 避免大词堆叠、句式整齐、强行概括
6. 不要强行升华、结尾金句、苦难叙事
7. 可以有小瑕疵、口语化表达、语气词，更像真人

【基于高赞帖子二次创作 - 深度参考】
8. 必须深度参考同领域高赞帖子的结构和表达方式：
   - 短段落，每段不超过3行
   - 分点清晰，用emoji或数字标号
   - 关键词堆叠，用短句代替长句
   - 避坑提醒用⚠️标注
   - 重要信息用加粗或emoji突出
9. 学习高赞帖子的标题公式：痛点+数字+情绪+承诺
10. 但必须原创，不能直接复制内容，要加入自己的真实经验

【教程细节要求 - 傻瓜式但不啰嗦】
11. 假设读者是完全的小白，但不要每个术语都长篇大论解释，用简短括号解释就行，比如：
    - GitHub（放代码的网站）
    - API密钥（一串密码）
    - 命令行（黑色输入框）
    - 科学上网（访问国外网站的工具）
12. 每一步要有具体操作：点哪个按钮、输入什么、选哪个选项
13. 辨别官方账号要教方法："看作者名是不是OpenAI"、"看星星/下载量最多的"
14. 安装路径要说明默认位置，或者教怎么找（右键快捷方式→打开文件所在位置）
15. 复杂步骤（如OpenAI注册）简化说明，或者说"这步需要科学上网，具体方法自行搜索"
16. 避坑提醒用⚠️简短标注，不要长篇大论
17. 验证步骤要简单明了："看到XX就是成功了"
18. 绝对禁止使用"最"、"第一"等绝对化用语，用"特别"、"非常"、"比较"代替

【内容结构】
19. 标题控制在20字以内，用数字+emoji吸引点击
20. 开头用痛点/场景引入（1-2句）
21. 中间给步骤/方法（分点，每点简短）
22. 结尾给总结+互动引导
23. 标签5-8个，用空格分隔

【输出格式】
第一行是标题，空一行，然后是正文，最后一行是标签

参考内容标题：{title}
参考内容正文：
{content}

账号定位：{position}
""",
        "max_tokens": 2000,
        "target_length": 1000
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
    v1.7优化：排除步骤描述误判（第一步、第二步等）
    """
    compliance_config = config.settings.get("compliance", {})
    if not compliance_config.get("enabled", True):
        return {"passed": True, "issues": [], "banned_words_found": []}

    private_banned = compliance_config.get("private_traffic_banned_words", [])
    ad_banned = compliance_config.get("ad_law_banned_words", [])

    issues = []
    banned_found = []
    full_text = f"{title}\n{content}"

    # 需要排除的常见词组（不是违禁用法）
    safe_phrases = {
        "第一": ["第一步", "第二步骤", "第一次", "第一时间", "第一行", "第一列", "第一个", "第一种", "第一页", "第一节", "第一章", "第一篇", "第一版", "第一阶段", "第一部分", "第一轮"],
        "最": [
            # 时间相关
            "最近", "最后", "最终", "最早", "最晚", "最新",
            # 程度比较（口语化，非广告法绝对化）
            "最好", "最多", "最少", "最快", "最慢", "最高", "最低", "最大", "最小",
            "最佳", "最优", "最适合", "最常用", "最基础", "最简单", "最详细", "最全面",
            "最核心", "最关键", "最重要", "最有效", "最稳定", "最稳", "最方便", "最实用",
            "最受欢迎", "最常见", "最容易", "最直接", "最基本", "最主要", "最明显",
            # 其他常见用法
            "最前", "最后", "最初", "最终", "最为", "最多", "最少"
        ],
    }

    def is_safe_usage(word: str, text: str) -> bool:
        """检查是否是安全用法"""
        if word not in safe_phrases:
            return False
        for safe in safe_phrases[word]:
            if safe in text:
                # 检查这个safe词组是否包含了word的匹配位置
                # 简单处理：如果文本中包含safe词组，且word在safe词组中，认为是安全的
                return True
        return False

    # 检查私域引流违禁词
    for word in private_banned:
        if word in full_text:
            banned_found.append(word)
            issues.append(f"私域引流违禁词: '{word}'（违规，会被限流/封号）")

    # 检查广告法违禁词（排除步骤描述误判）
    for word in ad_banned:
        if word in full_text:
            # 检查是否是安全用法
            if is_safe_usage(word, full_text):
                # 进一步检查：是否有非安全用法的"第一"
                # 比如"全国第一"、"行业第一"等才是违规
                continue
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


def final_review(draft: Dict, platform: str) -> Dict:
    """
    v2.0新增：最终审核 - 对照用户画像进行全面审核
    检查去AI味、高赞参考、教程细节、合规等维度
    """
    title = draft.get("title", "")
    content = draft.get("content", "")
    full_text = f"{title}\n{content}"

    review = {
        "passed": True,
        "score": 0,
        "dimensions": {},
        "issues": [],
        "suggestions": []
    }

    # 1. 去AI味检查
    ai_signal_score = 100
    ai_issues = []

    # 检查AI味特征词
    ai_patterns = [
        ("首先", "连接词密集"),
        ("其次", "连接词密集"),
        ("最后", "连接词密集"),
        ("综上所述", "强行概括"),
        ("总而言之", "强行概括"),
        ("值得注意的是", "官腔"),
        ("需要指出的是", "官腔"),
        ("在这个过程中", "模板腔"),
        ("通过以上分析", "模板腔"),
        ("不仅...而且", "句式整齐"),
        ("一方面...另一方面", "句式整齐"),
    ]

    for word, issue in ai_patterns:
        if word in full_text:
            ai_signal_score -= 5
            ai_issues.append(f"包含'{word}'，{issue}")

    # 检查是否有个人感受
    personal_signals = ["我", "自己", "亲测", "踩坑", "折腾", "建议", "推荐", "觉得", "感觉"]
    has_personal = any(s in full_text for s in personal_signals)
    if not has_personal:
        ai_signal_score -= 20
        ai_issues.append("缺少个人真实感受，像AI写的")

    # 检查是否有踩坑经历
    pitfall_signals = ["坑", "报错", "失败", "折腾", "注意", "别", "小心"]
    has_pitfall = any(s in full_text for s in pitfall_signals)
    if not has_pitfall:
        ai_signal_score -= 10
        ai_issues.append("缺少踩坑经历和避坑提醒")

    review["dimensions"]["ai_signal"] = {
        "score": max(0, ai_signal_score),
        "issues": ai_issues
    }
    if ai_signal_score < 70:
        review["passed"] = False
        review["issues"].extend(ai_issues)

    # 2. 教程细节检查
    detail_score = 100
    detail_issues = []

    # 检查是否有步骤
    step_patterns = ["第一步", "第二步", "第三步", "1.", "2.", "3.", "①", "②", "③"]
    has_steps = any(p in full_text for p in step_patterns)
    if not has_steps:
        detail_score -= 30
        detail_issues.append("缺少分步骤说明")

    # 检查是否有具体操作细节
    detail_signals = ["点击", "打开", "输入", "选择", "安装", "下载", "配置", "设置", "复制", "粘贴"]
    detail_count = sum(1 for s in detail_signals if s in full_text)
    if detail_count < 3:
        detail_score -= 20
        detail_issues.append("操作细节不够具体，缺少按钮/菜单/路径说明")

    # 检查是否有注意事项
    notice_signals = ["注意", "提醒", "别", "不要", "小心", "坑"]
    has_notice = any(s in full_text for s in notice_signals)
    if not has_notice:
        detail_score -= 15
        detail_issues.append("缺少注意事项和避坑提醒")

    review["dimensions"]["tutorial_detail"] = {
        "score": max(0, detail_score),
        "issues": detail_issues
    }
    if detail_score < 70:
        review["passed"] = False
        review["issues"].extend(detail_issues)

    # 3. 高赞结构检查
    viral_score = 100
    viral_issues = []

    # 检查标题是否有数字
    import re
    if not re.search(r'\d+', title):
        viral_score -= 15
        viral_issues.append("标题缺少数字，不符合爆款公式")

    # 检查开头是否有痛点
    first_lines = content[:100]
    pain_signals = ["坑", "难", "懵", "累", "烦", "不会", "不懂", "折腾", "报错"]
    has_pain = any(s in first_lines for s in pain_signals)
    if not has_pain:
        viral_score -= 15
        viral_issues.append("开头缺少痛点共鸣")

    # 检查结尾是否有互动
    last_lines = content[-100:]
    cta_signals = ["评论", "留言", "告诉我", "你们", "大家", "点赞", "收藏", "关注"]
    has_cta = any(s in last_lines for s in cta_signals)
    if not has_cta:
        viral_score -= 10
        viral_issues.append("结尾缺少互动引导")

    review["dimensions"]["viral_structure"] = {
        "score": max(0, viral_score),
        "issues": viral_issues
    }

    # 4. 合规检查（已有，这里复用）
    compliance = draft.get("compliance", {})
    review["dimensions"]["compliance"] = {
        "passed": compliance.get("passed", True),
        "issues": compliance.get("issues", [])
    }
    if not compliance.get("passed", True):
        review["passed"] = False
        review["issues"].extend(compliance.get("issues", []))

    # 5. 综合评分
    total_score = (
        review["dimensions"]["ai_signal"]["score"] * 0.3 +
        review["dimensions"]["tutorial_detail"]["score"] * 0.3 +
        review["dimensions"]["viral_structure"]["score"] * 0.2 +
        (100 if review["dimensions"]["compliance"]["passed"] else 0) * 0.2
    )
    review["score"] = round(total_score, 1)

    # 生成建议
    if review["score"] >= 90:
        review["suggestions"].append("质量优秀，可以直接发布")
    elif review["score"] >= 75:
        review["suggestions"].append("质量良好，建议根据问题微调后发布")
    else:
        review["suggestions"].append("质量待提升，建议根据问题修改后重新审核")

    return review


def rewrite_single(title: str, content: str, platform: str, position: str = "",
                    source_note_id: str = None, dynamic_reference: str = "") -> Dict:
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

    # v1.6：注入爆款模板参考（从高赞帖子拆解的模板库中匹配）
    viral_reference = ""
    try:
        from scripts.utils.viral_template_helper import get_template_reference
        viral_reference = get_template_reference(title, top_n=2)
        if viral_reference:
            logger.info(f"已匹配爆款模板参考，注入改写Prompt")
    except Exception as e:
        logger.debug(f"爆款模板参考注入失败（不影响主流程）: {e}")

    # 构建Prompt
    user_prompt = template["user"].format(
        title=title,
        content=content if content else "（无正文，请根据标题自行创作）",
        position=position if position else "AI工具教程博主"
    )

    # 追加爆款模板参考
    if viral_reference:
        user_prompt += viral_reference

    # v1.7：追加动态爆款参考（最新采集的高赞帖子共性规律）
    if dynamic_reference:
        user_prompt += dynamic_reference
        logger.info(f"已注入动态爆款参考，共{len(dynamic_reference)}字符")

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

    # v2.0新增：最终审核 - 对照用户画像全面审核
    review = final_review(draft, platform)
    draft["final_review"] = review
    logger.info(f"最终审核: 综合评分{review['score']}分 | "
                f"去AI味{review['dimensions']['ai_signal']['score']}分 | "
                f"教程细节{review['dimensions']['tutorial_detail']['score']}分 | "
                f"爆款结构{review['dimensions']['viral_structure']['score']}分")
    if review["issues"]:
        logger.warning(f"最终审核问题: {review['issues'][:3]}")
    if review["suggestions"]:
        logger.info(f"审核建议: {review['suggestions'][0]}")

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


def rewrite_from_note(note_id: str, platforms: list, position: str = "", dynamic_reference: str = "") -> list:
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
        draft = rewrite_single(title, content, platform, position, source_note_id=note_id, dynamic_reference=dynamic_reference)
        if draft:
            filepath = save_draft(draft)
            saved_files.append(filepath)
            # 标记选题已使用
            db.mark_note_used(note_id)

    return saved_files


def rewrite_top_n(n: int, platforms: list, dynamic_reference: str = "") -> list:
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
            draft = rewrite_single(title, content, platform, position, source_note_id=note_id, dynamic_reference=dynamic_reference)
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
    parser.add_argument("--dynamic-reference", action="store_true",
                        help="启用动态爆款参考（自动采集小红书最新高赞帖子作为参考）")
    parser.add_argument("--keyword", type=str, default="",
                        help="动态参考的搜索关键词（不填则自动从标题提取）")
    parser.add_argument("--dynamic-top", type=int, default=3,
                        help="动态参考采集前N篇（默认3）")

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

    # v1.7：动态爆款参考（在改写前采集最新高赞帖子）
    dynamic_reference = ""
    if args.dynamic_reference:
        keyword = args.keyword
        if not keyword and args.title:
            keyword = args.title[:10]
        elif not keyword and args.text:
            keyword = args.text[:10]
        elif not keyword:
            keyword = "AI工具"

        print(f"\n🔍 正在采集动态爆款参考（关键词: {keyword}，前{args.dynamic_top}篇，赞≥1000或藏≥500）...")
        print("   （首次采集约需2-3分钟，后续使用缓存）")
        try:
            from scripts.utils.dynamic_viral_collector import get_dynamic_reference
            dynamic_reference = get_dynamic_reference(keyword, top_n=args.dynamic_top,
                                                       min_likes=1000, min_favorites=500)
            if dynamic_reference:
                print(f"   ✅ 动态参考采集完成，共{len(dynamic_reference)}字符")
            else:
                print("   ⚠️  动态参考采集失败，将只用静态模板库")
        except Exception as e:
            print(f"   ⚠️  动态参考采集异常: {e}")
            dynamic_reference = ""

    if args.text:
        # 从指定文本改写
        title = args.title or "未命名内容"
        saved_files = []
        for platform in platforms:
            draft = rewrite_single(title, args.text, platform, args.position, dynamic_reference=dynamic_reference)
            if draft:
                filepath = save_draft(draft)
                saved_files.append(filepath)
        print(f"\n改写完成: 共生成{len(saved_files)}篇草稿")
        return

    if args.note_id:
        saved_files = rewrite_from_note(args.note_id, platforms, args.position, dynamic_reference=dynamic_reference)
        print(f"\n改写完成: 共生成{len(saved_files)}篇草稿")
        return

    if args.top:
        saved_files = rewrite_top_n(args.top, platforms, dynamic_reference=dynamic_reference)
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
