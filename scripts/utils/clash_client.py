"""
Clash客户端 - 代理节点管理
通过Clash外部控制器API实现：
  - 获取代理节点列表
  - 切换代理节点
  - 节点可用性检测
  - 账号-节点绑定管理
"""
import requests
import time
from typing import List, Dict, Optional, Set
from datetime import datetime

from .config_loader import config


class ClashClient:
    """Clash代理客户端"""

    def __init__(self):
        clash_cfg = config.clash_config
        self._enabled = clash_cfg.get("enabled", True)
        self._base_url = clash_cfg.get("external_controller", "http://127.0.0.1:9090")
        self._selector = clash_cfg.get("proxy_selector", "Proxy")
        self._node_check_interval = clash_cfg.get("node_check_interval", 300)
        self._retry_on_fail = clash_cfg.get("retry_on_node_fail", True)
        self._available_nodes: List[str] = []
        self._last_check_time: float = 0
        self._account_node_map: Dict[str, str] = {}  # account_key -> node_name
        self._init_account_node_binding()

    def _init_account_node_binding(self):
        """从账号配置初始化账号-节点绑定"""
        for account in config.enabled_accounts:
            key = f"{account['platform']}_{account['name']}"
            node = account.get("clash_node", "")
            if node:
                self._account_node_map[key] = node

    def _request(self, method: str, path: str, **kwargs) -> Optional[Dict]:
        """发送请求到Clash API"""
        if not self._enabled:
            return None
        url = f"{self._base_url}{path}"
        try:
            resp = requests.request(method, url, timeout=10, **kwargs)
            if resp.status_code == 200:
                return resp.json()
            else:
                print(f"[Clash] API请求失败 {method} {path}: HTTP {resp.status_code}")
                return None
        except Exception as e:
            print(f"[Clash] API请求异常 {method} {path}: {e}")
            return None

    def is_available(self) -> bool:
        """检查Clash是否可用"""
        if not self._enabled:
            return False
        result = self._request("GET", "/version")
        return result is not None

    def get_version(self) -> Optional[str]:
        """获取Clash版本"""
        result = self._request("GET", "/version")
        if result:
            return result.get("version")
        return None

    def get_proxies(self) -> Optional[Dict]:
        """获取所有代理信息"""
        return self._request("GET", "/proxies")

    def get_selector_nodes(self) -> List[str]:
        """获取选择器下的所有可用节点"""
        proxies = self.get_proxies()
        if not proxies:
            return []
        selector = proxies.get("proxies", {}).get(self._selector, {})
        return selector.get("all", [])

    def get_current_node(self) -> Optional[str]:
        """获取当前使用的节点"""
        proxies = self.get_proxies()
        if not proxies:
            return None
        selector = proxies.get("proxies", {}).get(self._selector, {})
        return selector.get("now")

    def switch_node(self, node_name: str) -> bool:
        """
        切换代理节点

        Args:
            node_name: 目标节点名称

        Returns:
            是否切换成功
        """
        if not self._enabled:
            print("[Clash] Clash未启用，跳过节点切换")
            return True  # 未启用时视为成功（不影响流程）

        available = self.get_selector_nodes()
        if node_name not in available:
            print(f"[Clash] 节点 '{node_name}' 不在可用列表中，可用节点: {available[:5]}...")
            return False

        result = self._request(
            "PUT",
            f"/proxies/{self._selector}",
            json={"name": node_name}
        )

        if result is not None or self._verify_switch(node_name):
            print(f"[Clash] 节点切换成功: {node_name}")
            return True
        else:
            print(f"[Clash] 节点切换失败: {node_name}")
            return False

    def _verify_switch(self, expected_node: str) -> bool:
        """验证节点是否切换成功"""
        time.sleep(1)
        current = self.get_current_node()
        return current == expected_node

    def switch_for_account(self, platform: str, account_name: str) -> bool:
        """
        为指定账号切换到绑定的代理节点

        Args:
            platform: 平台
            account_name: 账号名

        Returns:
            是否切换成功
        """
        key = f"{platform}_{account_name}"
        node = self._account_node_map.get(key)

        if not node:
            print(f"[Clash] 账号 {key} 未绑定节点，使用当前节点")
            return True

        current = self.get_current_node()
        if current == node:
            return True  # 已经是目标节点

        return self.switch_node(node)

    def check_node_health(self, node_name: str, timeout: int = 5) -> bool:
        """
        检测单个节点的可用性（延迟测试）

        Args:
            node_name: 节点名称
            timeout: 超时时间（秒）

        Returns:
            是否可用
        """
        result = self._request(
            "GET",
            f"/proxies/{node_name}/delay",
            params={"timeout": timeout * 1000, "url": "http://www.gstatic.com/generate_204"}
        )
        if result and "delay" in result:
            return result["delay"] > 0
        return False

    def get_available_nodes(self, force_refresh: bool = False) -> List[str]:
        """
        获取所有可用节点（带缓存）

        Args:
            force_refresh: 是否强制刷新

        Returns:
            可用节点名称列表
        """
        now = time.time()
        if (not force_refresh
                and self._available_nodes
                and now - self._last_check_time < self._node_check_interval):
            return self._available_nodes

        all_nodes = self.get_selector_nodes()
        available = []
        for node in all_nodes:
            # 跳过DIRECT和REJECT等特殊节点
            if node in ["DIRECT", "REJECT", "GLOBAL"]:
                continue
            if self.check_node_health(node):
                available.append(node)

        self._available_nodes = available
        self._last_check_time = now
        print(f"[Clash] 节点检测完成: {len(available)}/{len(all_nodes)} 可用")
        return available

    def bind_account_node(self, platform: str, account_name: str, node_name: str):
        """绑定账号到指定节点"""
        key = f"{platform}_{account_name}"
        self._account_node_map[key] = node_name
        print(f"[Clash] 账号 {key} 绑定到节点: {node_name}")

    def auto_assign_nodes(self):
        """
        自动为所有启用的账号分配可用节点
        同平台账号使用不同节点，不同平台可复用
        """
        available = self.get_available_nodes(force_refresh=True)
        if not available:
            print("[Clash] 没有可用节点，无法自动分配")
            return

        platform_nodes: Dict[str, Set[str]] = {}  # 记录每个平台已使用的节点
        node_idx = 0

        for account in config.enabled_accounts:
            platform = account["platform"]
            key = f"{platform}_{account['name']}"

            # 如果已经绑定了节点且节点可用，保留
            existing = self._account_node_map.get(key)
            if existing and existing in available:
                platform_nodes.setdefault(platform, set()).add(existing)
                continue

            # 找一个该平台未使用的节点
            if platform not in platform_nodes:
                platform_nodes[platform] = set()

            assigned = None
            for i in range(len(available)):
                candidate = available[(node_idx + i) % len(available)]
                if candidate not in platform_nodes[platform]:
                    assigned = candidate
                    node_idx = (node_idx + i + 1) % len(available)
                    break

            if not assigned:
                # 节点不够，复用（同平台可能同节点，有风险但可接受）
                assigned = available[node_idx % len(available)]
                node_idx += 1

            self._account_node_map[key] = assigned
            platform_nodes[platform].add(assigned)
            print(f"[Clash] 自动分配: {key} -> {assigned}")

    def get_status(self) -> Dict:
        """获取Clash状态信息"""
        return {
            "enabled": self._enabled,
            "base_url": self._base_url,
            "available": self.is_available(),
            "version": self.get_version(),
            "current_node": self.get_current_node(),
            "total_nodes": len(self.get_selector_nodes()),
            "available_nodes": len(self._available_nodes),
            "account_bindings": len(self._account_node_map)
        }

    def print_status(self):
        """打印Clash状态"""
        status = self.get_status()
        print("=" * 50)
        print("Clash状态")
        print("=" * 50)
        print(f"  启用: {status['enabled']}")
        print(f"  地址: {status['base_url']}")
        print(f"  可用: {status['available']}")
        print(f"  版本: {status['version']}")
        print(f"  当前节点: {status['current_node']}")
        print(f"  总节点数: {status['total_nodes']}")
        print(f"  可用节点数: {status['available_nodes']}")
        print(f"  账号绑定数: {status['account_bindings']}")
        print("=" * 50)


# 全局单例
clash = ClashClient()


if __name__ == "__main__":
    print("=" * 50)
    print("Clash客户端测试")
    print("=" * 50)

    # 检查可用性
    if clash.is_available():
        print(f"\nClash版本: {clash.get_version()}")
        print(f"当前节点: {clash.get_current_node()}")

        # 获取节点列表
        nodes = clash.get_selector_nodes()
        print(f"\n选择器节点数: {len(nodes)}")
        print(f"前5个节点: {nodes[:5]}")

        # 检测可用节点
        print("\n正在检测节点可用性（可能需要一些时间）...")
        available = clash.get_available_nodes(force_refresh=True)
        print(f"可用节点数: {len(available)}")

        # 自动分配节点
        print("\n自动为账号分配节点...")
        clash.auto_assign_nodes()

        # 打印绑定关系
        print("\n账号-节点绑定:")
        for key, node in clash._account_node_map.items():
            print(f"  {key} -> {node}")
    else:
        print("\n[警告] Clash不可用，请检查:")
        print("  1. Clash是否已启动")
        print("  2. 配置文件中是否开启了 external-controller: 127.0.0.1:9090")
        print("  3. config/settings.yaml 中 clash.enabled 是否为 true")

    clash.print_status()
