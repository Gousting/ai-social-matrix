#!/usr/bin/env python3
"""
动态爆款采集脚本 (00_dynamic_viral_collector.py)

功能：
  1. 用DrissionPage打开小红书搜索页，按关键词搜索
  2. 采集前N篇高赞帖子（标题、点赞数、收藏数、链接）
  3. 逐个打开帖子详情页，采集正文、标签
  4. 实时调用LLM拆解，生成爆款参考
  5. 24小时缓存机制，相同关键词不重复采集
  6. 可被AI改写脚本调用，注入动态参考

用法：
  # 采集指定关键词的爆款帖子
  python scripts/00_dynamic_viral_collector.py --keyword "Codex安装" --top 5

  # 采集并查看拆解结果
  python scripts/00_dynamic_viral_collector.py --keyword "AI工具" --top 3 --show

  # 清除缓存
  python scripts/00_dynamic_viral_collector.py --clear-cache

  # 查看缓存列表
  python scripts/00_dynamic_viral_collector.py --list-cache

  # 作为模块被调用
  from scripts.utils.dynamic_viral_collector import get_dynamic_reference
  reference = get_dynamic_reference("Codex安装", top_n=3)
"""
import sys
import os
import json
import time
import hashlib
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# 项目根目录（文件在 scripts/utils/ 下，需要往上三层）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from scripts.utils.config_loader import config
from scripts.utils.api_client import api_client
from scripts.utils.logger import logger


# 缓存目录
CACHE_DIR = os.path.join(PROJECT_ROOT, "data", "dynamic_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# 缓存有效期（24小时）
CACHE_TTL_HOURS = 24


def get_cache_key(keyword: str, top_n: int) -> str:
    """生成缓存键名"""
    raw = f"{keyword.lower().strip()}_{top_n}"
    return hashlib.md5(raw.encode('utf-8')).hexdigest()


def get_cache_path(keyword: str, top_n: int) -> str:
    """获取缓存文件路径"""
    cache_key = get_cache_key(keyword, top_n)
    return os.path.join(CACHE_DIR, f"{cache_key}.json")


def is_cache_valid(keyword: str, top_n: int) -> bool:
    """检查缓存是否有效（24小时内）"""
    cache_path = get_cache_path(keyword, top_n)
    if not os.path.exists(cache_path):
        return False

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        cached_time = datetime.fromisoformat(cache.get("cached_at", ""))
        return datetime.now() - cached_time < timedelta(hours=CACHE_TTL_HOURS)
    except Exception:
        return False


def load_cache(keyword: str, top_n: int) -> Optional[Dict]:
    """加载缓存"""
    cache_path = get_cache_path(keyword, top_n)
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"加载缓存失败: {e}")
        return None


def save_cache(keyword: str, top_n: int, data: Dict):
    """保存缓存"""
    cache_path = get_cache_path(keyword, top_n)
    data["cached_at"] = datetime.now().isoformat()
    data["keyword"] = keyword
    data["top_n"] = top_n
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"缓存已保存: {cache_path}")
    except Exception as e:
        logger.warning(f"保存缓存失败: {e}")


def search_xiaohongshu(keyword: str, top_n: int = 5) -> List[Dict]:
    """
    用DrissionPage搜索小红书，采集高赞帖子列表

    Args:
        keyword: 搜索关键词
        top_n: 采集前N篇

    Returns:
        帖子列表，每个包含title, likes, favorites, url
    """
    from DrissionPage import ChromiumPage, ChromiumOptions

    logger.info(f"开始搜索小红书: {keyword}")

    # 配置浏览器（复用已登录的Profile）
    co = ChromiumOptions()
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.set_argument('--no-sandbox')
    co.set_argument('--start-maximized')

    # 使用小红书账号的Profile
    xhs_account = None
    for acc in config.enabled_accounts:
        if acc.get("platform") == "xiaohongshu":
            xhs_account = acc
            break

    if xhs_account:
        user_data_dir = xhs_account.get("user_data_dir", "./profiles/xhs/default")
        if not os.path.isabs(user_data_dir):
            user_data_dir = os.path.join(PROJECT_ROOT, user_data_dir)
        co.set_user_data_path(user_data_dir)
        logger.info(f"使用Profile: {user_data_dir}")
    else:
        logger.warning("未找到小红书账号配置，使用临时Profile")

    page = ChromiumPage(co)

    try:
        # 构造搜索URL
        search_url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}&source=web_explore_feed"
        logger.info(f"访问搜索页: {search_url}")
        page.get(search_url, timeout=30)
        time.sleep(8)

        # 截图（调试用）
        screenshot_dir = os.path.join(PROJECT_ROOT, "logs", "screenshots", "dynamic_collect")
        os.makedirs(screenshot_dir, exist_ok=True)
        page.get_screenshot(path=os.path.join(screenshot_dir, f"search_{int(time.time())}.png"))

        # 滚动页面加载更多内容
        logger.info("滚动页面加载更多内容...")
        for i in range(3):
            page.scroll.down(500)
            time.sleep(2)

        # 采集帖子列表
        posts = []

        # 尝试多种选择器采集帖子卡片
        selectors = [
            'css:.note-item',
            'css:.feeds-page .note-item',
            'css:[class*="note-item"]',
            'css:a[href*="/explore/"]',
            'css:section.note-item',
        ]

        note_elements = []
        for selector in selectors:
            try:
                eles = page.eles(selector)
                if eles and len(eles) > 0:
                    note_elements = eles
                    logger.info(f"使用选择器 {selector} 找到 {len(eles)} 个帖子")
                    break
            except Exception:
                continue

        if not note_elements:
            logger.warning("未找到帖子元素，尝试备用采集方式")
            # 备用：采集所有包含explore链接的a标签
            try:
                links = page.eles('css:a[href*="/explore/"]')
                for link in links[:top_n * 2]:
                    try:
                        href = link.attr('href') or ''
                        if href and '/explore/' in href:
                            title = link.text[:50] if link.text else '无标题'
                            posts.append({
                                "title": title,
                                "url": href if href.startswith('http') else f"https://www.xiaohongshu.com{href}",
                                "likes": 0,
                                "favorites": 0
                            })
                    except Exception:
                        continue
            except Exception as e:
                logger.error(f"备用采集方式失败: {e}")

        # 解析帖子元素
        for ele in note_elements[:top_n * 2]:
            try:
                # 提取标题
                title = ''
                try:
                    title_ele = ele.ele('css:.title, [class*="title"], .footer .title', timeout=1)
                    if title_ele:
                        title = title_ele.text[:80]
                except Exception:
                    pass

                if not title:
                    title = ele.text[:50] if ele.text else '无标题'

                # 提取链接
                url = ''
                try:
                    link_ele = ele.ele('css:a', timeout=1)
                    if link_ele:
                        href = link_ele.attr('href') or ''
                        if href:
                            url = href if href.startswith('http') else f"https://www.xiaohongshu.com{href}"
                except Exception:
                    pass

                if not url:
                    try:
                        href = ele.attr('href') or ''
                        if href:
                            url = href if href.startswith('http') else f"https://www.xiaohongshu.com{href}"
                    except Exception:
                        pass

                # 提取点赞数
                likes = 0
                try:
                    like_ele = ele.ele('css:.like-count, [class*="like"], .count', timeout=1)
                    if like_ele:
                        like_text = like_ele.text.strip()
                        likes = parse_count(like_text)
                except Exception:
                    pass

                # 提取收藏数
                favorites = 0
                try:
                    fav_ele = ele.ele('css:.collect-count, [class*="collect"]', timeout=1)
                    if fav_ele:
                        fav_text = fav_ele.text.strip()
                        favorites = parse_count(fav_text)
                except Exception:
                    pass

                if title and url:
                    posts.append({
                        "title": title,
                        "url": url,
                        "likes": likes,
                        "favorites": favorites
                    })
            except Exception as e:
                logger.debug(f"解析帖子元素失败: {e}")
                continue

        # 去重
        seen_urls = set()
        unique_posts = []
        for p in posts:
            if p["url"] not in seen_urls:
                seen_urls.add(p["url"])
                unique_posts.append(p)

        # 按点赞数排序，取前N篇
        unique_posts.sort(key=lambda x: x.get("likes", 0), reverse=True)
        result = unique_posts[:top_n]

        logger.info(f"采集到 {len(result)} 篇高赞帖子")
        for i, p in enumerate(result, 1):
            logger.info(f"  [{i}] {p['title'][:40]}... (赞:{p['likes']} 藏:{p['favorites']})")

        return result

    except Exception as e:
        logger.error(f"搜索采集失败: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        try:
            page.quit()
        except Exception:
            pass


def parse_count(text: str) -> int:
    """解析点赞/收藏数（支持万、w等单位）"""
    if not text:
        return 0
    text = text.strip().lower()
    try:
        if '万' in text or 'w' in text:
            num = float(text.replace('万', '').replace('w', '').replace('+', ''))
            return int(num * 10000)
        elif 'k' in text:
            num = float(text.replace('k', '').replace('+', ''))
            return int(num * 1000)
        else:
            return int(text.replace('+', '').replace(',', ''))
    except Exception:
        return 0


def collect_post_detail(url: str) -> Optional[Dict]:
    """
    采集帖子详情页内容

    Args:
        url: 帖子URL

    Returns:
        帖子详情字典
    """
    from DrissionPage import ChromiumPage, ChromiumOptions

    logger.info(f"采集帖子详情: {url}")

    co = ChromiumOptions()
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.set_argument('--no-sandbox')

    # 使用小红书账号的Profile
    xhs_account = None
    for acc in config.enabled_accounts:
        if acc.get("platform") == "xiaohongshu":
            xhs_account = acc
            break

    if xhs_account:
        user_data_dir = xhs_account.get("user_data_dir", "./profiles/xhs/default")
        if not os.path.isabs(user_data_dir):
            user_data_dir = os.path.join(PROJECT_ROOT, user_data_dir)
        co.set_user_data_path(user_data_dir)

    page = ChromiumPage(co)

    try:
        page.get(url, timeout=30)
        time.sleep(6)

        # 提取标题
        title = ''
        try:
            title_ele = page.ele('css:#detail-title, .title, h1, [class*="title"]', timeout=3)
            if title_ele:
                title = title_ele.text.strip()
        except Exception:
            pass

        # 提取正文
        content = ''
        try:
            content_ele = page.ele('css:#detail-desc, .desc, [class*="desc"], .content', timeout=3)
            if content_ele:
                content = content_ele.text.strip()
        except Exception:
            pass

        # 如果没找到正文，尝试从页面文本中提取
        if not content:
            try:
                # 小红书详情页正文通常在特定的div中
                all_text = page.ele('css:.note-container, .detail-container, body').text
                if all_text:
                    # 简单提取：取标题后面的内容
                    if title and title in all_text:
                        content = all_text.split(title, 1)[1][:2000].strip()
                    else:
                        content = all_text[:2000]
            except Exception:
                pass

        # 提取标签
        tags = []
        try:
            tag_eles = page.eles('css:.tag, a[href*="/search_result?keyword="], [class*="tag"]')
            for tag_ele in tag_eles:
                tag_text = tag_ele.text.strip().lstrip('#')
                if tag_text and len(tag_text) < 20:
                    tags.append(tag_text)
        except Exception:
            pass

        # 从正文中提取标签
        if not tags and content:
            import re
            tags = re.findall(r'#(\w+)', content)
            tags = list(set(tags))[:10]

        # 提取点赞/收藏/评论数
        likes = 0
        favorites = 0
        comments = 0
        try:
            interact_eles = page.eles('css:.interact-container .count, [class*="like"] .count, [class*="collect"] .count')
            for i, ele in enumerate(interact_eles[:3]):
                count = parse_count(ele.text)
                if i == 0:
                    likes = count
                elif i == 1:
                    favorites = count
                elif i == 2:
                    comments = count
        except Exception:
            pass

        result = {
            "title": title or "无标题",
            "content": content or "（无法采集正文）",
            "tags": tags,
            "likes": likes,
            "favorites": favorites,
            "comments": comments,
            "url": url,
            "platform": "xiaohongshu",
            "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        logger.info(f"帖子详情采集完成: {result['title'][:30]} (赞:{likes} 藏:{favorites})")
        return result

    except Exception as e:
        logger.error(f"帖子详情采集失败: {e}")
        return None
    finally:
        try:
            page.quit()
        except Exception:
            pass


def analyze_posts(posts: List[Dict]) -> str:
    """
    批量拆解帖子，生成参考文本

    Args:
        posts: 帖子详情列表

    Returns:
        格式化的参考文本
    """
    if not posts:
        return ""

    logger.info(f"开始批量拆解 {len(posts)} 篇帖子")

    # 构建分析Prompt
    posts_text = ""
    for i, post in enumerate(posts, 1):
        posts_text += f"\n--- 帖子{i} ---\n"
        posts_text += f"标题: {post.get('title', '')}\n"
        posts_text += f"点赞: {post.get('likes', 0)}, 收藏: {post.get('favorites', 0)}, 评论: {post.get('comments', 0)}\n"
        posts_text += f"标签: {', '.join(post.get('tags', []))}\n"
        posts_text += f"正文:\n{post.get('content', '')[:1500]}\n"

    system_prompt = """你是一个资深社交媒体内容分析师，擅长从多篇高赞帖子中提炼共性规律。
请分析以下多篇高赞帖子，提炼它们的共同爆款要素，生成可复用的写作参考。

输出格式：
1. 共性标题公式（从多篇标题中提炼）
2. 共性开头钩子（前3行的共同特点）
3. 共性正文结构（分段逻辑、步骤数量）
4. 共性结尾CTA（互动引导方式）
5. 高频标签（出现次数最多的标签）
6. 爆款共性总结（为什么这些帖子能爆）
7. 可复用的写作模板（整合多篇的优点）"""

    user_prompt = f"请分析以下{len(posts)}篇高赞帖子，提炼共性爆款规律：\n{posts_text}\n\n请输出结构化的分析结果。"

    try:
        response, provider = api_client.chat(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=2500,
            temperature=0.3
        )
        logger.info(f"批量拆解完成，使用服务商: {provider}")
        return response
    except Exception as e:
        logger.error(f"批量拆解失败: {e}")
        return ""


def search_and_collect(keyword: str, top_n: int = 5) -> List[Dict]:
    """
    搜索并采集帖子详情（在同一个浏览器会话中完成）

    Args:
        keyword: 搜索关键词
        top_n: 采集前N篇

    Returns:
        帖子详情列表
    """
    from DrissionPage import ChromiumPage, ChromiumOptions

    logger.info(f"开始搜索并采集: {keyword}")

    co = ChromiumOptions()
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.set_argument('--no-sandbox')
    co.set_argument('--start-maximized')

    # 使用小红书账号的Profile
    xhs_account = None
    for acc in config.enabled_accounts:
        if acc.get("platform") == "xiaohongshu":
            xhs_account = acc
            break

    if xhs_account:
        user_data_dir = xhs_account.get("user_data_dir", "./profiles/xhs/default")
        if not os.path.isabs(user_data_dir):
            user_data_dir = os.path.join(PROJECT_ROOT, user_data_dir)
        co.set_user_data_path(user_data_dir)
        logger.info(f"使用Profile: {user_data_dir}")

    page = ChromiumPage(co)
    details = []

    try:
        # 构造搜索URL
        search_url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}&source=web_explore_feed"
        logger.info(f"访问搜索页: {search_url}")
        page.get(search_url, timeout=30)
        time.sleep(8)

        # 关闭登录弹窗（如果有）
        try:
            close_btn = page.ele('css:.close, [class*="close"], .icon-close', timeout=2)
            if close_btn:
                close_btn.click()
                time.sleep(2)
        except Exception:
            pass

        # 滚动页面加载更多内容
        logger.info("滚动页面加载更多内容...")
        for i in range(3):
            page.scroll.down(500)
            time.sleep(2)

        # 采集帖子列表
        note_elements = []
        try:
            note_elements = page.eles('css:.note-item')
            logger.info(f"找到 {len(note_elements)} 个帖子")
        except Exception as e:
            logger.error(f"采集帖子列表失败: {e}")
            return []

        if not note_elements:
            logger.warning("未找到帖子元素")
            return []

        # 逐个点击帖子，采集详情
        collected = 0
        max_attempts = top_n * 3  # 最大尝试次数
        attempt = 0

        while collected < top_n and attempt < max_attempts:
            attempt += 1

            try:
                # 每次重新获取帖子元素列表（避免元素失效）
                note_elements = page.eles('css:.note-item')
                if not note_elements or attempt >= len(note_elements):
                    logger.warning("没有更多帖子可采集")
                    break

                note_ele = note_elements[attempt]

                # 提取列表页的标题和点赞数
                list_title = ""
                list_likes = 0
                try:
                    title_ele = note_ele.ele('css:.title', timeout=1)
                    if title_ele:
                        list_title = title_ele.text.strip()
                except Exception:
                    pass

                try:
                    like_ele = note_ele.ele('css:.like-count, .count, [class*="like"]', timeout=1)
                    if like_ele:
                        list_likes = parse_count(like_ele.text)
                except Exception:
                    pass

                # 点击帖子打开详情弹窗
                logger.info(f"[{collected+1}/{top_n}] 点击帖子: {list_title[:30]}...")
                note_ele.click()
                time.sleep(6)

                # 从详情弹窗采集内容
                detail = collect_detail_from_modal(page)

                if detail:
                    # 合并列表页的数据
                    detail["likes"] = max(detail.get("likes", 0), list_likes)
                    if list_title and not detail.get("title"):
                        detail["title"] = list_title
                    detail["platform"] = "xiaohongshu"
                    detail["collected_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    details.append(detail)
                    collected += 1
                    logger.info(f"  ✅ 采集完成: {detail.get('title', '')[:30]} (赞:{detail.get('likes', 0)})")
                else:
                    logger.warning(f"  ⚠️  详情采集失败，跳过")

                # 关闭详情弹窗
                try:
                    # 按ESC关闭弹窗
                    page.actions.key_down('esc')
                    time.sleep(1)
                except Exception:
                    pass

                try:
                    # 或者点击关闭按钮
                    close_btn = page.ele('css:.close, [class*="close"], .icon-close', timeout=1)
                    if close_btn:
                        close_btn.click()
                except Exception:
                    pass

                time.sleep(2)

            except Exception as e:
                logger.warning(f"采集帖子失败: {e}")
                # 关闭可能打开的弹窗
                try:
                    page.actions.key_down('esc')
                except Exception:
                    pass
                time.sleep(2)
                continue

        logger.info(f"共采集到 {len(details)} 篇帖子详情")
        return details

    except Exception as e:
        logger.error(f"搜索采集失败: {e}")
        import traceback
        traceback.print_exc()
        return details
    finally:
        try:
            page.quit()
        except Exception:
            pass


def collect_detail_from_modal(page) -> Optional[Dict]:
    """
    从详情弹窗中采集帖子内容

    Args:
        page: DrissionPage页面对象

    Returns:
        帖子详情字典
    """
    try:
        # 提取标题
        title = ""
        try:
            title_ele = page.ele('css:#detail-title, .note-detail-mask .title, .note-container .title', timeout=3)
            if title_ele:
                title = title_ele.text.strip()
        except Exception:
            pass

        # 提取正文
        content = ""
        try:
            desc_ele = page.ele('css:#detail-desc, .note-detail-mask .desc, .note-container .desc', timeout=3)
            if desc_ele:
                content = desc_ele.text.strip()
        except Exception:
            pass

        # 如果没找到正文，尝试从note-content获取
        if not content:
            try:
                note_content = page.ele('css:.note-content', timeout=2)
                if note_content:
                    full_text = note_content.text
                    if title and title in full_text:
                        content = full_text.split(title, 1)[1].strip()
                    else:
                        content = full_text
            except Exception:
                pass

        # 提取标签
        tags = []
        try:
            tag_eles = page.eles('css:.tag, a[href*="/search_result?keyword="], .note-detail-mask .tag')
            for tag_ele in tag_eles:
                tag_text = tag_ele.text.strip().lstrip('#')
                if tag_text and len(tag_text) < 20:
                    tags.append(tag_text)
        except Exception:
            pass

        # 从正文中提取标签
        if not tags and content:
            import re
            tags = list(set(re.findall(r'#(\w+)', content)))[:10]

        # 提取点赞/收藏/评论数
        likes = 0
        favorites = 0
        comments = 0
        try:
            interact_eles = page.eles('css:.interaction-container .count, .note-detail-mask .count, [class*="like"] .count, [class*="collect"] .count')
            counts = []
            for ele in interact_eles:
                try:
                    count_text = ele.text.strip()
                    if count_text:
                        counts.append(parse_count(count_text))
                except Exception:
                    pass
            if len(counts) >= 1:
                likes = counts[0]
            if len(counts) >= 2:
                favorites = counts[1]
            if len(counts) >= 3:
                comments = counts[2]
        except Exception:
            pass

        # 提取作者
        author = ""
        try:
            author_ele = page.ele('css:.author, .username, [class*="author"]', timeout=2)
            if author_ele:
                author = author_ele.text.strip()
        except Exception:
            pass

        if not title and not content:
            return None

        return {
            "title": title or "无标题",
            "content": content or "（无法采集正文）",
            "tags": tags,
            "likes": likes,
            "favorites": favorites,
            "comments": comments,
            "author": author,
            "url": page.url
        }

    except Exception as e:
        logger.debug(f"详情采集异常: {e}")
        return None


def get_dynamic_reference(keyword: str, top_n: int = 3, use_cache: bool = True) -> str:
    """
    获取动态爆款参考（对外接口，被AI改写脚本调用）

    Args:
        keyword: 搜索关键词
        top_n: 采集前N篇
        use_cache: 是否使用缓存

    Returns:
        格式化的参考文本
    """
    # 检查缓存
    if use_cache and is_cache_valid(keyword, top_n):
        cache = load_cache(keyword, top_n)
        if cache and cache.get("reference"):
            logger.info(f"使用缓存的动态参考: {keyword}")
            return cache["reference"]

    # 搜索并采集帖子详情（在同一个浏览器会话中完成）
    details = search_and_collect(keyword, top_n=top_n)
    if not details:
        logger.warning(f"未采集到帖子: {keyword}")
        return ""

    # 批量拆解
    reference = analyze_posts(details)

    # 保存缓存
    if reference:
        cache_data = {
            "reference": reference,
            "posts": details,
            "post_count": len(details)
        }
        save_cache(keyword, top_n, cache_data)

    # 格式化参考文本
    if reference:
        result = f"\n\n===== 动态爆款参考（关键词: {keyword}，采集{len(details)}篇最新高赞帖子） =====\n"
        result += reference
        result += "\n===== 请参考以上最新爆款帖子的共性规律进行改写，但必须原创 =====\n"
        return result
    else:
        return ""


def list_cache():
    """列出所有缓存"""
    if not os.path.exists(CACHE_DIR):
        print("\n📭 缓存目录为空\n")
        return

    caches = []
    for filename in os.listdir(CACHE_DIR):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(CACHE_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                cache = json.load(f)
            caches.append(cache)
        except Exception:
            continue

    if not caches:
        print("\n📭 没有有效缓存\n")
        return

    print(f"\n{'='*80}")
    print(f"  动态采集缓存 ({len(caches)}个)")
    print(f"{'='*80}")
    print(f"{'关键词':<25} {'数量':<8} {'采集时间':<20} {'状态'}")
    print(f"{'-'*80}")

    for cache in caches:
        keyword = cache.get("keyword", "未知")[:22]
        top_n = cache.get("top_n", 0)
        cached_at = cache.get("cached_at", "")[:19]
        post_count = cache.get("post_count", len(cache.get("posts", [])))
        is_valid = is_cache_valid(cache.get("keyword", ""), cache.get("top_n", 0))
        status = "✅有效" if is_valid else "❌过期"
        print(f"{keyword:<25} {post_count:<8} {cached_at:<20} {status}")

    print(f"{'='*80}\n")


def clear_cache():
    """清除所有缓存"""
    if not os.path.exists(CACHE_DIR):
        print("\n📭 缓存目录为空\n")
        return

    count = 0
    for filename in os.listdir(CACHE_DIR):
        if filename.endswith(".json"):
            os.remove(os.path.join(CACHE_DIR, filename))
            count += 1

    print(f"\n✅ 已清除 {count} 个缓存文件\n")


def main():
    parser = argparse.ArgumentParser(description="动态爆款采集脚本")
    parser.add_argument("--keyword", type=str, help="搜索关键词")
    parser.add_argument("--top", type=int, default=5, help="采集前N篇（默认5）")
    parser.add_argument("--show", action="store_true", help="显示拆解结果")
    parser.add_argument("--no-cache", action="store_true", help="不使用缓存，强制重新采集")
    parser.add_argument("--list-cache", action="store_true", help="列出所有缓存")
    parser.add_argument("--clear-cache", action="store_true", help="清除所有缓存")

    args = parser.parse_args()

    if args.list_cache:
        list_cache()
        return

    if args.clear_cache:
        clear_cache()
        return

    if not args.keyword:
        parser.print_help()
        print("\n💡 示例:")
        print("  python scripts/00_dynamic_viral_collector.py --keyword 'Codex安装' --top 5 --show")
        print("  python scripts/00_dynamic_viral_collector.py --list-cache")
        print()
        return

    print(f"\n🔍 开始动态采集: 关键词='{args.keyword}', 采集前{args.top}篇")
    if args.no_cache:
        print("   （不使用缓存，强制重新采集）")
    print()

    reference = get_dynamic_reference(
        keyword=args.keyword,
        top_n=args.top,
        use_cache=not args.no_cache
    )

    if reference:
        print(f"\n{'='*80}")
        print(f"  动态爆款参考（关键词: {args.keyword}）")
        print(f"{'='*80}")
        if args.show:
            print(reference)
        else:
            print(reference[:1000])
            if len(reference) > 1000:
                print(f"\n...（共{len(reference)}字符，使用 --show 查看完整内容）")
        print(f"{'='*80}\n")
    else:
        print("\n❌ 未获取到动态参考，请检查网络和小红书登录状态\n")


if __name__ == "__main__":
    main()
