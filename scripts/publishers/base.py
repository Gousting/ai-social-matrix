"""
基础发布器类 (base.py)

所有平台发布器的基类，提供：
  - Playwright浏览器启动/关闭（持久化Profile，复用登录态）
  - 登录状态检查
  - 截图保存
  - 发布结果统一返回格式
  - 错误处理和重试机制

子类需要实现：
  - publish(draft) -> dict  执行实际发布操作
"""
import os
import sys
import time
from datetime import datetime
from abc import ABC, abstractmethod
from typing import Dict, Optional, List

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from scripts.utils.config_loader import config
from scripts.utils.logger import logger


class PublishResult:
    """发布结果"""

    def __init__(self, success: bool, platform: str, account: str,
                 post_url: str = "", error: str = "", screenshot: str = ""):
        self.success = success
        self.platform = platform
        self.account = account
        self.post_url = post_url
        self.error = error
        self.screenshot = screenshot
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "platform": self.platform,
            "account": self.account,
            "post_url": self.post_url,
            "error": self.error,
            "screenshot": self.screenshot,
            "timestamp": self.timestamp
        }

    def __repr__(self):
        status = "✅成功" if self.success else "❌失败"
        return f"[{self.platform}/{self.account}] {status} {self.post_url or self.error}"


class BasePublisher(ABC):
    """基础发布器抽象类"""

    # 子类需要设置平台名称
    PLATFORM = ""
    PLATFORM_NAME = ""

    def __init__(self, account_config: Dict, headless: bool = True):
        """
        初始化发布器

        Args:
            account_config: 账号配置字典（来自accounts.yaml）
            headless: 是否无头模式
        """
        self.account = account_config
        self.platform = account_config.get("platform", self.PLATFORM)
        self.account_name = account_config.get("name", "")
        self.display_name = account_config.get("display_name", "")
        self.headless = headless

        # 路径
        self.user_data_dir = os.path.join(PROJECT_ROOT, account_config.get("user_data_dir", ""))
        self.cookie_path = os.path.join(PROJECT_ROOT, account_config.get("cookie_path", ""))
        self.screenshot_dir = os.path.join(PROJECT_ROOT, "logs", "screenshots", self.platform)

        # 浏览器对象
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

        # 确保目录存在
        os.makedirs(self.user_data_dir, exist_ok=True)
        os.makedirs(self.screenshot_dir, exist_ok=True)

    def start(self):
        """启动浏览器"""
        from playwright.sync_api import sync_playwright

        logger.info(f"[{self.platform}/{self.account_name}] 启动浏览器...")
        self._playwright = sync_playwright().start()

        # 使用持久化上下文（复用登录态）
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=self.user_data_dir,
            headless=self.headless,
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ]
        )

        # 隐藏webdriver特征
        self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = {runtime: {}};
        """)

        self._page = self._context.new_page()
        logger.info(f"[{self.platform}/{self.account_name}] 浏览器启动成功")

    def close(self):
        """关闭浏览器"""
        try:
            if self._page:
                self._page.close()
            if self._context:
                self._context.close()
            if self._playwright:
                self._playwright.stop()
            logger.info(f"[{self.platform}/{self.account_name}] 浏览器已关闭")
        except Exception as e:
            logger.error(f"[{self.platform}/{self.account_name}] 关闭浏览器异常: {e}")
        finally:
            self._page = None
            self._context = None
            self._playwright = None

    def screenshot(self, name: str = "") -> str:
        """
        截图保存

        Returns:
            截图文件路径
        """
        if not self._page:
            return ""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.account_name}_{name or 'screenshot'}_{timestamp}.png"
        filepath = os.path.join(self.screenshot_dir, filename)
        try:
            self._page.screenshot(path=filepath, full_page=True)
            logger.info(f"[{self.platform}/{self.account_name}] 截图已保存: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"[{self.platform}/{self.account_name}] 截图失败: {e}")
            return ""

    def safe_goto(self, url: str, timeout: int = 30000, retries: int = 3) -> bool:
        """
        安全导航（带重试）

        Returns:
            是否成功
        """
        for attempt in range(retries):
            try:
                self._page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                self._page.wait_for_timeout(2000)
                return True
            except Exception as e:
                logger.warning(f"[{self.platform}/{self.account_name}] 导航失败(尝试{attempt+1}/{retries}): {e}")
                if attempt < retries - 1:
                    self._page.wait_for_timeout(3000)
        return False

    def wait_for_selector(self, selector: str, timeout: int = 10000) -> bool:
        """等待元素出现"""
        try:
            self._page.wait_for_selector(selector, timeout=timeout)
            return True
        except Exception:
            return False

    def is_logged_in(self) -> bool:
        """
        检查是否已登录（子类需要实现）
        默认返回True，由子类覆盖
        """
        return True

    def check_login(self) -> bool:
        """检查登录状态，未登录则提示"""
        if not self.is_logged_in():
            logger.error(f"[{self.platform}/{self.account_name}] 未登录，请先运行登录脚本绑定账号")
            return False
        return True

    @abstractmethod
    def publish(self, draft: Dict) -> PublishResult:
        """
        执行发布操作（子类必须实现）

        Args:
            draft: 草稿字典（包含title, content, tags, images等）

        Returns:
            PublishResult 发布结果
        """
        pass

    def publish_with_retry(self, draft: Dict, max_retries: int = 3) -> PublishResult:
        """
        带重试的发布

        Args:
            draft: 草稿字典
            max_retries: 最大重试次数

        Returns:
            PublishResult 发布结果
        """
        last_error = ""
        for attempt in range(max_retries):
            try:
                logger.info(f"[{self.platform}/{self.account_name}] 发布尝试 {attempt+1}/{max_retries}")
                result = self.publish(draft)
                if result.success:
                    return result
                last_error = result.error
                logger.warning(f"[{self.platform}/{self.account_name}] 发布失败: {last_error}")
            except Exception as e:
                last_error = str(e)
                logger.error(f"[{self.platform}/{self.account_name}] 发布异常: {e}")

            if attempt < max_retries - 1:
                logger.info(f"[{self.platform}/{self.account_name}] 5秒后重试...")
                time.sleep(5)

        return PublishResult(
            success=False,
            platform=self.platform,
            account=self.account_name,
            error=last_error
        )

    def __enter__(self):
        """上下文管理器入口"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()
        return False
