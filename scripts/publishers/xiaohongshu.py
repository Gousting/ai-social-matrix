"""
小红书发布器 (xiaohongshu.py)

基于Playwright的小红书图文笔记自动发布器。
发布流程：
  1. 打开创作者中心
  2. 检查登录状态
  3. 上传图片
  4. 填写标题、正文、标签
  5. 点击发布
  6. 检查发布结果

注意：小红书页面结构可能变化，选择器需要根据实际页面调整。
"""
import os
import sys
import time
from typing import Dict, List, Optional

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from scripts.publishers.base import BasePublisher, PublishResult
from scripts.utils.logger import logger


class XiaohongshuPublisher(BasePublisher):
    """小红书图文笔记发布器"""

    PLATFORM = "xiaohongshu"
    PLATFORM_NAME = "小红书"

    # 创作者中心URL
    CREATOR_URL = "https://creator.xiaohongshu.com/"
    PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish"

    def is_logged_in(self) -> bool:
        """检查是否已登录"""
        try:
            self.safe_goto(self.CREATOR_URL, timeout=15000)
            # 检查是否有登录按钮（未登录时会显示登录按钮）
            login_selectors = [
                "text=登录",
                ".login-btn",
                "button:has-text('登录')",
            ]
            for selector in login_selectors:
                try:
                    if self._page.locator(selector).count() > 0:
                        # 检查是否可见
                        if self._page.locator(selector).first.is_visible(timeout=2000):
                            return False
                except Exception:
                    continue
            # 检查是否有用户头像/昵称（已登录标志）
            user_selectors = [
                ".user-info",
                ".avatar",
                "img.avatar",
                "text=创作中心",
            ]
            for selector in user_selectors:
                try:
                    if self._page.locator(selector).count() > 0:
                        return True
                except Exception:
                    continue
            # 如果URL没有跳转到登录页，认为已登录
            current_url = self._page.url
            if "login" not in current_url.lower():
                return True
            return False
        except Exception as e:
            logger.warning(f"[{self.platform}] 登录状态检查异常: {e}")
            return False

    def _upload_images(self, image_paths: List[str]) -> bool:
        """
        上传图片

        Args:
            image_paths: 图片路径列表

        Returns:
            是否上传成功
        """
        if not image_paths:
            logger.warning(f"[{self.platform}] 没有图片需要上传")
            return False

        # 过滤存在的图片
        valid_images = [p for p in image_paths if os.path.exists(p)]
        if not valid_images:
            logger.error(f"[{self.platform}] 所有图片路径都不存在")
            return False

        logger.info(f"[{self.platform}] 上传{len(valid_images)}张图片...")

        try:
            # 查找文件上传输入框
            upload_selectors = [
                "input[type='file']",
                "input[type=file]",
                ".upload-input input[type='file']",
            ]

            file_input = None
            for selector in upload_selectors:
                try:
                    locator = self._page.locator(selector)
                    if locator.count() > 0:
                        file_input = locator.first
                        break
                except Exception:
                    continue

            if not file_input:
                # 尝试通过拖拽区域上传
                logger.info(f"[{self.platform}] 未找到文件输入框，尝试拖拽上传")
                drop_zone = self._page.locator(".upload-wrapper, .upload-area, [class*='upload']").first
                if drop_zone.count() > 0:
                    # 设置文件输入框的值（隐藏的input）
                    self._page.evaluate("""() => {
                        const input = document.querySelector('input[type=file]');
                        if (input) {
                            input.style.display = 'block';
                            input.style.opacity = '1';
                        }
                    }""")
                    time.sleep(1)
                    file_input = self._page.locator("input[type='file']").first

            if file_input:
                file_input.set_input_files(valid_images)
                # 等待上传完成
                logger.info(f"[{self.platform}] 等待图片上传完成...")
                self._page.wait_for_timeout(5000)

                # 检查是否上传成功（图片缩略图出现）
                preview_selectors = [
                    ".image-item",
                    ".upload-preview img",
                    "[class*='preview'] img",
                    "img[class*='image']",
                ]
                for selector in preview_selectors:
                    try:
                        count = self._page.locator(selector).count()
                        if count >= len(valid_images):
                            logger.info(f"[{self.platform}] 图片上传成功，共{count}张")
                            return True
                    except Exception:
                        continue

                # 即使没找到预览，也认为上传可能成功（选择器可能变化）
                logger.info(f"[{self.platform}] 图片上传完成（未检测到预览，继续下一步）")
                return True
            else:
                logger.error(f"[{self.platform}] 未找到文件上传控件")
                self.screenshot("upload_error")
                return False

        except Exception as e:
            logger.error(f"[{self.platform}] 图片上传异常: {e}")
            self.screenshot("upload_exception")
            return False

    def _fill_title(self, title: str) -> bool:
        """填写标题"""
        try:
            title_selectors = [
                "input[placeholder*='标题']",
                "input[placeholder*='title']",
                ".title-input input",
                "input[class*='title']",
                "#title",
            ]

            for selector in title_selectors:
                try:
                    locator = self._page.locator(selector)
                    if locator.count() > 0 and locator.first.is_visible(timeout=2000):
                        locator.first.fill(title)
                        logger.info(f"[{self.platform}] 标题填写完成: {title[:20]}...")
                        return True
                except Exception:
                    continue

            # 尝试通过内容可编辑div填写
            content_selectors = [
                "[contenteditable='true']",
                ".editor-content",
                "[class*='editor']",
            ]
            for selector in content_selectors:
                try:
                    locator = self._page.locator(selector)
                    if locator.count() > 0:
                        # 第一个可编辑区域可能是标题
                        locator.first.click()
                        locator.first.fill(title)
                        logger.info(f"[{self.platform}] 标题（可编辑区域）填写完成")
                        return True
                except Exception:
                    continue

            logger.warning(f"[{self.platform}] 未找到标题输入框")
            return False
        except Exception as e:
            logger.error(f"[{self.platform}] 标题填写异常: {e}")
            return False

    def _fill_content(self, content: str) -> bool:
        """填写正文"""
        try:
            # 小红书正文通常是contenteditable的div
            content_selectors = [
                ".editor-content",
                "[class*='content-editor']",
                "div[contenteditable='true']",
                "[class*='ql-editor']",
                ".ProseMirror",
            ]

            for selector in content_selectors:
                try:
                    locator = self._page.locator(selector)
                    count = locator.count()
                    if count > 0:
                        # 正文通常是第二个可编辑区域（第一个是标题）
                        target = locator.nth(min(1, count - 1)) if count > 1 else locator.first
                        target.click()
                        # 清空原有内容
                        target.press("Control+A")
                        target.press("Delete")
                        # 输入内容（按行输入，保留换行）
                        lines = content.split("\n")
                        for i, line in enumerate(lines):
                            target.type(line)
                            if i < len(lines) - 1:
                                target.press("Enter")
                        logger.info(f"[{self.platform}] 正文填写完成，共{len(content)}字")
                        return True
                except Exception as e:
                    logger.debug(f"[{self.platform}] 选择器{selector}失败: {e}")
                    continue

            logger.warning(f"[{self.platform}] 未找到正文编辑区域")
            self.screenshot("content_error")
            return False
        except Exception as e:
            logger.error(f"[{self.platform}] 正文填写异常: {e}")
            return False

    def _fill_tags(self, tags: List[str]) -> bool:
        """添加标签"""
        if not tags:
            return True

        try:
            # 小红书标签通常在正文末尾输入#号触发
            tag_input_selectors = [
                ".tag-input input",
                "input[placeholder*='话题']",
                "input[placeholder*='标签']",
                "[class*='tag'] input",
            ]

            # 尝试找到标签输入框
            tag_input = None
            for selector in tag_input_selectors:
                try:
                    locator = self._page.locator(selector)
                    if locator.count() > 0 and locator.first.is_visible(timeout=2000):
                        tag_input = locator.first
                        break
                except Exception:
                    continue

            if tag_input:
                for tag in tags[:5]:  # 最多5个标签
                    tag_clean = tag.lstrip("#").strip()
                    tag_input.fill(tag_clean)
                    time.sleep(1)
                    # 选择第一个建议
                    suggestion_selectors = [
                        ".tag-suggestion-item",
                        "[class*='suggestion'] li",
                        ".search-result-item",
                    ]
                    for s_selector in suggestion_selectors:
                        try:
                            suggestions = self._page.locator(s_selector)
                            if suggestions.count() > 0:
                                suggestions.first.click()
                                break
                        except Exception:
                            continue
                    time.sleep(1)
                logger.info(f"[{self.platform}] 标签添加完成: {tags}")
                return True
            else:
                # 如果没有独立标签输入框，在正文末尾添加#标签
                logger.info(f"[{self.platform}] 未找到独立标签输入框，在正文末尾添加标签")
                tag_text = " " + " ".join(tags[:5])
                # 在正文末尾追加
                content_selectors = [
                    ".editor-content",
                    "div[contenteditable='true']",
                ]
                for selector in content_selectors:
                    try:
                        locator = self._page.locator(selector)
                        if locator.count() > 0:
                            target = locator.nth(min(1, locator.count() - 1))
                            target.click()
                            target.press("Control+End")
                            target.type(tag_text)
                            return True
                    except Exception:
                        continue
                return False

        except Exception as e:
            logger.error(f"[{self.platform}] 标签添加异常: {e}")
            return False

    def _click_publish(self) -> bool:
        """点击发布按钮"""
        try:
            publish_selectors = [
                "button:has-text('发布')",
                ".publish-btn",
                "button.submit",
                "button[class*='publish']",
                "button:has-text('立即发布')",
                "button:has-text('发布笔记')",
            ]

            for selector in publish_selectors:
                try:
                    locator = self._page.locator(selector)
                    if locator.count() > 0 and locator.first.is_visible(timeout=2000):
                        # 检查按钮是否可点击（不是disabled状态）
                        if locator.first.is_enabled():
                            locator.first.click()
                            logger.info(f"[{self.platform}] 点击发布按钮")
                            return True
                        else:
                            logger.warning(f"[{self.platform}] 发布按钮不可点击（可能内容未填写完整）")
                except Exception:
                    continue

            logger.error(f"[{self.platform}] 未找到发布按钮")
            self.screenshot("publish_button_error")
            return False
        except Exception as e:
            logger.error(f"[{self.platform}] 点击发布异常: {e}")
            return False

    def _check_publish_result(self, timeout: int = 15000) -> PublishResult:
        """检查发布结果"""
        try:
            # 等待发布结果页面
            self._page.wait_for_timeout(3000)

            # 检查是否有成功提示
            success_selectors = [
                "text=发布成功",
                "text=笔记发布成功",
                ".publish-success",
                "[class*='success']",
                "text=已发布",
            ]

            for selector in success_selectors:
                try:
                    if self._page.locator(selector).count() > 0:
                        if self._page.locator(selector).first.is_visible(timeout=2000):
                            screenshot = self.screenshot("publish_success")
                            # 获取发布后的链接
                            post_url = self._page.url
                            logger.info(f"[{self.platform}] 发布成功!")
                            return PublishResult(
                                success=True,
                                platform=self.platform,
                                account=self.account_name,
                                post_url=post_url,
                                screenshot=screenshot
                            )
                except Exception:
                    continue

            # 检查是否有错误提示
            error_selectors = [
                "text=发布失败",
                "text=内容包含违规",
                "text=网络错误",
                ".error-message",
                "[class*='error']",
            ]

            for selector in error_selectors:
                try:
                    if self._page.locator(selector).count() > 0:
                        if self._page.locator(selector).first.is_visible(timeout=2000):
                            error_text = self._page.locator(selector).first.inner_text()
                            screenshot = self.screenshot("publish_error")
                            return PublishResult(
                                success=False,
                                platform=self.platform,
                                account=self.account_name,
                                error=error_text,
                                screenshot=screenshot
                            )
                except Exception:
                    continue

            # 如果没有明确的成功/失败提示，检查URL是否变化
            current_url = self._page.url
            if "publish" not in current_url:
                # 离开发布页面，可能发布成功
                screenshot = self.screenshot("publish_maybe_success")
                return PublishResult(
                    success=True,
                    platform=self.platform,
                    account=self.account_name,
                    post_url=current_url,
                    screenshot=screenshot
                )

            # 仍在发布页面，可能需要确认
            screenshot = self.screenshot("publish_unknown")
            return PublishResult(
                success=False,
                platform=self.platform,
                account=self.account_name,
                error="发布结果未知，仍在发布页面",
                screenshot=screenshot
            )

        except Exception as e:
            return PublishResult(
                success=False,
                platform=self.platform,
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

        logger.info(f"[{self.platform}/{self.account_name}] 开始发布: {title[:30]}...")

        # 检查登录状态
        if not self.check_login():
            return PublishResult(
                success=False,
                platform=self.platform,
                account=self.account_name,
                error="未登录"
            )

        # 导航到发布页面
        if not self.safe_goto(self.PUBLISH_URL, timeout=20000):
            return PublishResult(
                success=False,
                platform=self.platform,
                account=self.account_name,
                error="无法打开发布页面"
            )

        self._page.wait_for_timeout(3000)

        # 上传图片
        if images:
            if not self._upload_images(images):
                return PublishResult(
                    success=False,
                    platform=self.platform,
                    account=self.account_name,
                    error="图片上传失败"
                )
        else:
            logger.warning(f"[{self.platform}] 草稿没有图片，小红书图文笔记需要至少1张图片")

        # 填写标题
        if title:
            self._fill_title(title)

        # 填写正文
        if content:
            self._fill_content(content)

        # 添加标签
        if tags:
            self._fill_tags(tags)

        # 截图（发布前）
        self.screenshot("before_publish")

        # 点击发布
        if not self._click_publish():
            return PublishResult(
                success=False,
                platform=self.platform,
                account=self.account_name,
                error="未找到或无法点击发布按钮"
            )

        # 检查发布结果
        result = self._check_publish_result()
        return result
