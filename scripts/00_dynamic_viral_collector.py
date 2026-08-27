#!/usr/bin/env python3
"""
动态爆款采集脚本 (00_dynamic_viral_collector.py)

命令行接口，核心逻辑在 scripts/utils/dynamic_viral_collector.py

用法：
  # 采集指定关键词的爆款帖子
  python scripts/00_dynamic_viral_collector.py --keyword "Codex安装" --top 5

  # 采集并查看拆解结果
  python scripts/00_dynamic_viral_collector.py --keyword "AI工具" --top 3 --show

  # 清除缓存
  python scripts/00_dynamic_viral_collector.py --clear-cache

  # 查看缓存列表
  python scripts/00_dynamic_viral_collector.py --list-cache
"""
import sys
import os
import argparse

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# 从utils导入核心函数
from scripts.utils.dynamic_viral_collector import (
    get_dynamic_reference,
    list_cache,
    clear_cache,
)


def main():
    parser = argparse.ArgumentParser(description="动态爆款采集脚本")
    parser.add_argument("--keyword", type=str, help="搜索关键词")
    parser.add_argument("--top", type=int, default=5, help="采集前N篇（默认5）")
    parser.add_argument("--show", action="store_true", help="显示拆解结果")
    parser.add_argument("--no-cache", action="store_true", help="不使用缓存，强制重新采集")
    parser.add_argument("--list-cache", action="store_true", help="列出所有缓存")
    parser.add_argument("--clear-cache", action="store_true", help="清除所有缓存")

    args = parser.parse_args()

    if args.list_cache:
        list_cache()
        return

    if args.clear_cache:
        clear_cache()
        return

    if not args.keyword:
        parser.print_help()
        print("\n💡 示例:")
        print("  python scripts/00_dynamic_viral_collector.py --keyword 'Codex安装' --top 5 --show")
        print("  python scripts/00_dynamic_viral_collector.py --list-cache")
        print()
        return

    print(f"\n🔍 开始动态采集: 关键词='{args.keyword}', 采集前{args.top}篇")
    if args.no_cache:
        print("   （不使用缓存，强制重新采集）")
    print()

    reference = get_dynamic_reference(
        keyword=args.keyword,
        top_n=args.top,
        use_cache=not args.no_cache
    )

    if reference:
        print(f"\n{'='*80}")
        print(f"  动态爆款参考（关键词: {args.keyword}）")
        print(f"{'='*80}")
        if args.show:
            print(reference)
        else:
            print(reference[:1000])
            if len(reference) > 1000:
                print(f"\n...（共{len(reference)}字符，使用 --show 查看完整内容）")
        print(f"{'='*80}\n")
    else:
        print("\n❌ 未获取到动态参考，请检查网络和小红书登录状态\n")


if __name__ == "__main__":
    main()
