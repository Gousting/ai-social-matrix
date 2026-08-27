#!/usr/bin/env python3
"""
M4 数据监控与复盘脚本 (07_metrics_collector.py)

功能：
  1. 从发布日志获取已发布的笔记列表
  2. 用DrissionPage访问笔记详情页，采集数据（点赞、收藏、评论、阅读量）
  3. 将数据存入metrics数据库（posts表 + daily_metrics表）
  4. 生成效果分析报告（爆款识别、内容优化建议）
  5. 支持定时回访采集（发布后10分钟、1小时、24小时、7天）

用法：
  # 采集所有已发布笔记的最新数据
  python scripts/07_metrics_collector.py

  # 采集指定平台的笔记数据
  python scripts/07_metrics_collector.py --platform xiaohongshu

  # 生成效果分析报告
  python scripts/07_metrics_collector.py --report

  # 查看数据统计
  python scripts/07_metrics_collector.py --stats
"""
import sys
import os
import json
import argparse
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from scripts.utils.config_loader import config
from scripts.utils.logger import logger
from scripts.utils.db import DatabaseManager


class MetricsCollector:
    """数据采集器"""

    def __init__(self, platform: str = None):
        self.platform = platform
        self.db = DatabaseManager()
        self._page = None
        self._browser = None

    def get_published_posts(self) -> List[Dict]:
        """从发布日志获取已发布的笔记列表"""
        try:
            # 从publish_log.db获取已发布的笔记
            publish_log_db = config.get_path("publish_log_db")
            import sqlite3
            conn = sqlite3.connect(publish_log_db)
            conn.row_factory = sqlite3.Row

            if self.platform:
                rows = conn.execute(
                    "SELECT * FROM publish_log WHERE status='success' AND platform=? ORDER BY actual_publish_time DESC",
                    (self.platform,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM publish_log WHERE status='success' ORDER BY actual_publish_time DESC"
                ).fetchall()

            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"获取已发布笔记失败: {e}")
            return []

    def collect_post_metrics(self, post_url: str) -> Optional[Dict]:
        """
        采集单篇笔记的数据
        返回: {views, likes, favorites, comments, shares}
        """
        if not post_url:
            return None

        try:
            if not self._page:
                self._start_browser()

            logger.info(f"采集笔记数据: {post_url}")
            self._page.get(post_url, timeout=20)
            time.sleep(5)

            metrics = {
                "views": 0,
                "likes": 0,
                "favorites": 0,
                "comments": 0,
                "shares": 0
            }

            # 小红书数据采集
            if "xiaohongshu.com" in post_url:
                metrics = self._collect_xiaohongshu_metrics()

            logger.info(f"采集结果: 赞={metrics['likes']}, 藏={metrics['favorites']}, 评={metrics['comments']}")
            return metrics

        except Exception as e:
            logger.error(f"采集笔记数据失败: {e}")
            return None

    def _collect_xiaohongshu_metrics(self) -> Dict:
        """采集小红书笔记数据"""
        metrics = {
            "views": 0,
            "likes": 0,
            "favorites": 0,
            "comments": 0,
            "shares": 0
        }

        try:
            # 点赞数
            try:
                like_ele = self._page.ele('css:.like-count, .count, [class*="like"]', timeout=3)
                if like_ele:
                    metrics["likes"] = self._parse_count(like_ele.text)
            except Exception:
                pass

            # 收藏数
            try:
                fav_ele = self._page.ele('css:.collect-count, [class*="collect"]', timeout=3)
                if fav_ele:
                    metrics["favorites"] = self._parse_count(fav_ele.text)
            except Exception:
                pass

            # 评论数
            try:
                comment_ele = self._page.ele('css:.comment-count, [class*="comment"]', timeout=3)
                if comment_ele:
                    metrics["comments"] = self._parse_count(comment_ele.text)
            except Exception:
                pass

            # 分享数
            try:
                share_ele = self._page.ele('css:.share-count, [class*="share"]', timeout=3)
                if share_ele:
                    metrics["shares"] = self._parse_count(share_ele.text)
            except Exception:
                pass

            # 阅读量（小红书可能不直接显示）
            metrics["views"] = 0

        except Exception as e:
            logger.warning(f"采集小红书数据异常: {e}")

        return metrics

    @staticmethod
    def _parse_count(text: str) -> int:
        """解析数字（支持1.1万、1000+等格式）"""
        if not text:
            return 0
        text = text.strip()
        try:
            if "万" in text:
                num = float(text.replace("万", "").replace("+", ""))
                return int(num * 10000)
            elif "+" in text:
                return int(text.replace("+", "").replace(",", ""))
            else:
                return int(text.replace(",", ""))
        except Exception:
            return 0

    def _start_browser(self):
        """启动浏览器"""
        from DrissionPage import ChromiumPage, ChromiumOptions

        logger.info("启动DrissionPage浏览器（数据采集）...")

        co = ChromiumOptions()
        co.set_argument('--disable-blink-features=AutomationControlled')
        co.set_argument('--no-sandbox')

        # 使用小红书账号的Profile（已登录状态）
        xhs_accounts = config.get_accounts_by_platform("xiaohongshu")
        if xhs_accounts:
            user_data_dir = xhs_accounts[0].get("user_data_dir", "./profiles/xhs/default")
            if not os.path.isabs(user_data_dir):
                user_data_dir = os.path.join(PROJECT_ROOT, user_data_dir)
            co.set_user_data_path(user_data_dir)
            logger.info(f"使用Profile: {user_data_dir}")

        self._page = ChromiumPage(co)
        logger.info("浏览器启动成功")

    def collect_all(self) -> int:
        """采集所有已发布笔记的最新数据"""
        posts = self.get_published_posts()
        if not posts:
            logger.warning("没有找到已发布的笔记")
            return 0

        logger.info(f"找到 {len(posts)} 篇已发布笔记，开始采集数据...")

        success_count = 0
        today = datetime.now().strftime("%Y-%m-%d")

        for i, post in enumerate(posts, 1):
            logger.info(f"[{i}/{len(posts)}] 采集: {post.get('title', '无标题')[:30]}")

            post_url = post.get("post_url", "")
            if not post_url:
                logger.warning("  跳过：没有post_url")
                continue

            metrics = self.collect_post_metrics(post_url)
            if metrics:
                # 存入daily_metrics表
                content_id = post.get("content_id", f"post_{post.get('id', i)}")
                metrics_data = {
                    "content_id": content_id,
                    "date": today,
                    "platform": post.get("platform"),
                    "account": post.get("account"),
                    "views": metrics["views"],
                    "likes": metrics["likes"],
                    "favorites": metrics["favorites"],
                    "comments": metrics["comments"],
                    "shares": metrics["shares"],
                    "followers_gain": 0
                }
                self.db.upsert_daily_metrics(metrics_data)
                success_count += 1
                logger.info(f"  ✅ 数据已保存")
            else:
                logger.warning(f"  ❌ 采集失败")

            # 间隔，避免被限流
            time.sleep(3)

        logger.info(f"采集完成: 成功{success_count}/{len(posts)}篇")

        # 关闭浏览器
        if self._page:
            try:
                self._page.quit()
            except Exception:
                pass

        return success_count

    def generate_report(self) -> str:
        """生成效果分析报告"""
        try:
            metrics_db = config.get_path("metrics_db")
            import sqlite3
            conn = sqlite3.connect(metrics_db)
            conn.row_factory = sqlite3.Row

            # 获取所有笔记的汇总数据
            posts = conn.execute("SELECT * FROM posts ORDER BY total_likes DESC").fetchall()

            report = []
            report.append("=" * 60)
            report.append("📊 内容效果分析报告")
            report.append("=" * 60)
            report.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            report.append(f"笔记总数: {len(posts)}")

            if not posts:
                report.append("\n⚠️  暂无数据，请先发布笔记并采集数据")
                conn.close()
                return "\n".join(report)

            # 统计汇总
            total_likes = sum(p["total_likes"] for p in posts)
            total_favorites = sum(p["total_favorites"] for p in posts)
            total_comments = sum(p["total_comments"] for p in posts)

            report.append(f"\n📈 数据汇总:")
            report.append(f"  总点赞: {total_likes}")
            report.append(f"  总收藏: {total_favorites}")
            report.append(f"  总评论: {total_comments}")
            report.append(f"  平均点赞: {total_likes // len(posts) if posts else 0}")
            report.append(f"  平均收藏: {total_favorites // len(posts) if posts else 0}")

            # 爆款识别（点赞>1000或收藏>500）
            viral_posts = [p for p in posts if p["total_likes"] >= 1000 or p["total_favorites"] >= 500]
            report.append(f"\n🔥 爆款笔记（赞≥1000或藏≥500）: {len(viral_posts)}篇")
            for p in viral_posts[:5]:
                report.append(f"  - {p['title'][:40]} (赞:{p['total_likes']}, 藏:{p['total_favorites']})")

            # 待优化笔记（点赞<100）
            low_posts = [p for p in posts if p["total_likes"] < 100]
            report.append(f"\n📉 待优化笔记（赞<100）: {len(low_posts)}篇")
            for p in low_posts[:5]:
                report.append(f"  - {p['title'][:40]} (赞:{p['total_likes']}, 藏:{p['total_favorites']})")

            # 优化建议
            report.append(f"\n💡 优化建议:")
            if viral_posts:
                report.append("  1. 分析爆款笔记的标题、封面、内容结构，总结爆款规律")
                report.append("  2. 将爆款模板应用到新内容创作中")
            if low_posts:
                report.append("  3. 低赞笔记可能标题不够吸引人，建议优化标题公式")
                report.append("  4. 检查封面是否清晰、有吸引力")
                report.append("  5. 发布时间可能不在流量高峰，建议调整发布时间")
            report.append("  6. 持续日更，积累账号权重和粉丝基础")

            report.append("\n" + "=" * 60)

            conn.close()
            return "\n".join(report)

        except Exception as e:
            logger.error(f"生成报告失败: {e}")
            return f"生成报告失败: {e}"

    def show_stats(self):
        """显示数据统计"""
        print(self.generate_report())


def main():
    parser = argparse.ArgumentParser(description="M4 数据监控与复盘脚本")
    parser.add_argument("--platform", type=str, default=None, help="指定平台（如xiaohongshu）")
    parser.add_argument("--report", action="store_true", help="生成效果分析报告")
    parser.add_argument("--stats", action="store_true", help="显示数据统计")
    args = parser.parse_args()

    collector = MetricsCollector(platform=args.platform)

    if args.report or args.stats:
        collector.show_stats()
    else:
        # 采集数据
        success_count = collector.collect_all()
        print(f"\n✅ 采集完成: 成功{success_count}篇")
        print("\n📊 采集后数据统计:")
        collector.show_stats()


if __name__ == "__main__":
    main()
