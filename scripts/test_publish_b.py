#!/usr/bin/env python3
"""
测试小红书自动发布流程（方案B）
只测试打开发布页面和填写内容，不真正点击发布
"""
import sys
import os
import json
import time

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from scripts.utils.config_loader import config
from scripts.utils.logger import logger


def test_publish_flow():
    """测试发布流程"""
    print("=" * 60)
    print("小红书自动发布流程测试（方案B）")
    print("=" * 60)

    # 加载账号配置
    all_accounts = config.settings.get("accounts", [])
    xhs_accounts = [a for a in all_accounts if a.get("platform") == "xiaohongshu" and a.get("enabled", True)]

    if not xhs_accounts:
        print("❌ 未找到小红书账号配置")
        return

    account = xhs_accounts[0]
    print(f"\n📱 使用账号: {account.get('name', 'unknown')}")
    print(f"   Profile目录: {account.get('user_data_dir', './profiles/xhs/default')}")

    # 测试草稿
    test_draft = {
        "title": "【测试】Codex安装教程",
        "content": "这是一篇测试笔记，用于测试自动发布流程。\n\n第一步：装Node.js\n第二步：注册账号\n第三步：命令行装Codex\n\n#AI工具 #Codex #编程工具",
        "tags": ["#AI工具", "#Codex", "#编程工具"],
        "images": []
    }

    print(f"\n📝 测试标题: {test_draft['title']}")
    print(f"   测试正文长度: {len(test_draft['content'])}字")

    # 导入发布器
    try:
        from scripts.publishers.xiaohongshu_drission import XiaohongshuDrissionPublisher
    except Exception as e:
        print(f"❌ 导入发布器失败: {e}")
        return

    print("\n🚀 启动浏览器...")
    try:
        publisher = XiaohongshuDrissionPublisher(account, headless=False)
        publisher.start()
    except Exception as e:
        print(f"❌ 启动浏览器失败: {e}")
        return

    try:
        # 1. 检查登录状态
        print("\n1️⃣  检查登录状态...")
        if publisher.is_logged_in():
            print("   ✅ 已登录")
        else:
            print("   ❌ 未登录，请先扫码登录")
            print("   浏览器将保持打开，请手动登录后重新运行测试")
            input("\n按回车键关闭浏览器...")
            return

        # 2. 打开发布页面
        print("\n2️⃣  打开发布页面...")
        try:
            publisher._page.get(publisher.PUBLISH_URL, timeout=20)
            time.sleep(5)
            print(f"   ✅ 已打开: {publisher._page.url}")
        except Exception as e:
            print(f"   ❌ 打开发布页面失败: {e}")
            input("\n按回车键关闭浏览器...")
            return

        # 3. 截图保存
        screenshot_path = os.path.join(PROJECT_ROOT, "data", "publish_test", "publish_page.png")
        os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
        try:
            publisher._page.get_screenshot(path=screenshot_path)
            print(f"\n📸 发布页面截图已保存: {screenshot_path}")
        except Exception as e:
            print(f"   ⚠️  截图失败: {e}")

        # 4. 尝试填写标题
        print("\n3️⃣  尝试填写标题...")
        try:
            title_input = publisher._page.ele('css:input[placeholder*="标题"], textarea[placeholder*="标题"], .title-input', timeout=5)
            if title_input:
                title_input.clear()
                title_input.input(test_draft["title"])
                print(f"   ✅ 标题已填写: {test_draft['title']}")
            else:
                print("   ⚠️  未找到标题输入框，请手动检查页面结构")
        except Exception as e:
            print(f"   ⚠️  填写标题失败: {e}")

        # 5. 尝试填写正文
        print("\n4️⃣  尝试填写正文...")
        try:
            content_input = publisher._page.ele('css:textarea[placeholder*="正文"], .content-input, .ql-editor', timeout=5)
            if content_input:
                content_input.clear()
                content_input.input(test_draft["content"])
                print(f"   ✅ 正文已填写: {len(test_draft['content'])}字")
            else:
                print("   ⚠️  未找到正文输入框，请手动检查页面结构")
        except Exception as e:
            print(f"   ⚠️  填写正文失败: {e}")

        # 6. 再次截图
        try:
            screenshot_path2 = os.path.join(PROJECT_ROOT, "data", "publish_test", "publish_filled.png")
            publisher._page.get_screenshot(path=screenshot_path2)
            print(f"\n📸 填写后截图已保存: {screenshot_path2}")
        except Exception:
            pass

        print("\n" + "=" * 60)
        print("✅ 测试完成！")
        print("=" * 60)
        print("\n📊 测试结果:")
        print("   - 浏览器启动: ✅")
        print("   - 登录状态: ✅")
        print("   - 打开发布页面: ✅")
        print("   - 填写标题: 请查看截图确认")
        print("   - 填写正文: 请查看截图确认")
        print("   - 点击发布: ⏸️  已暂停（未真正发布）")
        print("\n💡 下一步:")
        print("   1. 查看截图，确认标题和正文是否正确填写")
        print("   2. 如果填写成功，可以测试上传图片")
        print("   3. 最后测试点击发布（需要确认）")
        print("\n⚠️  注意: 小红书页面结构可能变化，如果选择器不匹配，需要手动调整")

        input("\n按回车键关闭浏览器...")

    except Exception as e:
        print(f"\n❌ 测试过程中出错: {e}")
        import traceback
        traceback.print_exc()
        input("\n按回车键关闭浏览器...")
    finally:
        try:
            publisher.close()
        except Exception:
            pass


if __name__ == "__main__":
    test_publish_flow()
