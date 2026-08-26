#!/usr/bin/env python3
"""
账号登录绑定脚本 (login_account.py)

功能：
  1. 列出所有配置的账号
  2. 用Playwright打开对应平台的创作者中心（非无头模式）
  3. 等待用户手动扫码登录
  4. 登录成功后Profile自动保存（持久化上下文）
  5. 验证登录状态

用法：
  # 列出所有账号
  python scripts/login_account.py --list

  # 登录指定账号（按账号名）
  python scripts/login_account.py --account "AI小白日记"

  # 登录指定平台的第一个账号
  python scripts/login_account.py --platform xiaohongshu

  # 验证所有账号登录状态
  python scripts/login_account.py --check-all
"""
import sys
import os
import argparse
import time
from typing import Dict, Optional

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from scripts.utils.config_loader import config
from scripts.utils.logger import logger


# 各平台登录URL
LOGIN_URLS = {
    "xiaohongshu": "https://www.xiaohongshu.com",  # 创作者中心可能被封锁，改用主页登录
    "zhihu": "https://www.zhihu.com/creator",
    "bilibili": "https://member.bilibili.com/",
    "wechat_mp": "https://mp.weixin.qq.com/",
    "wechat_channels": "https://channels.weixin.qq.com/",
}


def list_accounts():
    """列出所有配置的账号"""
    accounts = config.enabled_accounts
    if not accounts:
        print("\n没有配置启用的账号\n")
        return

    print(f"\n{'='*80}")
    print(f"  账号列表 ({len(accounts)}个)")
    print(f"{'='*80}")
    print(f"{'平台':<12} {'账号名':<20} {'显示名':<20} {'状态':<8} Cookie路径")
    print(f"{'-'*80}")

    for acc in accounts:
        platform = acc.get("platform", "")
        name = acc.get("name", "")
        display_name = acc.get("display_name", "")
        enabled = "✅启用" if acc.get("enabled", True) else "❌禁用"
        cookie_path = acc.get("cookie_path", "")
        print(f"{platform:<12} {name:<20} {display_name:<20} {enabled:<8} {cookie_path}")

    print(f"{'='*80}\n")


def login_account(account_config: Dict):
    """
    登录指定账号

    Args:
        account_config: 账号配置字典
    """
    from playwright.sync_api import sync_playwright

    platform = account_config.get("platform", "")
    account_name = account_config.get("name", "")
    display_name = account_config.get("display_name", "")
    user_data_dir = os.path.join(PROJECT_ROOT, account_config.get("user_data_dir", ""))
    login_url = LOGIN_URLS.get(platform, "")

    if not login_url:
        logger.error(f"不支持的平台: {platform}")
        return False

    # 确保目录存在
    os.makedirs(user_data_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  开始登录账号")
    print(f"  平台: {platform}")
    print(f"  账号: {account_name} ({display_name})")
    print(f"  Profile目录: {user_data_dir}")
    print(f"  登录URL: {login_url}")
    print(f"{'='*60}")
    print(f"\n⚠️  即将打开浏览器，请在浏览器中手动扫码登录")
    print(f"⚠️  登录成功后，浏览器会自动关闭")
    print(f"⚠️  如果之前已登录过，会直接检测登录状态\n")

    try:
        with sync_playwright() as p:
            # 使用持久化上下文（非无头模式，方便用户操作）
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ]
            )

            # 隐藏webdriver特征
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = {runtime: {}};
            """)

            page = context.new_page()
            page.goto(login_url, wait_until="domcontentloaded")

            print(f"\n✅ 浏览器已打开: {login_url}")
            print(f"⏳ 请在浏览器中完成登录操作...")
            print(f"⏳ 登录完成后，程序会自动检测登录状态\n")

            # 等待用户登录（最多5分钟）
            max_wait = 300  # 5分钟
            start_time = time.time()
            logged_in = False

            while time.time() - start_time < max_wait:
                time.sleep(5)
                try:
                    # 检测登录状态：检查页面是否有用户头像或已登录标志
                    # 小红书：登录后右上角会显示用户头像，未登录显示"登录"按钮
                    if platform == "xiaohongshu":
                        # 检查是否有用户头像元素（已登录标志）
                        avatar = page.query_selector("img.avatar, .user-avatar, [class*='avatar']")
                        # 检查是否还有登录按钮（未登录标志）
                        login_btn = page.query_selector("text=登录, button:has-text('登录'), .login-btn")
                        if avatar and not login_btn:
                            logged_in = True
                            break
                        # 备用：检查URL是否包含个人主页路径
                        if "/user/profile" in page.url or "/me" in page.url:
                            logged_in = True
                            break
                    else:
                        # 其他平台：检查URL是否离开登录页
                        current_url = page.url
                        if "login" not in current_url.lower() and "signin" not in current_url.lower():
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
                # 等待页面完全加载
                page.wait_for_timeout(3000)
                # 截图保存
                screenshot_dir = os.path.join(PROJECT_ROOT, "logs", "screenshots", "login")
                os.makedirs(screenshot_dir, exist_ok=True)
                screenshot_path = os.path.join(screenshot_dir, f"{platform}_{account_name}_login.png")
                page.screenshot(path=screenshot_path, full_page=True)
                print(f"📸 登录截图已保存: {screenshot_path}")

                # 保存Cookie（额外备份）
                cookie_path = os.path.join(PROJECT_ROOT, account_config.get("cookie_path", ""))
                os.makedirs(os.path.dirname(cookie_path), exist_ok=True)
                cookies = context.cookies()
                with open(cookie_path, "w", encoding="utf-8") as f:
                    import json
                    json.dump(cookies, f, ensure_ascii=False, indent=2)
                print(f"🍪 Cookie已备份: {cookie_path}")

                print(f"\n✅ 账号登录绑定完成!")
                print(f"   平台: {platform}")
                print(f"   账号: {account_name} ({display_name})")
                print(f"   Profile已保存到: {user_data_dir}")
                print(f"   后续发布时会自动复用此登录态\n")

                context.close()
                return True
            else:
                print(f"\n⚠️  等待超时（{max_wait}秒），未检测到登录成功")
                print(f"   请检查是否完成扫码登录")
                print(f"   浏览器将在10秒后关闭，Profile会自动保存\n")
                time.sleep(10)
                context.close()
                return False

    except Exception as e:
        logger.error(f"登录过程异常: {e}")
        print(f"\n❌ 登录过程异常: {e}\n")
        return False


def check_login_status(account_config: Dict) -> bool:
    """
    检查账号登录状态（无头模式快速检测）

    Args:
        account_config: 账号配置

    Returns:
        是否已登录
    """
    from playwright.sync_api import sync_playwright

    platform = account_config.get("platform", "")
    account_name = account_config.get("name", "")
    user_data_dir = os.path.join(PROJECT_ROOT, account_config.get("user_data_dir", ""))
    login_url = LOGIN_URLS.get(platform, "")

    if not os.path.exists(user_data_dir):
        return False

    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=True,
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
            )
            page = context.new_page()
            page.goto(login_url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(3000)

            current_url = page.url
            # 简单判断：如果URL不包含login/signin，认为已登录
            is_logged_in = "login" not in current_url.lower() and "signin" not in current_url.lower()

            context.close()
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
    print(f"  账号登录状态检查")
    print(f"{'='*70}")
    print(f"{'平台':<12} {'账号名':<20} {'状态':<10} 说明")
    print(f"{'-'*70}")

    for acc in accounts:
        platform = acc.get("platform", "")
        name = acc.get("name", "")
        user_data_dir = os.path.join(PROJECT_ROOT, acc.get("user_data_dir", ""))

        if not os.path.exists(user_data_dir) or not os.listdir(user_data_dir):
            status = "❌未登录"
            note = "Profile目录为空，请先登录"
        else:
            # 快速检查（不实际打开浏览器，只检查Profile是否存在）
            status = "⚠️待验证"
            note = "Profile存在，建议运行 --check-all 实际验证"

        print(f"{platform:<12} {name:<20} {status:<10} {note}")

    print(f"{'='*70}")
    print(f"\n提示: 实际验证登录状态需要打开浏览器，耗时较长。")
    print(f"      如需实际验证，请运行: python scripts/login_account.py --check-all --real\n")


def main():
    parser = argparse.ArgumentParser(description="账号登录绑定脚本")
    parser.add_argument("--list", action="store_true", help="列出所有账号")
    parser.add_argument("--account", type=str, help="登录指定账号（按账号名）")
    parser.add_argument("--platform", type=str, help="登录指定平台的第一个账号")
    parser.add_argument("--check-all", action="store_true", help="检查所有账号登录状态")
    parser.add_argument("--real", action="store_true", help="实际打开浏览器验证（配合--check-all使用）")

    args = parser.parse_args()

    if args.list:
        list_accounts()
        return

    if args.check_all:
        if args.real:
            # 实际验证（需要打开浏览器，耗时较长）
            accounts = config.enabled_accounts
            print(f"\n开始实际验证{len(accounts)}个账号的登录状态...\n")
            for acc in accounts:
                platform = acc.get("platform", "")
                name = acc.get("name", "")
                print(f"检查 [{platform}/{name}] ...", end=" ", flush=True)
                is_logged_in = check_login_status(acc)
                if is_logged_in:
                    print("✅已登录")
                else:
                    print("❌未登录")
            print()
        else:
            check_all_accounts()
        return

    # 找到要登录的账号
    target_account = None

    if args.account:
        for acc in config.enabled_accounts:
            if acc.get("name") == args.account or acc.get("display_name") == args.account:
                target_account = acc
                break
        if not target_account:
            print(f"\n❌ 未找到账号: {args.account}")
            print(f"   可用账号:")
            for acc in config.enabled_accounts:
                print(f"     - {acc.get('name')} ({acc.get('display_name')})")
            print()
            return

    elif args.platform:
        accounts = config.get_accounts_by_platform(args.platform)
        if accounts:
            target_account = accounts[0]
        else:
            print(f"\n❌ 平台 {args.platform} 没有配置账号\n")
            return

    if target_account:
        login_account(target_account)
        return

    # 默认显示帮助
    parser.print_help()
    print("\n常用命令:")
    print("  # 列出所有账号")
    print("  python scripts/login_account.py --list")
    print("  # 登录小红书第一个账号")
    print("  python scripts/login_account.py --platform xiaohongshu")
    print("  # 登录指定账号")
    print('  python scripts/login_account.py --account "AI小白日记"')
    print("  # 检查所有账号登录状态（快速）")
    print("  python scripts/login_account.py --check-all")
    print("  # 实际验证所有账号登录状态")
    print("  python scripts/login_account.py --check-all --real")


if __name__ == "__main__":
    main()
