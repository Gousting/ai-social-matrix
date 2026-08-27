#!/usr/bin/env python3
"""
小红书自动发布分步测试脚本（方案B）
每一步都截图，方便分析页面结构和选择器有效性
不真正点击发布，只测试到填写完成
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


def step_test():
    """分步测试"""
    print("=" * 60)
    print("小红书自动发布分步测试（方案B）")
    print("=" * 60)

    # 加载账号配置
    xhs_accounts = config.get_accounts_by_platform("xiaohongshu")

    if not xhs_accounts:
        print("❌ 未找到启用的小红书账号配置")
        return

    account = xhs_accounts[0]
    print(f"\n📱 使用账号: {account.get('name', 'unknown')}")
    print(f"   显示名: {account.get('display_name', '')}")
    print(f"   Profile: {account.get('user_data_dir', './profiles/xhs/default')}")

    # 测试草稿
    test_draft = {
        "title": "【测试】Codex安装保姆级教程",
        "content": "这是一篇自动发布测试笔记。\n\n第一步：装Node.js\n第二步：注册账号拿API密钥\n第三步：命令行装Codex\n第四步：配置API密钥\n第五步：VS Code装插件\n\n#AI工具 #Codex #编程工具 #保姆级教程",
        "tags": ["#AI工具", "#Codex", "#编程工具", "#保姆级教程"],
        "images": []
    }

    # 截图目录
    screenshot_dir = os.path.join(PROJECT_ROOT, "data", "publish_test", "steps")
    os.makedirs(screenshot_dir, exist_ok=True)

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

    results = {}

    try:
        # 步骤1：检查登录状态
        print("\n" + "=" * 60)
        print("步骤1：检查登录状态")
        print("=" * 60)
        try:
            logged_in = publisher.is_logged_in()
            results["login"] = logged_in
            if logged_in:
                print("✅ 已登录")
            else:
                print("❌ 未登录，请先扫码登录")
                publisher.screenshot("step1_not_logged_in")
                input("\n请在浏览器中完成登录，然后按回车键继续...")
                logged_in = publisher.is_logged_in()
                results["login"] = logged_in
                if not logged_in:
                    print("❌ 登录仍未成功，测试终止")
                    return
        except Exception as e:
            print(f"❌ 登录检查异常: {e}")
            return

        # 步骤2：打开发布页面
        print("\n" + "=" * 60)
        print("步骤2：打开发布页面")
        print("=" * 60)
        try:
            publisher._page.get(publisher.PUBLISH_URL, timeout=20)
            time.sleep(5)
            current_url = publisher._page.url
            page_title = publisher._page.title
            print(f"   当前URL: {current_url}")
            print(f"   页面标题: {page_title}")

            # 截图
            screenshot_path = os.path.join(screenshot_dir, "step2_publish_page.png")
            publisher._page.get_screenshot(path=screenshot_path)
            print(f"   ✅ 截图已保存: {screenshot_path}")

            # 检查页面元素
            print("\n   🔍 分析页面元素...")

            # 查找标题输入框
            title_selectors = [
                'css:input[placeholder*="填写标题"]',
                'css:input[placeholder*="标题"]',
                'css:input[placeholder*="title"]',
            ]
            title_found = False
            for sel in title_selectors:
                try:
                    ele = publisher._page.ele(sel, timeout=2)
                    if ele and ele.states.is_displayed:
                        print(f"   ✅ 找到标题输入框: {sel}")
                        print(f"      placeholder: {ele.attr('placeholder')}")
                        title_found = True
                        break
                except Exception:
                    continue
            if not title_found:
                print("   ⚠️  未找到标题输入框（尝试的选择器都不匹配）")

            # 查找正文编辑区域
            content_selectors = [
                'css:textarea[placeholder*="输入正文"]',
                'css:textarea[placeholder*="正文"]',
                'css:[contenteditable="true"]',
            ]
            content_found = False
            for sel in content_selectors:
                try:
                    eles = publisher._page.eles(sel)
                    if eles:
                        print(f"   ✅ 找到正文编辑区域: {sel} (共{len(eles)}个)")
                        for i, e in enumerate(eles[:3]):
                            try:
                                print(f"      [{i}] tag={e.tag}, placeholder={e.attr('placeholder')}, class={e.attr('class')[:50] if e.attr('class') else ''}")
                            except Exception:
                                pass
                        content_found = True
                        break
                except Exception:
                    continue
            if not content_found:
                print("   ⚠️  未找到正文编辑区域")

            # 查找文件上传input
            try:
                file_inputs = publisher._page.eles('css:input[type="file"]')
                if file_inputs:
                    print(f"   ✅ 找到文件上传input: {len(file_inputs)}个")
                    for i, fi in enumerate(file_inputs):
                        try:
                            print(f"      [{i}] accept={fi.attr('accept')}, multiple={fi.attr('multiple')}")
                        except Exception:
                            pass
                else:
                    print("   ⚠️  未找到文件上传input")
            except Exception as e:
                print(f"   ⚠️  查找文件上传input异常: {e}")

            # 查找发布按钮
            publish_selectors = [
                'text:发布',
                'text:立即发布',
                'text:发布笔记',
                'css:button[class*="publish"]',
                'css:.publish-btn',
            ]
            publish_found = False
            for sel in publish_selectors:
                try:
                    ele = publisher._page.ele(sel, timeout=2)
                    if ele and ele.states.is_displayed:
                        print(f"   ✅ 找到发布按钮: {sel}")
                        print(f"      text={ele.text[:30]}, disabled={ele.states.is_disabled}")
                        publish_found = True
                        break
                except Exception:
                    continue
            if not publish_found:
                print("   ⚠️  未找到发布按钮")

            results["publish_page"] = True

        except Exception as e:
            print(f"❌ 打开发布页面失败: {e}")
            import traceback
            traceback.print_exc()
            return

        # 步骤3：填写标题
        print("\n" + "=" * 60)
        print("步骤3：填写标题")
        print("=" * 60)
        try:
            success = publisher._fill_title(test_draft["title"])
            results["fill_title"] = success
            if success:
                print(f"✅ 标题填写成功: {test_draft['title']}")
                screenshot_path = os.path.join(screenshot_dir, "step3_title_filled.png")
                publisher._page.get_screenshot(path=screenshot_path)
                print(f"   截图已保存: {screenshot_path}")
            else:
                print("❌ 标题填写失败")
        except Exception as e:
            print(f"❌ 标题填写异常: {e}")
            results["fill_title"] = False

        # 步骤4：填写正文
        print("\n" + "=" * 60)
        print("步骤4：填写正文")
        print("=" * 60)
        try:
            success = publisher._fill_content(test_draft["content"])
            results["fill_content"] = success
            if success:
                print(f"✅ 正文填写成功: {len(test_draft['content'])}字")
                screenshot_path = os.path.join(screenshot_dir, "step4_content_filled.png")
                publisher._page.get_screenshot(path=screenshot_path)
                print(f"   截图已保存: {screenshot_path}")
            else:
                print("❌ 正文填写失败")
        except Exception as e:
            print(f"❌ 正文填写异常: {e}")
            results["fill_content"] = False

        # 步骤5：添加标签
        print("\n" + "=" * 60)
        print("步骤5：添加标签")
        print("=" * 60)
        try:
            success = publisher._fill_tags(test_draft["tags"])
            results["fill_tags"] = success
            if success:
                print(f"✅ 标签添加成功: {test_draft['tags']}")
                screenshot_path = os.path.join(screenshot_dir, "step5_tags_filled.png")
                publisher._page.get_screenshot(path=screenshot_path)
                print(f"   截图已保存: {screenshot_path}")
            else:
                print("❌ 标签添加失败")
        except Exception as e:
            print(f"❌ 标签添加异常: {e}")
            results["fill_tags"] = False

        # 步骤6：检查发布按钮状态
        print("\n" + "=" * 60)
        print("步骤6：检查发布按钮状态（不点击）")
        print("=" * 60)
        try:
            publish_selectors = [
                'text:发布',
                'text:立即发布',
                'text:发布笔记',
            ]
            for sel in publish_selectors:
                try:
                    ele = publisher._page.ele(sel, timeout=2)
                    if ele and ele.states.is_displayed:
                        disabled = ele.states.is_disabled
                        print(f"   发布按钮: {sel}")
                        print(f"   可点击: {'❌ 否（内容未填写完整）' if disabled else '✅ 是'}")
                        results["publish_button_ready"] = not disabled
                        break
                except Exception:
                    continue

            screenshot_path = os.path.join(screenshot_dir, "step6_final_state.png")
            publisher._page.get_screenshot(path=screenshot_path)
            print(f"\n   ✅ 最终状态截图已保存: {screenshot_path}")

        except Exception as e:
            print(f"❌ 检查发布按钮异常: {e}")

        # 测试结果汇总
        print("\n" + "=" * 60)
        print("📊 测试结果汇总")
        print("=" * 60)
        for step, result in results.items():
            status = "✅ 通过" if result else "❌ 失败"
            print(f"   {step:20s}: {status}")

        # 保存测试结果
        result_path = os.path.join(screenshot_dir, "test_results.json")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n   测试结果已保存: {result_path}")

        print("\n" + "=" * 60)
        print("💡 下一步建议")
        print("=" * 60)
        print("   1. 查看截图，确认标题/正文/标签是否正确填写")
        print("   2. 如果有步骤失败，根据截图分析页面结构，调整选择器")
        print("   3. 如果所有步骤都通过，可以测试上传图片")
        print("   4. 最后测试点击发布（建议先用测试内容，发布后立即删除）")

        input("\n按回车键关闭浏览器...")

    except Exception as e:
        print(f"\n❌ 测试过程中出错: {e}")
        import traceback
        traceback.print_exc()
        input("\n按回车键关闭浏览器...")
    finally:
        try:
            publisher.quit()
        except Exception:
            pass


if __name__ == "__main__":
    step_test()
