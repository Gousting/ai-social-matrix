#!/usr/bin/env python3
"""
账号登录绑定脚本 - DrissionPage版本 (login_drission.py)

功能：
  1. 列出所有配置的账号
  2. 用DrissionPage打开对应平台的创作者中心
  3. 等待用户手动扫码登录
  4. 登录成功后Profile自动保存（持久化上下文）
  5. 验证登录状态

用法：
  # 列出所有账号
  python scripts/login_drission.py --list

  # 登录指定平台的第一个账号
  python scripts/login_drission.py --platform xiaohongshu

  # 登录指定账号（按账号名）
  python scripts/login_drission.py --account ai_main

  # 验证所有账号登录状态
  python scripts/login_drission.py --check-all
"""
import sys
import os
import json
import argparse
import time
from typing import Dict

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from scripts.utils.config_loader import config
from scripts.utils.logger import logger


# 各平台登录URL
LOGIN_URLS = {
    "xiaohongshu": "https://creator.xiaohongshu.com/",
    "douyin": "https://creator.douyin.com/",
    "zhihu": "https://www.zhihu.com/creator",
    "bilibili": "https://member.bilibili.com/",
    "wechat_mp": "https://mp.weixin.qq.com/",
}


def list_accounts():
    """列出所有账号"""
    accounts = config.enabled_accounts
    if not accounts:
        print("\n没有配置启用的账号\n")
        return

    print(f"\n{'='*80}")
    print(f"  账号列表 ({len(accounts)}个)")
    print(f"{'='*80}")
    print(f"{'平台':<12} {'账号名':<20} {'显示名':<20} {'状态':<8} Profile路径")
    print(f"{'-'*80}")

    for acc in accounts:
        platform = acc.get("platform", "")
        name = acc.get("name", "")
        display_name = acc.get("display_name", "")
        enabled = "✅启用" if acc.get("enabled", True) else "❌禁用"
        user_data_dir = acc.get("user_data_dir", "")
        print(f"{platform:<12} {name:<20} {display_name:<20} {enabled:<8} {user_data_dir}")

    print(f"{'='*80}\n")


def login_account(account_config: Dict):
    """
    登录指定账号（DrissionPage版本）

    Args:
        account_config: 账号配置字典
    """
    from DrissionPage import ChromiumPage, ChromiumOptions

    platform = account_config.get("platform", "")
    account_name = account_config.get("name", "")
    display_name = account_config.get("display_name", "")
    user_data_dir = account_config.get("user_data_dir", "")
    if not os.path.isabs(user_data_dir):
        user_data_dir = os.path.join(PROJECT_ROOT, user_data_dir)
    login_url = LOGIN_URLS.get(platform, "")

    if not login_url:
        logger.error(f"不支持的平台: {platform}")
        return False

    # 确保目录存在
    os.makedirs(user_data_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  开始登录账号 (DrissionPage版本)")
    print(f"  平台: {platform}")
    print(f"  账号: {account_name} ({display_name})")
    print(f"  Profile目录: {user_data_dir}")
    print(f"  登录URL: {login_url}")
    print(f"{'='*60}")
    print(f"\n⚠️  即将打开浏览器，请在浏览器中手动扫码登录")
    print(f"⚠️  登录成功后，程序会自动检测并保存登录状态")
    print(f"⚠️  如果之前已登录过，会直接检测登录状态\n")

    try:
        # 配置浏览器
        co = ChromiumOptions()
        co.set_argument('--disable-blink-features=AutomationControlled')
        co.set_argument('--no-sandbox')
        co.set_argument('--start-maximized')
        co.set_user_data_path(user_data_dir)
        co.set_user_agent(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        )

        page = ChromiumPage(co)
        print(f"✅ 浏览器已打开")

        # 访问登录页面
        print(f"导航到 {login_url}...")
        page.get(login_url, timeout=30)
        time.sleep(5)

        print(f"\n⏳ 请在浏览器中完成登录操作...")
        print(f"⏳ 登录完成后，程序会自动检测登录状态")
        print(f"⏳ 最多等待5分钟...\n")

        # 等待用户登录（最多5分钟）
        max_wait = 300  # 5分钟
        start_time = time.time()
        logged_in = False

        while time.time() - start_time < max_wait:
            time.sleep(5)
            try:
                current_url = page.url
                title = page.title

                # 检查是否已登录（URL不包含login，标题不包含登录）
                if 'login' not in current_url.lower() and '登录' not in title:
                    # 额外检查：是否有用户头像或昵称
                    try:
                        avatar = page.ele('css:img.avatar, .user-avatar, [class*="avatar"]', timeout=2)
                        if avatar:
                            logged_in = True
                            break
                    except Exception:
                        # 没有找到头像，但URL已经离开登录页，也认为登录成功
                        logged_in = True
                        break
            except Exception:
                continue

            # 每30秒提示一次
            elapsed = int(time.time() - start_time)
            if elapsed % 30 == 0:
                print(f"  等待登录中... 已等待{elapsed}秒 (最多{max_wait}秒)")
                print(f"  当前URL: {page.url}")

        if logged_in:
            print(f"\n✅ 检测到登录成功!")
            time.sleep(3)

            # 截图保存
            screenshot_dir = os.path.join(PROJECT_ROOT, "logs", "screenshots", "login")
            os.makedirs(screenshot_dir, exist_ok=True)
            screenshot_path = os.path.join(screenshot_dir, f"{platform}_{account_name}_login.png")
            try:
                page.get_screenshot(path=screenshot_path)
                print(f"📸 登录截图已保存: {screenshot_path}")
            except Exception as e:
                print(f"📸 截图失败: {e}")

            # 保存Cookie（额外备份）
            cookie_path = account_config.get("cookie_path", "")
            if cookie_path:
                if not os.path.isabs(cookie_path):
                    cookie_path = os.path.join(PROJECT_ROOT, cookie_path)
                os.makedirs(os.path.dirname(cookie_path), exist_ok=True)
                try:
                    cookies = page.cookies()
                    with open(cookie_path, "w", encoding="utf-8") as f:
                        json.dump(cookies, f, ensure_ascii=False, indent=2)
                    print(f"🍪 Cookie已备份: {cookie_path} ({len(cookies)}个)")
                except Exception as e:
                    print(f"🍪 Cookie备份失败: {e}")

            print(f"\n✅ 账号登录绑定完成!")
            print(f"   平台: {platform}")
            print(f"   账号: {account_name} ({display_name})")
            print(f"   Profile已保存到: {user_data_dir}")
            print(f"   后续发布时会自动复用此登录态\n")

            page.quit()
            return True
        else:
            print(f"\n⚠️  等待超时（{max_wait}秒），未检测到登录成功")
            print(f"   请检查是否完成扫码登录")
            print(f"   浏览器将在10秒后关闭，Profile会自动保存\n")
            time.sleep(10)
            page.quit()
            return False

    except Exception as e:
        logger.error(f"登录过程异常: {e}")
        print(f"\n❌ 登录过程异常: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def check_login_status(account_config: Dict) -> bool:
    """
    检查账号登录状态（DrissionPage版本）

    Args:
        account_config: 账号配置

    Returns:
        是否已登录
    """
    from DrissionPage import ChromiumPage, ChromiumOptions

    platform = account_config.get("platform", "")
    account_name = account_config.get("name", "")
    user_data_dir = account_config.get("user_data_dir", "")
    if not os.path.isabs(user_data_dir):
        user_data_dir = os.path.join(PROJECT_ROOT, user_data_dir)
    login_url = LOGIN_URLS.get(platform, "")

    if not os.path.exists(user_data_dir) or not os.listdir(user_data_dir):
        return False

    try:
        co = ChromiumOptions()
        co.set_argument('--disable-blink-features=AutomationControlled')
        co.set_argument('--no-sandbox')
        co.set_user_data_path(user_data_dir)

        page = ChromiumPage(co)
        page.get(login_url, timeout=20)
        time.sleep(5)

        current_url = page.url
        title = page.title

        is_logged_in = 'login' not in current_url.lower() and '登录' not in title

        page.quit()
        return is_logged_in
    except Exception as e:
        logger.debug(f"检查登录状态异常: {e}")
        return False


def check_all_accounts():
    """检查所有账号登录状态"""
    accounts = config.enabled_accounts
    if not accounts:
        print("\n没有配置启用的账号\n")
        return

    print(f"\n{'='*70}")
    print(f"  账号登录状态检查 (DrissionPage版本)")
    print(f"{'='*70}")
    print(f"{'平台':<12} {'账号名':<20} {'状态':<10} 说明")
    print(f"{'-'*70}")

    for acc in accounts:
        platform = acc.get("platform", "")
        name = acc.get("name", "")
        user_data_dir = acc.get("user_data_dir", "")
        if not os.path.isabs(user_data_dir):
            user_data_dir = os.path.join(PROJECT_ROOT, user_data_dir)

        if not os.path.exists(user_data_dir) or not os.listdir(user_data_dir):
            status = "❌未登录"
            note = "Profile目录为空，请先登录"
        else:
            print(f"检查 [{platform}/{name}] ...", end=" ", flush=True)
            is_logged_in = check_login_status(acc)
            if is_logged_in:
                status = "✅已登录"
                note = "登录状态有效"
            else:
                status = "❌未登录"
                note = "登录已过期，请重新登录"
            print(status)

        print(f"{platform:<12} {name:<20} {status:<10} {note}")

    print(f"{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(description="账号登录绑定脚本（DrissionPage版本）")
    parser.add_argument("--list", action="store_true", help="列出所有账号")
    parser.add_argument("--account", type=str, help="登录指定账号（按账号名）")
    parser.add_argument("--platform", type=str, help="登录指定平台的第一个账号")
    parser.add_argument("--check-all", action="store_true", help="检查所有账号登录状态")

    args = parser.parse_args()

    if args.list:
        list_accounts()
        return

    if args.check_all:
        check_all_accounts()
        return

    # 确定要登录的账号
    target_account = None

    if args.account:
        for acc in config.all_accounts:
            if acc.get("name") == args.account:
                target_account = acc
                break
        if not target_account:
            print(f"\n❌ 未找到账号: {args.account}\n")
            return
    elif args.platform:
        accounts = config.get_accounts_by_platform(args.platform)
        if accounts:
            target_account = accounts[0]
        else:
            print(f"\n❌ 平台 {args.platform} 没有配置账号\n")
            return
    else:
        # 默认登录第一个启用的账号
        if config.enabled_accounts:
            target_account = config.enabled_accounts[0]
        else:
            print("\n❌ 没有配置启用的账号\n")
            return

    # 执行登录
    login_account(target_account)


if __name__ == "__main__":
    main()
