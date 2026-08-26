"""
配置加载器
加载 api_keys.yaml / accounts.yaml / settings.yaml
提供统一的配置访问接口
"""
import os
import yaml
from typing import Dict, List, Any, Optional


# 项目根目录（scripts/utils/ 的上两级）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")


class ConfigLoader:
    """配置加载器（单例模式）"""

    _instance = None
    _api_keys: Dict = None
    _accounts: Dict = None
    _settings: Dict = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._api_keys is None:
            self._load_all()

    def _load_all(self):
        """加载所有配置文件"""
        self._api_keys = self._load_yaml(os.path.join(CONFIG_DIR, "api_keys.yaml"))
        self._accounts = self._load_yaml(os.path.join(CONFIG_DIR, "accounts.yaml"))
        self._settings = self._load_yaml(os.path.join(CONFIG_DIR, "settings.yaml"))

    @staticmethod
    def _load_yaml(filepath: str) -> Dict:
        """加载单个YAML文件"""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"配置文件不存在: {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def reload(self):
        """重新加载所有配置（修改配置文件后调用）"""
        self._load_all()

    # ---------- API Key配置 ----------
    @property
    def api_providers(self) -> List[Dict]:
        """获取所有启用的API服务商列表（按priority排序）"""
        providers = self._api_keys.get("providers", [])
        enabled = [p for p in providers if p.get("enabled", False)]
        return sorted(enabled, key=lambda x: x.get("priority", 99))

    @property
    def api_call_config(self) -> Dict:
        """获取API调用配置"""
        return self._api_keys.get("call_config", {
            "temperature": 0.7,
            "max_tokens": 4000,
            "retry_count": 3,
            "retry_delay": 2,
            "timeout": 60
        })

    # ---------- 账号配置 ----------
    @property
    def all_accounts(self) -> List[Dict]:
        """获取所有账号"""
        return self._accounts.get("accounts", [])

    @property
    def enabled_accounts(self) -> List[Dict]:
        """获取所有启用的账号"""
        return [a for a in self.all_accounts if a.get("enabled", False)]

    def get_accounts_by_platform(self, platform: str) -> List[Dict]:
        """按平台获取启用的账号"""
        return [a for a in self.enabled_accounts if a.get("platform") == platform]

    def get_account(self, platform: str, name: str) -> Optional[Dict]:
        """按平台和账号名获取账号配置"""
        for a in self.all_accounts:
            if a.get("platform") == platform and a.get("name") == name:
                return a
        return None

    @property
    def platforms(self) -> List[str]:
        """获取所有启用账号涉及的平台列表（去重）"""
        return list(set(a.get("platform") for a in self.enabled_accounts))

    # ---------- 系统设置 ----------
    @property
    def settings(self) -> Dict:
        """获取全部系统设置"""
        return self._settings

    @property
    def paths(self) -> Dict:
        """获取路径配置"""
        return self._settings.get("paths", {})

    @property
    def clash_config(self) -> Dict:
        """获取Clash配置"""
        return self._settings.get("clash", {})

    @property
    def schedule_config(self) -> Dict:
        """获取排期配置"""
        return self._settings.get("schedule", {})

    @property
    def topic_config(self) -> Dict:
        """获取选题采集配置"""
        return self._settings.get("topic_collection", {})

    @property
    def rewrite_config(self) -> Dict:
        """获取内容改写配置"""
        return self._settings.get("rewrite", {})

    @property
    def metrics_config(self) -> Dict:
        """获取数据采集配置"""
        return self._settings.get("metrics", {})

    @property
    def logging_config(self) -> Dict:
        """获取日志配置"""
        return self._settings.get("logging", {})

    def get_path(self, key: str) -> str:
        """获取指定路径（自动转为绝对路径）"""
        rel_path = self.paths.get(key, "")
        if not rel_path:
            return ""
        return os.path.join(PROJECT_ROOT, rel_path) if not os.path.isabs(rel_path) else rel_path


# 全局单例
config = ConfigLoader()


if __name__ == "__main__":
    # 测试配置加载
    print("=" * 50)
    print("配置加载测试")
    print("=" * 50)
    print(f"\n项目根目录: {PROJECT_ROOT}")
    print(f"\n启用的API服务商: {[p['name'] for p in config.api_providers]}")
    print(f"\n启用的账号数: {len(config.enabled_accounts)}")
    print(f"涉及平台: {config.platforms}")
    for platform in config.platforms:
        accounts = config.get_accounts_by_platform(platform)
        print(f"  {platform}: {len(accounts)}个 - {[a['name'] for a in accounts]}")
    print(f"\n排期配置: 每日{config.schedule_config.get('posts_per_day')}篇")
    print(f"Clash配置: {config.clash_config.get('external_controller')}")
    print("\n配置加载成功!")
