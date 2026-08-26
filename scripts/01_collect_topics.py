#!/usr/bin/env python3
"""
选题采集脚本 (01_collect_topics.py)

功能：
  1. 从JSON文件手动导入选题
  2. 用Playwright自动采集小红书/知乎/B站搜索结果（需登录态）
  3. 计算热度分，去重，存入数据库
  4. 输出Top N候选选题

用法：
  # 从JSON文件导入选题
  python scripts/01_collect_topics.py --import-file topics.json

  # 自动采集（需先配置账号Cookie）
  python scripts/01_collect_topics.py --auto --platform xiaohongshu --keyword "codex 安装"

  # 查看Top N候选选题
  python scripts/01_collect_topics.py --top 20

  # 查看指定平台的Top N
  python scripts/01_collect_topics.py --top 10 --platform xiaohongshu
"""
import sys
import os
import json
import argparse
from datetime import datetime, timedelta

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from scripts.utils.config_loader import config
from scripts.utils.db import db
from scripts.utils.logger import logger


def calculate_heat_score(likes: int = 0, favorites: int = 0, comments: int = 0,
                         shares: int = 0, publish_time: str = None) -> float:
    """
    计算热度分
    热度分 = 点赞×0.3 + 收藏×0.4 + 评论×0.3 + 分享×0.2
    时间衰减：发布时间越近，权重越高
    """
    weights = config.topic_config.get("heat_score_weights", {
        "likes": 0.3, "favorites": 0.4, "comments": 0.3
    })

    score = (likes * weights.get("likes", 0.3)
             + favorites * weights.get("favorites", 0.4)
             + comments * weights.get("comments", 0.3)
             + shares * 0.2)

    # 时间衰减（7天内不衰减，超过7天每天衰减2%）
    if publish_time:
        try:
            pub_date = datetime.strptime(publish_time[:10], "%Y-%m-%d")
            days_ago = (datetime.now() - pub_date).days
            if days_ago > 7:
                decay = max(0.3, 1 - (days_ago - 7) * 0.02)
                score *= decay
        except (ValueError, TypeError):
            pass

    return round(score, 1)


def import_from_json(filepath: str) -> int:
    """
    从JSON文件导入选题
    JSON格式：
    [
      {
        "note_id": "唯一ID",
        "platform": "xiaohongshu",
        "title": "标题",
        "content": "正文内容",
        "author": "作者",
        "likes": 100,
        "favorites": 80,
        "comments": 20,
        "shares": 10,
        "publish_time": "2026-08-20",
        "url": "https://...",
        "tags": ["tag1", "tag2"]
      }
    ]
    """
    if not os.path.exists(filepath):
        logger.error(f"文件不存在: {filepath}")
        return 0

    with open(filepath, "r", encoding="utf-8") as f:
        topics = json.load(f)

    if not isinstance(topics, list):
        logger.error("JSON格式错误，应为数组")
        return 0

    success_count = 0
    for topic in topics:
        # 计算热度分
        topic["heat_score"] = calculate_heat_score(
            likes=topic.get("likes", 0),
            favorites=topic.get("favorites", 0),
            comments=topic.get("comments", 0),
            shares=topic.get("shares", 0),
            publish_time=topic.get("publish_time")
        )
        # 确保有note_id
        if not topic.get("note_id"):
            topic["note_id"] = f"{topic.get('platform', 'unknown')}_{hash(topic.get('title', ''))}"

        if db.insert_raw_note(topic):
            success_count += 1
            logger.info(f"导入选题: [{topic.get('platform')}] {topic.get('title', '')[:30]} (热度:{topic['heat_score']})")

    logger.info(f"从JSON导入完成: 成功{success_count}/{len(topics)}条")
    return success_count


def auto_collect(platform: str, keyword: str, max_pages: int = 3) -> int:
    """
    用Playwright自动采集搜索结果（需登录态）
    目前实现基础框架，具体选择器需根据平台页面调整
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("请先安装playwright: pip install playwright && playwright install chromium")
        return 0

    # 获取该平台的第一个启用账号（用于加载Cookie）
    accounts = config.get_accounts_by_platform(platform)
    if not accounts:
        logger.error(f"平台 {platform} 没有配置启用的账号")
        return 0

    account = accounts[0]
    cookie_path = os.path.join(PROJECT_ROOT, account["cookie_path"])
    user_data_dir = os.path.join(PROJECT_ROOT, account["user_data_dir"])

    if not os.path.exists(user_data_dir):
        logger.error(f"浏览器Profile不存在: {user_data_dir}")
        logger.info("请先完成账号登录（首次登录会生成Profile）")
        return 0

    collected = []
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=True,
            viewport={"width": 1280, "height": 800}
        )
        page = browser.new_page()

        try:
            if platform == "xiaohongshu":
                # 小红书搜索
                search_url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}&source=web_search_result_notes"
                page.goto(search_url, wait_until="networkidle")
                page.wait_for_timeout(3000)

                # 抓取笔记卡片（选择器需根据实际页面调整）
                notes = page.evaluate("""() => {
                    const items = [];
                    document.querySelectorAll('section.note-item, div.note-item').forEach(el => {
                        const title = el.querySelector('.title, .note-title')?.innerText || '';
                        const likes = parseInt(el.querySelector('.like-count, .count')?.innerText || '0');
                        items.push({title, likes});
                    });
                    return items;
                }""")

                for i, note in enumerate(notes):
                    collected.append({
                        "note_id": f"xhs_auto_{keyword}_{i}_{int(datetime.now().timestamp())}",
                        "platform": "xiaohongshu",
                        "title": note.get("title", ""),
                        "content": "",
                        "author": "",
                        "likes": note.get("likes", 0),
                        "favorites": 0,
                        "comments": 0,
                        "publish_time": datetime.now().strftime("%Y-%m-%d"),
                        "url": "",
                        "tags": [keyword]
                    })

            elif platform == "zhihu":
                # 知乎搜索
                search_url = f"https://www.zhihu.com/search?type=content&q={keyword}"
                page.goto(search_url, wait_until="networkidle")
                page.wait_for_timeout(3000)

                items = page.evaluate("""() => {
                    const results = [];
                    document.querySelectorAll('.SearchResult-Card, .List-item').forEach(el => {
                        const title = el.querySelector('.ContentItem-title, h2')?.innerText || '';
                        const likes = parseInt(el.querySelector('.VoteButton--up, .upvote')?.innerText || '0');
                        results.push({title, likes});
                    });
                    return results;
                }""")

                for i, item in enumerate(items):
                    collected.append({
                        "note_id": f"zhihu_auto_{keyword}_{i}_{int(datetime.now().timestamp())}",
                        "platform": "zhihu",
                        "title": item.get("title", ""),
                        "content": "",
                        "author": "",
                        "likes": item.get("likes", 0),
                        "favorites": 0,
                        "comments": 0,
                        "publish_time": datetime.now().strftime("%Y-%m-%d"),
                        "url": "",
                        "tags": [keyword]
                    })

            elif platform == "bilibili":
                # B站搜索
                search_url = f"https://search.bilibili.com/all?keyword={keyword}"
                page.goto(search_url, wait_until="networkidle")
                page.wait_for_timeout(3000)

                videos = page.evaluate("""() => {
                    const results = [];
                    document.querySelectorAll('.video-list-item, .bili-video-card').forEach(el => {
                        const title = el.querySelector('.title, h3')?.innerText || '';
                        const play = el.querySelector('.play, .bili-video-card__stats--item')?.innerText || '0';
                        results.push({title, play});
                    });
                    return results;
                }""")

                for i, v in enumerate(videos):
                    collected.append({
                        "note_id": f"bili_auto_{keyword}_{i}_{int(datetime.now().timestamp())}",
                        "platform": "bilibili",
                        "title": v.get("title", ""),
                        "content": "",
                        "author": "",
                        "likes": 0,
                        "favorites": 0,
                        "comments": 0,
                        "shares": 0,
                        "publish_time": datetime.now().strftime("%Y-%m-%d"),
                        "url": "",
                        "tags": [keyword]
                    })

            else:
                logger.error(f"不支持的平台: {platform}")
                browser.close()
                return 0

        except Exception as e:
            logger.error(f"采集失败: {e}")
        finally:
            browser.close()

    # 计算热度分并存入数据库
    success_count = 0
    for topic in collected:
        topic["heat_score"] = calculate_heat_score(
            likes=topic.get("likes", 0),
            favorites=topic.get("favorites", 0),
            comments=topic.get("comments", 0),
            shares=topic.get("shares", 0),
            publish_time=topic.get("publish_time")
        )
        if db.insert_raw_note(topic):
            success_count += 1

    logger.info(f"自动采集完成: {platform} - {keyword} - 成功{success_count}/{len(collected)}条")
    return success_count


def show_top_topics(limit: int = 20, platform: str = None):
    """显示Top N候选选题"""
    topics = db.get_top_topics(limit=limit, platform=platform)

    if not topics:
        logger.info("选题库为空，请先导入或采集选题")
        return

    platform_label = platform if platform else "全部平台"
    print(f"\n{'='*80}")
    print(f"  Top {len(topics)} 候选选题 ({platform_label})")
    print(f"{'='*80}")
    print(f"{'排名':<4} {'平台':<12} {'热度':<8} {'点赞':<6} {'收藏':<6} {'评论':<6} 标题")
    print(f"{'-'*80}")

    for i, t in enumerate(topics, 1):
        title = t.get("title", "")[:40]
        print(f"{i:<4} {t.get('platform',''):<12} {t.get('heat_score',0):<8} "
              f"{t.get('likes',0):<6} {t.get('favorites',0):<6} {t.get('comments',0):<6} {title}")

    print(f"{'='*80}\n")


def generate_sample_json(filepath: str):
    """生成示例JSON文件，方便用户参考格式"""
    sample = [
        {
            "note_id": "sample_001",
            "platform": "xiaohongshu",
            "title": "终于把Codex装好了！保姆级教程",
            "content": "折腾了3天终于把Codex装好了，把踩过的坑全整理出来...",
            "author": "AI小白",
            "likes": 328,
            "favorites": 215,
            "comments": 42,
            "shares": 18,
            "publish_time": "2026-08-20",
            "url": "https://www.xiaohongshu.com/explore/xxx",
            "tags": ["AI工具", "codex", "教程"]
        },
        {
            "note_id": "sample_002",
            "platform": "zhihu",
            "title": "如何评价Codex？和Cursor比哪个更好？",
            "content": "作为一个用了半年AI代码助手的开发者，我来对比一下...",
            "author": "程序员老王",
            "likes": 256,
            "favorites": 189,
            "comments": 67,
            "shares": 32,
            "publish_time": "2026-08-22",
            "url": "https://www.zhihu.com/question/xxx",
            "tags": ["AI工具", "codex", "对比"]
        }
    ]
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)
    logger.info(f"已生成示例文件: {filepath}")


def main():
    parser = argparse.ArgumentParser(description="选题采集脚本")
    parser.add_argument("--import-file", type=str, help="从JSON文件导入选题")
    parser.add_argument("--auto", action="store_true", help="自动采集模式（需登录态）")
    parser.add_argument("--platform", type=str, choices=["xiaohongshu", "zhihu", "bilibili"],
                        help="采集平台（自动采集模式）")
    parser.add_argument("--keyword", type=str, help="搜索关键词（自动采集模式）")
    parser.add_argument("--max-pages", type=int, default=3, help="采集页数（默认3）")
    parser.add_argument("--top", type=int, help="显示Top N候选选题")
    parser.add_argument("--generate-sample", type=str, help="生成示例JSON文件")

    args = parser.parse_args()

    if args.generate_sample:
        generate_sample_json(args.generate_sample)
        return

    if args.import_file:
        count = import_from_json(args.import_file)
        print(f"\n导入完成: {count}条选题")
        return

    if args.auto:
        if not args.platform or not args.keyword:
            logger.error("自动采集模式需要指定 --platform 和 --keyword")
            return
        count = auto_collect(args.platform, args.keyword, args.max_pages)
        print(f"\n采集完成: {count}条选题")
        return

    if args.top:
        show_top_topics(limit=args.top, platform=args.platform)
        return

    # 默认显示帮助
    parser.print_help()
    print("\n常用命令:")
    print("  # 生成示例JSON")
    print("  python scripts/01_collect_topics.py --generate-sample topics_sample.json")
    print("  # 从JSON导入")
    print("  python scripts/01_collect_topics.py --import-file topics.json")
    print("  # 查看Top20")
    print("  python scripts/01_collect_topics.py --top 20")


if __name__ == "__main__":
    main()
