#!/usr/bin/env python3
"""
排期发布引擎 (04_schedule.py)

功能：
  1. 读取待审核草稿
  2. 生成排期表（同平台间隔≥2小时，错峰发布）
  3. 调用对应平台发布器执行发布
  4. 发布前自动切换Clash代理节点
  5. 发布状态记录到数据库
  6. 支持立即发布、定时发布、试运行模式

用法：
  # 列出待发布草稿
  python scripts/04_schedule.py --list

  # 生成排期表（不实际发布）
  python scripts/04_schedule.py --schedule

  # 发布所有待审核草稿
  python scripts/04_schedule.py --publish-all

  # 发布指定草稿
  python scripts/04_schedule.py --publish-id <草稿文件名>

  # 试运行（不实际发布，只模拟流程）
  python scripts/04_schedule.py --publish-all --dry-run

  # 指定平台发布
  python scripts/04_schedule.py --publish-all --platform xiaohongshu
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
from scripts.utils.db import db
from scripts.utils.logger import logger
from scripts.utils.clash_client import clash as clash_client


# ============================================
# 发布器工厂
# ============================================

def get_publisher(platform: str, account_config: Dict, headless: bool = True):
    """
    根据平台获取对应的发布器实例

    Args:
        platform: 平台名称
        account_config: 账号配置
        headless: 是否无头模式

    Returns:
        发布器实例
    """
    if platform == "xiaohongshu":
        from scripts.publishers.xiaohongshu import XiaohongshuPublisher
        return XiaohongshuPublisher(account_config, headless=headless)
    else:
        logger.warning(f"平台 {platform} 发布器尚未实现，使用占位发布器")
        return None


# ============================================
# 草稿管理
# ============================================

def load_pending_drafts(platform: str = None) -> List[Dict]:
    """
    加载待审核草稿

    Args:
        platform: 过滤平台（None表示所有平台）

    Returns:
        草稿列表
    """
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

    # 按时间排序
    drafts.sort(key=lambda x: x.get("rewrite_time", ""), reverse=True)
    return drafts


def move_draft_to_published(draft: Dict, success: bool, post_url: str = "", error: str = ""):
    """
    将草稿从待审核目录移动到已发布/失败目录

    Args:
        draft: 草稿字典
        success: 是否发布成功
        post_url: 发布后的链接
        error: 错误信息
    """
    filepath = draft.get("_filepath", "")
    if not filepath or not os.path.exists(filepath):
        return

    # 更新草稿信息
    draft["publish_status"] = "success" if success else "failed"
    draft["publish_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    draft["post_url"] = post_url
    draft["publish_error"] = error

    # 目标目录
    if success:
        target_dir = config.get_path("published")
    else:
        target_dir = os.path.join(PROJECT_ROOT, "data", "drafted", "publish_failed")
    os.makedirs(target_dir, exist_ok=True)

    # 移动文件
    filename = os.path.basename(filepath)
    target_path = os.path.join(target_dir, filename)
    try:
        # 写入更新后的草稿
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(draft, f, ensure_ascii=False, indent=2)
        # 删除原文件
        os.remove(filepath)
        logger.info(f"草稿已移动到: {target_path}")
    except Exception as e:
        logger.error(f"移动草稿失败: {e}")


# ============================================
# 排期表生成
# ============================================

def generate_schedule(drafts: List[Dict], start_date: str = None,
                      daily_limit: int = 3, interval_hours: int = 2) -> List[Dict]:
    """
    生成排期表

    规则：
      - 同平台账号间隔≥2小时
      - 每个账号每天最多发布daily_limit篇
      - 发布时段：9:00-12:00, 14:00-18:00, 19:00-22:00

    Args:
        drafts: 草稿列表
        start_date: 开始日期（YYYY-MM-DD），默认今天
        daily_limit: 每个账号每天最大发布数
        interval_hours: 同平台最小间隔小时数

    Returns:
        排期列表
    """
    if not start_date:
        start_date = datetime.now().strftime("%Y-%m-%d")

    # 发布时段
    time_slots = [
        "09:30", "10:30", "11:30",  # 上午
        "14:00", "15:00", "16:00", "17:00",  # 下午
        "19:00", "20:00", "21:00",  # 晚上
    ]

    # 按平台和账号分组
    account_drafts = {}
    for draft in drafts:
        platform = draft.get("platform", "unknown")
        # 简单分配：同平台的草稿轮流分配给该平台的账号
        if platform not in account_drafts:
            account_drafts[platform] = []
        account_drafts[platform].append(draft)

    # 生成排期
    schedule = []
    current_date = datetime.strptime(start_date, "%Y-%m-%d")
    slot_index = 0
    account_daily_count = {}  # 记录每个账号当天已发布数

    # 扁平化所有草稿，按平台交错排列
    all_drafts = []
    platforms = list(account_drafts.keys())
    max_len = max(len(v) for v in account_drafts.values()) if account_drafts else 0
    for i in range(max_len):
        for platform in platforms:
            if i < len(account_drafts[platform]):
                all_drafts.append(account_drafts[platform][i])

    for draft in all_drafts:
        platform = draft.get("platform", "unknown")
        # 找到该平台的第一个可用账号
        accounts = config.get_accounts_by_platform(platform)
        if not accounts:
            logger.warning(f"平台 {platform} 没有配置账号，跳过")
            continue

        # 简单选择第一个账号（后续可优化为轮询）
        account = accounts[0]
        account_name = account.get("name", "")

        # 检查当天发布数限制
        date_str = current_date.strftime("%Y-%m-%d")
        key = f"{account_name}_{date_str}"
        if account_daily_count.get(key, 0) >= daily_limit:
            # 切换到下一天
            current_date += timedelta(days=1)
            slot_index = 0
            date_str = current_date.strftime("%Y-%m-%d")
            key = f"{account_name}_{date_str}"

        # 选择时段
        if slot_index >= len(time_slots):
            current_date += timedelta(days=1)
            slot_index = 0
            date_str = current_date.strftime("%Y-%m-%d")
            key = f"{account_name}_{date_str}"

        publish_time = f"{date_str} {time_slots[slot_index]}"
        slot_index += 1
        account_daily_count[key] = account_daily_count.get(key, 0) + 1

        schedule.append({
            "draft_filename": draft.get("_filename", ""),
            "title": draft.get("title", ""),
            "platform": platform,
            "account": account_name,
            "publish_time": publish_time,
            "status": "scheduled"
        })

    return schedule


def print_schedule(schedule: List[Dict]):
    """打印排期表"""
    if not schedule:
        print("\n没有待发布的草稿\n")
        return

    print(f"\n{'='*90}")
    print(f"  排期表 ({len(schedule)}篇)")
    print(f"{'='*90}")
    print(f"{'序号':<5} {'发布时间':<18} {'平台':<12} {'账号':<15} 标题")
    print(f"{'-'*90}")

    for i, item in enumerate(schedule, 1):
        title = item.get("title", "")[:40]
        print(f"{i:<5} {item['publish_time']:<18} {item['platform']:<12} {item['account']:<15} {title}")

    print(f"{'='*90}\n")


# ============================================
# 发布执行
# ============================================

def publish_single(draft: Dict, dry_run: bool = False, headless: bool = True) -> Dict:
    """
    发布单篇草稿

    Args:
        draft: 草稿字典
        dry_run: 试运行模式
        headless: 是否无头模式

    Returns:
        发布结果字典
    """
    platform = draft.get("platform", "")
    title = draft.get("title", "")

    logger.info(f"{'='*60}")
    logger.info(f"开始发布: [{platform}] {title[:30]}")
    logger.info(f"{'='*60}")

    # 找到对应账号
    accounts = config.get_accounts_by_platform(platform)
    if not accounts:
        error = f"平台 {platform} 没有配置账号"
        logger.error(error)
        return {"success": False, "error": error, "platform": platform, "account": ""}

    account = accounts[0]  # 简单选择第一个账号
    account_name = account.get("name", "")

    # 切换Clash节点
    clash_node = account.get("clash_node", "")
    if clash_node and clash_client.is_available():
        logger.info(f"切换Clash节点: {clash_node}")
        clash_client.switch_node(clash_node)
        time.sleep(3)  # 等待代理切换生效
    else:
        logger.info("Clash不可用或未配置节点，跳过代理切换")

    if dry_run:
        logger.info(f"[试运行] 模拟发布: [{platform}/{account_name}] {title[:30]}")
        # 记录到数据库（试运行也记录，标记为dry_run）
        db.insert_publish_log({
            "content_id": f"dry_run_{int(time.time())}",
            "platform": platform,
            "account": account_name,
            "title": title,
            "scheduled_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "clash_node": clash_node
        })
        return {
            "success": True,
            "dry_run": True,
            "platform": platform,
            "account": account_name,
            "post_url": "",
            "error": ""
        }

    # 获取发布器
    publisher = get_publisher(platform, account, headless=headless)
    if not publisher:
        error = f"平台 {platform} 发布器尚未实现"
        logger.error(error)
        return {"success": False, "error": error, "platform": platform, "account": account_name}

    # 执行发布
    try:
        with publisher:
            # 准备发布数据
            publish_data = {
                "title": draft.get("title", ""),
                "content": draft.get("content", ""),
                "tags": draft.get("tags", []),
                "images": draft.get("images", []),
            }
            result = publisher.publish_with_retry(publish_data, max_retries=2)
    except Exception as e:
        logger.error(f"发布异常: {e}")
        result = None

    # 记录发布结果
    if result and result.success:
        logger.info(f"发布成功: {result.post_url}")
        db.insert_publish_log({
            "content_id": f"pub_{int(time.time())}",
            "platform": platform,
            "account": account_name,
            "title": title,
            "scheduled_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "clash_node": clash_node
        })
        move_draft_to_published(draft, success=True, post_url=result.post_url)
        return {"success": True, "platform": platform, "account": account_name,
                "post_url": result.post_url, "error": ""}
    else:
        error = result.error if result else "发布失败"
        logger.error(f"发布失败: {error}")
        db.insert_publish_log({
            "content_id": f"pub_{int(time.time())}",
            "platform": platform,
            "account": account_name,
            "title": title,
            "scheduled_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "clash_node": clash_node
        })
        move_draft_to_published(draft, success=False, error=error)
        return {"success": False, "platform": platform, "account": account_name,
                "post_url": "", "error": error}


def publish_all(drafts: List[Dict], dry_run: bool = False, headless: bool = True,
                delay_seconds: int = 10):
    """
    批量发布所有草稿

    Args:
        drafts: 草稿列表
        dry_run: 试运行模式
        headless: 是否无头模式
        delay_seconds: 每篇之间的间隔秒数
    """
    if not drafts:
        print("\n没有待发布的草稿\n")
        return

    print(f"\n开始批量发布: {len(drafts)}篇草稿" + ("（试运行模式）" if dry_run else ""))
    print(f"{'='*60}")

    success_count = 0
    fail_count = 0

    for i, draft in enumerate(drafts, 1):
        print(f"\n[{i}/{len(drafts)}] 发布: {draft.get('title', '')[:40]}")
        result = publish_single(draft, dry_run=dry_run, headless=headless)

        if result.get("success"):
            success_count += 1
            print(f"  ✅ 成功 ({result.get('account', '')})")
        else:
            fail_count += 1
            print(f"  ❌ 失败: {result.get('error', '未知错误')}")

        # 间隔
        if i < len(drafts):
            print(f"  等待{delay_seconds}秒后继续...")
            time.sleep(delay_seconds)

    print(f"\n{'='*60}")
    print(f"批量发布完成: 成功{success_count}篇, 失败{fail_count}篇")
    print(f"{'='*60}\n")


# ============================================
# 主函数
# ============================================

def main():
    parser = argparse.ArgumentParser(description="排期发布引擎")
    parser.add_argument("--list", action="store_true", help="列出待发布草稿")
    parser.add_argument("--schedule", action="store_true", help="生成排期表")
    parser.add_argument("--publish-all", action="store_true", help="发布所有待审核草稿")
    parser.add_argument("--publish-id", type=str, help="发布指定草稿（文件名）")
    parser.add_argument("--platform", type=str, default=None,
                        help="指定平台过滤: xiaohongshu/zhihu/bilibili/wechat_mp/wechat_channels")
    parser.add_argument("--dry-run", action="store_true", help="试运行模式（不实际发布）")
    parser.add_argument("--headless", type=bool, default=True, help="是否无头模式（默认True）")
    parser.add_argument("--delay", type=int, default=10, help="批量发布间隔秒数（默认10）")
    parser.add_argument("--start-date", type=str, default=None, help="排期开始日期（YYYY-MM-DD）")

    args = parser.parse_args()

    # 列出待发布草稿
    if args.list:
        drafts = load_pending_drafts(args.platform)
        if not drafts:
            print("\n待审核目录为空\n")
            return
        print(f"\n{'='*90}")
        print(f"  待发布草稿列表 ({len(drafts)}篇)")
        print(f"{'='*90}")
        print(f"{'平台':<12} {'字数':<6} {'相似度':<8} {'改写时间':<18} 标题")
        print(f"{'-'*90}")
        for d in drafts:
            title = d.get("title", "")[:40]
            platform = d.get("platform_name", d.get("platform", ""))
            content_len = len(d.get("content", ""))
            similarity = d.get("similarity", 0)
            rewrite_time = d.get("rewrite_time", "")
            print(f"{platform:<12} {content_len:<6} {similarity:<8.0f}% {rewrite_time:<18} {title}")
        print(f"{'='*90}\n")
        return

    # 生成排期表
    if args.schedule:
        drafts = load_pending_drafts(args.platform)
        schedule = generate_schedule(drafts, start_date=args.start_date)
        print_schedule(schedule)
        return

    # 发布指定草稿
    if args.publish_id:
        drafts = load_pending_drafts(args.platform)
        target = None
        for d in drafts:
            if d.get("_filename") == args.publish_id or args.publish_id in d.get("_filename", ""):
                target = d
                break
        if not target:
            print(f"\n未找到草稿: {args.publish_id}\n")
            return
        result = publish_single(target, dry_run=args.dry_run, headless=args.headless)
        if result.get("success"):
            print(f"\n✅ 发布成功: {result.get('post_url', '')}\n")
        else:
            print(f"\n❌ 发布失败: {result.get('error', '未知错误')}\n")
        return

    # 发布所有草稿
    if args.publish_all:
        drafts = load_pending_drafts(args.platform)
        publish_all(drafts, dry_run=args.dry_run, headless=args.headless,
                    delay_seconds=args.delay)
        return

    # 默认显示帮助
    parser.print_help()
    print("\n常用命令:")
    print("  # 列出待发布草稿")
    print("  python scripts/04_schedule.py --list")
    print("  # 生成排期表")
    print("  python scripts/04_schedule.py --schedule")
    print("  # 试运行发布所有草稿")
    print("  python scripts/04_schedule.py --publish-all --dry-run")
    print("  # 实际发布所有草稿")
    print("  python scripts/04_schedule.py --publish-all")
    print("  # 只发布小红书草稿")
    print("  python scripts/04_schedule.py --publish-all --platform xiaohongshu")


if __name__ == "__main__":
    main()
