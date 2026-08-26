"""
免费LLM API客户端 - 多Key轮询
支持 DeepSeek / 通义千问 / 硅基流动 / 豆包 / 智谱AI 等OpenAI兼容接口
特性：
  - 多服务商多Key自动轮询
  - 单Key失败自动切换下一个
  - 调用统计和失败计数
  - 统一的chat/completion接口
"""
import time
import json
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from openai import OpenAI

from .config_loader import config


class APIClient:
    """免费LLM API多Key轮询客户端"""

    def __init__(self):
        self._providers = config.api_providers
        self._call_config = config.api_call_config
        self._clients: Dict[str, OpenAI] = {}
        self._stats: Dict[str, Dict] = {}  # 每个服务商的调用统计
        self._failed_providers: Dict[str, float] = {}  # 暂时不可用的服务商及恢复时间
        self._init_clients()

    def _init_clients(self):
        """初始化所有API客户端"""
        for p in self._providers:
            name = p["name"]
            try:
                client = OpenAI(
                    api_key=p["api_key"],
                    base_url=p["base_url"],
                    timeout=self._call_config.get("timeout", 60)
                )
                self._clients[name] = client
                self._stats[name] = {
                    "total_calls": 0,
                    "success_calls": 0,
                    "failed_calls": 0,
                    "total_tokens": 0,
                    "last_call_time": None,
                    "last_error": None
                }
            except Exception as e:
                print(f"[API Client] 初始化 {name} 失败: {e}")

    def _get_available_providers(self) -> List[Dict]:
        """获取当前可用的服务商列表（排除暂时失败的）"""
        now = time.time()
        available = []
        for p in self._providers:
            name = p["name"]
            if name not in self._clients:
                continue
            # 检查是否在冷却期
            if name in self._failed_providers:
                if now < self._failed_providers[name]:
                    continue
                else:
                    del self._failed_providers[name]
            available.append(p)
        return available

    def _mark_provider_failed(self, name: str, error: str, cooldown: int = 60):
        """标记服务商暂时不可用"""
        self._failed_providers[name] = time.time() + cooldown
        if name in self._stats:
            self._stats[name]["last_error"] = error
            self._stats[name]["failed_calls"] += 1

    def chat(self, prompt: str, system_prompt: str = None,
             temperature: float = None, max_tokens: int = None) -> Tuple[str, str]:
        """
        调用LLM生成回复（多Key轮询）

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词（可选）
            temperature: 生成温度（可选，默认用配置）
            max_tokens: 最大token数（可选，默认用配置）

        Returns:
            (生成的文本, 使用的服务商名称)

        Raises:
            RuntimeError: 所有服务商均不可用
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        temp = temperature if temperature is not None else self._call_config.get("temperature", 0.7)
        max_tok = max_tokens if max_tokens is not None else self._call_config.get("max_tokens", 4000)
        retry_count = self._call_config.get("retry_count", 3)
        retry_delay = self._call_config.get("retry_delay", 2)

        available = self._get_available_providers()
        if not available:
            raise RuntimeError("所有API服务商均不可用，请检查API Key和网络连接")

        last_error = None
        for attempt in range(retry_count):
            for provider in available:
                name = provider["name"]
                client = self._clients.get(name)
                if not client:
                    continue

                try:
                    self._stats[name]["total_calls"] += 1
                    self._stats[name]["last_call_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    response = client.chat.completions.create(
                        model=provider["model"],
                        messages=messages,
                        temperature=temp,
                        max_tokens=max_tok
                    )

                    result = response.choices[0].message.content
                    self._stats[name]["success_calls"] += 1
                    if response.usage:
                        self._stats[name]["total_tokens"] += response.usage.total_tokens

                    return result, name

                except Exception as e:
                    last_error = str(e)
                    print(f"[API Client] {name} 调用失败 (尝试{attempt+1}/{retry_count}): {e}")
                    self._mark_provider_failed(name, str(e), cooldown=30)
                    continue

            if attempt < retry_count - 1:
                print(f"[API Client] 所有服务商本轮均失败，{retry_delay}秒后重试...")
                time.sleep(retry_delay)
                available = self._get_available_providers()
                if not available:
                    break

        raise RuntimeError(f"所有API服务商调用失败，最后错误: {last_error}")

    def check_similarity(self, text1: str, text2: str) -> float:
        """
        用LLM判断两段文本的相似度（0-100）
        用于原创性自检
        """
        prompt = f"""请判断以下两段文本的相似度，返回0-100的数字（0=完全不同，100=完全相同）。
只返回数字，不要其他内容。

文本1:
{text1[:2000]}

文本2:
{text2[:2000]}

相似度:"""
        try:
            result, _ = self.chat(prompt, temperature=0.1, max_tokens=10)
            # 提取数字
            import re
            match = re.search(r'\d+', result)
            if match:
                return float(match.group())
            return 50.0
        except Exception as e:
            print(f"[API Client] 相似度检测失败: {e}")
            return 50.0

    def get_stats(self) -> Dict:
        """获取所有服务商的调用统计"""
        return {
            "providers": self._stats,
            "available_count": len(self._get_available_providers()),
            "total_providers": len(self._providers),
            "failed_providers": list(self._failed_providers.keys())
        }

    def print_stats(self):
        """打印调用统计"""
        stats = self.get_stats()
        print("=" * 60)
        print("API调用统计")
        print("=" * 60)
        print(f"可用服务商: {stats['available_count']}/{stats['total_providers']}")
        if stats['failed_providers']:
            print(f"暂时不可用: {stats['failed_providers']}")
        print("-" * 60)
        for name, s in stats["providers"].items():
            success_rate = (s["success_calls"] / s["total_calls"] * 100) if s["total_calls"] > 0 else 0
            print(f"  {name:15s} | 调用:{s['total_calls']:4d} | 成功:{s['success_calls']:4d} | "
                  f"失败:{s['failed_calls']:4d} | 成功率:{success_rate:5.1f}% | Token:{s['total_tokens']:6d}")
        print("=" * 60)


# 全局单例
api_client = APIClient()


if __name__ == "__main__":
    print("=" * 50)
    print("API客户端测试")
    print("=" * 50)

    # 检查配置的服务商
    print(f"\n配置的API服务商: {[p['name'] for p in config.api_providers]}")
    print(f"可用客户端数: {len(api_client._clients)}")

    if not api_client._clients:
        print("\n[警告] 没有可用的API客户端，请在 config/api_keys.yaml 中配置API Key")
        print("注册地址:")
        print("  DeepSeek:    https://platform.deepseek.com")
        print("  通义千问:    https://dashscope.aliyun.com")
        print("  硅基流动:    https://cloud.siliconflow.cn")
    else:
        # 测试调用
        try:
            result, provider = api_client.chat(
                "请用一句话介绍你自己",
                system_prompt="你是一个AI助手",
                temperature=0.7,
                max_tokens=100
            )
            print(f"\n测试调用成功!")
            print(f"使用服务商: {provider}")
            print(f"回复: {result}")
        except Exception as e:
            print(f"\n测试调用失败: {e}")
            print("请检查API Key是否正确、是否有免费额度、网络是否可访问")

    # 打印统计
    api_client.print_stats()
