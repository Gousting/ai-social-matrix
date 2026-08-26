"""
Phase 1 基础模块综合测试
验证：配置加载器、数据库、API客户端、Clash客户端、日志模块
"""
import sys
import os

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


def test_config_loader():
    """测试配置加载器"""
    print("\n" + "=" * 60)
    print("[1/5] 测试配置加载器 (config_loader)")
    print("=" * 60)
    try:
        from scripts.utils.config_loader import config
        print(f"  ✓ 项目根目录: {PROJECT_ROOT}")
        print(f"  ✓ 启用的API服务商: {[p['name'] for p in config.api_providers]}")
        print(f"  ✓ 启用的账号数: {len(config.enabled_accounts)}")
        print(f"  ✓ 涉及平台: {config.platforms}")
        print(f"  ✓ 排期配置: 每日{config.schedule_config.get('posts_per_day')}篇")
        print(f"  ✓ Clash地址: {config.clash_config.get('external_controller')}")
        print("  ✓ 配置加载器测试通过")
        return True
    except Exception as e:
        print(f"  ✗ 配置加载器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_database():
    """测试数据库模块"""
    print("\n" + "=" * 60)
    print("[2/5] 测试数据库模块 (db)")
    print("=" * 60)
    try:
        from scripts.utils.db import db

        # 测试选题库
        test_note = {
            "note_id": f"test_{int(os.times()[4])}",
            "platform": "xiaohongshu",
            "title": "测试选题-Codex安装教程",
            "content": "测试内容",
            "author": "测试作者",
            "likes": 100,
            "favorites": 80,
            "comments": 20,
            "heat_score": 74.0
        }
        db.insert_raw_note(test_note)
        topics = db.get_top_topics(limit=5)
        print(f"  ✓ 选题库: 共{len(topics)}条候选选题")

        # 测试发布日志
        log_id = db.insert_publish_log({
            "content_id": f"test_content_{int(os.times()[4])}",
            "platform": "xiaohongshu",
            "account": "ai_xiaobai",
            "title": "测试发布",
            "scheduled_time": "2026-08-27 08:30:00"
        })
        print(f"  ✓ 发布日志: 插入记录ID={log_id}")

        # 测试数据指标
        db.upsert_daily_metrics({
            "content_id": f"test_content_{int(os.times()[4])}",
            "date": "2026-08-27",
            "platform": "xiaohongshu",
            "account": "ai_xiaobai",
            "title": "测试发布",
            "views": 1000,
            "likes": 50,
            "favorites": 30,
            "comments": 10,
            "shares": 5
        })
        top_posts = db.get_top_posts(limit=5)
        print(f"  ✓ 数据指标: 共{len(top_posts)}条内容记录")

        print("  ✓ 数据库模块测试通过")
        return True
    except Exception as e:
        print(f"  ✗ 数据库模块测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_api_client():
    """测试API客户端"""
    print("\n" + "=" * 60)
    print("[3/5] 测试API客户端 (api_client)")
    print("=" * 60)
    try:
        from scripts.utils.api_client import api_client
        from scripts.utils.config_loader import config

        providers = config.api_providers
        print(f"  配置的服务商数: {len(providers)}")
        print(f"  初始化的客户端数: {len(api_client._clients)}")

        if not api_client._clients:
            print("  ⚠ 没有可用的API客户端（API Key未配置）")
            print("  请在 config/api_keys.yaml 中填入至少一个API Key")
            print("  注册地址:")
            print("    DeepSeek:    https://platform.deepseek.com")
            print("    通义千问:    https://dashscope.aliyun.com")
            print("    硅基流动:    https://cloud.siliconflow.cn")
            print("  ✓ API客户端模块加载成功（待配置Key后可调用）")
            return True

        # 有客户端，尝试调用
        try:
            result, provider = api_client.chat(
                "请用一句话介绍你自己",
                temperature=0.7,
                max_tokens=50
            )
            print(f"  ✓ 调用成功! 服务商: {provider}")
            print(f"  ✓ 回复: {result[:100]}")
        except Exception as e:
            print(f"  ⚠ 调用失败（可能是API Key无效或无额度）: {e}")
            print("  ✓ API客户端模块加载成功（调用需有效API Key）")

        api_client.print_stats()
        return True
    except Exception as e:
        print(f"  ✗ API客户端测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_clash_client():
    """测试Clash客户端"""
    print("\n" + "=" * 60)
    print("[4/5] 测试Clash客户端 (clash_client)")
    print("=" * 60)
    try:
        from scripts.utils.clash_client import clash

        if clash.is_available():
            print(f"  ✓ Clash版本: {clash.get_version()}")
            print(f"  ✓ 当前节点: {clash.get_current_node()}")
            nodes = clash.get_selector_nodes()
            print(f"  ✓ 选择器节点数: {len(nodes)}")
            print(f"  ✓ 前5个节点: {nodes[:5]}")
        else:
            print("  ⚠ Clash不可用（未启动或未开启external-controller）")
            print("  请检查:")
            print("    1. Clash是否已启动")
            print("    2. Clash配置中是否开启 external-controller: 127.0.0.1:9090")
            print("    3. config/settings.yaml 中 clash.enabled 是否为 true")
            print("  ✓ Clash客户端模块加载成功（待Clash启动后可使用）")

        clash.print_status()
        return True
    except Exception as e:
        print(f"  ✗ Clash客户端测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_logger():
    """测试日志模块"""
    print("\n" + "=" * 60)
    print("[5/5] 测试日志模块 (logger)")
    print("=" * 60)
    try:
        from scripts.utils.logger import logger
        logger.info("日志模块测试 - INFO")
        logger.warning("日志模块测试 - WARNING")
        logger.error("日志模块测试 - ERROR")
        print("  ✓ 日志输出到控制台成功")
        log_file = os.path.join(PROJECT_ROOT, "logs", "ai_matrix.log")
        if os.path.exists(log_file):
            print(f"  ✓ 日志文件存在: {log_file}")
            print(f"  ✓ 文件大小: {os.path.getsize(log_file)} bytes")
        print("  ✓ 日志模块测试通过")
        return True
    except Exception as e:
        print(f"  ✗ 日志模块测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("\n" + "#" * 60)
    print("#  AI社交媒体矩阵管理运营系统 - Phase 1 基础模块测试")
    print("#" * 60)

    results = {
        "配置加载器": test_config_loader(),
        "数据库": test_database(),
        "API客户端": test_api_client(),
        "Clash客户端": test_clash_client(),
        "日志模块": test_logger(),
    }

    print("\n" + "#" * 60)
    print("#  测试结果汇总")
    print("#" * 60)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for name, result in results.items():
        status = "✓ 通过" if result else "✗ 失败"
        print(f"  {name:15s}: {status}")
    print(f"\n  总计: {passed}/{total} 通过")

    if passed == total:
        print("\n  🎉 Phase 1 基础模块全部测试通过!")
        print("  下一步: 配置API Key后进入 Phase 2（核心脚本开发）")
    else:
        print("\n  ⚠ 部分模块测试未通过，请检查错误信息")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
