"""
小红书发布器 - DrissionPage版本 (xiaohongshu_drission.py)

基于DrissionPage的小红书图文笔记自动发布器。
DrissionPage基于真实浏览器，可绕过小红书的反自动化检测。

发布流程：
  1. 打开创作者中心（持久化Profile，保留登录状态）
  2. 检查登录状态
  3. 打开发布页面
  4. 上传图片
  5. 填写标题、正文、标签
  6. 点击发布
  7. 检查发布结果

注意：小红书页面结构可能变化，选择器需要根据实际页面调整。
"""
import os
import sys
import time
from typing import Dict, List, Optional
from dataclasses import dataclass

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from scripts.utils.logger import logger


@dataclass
class PublishResult:
    """发布结果"""
    success: bool
    platform: str = "xiaohongshu"
    account: str = ""
    post_url: str = ""
    error: str = ""
    screenshot: str = ""


class XiaohongshuDrissionPublisher:
    """小红书图文笔记发布器（DrissionPage版本）"""

    PLATFORM = "xiaohongshu"
    PLATFORM_NAME = "小红书"

    # 创作者中心URL
    CREATOR_URL = "https://creator.xiaohongshu.com/"
    PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish"

    def __init__(self, account_config: Dict, headless: bool = False):
        """
        初始化发布器

        Args:
            account_config: 账号配置字典
            headless: 是否无头模式（建议False，方便调试）
        """
        self.account_config = account_config
        self.account_name = account_config.get("name", "unknown")
        self.display_name = account_config.get("display_name", "")
        self.headless = headless

        # Profile目录（持久化登录状态）
        user_data_dir = account_config.get("user_data_dir", "./profiles/xhs/default")
        if not os.path.isabs(user_data_dir):
            user_data_dir = os.path.join(PROJECT_ROOT, user_data_dir)
        self.user_data_dir = user_data_dir
        os.makedirs(self.user_data_dir, exist_ok=True)

        self._page = None
        self._browser = None

    def __enter__(self):
        """上下文管理器入口"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.quit()

    def start(self):
        """启动浏览器"""
        from DrissionPage import ChromiumPage, ChromiumOptions

        logger.info(f"[{self.PLATFORM}/{self.account_name}] 启动DrissionPage浏览器...")

        co = ChromiumOptions()
        co.set_argument('--disable-blink-features=AutomationControlled')
        co.set_argument('--no-sandbox')
        if self.headless:
            co.set_argument('--headless')

        # 设置用户数据目录（持久化登录）
        co.set_user_data_path(self.user_data_dir)

        # 设置User-Agent
        co.set_user_agent(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        )

        self._page = ChromiumPage(co)
        logger.info(f"[{self.PLATFORM}/{self.account_name}] 浏览器启动成功")

    def quit(self):
        """关闭浏览器"""
        if self._page:
            try:
                self._page.quit()
                logger.info(f"[{self.PLATFORM}/{self.account_name}] 浏览器已关闭")
            except Exception as e:
                logger.warning(f"[{self.PLATFORM}/{self.account_name}] 关闭浏览器异常: {e}")
            self._page = None

    def screenshot(self, name: str = "screenshot") -> str:
        """截图保存"""
        try:
            screenshot_dir = os.path.join(PROJECT_ROOT, "logs", "screenshots")
            os.makedirs(screenshot_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(screenshot_dir, f"{self.PLATFORM}_{self.account_name}_{name}_{timestamp}.png")
            self._page.get_screenshot(path=filepath)
            logger.info(f"[{self.PLATFORM}] 截图已保存: {filepath}")
            return filepath
        except Exception as e:
            logger.warning(f"[{self.PLATFORM}] 截图失败: {e}")
            return ""

    def is_logged_in(self) -> bool:
        """检查是否已登录"""
        try:
            self._page.get(self.CREATOR_URL, timeout=20)
            time.sleep(3)

            # 检查是否有登录按钮
            try:
                login_btn = self._page.ele('text:登录', timeout=2)
                if login_btn and login_btn.states.is_displayed:
                    logger.info(f"[{self.PLATFORM}] 检测到登录按钮，未登录")
                    return False
            except Exception:
                pass

            # 检查URL是否包含login
            current_url = self._page.url
            if 'login' in current_url.lower() or 'signin' in current_url.lower():
                logger.info(f"[{self.PLATFORM}] URL包含login，未登录")
                return False

            # 检查页面标题
            title = self._page.title
            if '登录' in title or 'login' in title.lower():
                logger.info(f"[{self.PLATFORM}] 标题包含登录，未登录")
                return False

            logger.info(f"[{self.PLATFORM}] 已登录")
            return True

        except Exception as e:
            logger.warning(f"[{self.PLATFORM}] 登录状态检查异常: {e}")
            return False

    def _upload_images(self, image_paths: List[str]) -> bool:
        """上传图片"""
        if not image_paths:
            logger.warning(f"[{self.PLATFORM}] 没有图片需要上传")
            return False

        # 过滤存在的图片
        valid_images = [p for p in image_paths if os.path.exists(p)]
        if not valid_images:
            logger.error(f"[{self.PLATFORM}] 所有图片路径都不存在")
            return False

        logger.info(f"[{self.PLATFORM}] 上传{len(valid_images)}张图片...")

        try:
            # 先点击"上传图文"标签
            try:
                tab = self._page.ele('text:上传图文', timeout=3)
                if tab:
                    tab.click()
                    time.sleep(3)
                    logger.info(f"[{self.PLATFORM}] 已切换到上传图文标签")
            except Exception:
                pass

            # DrissionPage上传文件：找到file input然后设置值
            try:
                file_input = self._page.ele('css:input[type="file"]', timeout=5)
                if file_input:
                    # 使input可见
                    self._page.run_js('''
                        const input = document.querySelector('input[type="file"]');
                        if (input) {
                            input.style.display = 'block';
                            input.style.opacity = '1';
                            input.style.visibility = 'visible';
                        }
                    ''')
                    time.sleep(1)
                    # 上传第一张图片
                    file_input.input(valid_images[0])
                    logger.info(f"[{self.PLATFORM}] 第1张图片已选择，等待上传...")
                    time.sleep(8)

                    # 如果有多张图片，继续上传
                    for i, img in enumerate(valid_images[1:], 2):
                        try:
                            file_input = self._page.ele('css:input[type="file"]', timeout=3)
                            if file_input:
                                file_input.input(img)
                                logger.info(f"[{self.PLATFORM}] 第{i}张图片已选择")
                                time.sleep(5)
                        except Exception:
                            break

                    logger.info(f"[{self.PLATFORM}] 图片上传完成")
                    return True
            except Exception as e:
                logger.warning(f"[{self.PLATFORM}] file input方式失败: {e}")

            logger.error(f"[{self.PLATFORM}] 未找到文件上传控件")
            self.screenshot("upload_error")
            return False

        except Exception as e:
            logger.error(f"[{self.PLATFORM}] 图片上传异常: {e}")
            self.screenshot("upload_exception")
            return False

    def _fill_title(self, title: str) -> bool:
        """填写标题"""
        try:
            # 经过测试：小红书标题输入框 placeholder="填写标题会有更多赞哦"
            selectors = [
                'css:input[placeholder*="填写标题"]',
                'css:input[placeholder*="标题"]',
                'css:input[placeholder*="title"]',
            ]

            for selector in selectors:
                try:
                    ele = self._page.ele(selector, timeout=3)
                    if ele and ele.states.is_displayed:
                        ele.click()
                        ele.clear()
                        ele.input(title)
                        logger.info(f"[{self.PLATFORM}] 标题填写完成: {title[:20]}...")
                        return True
                except Exception:
                    continue

            # 备用：尝试contenteditable
            try:
                editables = self._page.eles('css:[contenteditable="true"]')
                if editables and len(editables) > 0:
                    title_ele = editables[0]
                    title_ele.click()
                    title_ele.clear()
                    title_ele.input(title)
                    logger.info(f"[{self.PLATFORM}] 标题（contenteditable）填写完成")
                    return True
            except Exception as e:
                logger.warning(f"[{self.PLATFORM}] contenteditable标题失败: {e}")

            logger.warning(f"[{self.PLATFORM}] 未找到标题输入框")
            self.screenshot("title_error")
            return False

        except Exception as e:
            logger.error(f"[{self.PLATFORM}] 标题填写异常: {e}")
            return False

    def _fill_content(self, content: str) -> bool:
        """填写正文"""
        try:
            # 经过测试：小红书正文是第二个contenteditable元素
            # 第一个可能是标题（但标题通常是input），第二个是正文

            # 先尝试textarea
            try:
                textarea = self._page.ele('css:textarea[placeholder*="输入正文"]', timeout=3)
                if textarea:
                    textarea.click()
                    textarea.clear()
                    textarea.input(content)
                    logger.info(f"[{self.PLATFORM}] 正文（textarea）填写完成，共{len(content)}字")
                    return True
            except Exception:
                pass

            # 尝试contenteditable
            try:
                editables = self._page.eles('css:[contenteditable="true"]')
                if editables and len(editables) > 0:
                    # 正文通常是第二个可编辑区域（第一个是标题）
                    target = editables[1] if len(editables) > 1 else editables[0]
                    target.click()
                    time.sleep(0.5)
                    # 清空原有内容
                    target.run_js('this.innerHTML = "";')
                    time.sleep(0.5)
                    # 逐行输入，保留换行
                    lines = content.split("\n")
                    for i, line in enumerate(lines):
                        target.input(line)
                        if i < len(lines) - 1:
                            target.input('\n')
                            time.sleep(0.1)
                    logger.info(f"[{self.PLATFORM}] 正文（contenteditable）填写完成，共{len(content)}字")
                    return True
            except Exception as e:
                logger.warning(f"[{self.PLATFORM}] contenteditable正文失败: {e}")

            logger.warning(f"[{self.PLATFORM}] 未找到正文编辑区域")
            self.screenshot("content_error")
            return False

        except Exception as e:
            logger.error(f"[{self.PLATFORM}] 正文填写异常: {e}")
            return False

    def _fill_tags(self, tags: List[str]) -> bool:
        """添加标签"""
        if not tags:
            return True

        try:
            # 小红书标签通常在正文末尾输入#号触发，或有独立标签输入框
            # 简化处理：在正文末尾添加#标签
            tag_text = " " + " ".join([f"#{t.lstrip('#')}" for t in tags[:5]])

            selectors = [
                'css:.editor-content',
                'css:div[contenteditable="true"]',
            ]

            for selector in selectors:
                try:
                    eles = self._page.eles(selector)
                    if eles and len(eles) > 0:
                        target = eles[1] if len(eles) > 1 else eles[0]
                        target.click()
                        # 移动到末尾
                        target.run_js('this.focus(); document.execCommand("selectAll", false, null); document.execCommand("insertText", false, arguments[0] + arguments[1]);', tag_text)
                        logger.info(f"[{self.PLATFORM}] 标签添加完成: {tags[:5]}")
                        return True
                except Exception:
                    continue

            logger.info(f"[{self.PLATFORM}] 标签添加跳过（未找到编辑区域）")
            return True

        except Exception as e:
            logger.error(f"[{self.PLATFORM}] 标签添加异常: {e}")
            return False

    def _enable_original_declaration(self) -> bool:
        """打开原创声明开关"""
        try:
            # 查找原创声明开关
            # 小红书的原创声明是一个switch开关
            selectors = [
                'css:.switch',
                'css:[class*="switch"]',
                'css:[role="switch"]',
                'css:.ant-switch',
            ]

            for selector in selectors:
                try:
                    switches = self._page.eles(selector)
                    for sw in switches:
                        # 检查开关附近是否有"原创声明"文字
                        try:
                            parent = sw.parent()
                            if parent and '原创' in parent.text:
                                # 检查开关状态
                                if 'checked' in (sw.attr('class') or '') or sw.attr('aria-checked') == 'true':
                                    logger.info(f"[{self.PLATFORM}] 原创声明已开启")
                                else:
                                    sw.click()
                                    time.sleep(1)
                                    logger.info(f"[{self.PLATFORM}] 已开启原创声明")
                                return True
                        except Exception:
                            continue
                except Exception:
                    continue

            # 备用：直接查找"原创声明"文字附近的开关
            try:
                original_text = self._page.ele('text:原创声明', timeout=3)
                if original_text:
                    # 查找父元素中的开关
                    parent = original_text.parent()
                    if parent:
                        switch = parent.ele('css:.switch, [class*="switch"], [role="switch"]', timeout=2)
                        if switch:
                            switch.click()
                            time.sleep(1)
                            logger.info(f"[{self.PLATFORM}] 已开启原创声明（备用方式）")
                            return True
            except Exception as e:
                logger.debug(f"[{self.PLATFORM}] 原创声明备用方式失败: {e}")

            logger.info(f"[{self.PLATFORM}] 未找到原创声明开关，跳过")
            return False

        except Exception as e:
            logger.warning(f"[{self.PLATFORM}] 原创声明设置异常: {e}")
            return False

    def _click_publish(self) -> bool:
        """点击发布按钮"""
        try:
            selectors = [
                'text:发布',
                'css:button[class*="publish"]',
                'css:.publish-btn',
                'css:button.submit',
                'text:立即发布',
                'text:发布笔记',
            ]

            for selector in selectors:
                try:
                    ele = self._page.ele(selector, timeout=3)
                    if ele and ele.states.is_displayed:
                        # 检查是否可点击
                        if not ele.states.is_disabled:
                            ele.click()
                            logger.info(f"[{self.PLATFORM}] 点击发布按钮")
                            time.sleep(3)
                            return True
                        else:
                            logger.warning(f"[{self.PLATFORM}] 发布按钮不可点击（可能内容未填写完整）")
                except Exception:
                    continue

            logger.error(f"[{self.PLATFORM}] 未找到发布按钮")
            self.screenshot("publish_button_error")
            return False

        except Exception as e:
            logger.error(f"[{self.PLATFORM}] 点击发布异常: {e}")
            return False

    def _check_publish_result(self, timeout: int = 15) -> PublishResult:
        """检查发布结果"""
        try:
            time.sleep(5)

            # 检查是否有成功提示
            success_texts = ['发布成功', '笔记发布成功', '已发布', '发布完成']
            for text in success_texts:
                try:
                    ele = self._page.ele(f'text:{text}', timeout=2)
                    if ele and ele.states.is_displayed:
                        screenshot = self.screenshot("publish_success")
                        post_url = self._page.url
                        logger.info(f"[{self.PLATFORM}] 发布成功!")
                        return PublishResult(
                            success=True,
                            platform=self.PLATFORM,
                            account=self.account_name,
                            post_url=post_url,
                            screenshot=screenshot
                        )
                except Exception:
                    continue

            # 检查是否有错误提示
            error_texts = ['发布失败', '内容包含违规', '网络错误', '发布失败']
            for text in error_texts:
                try:
                    ele = self._page.ele(f'text:{text}', timeout=2)
                    if ele and ele.states.is_displayed:
                        error_text = ele.text
                        screenshot = self.screenshot("publish_error")
                        return PublishResult(
                            success=False,
                            platform=self.PLATFORM,
                            account=self.account_name,
                            error=error_text,
                            screenshot=screenshot
                        )
                except Exception:
                    continue

            # 检查URL是否离开发布页面
            current_url = self._page.url
            if 'publish' not in current_url:
                screenshot = self.screenshot("publish_maybe_success")
                return PublishResult(
                    success=True,
                    platform=self.PLATFORM,
                    account=self.account_name,
                    post_url=current_url,
                    screenshot=screenshot
                )

            # 仍在发布页面
            screenshot = self.screenshot("publish_unknown")
            return PublishResult(
                success=False,
                platform=self.PLATFORM,
                account=self.account_name,
                error="发布结果未知，仍在发布页面",
                screenshot=screenshot
            )

        except Exception as e:
            return PublishResult(
                success=False,
                platform=self.PLATFORM,
                account=self.account_name,
                error=f"检查发布结果异常: {e}"
            )

    def publish(self, draft: Dict) -> PublishResult:
        """
        执行小红书图文笔记发布

        Args:
            draft: 草稿字典，包含：
                - title: 标题
                - content: 正文
                - tags: 标签列表
                - images: 图片路径列表

        Returns:
            PublishResult 发布结果
        """
        title = draft.get("title", "")
        content = draft.get("content", "")
        tags = draft.get("tags", [])
        images = draft.get("images", [])

        logger.info(f"[{self.PLATFORM}/{self.account_name}] 开始发布: {title[:30]}...")

        # 检查登录状态
        if not self.is_logged_in():
            return PublishResult(
                success=False,
                platform=self.PLATFORM,
                account=self.account_name,
                error="未登录"
            )

        # 导航到发布页面
        try:
            self._page.get(self.PUBLISH_URL, timeout=20)
            time.sleep(5)
        except Exception as e:
            logger.error(f"[{self.PLATFORM}] 无法打开发布页面: {e}")
            return PublishResult(
                success=False,
                platform=self.PLATFORM,
                account=self.account_name,
                error=f"无法打开发布页面: {e}"
            )

        # 上传图片
        if images:
            if not self._upload_images(images):
                return PublishResult(
                    success=False,
                    platform=self.PLATFORM,
                    account=self.account_name,
                    error="图片上传失败"
                )
        else:
            logger.warning(f"[{self.PLATFORM}] 草稿没有图片，小红书图文笔记需要至少1张图片")

        # 填写标题
        if title:
            self._fill_title(title)

        # 填写正文
        if content:
            self._fill_content(content)

        # 添加标签
        if tags:
            self._fill_tags(tags)

        # 打开原创声明
        self._enable_original_declaration()

        # 截图（发布前）
        self.screenshot("before_publish")

        # 点击发布
        if not self._click_publish():
            return PublishResult(
                success=False,
                platform=self.PLATFORM,
                account=self.account_name,
                error="未找到或无法点击发布按钮"
            )

        # 检查发布结果
        result = self._check_publish_result()
        return result
