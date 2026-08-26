#!/usr/bin/env python3
"""
合规检查脚本 (05_compliance_check.py)

功能：
  1. 批量检查待审核草稿的合规性
  2. 检测私域引流违禁词（扣1/加我/vx/微信等）
  3. 检测广告法违禁词（最/第一/唯一等）
  4. 检测AI内容标识是否存在
  5. 生成合规检查报告
  6. 标记不合规草稿，阻止发布

用法：
  # 检查所有待审核草稿
  python scripts/05_compliance_check.py

  # 检查指定平台的草稿
  python scripts/05_compliance_check.py --platform xiaohongshu

  # 检查指定草稿
  python scripts/05_compliance_check.py --draft <草稿文件名>

  # 自动修复（移除违禁词，添加AI标识）
  python scripts/05_compliance_check.py --auto-fix

  # 查看合规配置
  python scripts/05_compliance_check.py --show-config
"""
import sys
import os
import json
import argparse
from datetime import datetime
from typing import Dict, List

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from scripts.utils.config_loader import config
from scripts.utils.logger import logger


# ============================================
# 合规检查核心
# ============================================

def load_compliance_config() -> Dict:
    """加载合规检查配置"""
    return config.settings.get("compliance", {})


def check_private_traffic_words(content: str, title: str = "",
                                 banned_words: List[str] = None) -> Dict:
    """
    检查私域引流违禁词

    2026年小红书新规：评论区/正文/私信中出现"扣1"、"加我"、"vx"等
    属于私域导流违规，处罚：轻度限流15天，重度永久封号
    """
    if banned_words is None:
        compliance_config = load_compliance_config()
        banned_words = compliance_config.get("private_traffic_banned_words", [])

    full_text = f"{title}\n{content}"
    found = []
    positions = []

    for word in banned_words:
        if word in full_text:
            found.append(word)
            # 记录出现位置
            idx = full_text.find(word)
            context = full_text[max(0, idx-10):idx+len(word)+10]
            positions.append({"word": word, "context": context})

    return {
        "passed": len(found) == 0,
        "banned_words_found": found,
        "positions": positions,
        "severity": "high" if found else "none",
        "description": "私域引流违禁词检测（2026年新规，违规会限流/封号）"
    }


def check_ad_law_words(content: str, title: str = "",
                        banned_words: List[str] = None) -> Dict:
    """
    检查广告法违禁词（绝对化用语）
    """
    if banned_words is None:
        compliance_config = load_compliance_config()
        banned_words = compliance_config.get("ad_law_banned_words", [])

    full_text = f"{title}\n{content}"
    found = []

    for word in banned_words:
        if word in full_text:
            found.append(word)

    return {
        "passed": len(found) == 0,
        "banned_words_found": found,
        "severity": "medium" if found else "none",
        "description": "广告法违禁词检测（绝对化用语）"
    }


def check_ai_content_label(content: str) -> Dict:
    """
    检查AI内容标识是否存在

    2026年平台要求：发布AI生成内容必须主动标识
    - 发布时勾选"AI合成内容"
    - 正文标注"人工智能生成"（字体不小于正文80%）
    处罚：首次漏标限流7天，二次禁言30天，三次永久封禁
    """
    label_config = config.settings.get("rewrite", {}).get("ai_content_label", {})
    text_label = label_config.get("text_label", "人工智能生成")

    has_label = text_label in content or "AI生成" in content or "人工智能" in content

    return {
        "passed": has_label,
        "has_label": has_label,
        "required_label": text_label,
        "severity": "high" if not has_label else "none",
        "description": "AI内容标识检测（2026年新规，未标识会限流）"
    }


def check_draft_compliance(draft: Dict) -> Dict:
    """
    检查单篇草稿的完整合规性
    """
    title = draft.get("title", "")
    content = draft.get("content", "")

    results = {
        "private_traffic": check_private_traffic_words(content, title),
        "ad_law": check_ad_law_words(content, title),
        "ai_label": check_ai_content_label(content),
    }

    # 汇总
    all_passed = all(r["passed"] for r in results.values())
    high_severity_issues = [r for r in results.values() if r["severity"] == "high"]

    return {
        "draft_filename": draft.get("_filename", ""),
        "title": title,
        "platform": draft.get("platform", ""),
        "overall_passed": all_passed,
        "has_high_severity": len(high_severity_issues) > 0,
        "checks": results,
        "check_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


def auto_fix_draft(draft: Dict, compliance_result: Dict) -> Dict:
    """
    自动修复合规问题
    - 添加AI内容标识
    - 私域引流违禁词无法自动修复（需要人工改写），只做标记
    """
    content = draft.get("content", "")
    fixed = False
    fix_notes = []

    # 添加AI内容标识
    ai_check = compliance_result["checks"]["ai_label"]
    if not ai_check["passed"]:
        label_config = config.settings.get("rewrite", {}).get("ai_content_label", {})
        text_label = label_config.get("text_label", "人工智能生成")
        content = content.rstrip() + f"\n\n（{text_label}，已人工审核优化）"
        draft["content"] = content
        fixed = True
        fix_notes.append(f"已添加AI内容标识: {text_label}")

    # 私域引流违禁词无法自动修复，只做警告
    private_check = compliance_result["checks"]["private_traffic"]
    if not private_check["passed"]:
        fix_notes.append(
            f"⚠️ 私域引流违禁词无法自动修复，请人工改写: {private_check['banned_words_found']}"
        )

    draft["compliance_fixed"] = fixed
    draft["compliance_fix_notes"] = fix_notes

    return draft


# ============================================
# 草稿管理
# ============================================

def load_pending_drafts(platform: str = None) -> List[Dict]:
    """加载待审核草稿"""
    draft_dir = config.get_path("drafted_pending")
    if not os.path.exists(draft_dir):
        return []

    drafts = []
    for filename in os.listdir(draft_dir):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(draft_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                draft = json.load(f)
            draft["_filename"] = filename
            draft["_filepath"] = filepath
            if platform is None or draft.get("platform") == platform:
                drafts.append(draft)
        except Exception as e:
            logger.error(f"读取草稿失败 {filename}: {e}")

    return drafts


def save_draft(draft: Dict):
    """保存草稿（覆盖原文件）"""
    filepath = draft.get("_filepath", "")
    if not filepath:
        return
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)


# ============================================
# 报告输出
# ============================================

def print_compliance_report(results: List[Dict]):
    """打印合规检查报告"""
    if not results:
        print("\n没有待检查的草稿\n")
        return

    passed_count = sum(1 for r in results if r["overall_passed"])
    failed_count = len(results) - passed_count
    high_severity_count = sum(1 for r in results if r["has_high_severity"])

    print(f"\n{'='*90}")
    print(f"  合规检查报告 ({len(results)}篇)")
    print(f"  ✅ 通过: {passed_count}  ❌ 未通过: {failed_count}  ⚠️ 高风险: {high_severity_count}")
    print(f"{'='*90}")

    for i, result in enumerate(results, 1):
        status = "✅" if result["overall_passed"] else "❌"
        title = result["title"][:40]
        platform = result.get("platform", "")
        print(f"\n[{i}/{len(results)}] {status} [{platform}] {title}")

        if not result["overall_passed"]:
            for check_name, check_result in result["checks"].items():
                if not check_result["passed"]:
                    severity = check_result["severity"]
                    severity_icon = "🔴" if severity == "high" else "🟡"
                    print(f"  {severity_icon} {check_result['description']}")
                    if check_result.get("banned_words_found"):
                        print(f"     违禁词: {check_result['banned_words_found']}")
                    if check_result.get("positions"):
                        for pos in check_result["positions"][:2]:
                            print(f"     上下文: ...{pos['context']}...")

    print(f"\n{'='*90}")
    print(f"  总结: {passed_count}/{len(results)}篇通过合规检查")
    if high_severity_count > 0:
        print(f"  ⚠️  {high_severity_count}篇存在高风险问题，禁止发布！")
    print(f"{'='*90}\n")


def print_compliance_config():
    """打印合规配置"""
    config_data = load_compliance_config()
    print(f"\n{'='*60}")
    print(f"  合规检查配置")
    print(f"{'='*60}")
    print(f"启用: {config_data.get('enabled', True)}")
    print(f"\n私域引流违禁词 ({len(config_data.get('private_traffic_banned_words', []))}个):")
    for word in config_data.get("private_traffic_banned_words", []):
        print(f"  - {word}")
    print(f"\n广告法违禁词 ({len(config_data.get('ad_law_banned_words', []))}个):")
    for word in config_data.get("ad_law_banned_words", []):
        print(f"  - {word}")
    print(f"\n合规引流方式:")
    for method in config_data.get("allowed_private_traffic_methods", []):
        print(f"  ✅ {method}")
    print(f"{'='*60}\n")


# ============================================
# 主函数
# ============================================

def main():
    parser = argparse.ArgumentParser(description="合规检查脚本")
    parser.add_argument("--platform", type=str, default=None,
                        help="指定平台过滤: xiaohongshu/douyin/zhihu等")
    parser.add_argument("--draft", type=str, default=None,
                        help="检查指定草稿（文件名）")
    parser.add_argument("--auto-fix", action="store_true",
                        help="自动修复（添加AI标识，违禁词需人工改写）")
    parser.add_argument("--show-config", action="store_true",
                        help="查看合规配置")
    parser.add_argument("--block-publish", action="store_true",
                        help="不合规的草稿标记为禁止发布")

    args = parser.parse_args()

    # 查看配置
    if args.show_config:
        print_compliance_config()
        return

    # 加载草稿
    drafts = load_pending_drafts(args.platform)

    # 过滤指定草稿
    if args.draft:
        drafts = [d for d in drafts if args.draft in d.get("_filename", "")]

    if not drafts:
        print("\n没有待检查的草稿\n")
        return

    print(f"\n开始合规检查: {len(drafts)}篇草稿")

    # 执行检查
    results = []
    for draft in drafts:
        result = check_draft_compliance(draft)
        results.append(result)

        # 自动修复
        if args.auto_fix and not result["overall_passed"]:
            draft = auto_fix_draft(draft, result)
            save_draft(draft)
            # 重新检查
            result = check_draft_compliance(draft)
            results[-1] = result

        # 标记禁止发布
        if args.block_publish and result["has_high_severity"]:
            draft["publish_blocked"] = True
            draft["publish_block_reason"] = "合规检查未通过（高风险）"
            save_draft(draft)

    # 打印报告
    print_compliance_report(results)

    # 返回退出码
    failed = sum(1 for r in results if not r["overall_passed"])
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
