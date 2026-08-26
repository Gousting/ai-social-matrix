#!/usr/bin/env python3
"""
图片处理脚本 (03_image_process.py)

功能：
  1. 批量裁剪/缩放图片为各平台标准尺寸
  2. 添加文字水印
  3. 图片格式转换（PNG/JPG/WebP）
  4. 图片质量压缩
  5. 生成简单封面图（纯色背景+文字）

各平台标准尺寸：
  小红书:   1080×1440 (3:4)
  知乎:     宽≥900px（等比缩放）
  B站专栏:  宽≥960px（等比缩放）
  公众号:   宽900px（正文）/ 900×383（封面2.35:1）
  视频号:   1080×1260 (6:7)

用法：
  # 批量处理文件夹中的图片为小红书尺寸
  python scripts/03_image_process.py --input ./images/raw --output ./images/xhs --platform xiaohongshu

  # 处理所有平台尺寸
  python scripts/03_image_process.py --input ./images/raw --output ./images --platform all

  # 添加水印
  python scripts/03_image_process.py --input ./images/raw --output ./images/watermarked --watermark "AI工具箱"

  # 生成封面图
  python scripts/03_image_process.py --generate-cover --title "Codex安装教程" --platform xiaohongshu --output ./images/cover.jpg
"""
import sys
import os
import argparse
from typing import Tuple, Optional

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from scripts.utils.logger import logger

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:
    logger.error("请先安装Pillow: pip install Pillow")
    sys.exit(1)


# ============================================
# 各平台图片尺寸配置
# ============================================

PLATFORM_SIZES = {
    "xiaohongshu": {
        "name": "小红书",
        "size": (1080, 1440),
        "mode": "crop",  # crop=裁剪填充, fit=等比缩放留白
        "quality": 95,
        "format": "JPEG"
    },
    "zhihu": {
        "name": "知乎",
        "size": (1200, 0),  # 宽1200，高度等比
        "mode": "fit_width",
        "quality": 90,
        "format": "JPEG"
    },
    "bilibili": {
        "name": "B站专栏",
        "size": (1200, 0),
        "mode": "fit_width",
        "quality": 90,
        "format": "JPEG"
    },
    "wechat_mp": {
        "name": "公众号",
        "size": (900, 0),
        "mode": "fit_width",
        "quality": 85,
        "format": "JPEG"
    },
    "wechat_mp_cover": {
        "name": "公众号封面",
        "size": (900, 383),
        "mode": "crop",
        "quality": 90,
        "format": "JPEG"
    },
    "wechat_channels": {
        "name": "视频号",
        "size": (1080, 1260),
        "mode": "crop",
        "quality": 95,
        "format": "JPEG"
    }
}


def resize_crop(img: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
    """
    裁剪填充模式：先等比缩放覆盖目标尺寸，再居中裁剪
    """
    target_w, target_h = target_size
    if target_h == 0:
        # 只限定宽度，高度等比
        w_percent = target_w / float(img.size[0])
        h_size = int(float(img.size[1]) * w_percent)
        return img.resize((target_w, h_size), Image.LANCZOS)

    # 计算缩放比例
    src_ratio = img.size[0] / float(img.size[1])
    dst_ratio = target_w / float(target_h)

    if src_ratio > dst_ratio:
        # 原图更宽，以高度为准缩放
        new_h = target_h
        new_w = int(target_h * src_ratio)
    else:
        # 原图更高，以宽度为准缩放
        new_w = target_w
        new_h = int(target_w / src_ratio)

    img = img.resize((new_w, new_h), Image.LANCZOS)

    # 居中裁剪
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    right = left + target_w
    bottom = top + target_h
    return img.crop((left, top, right, bottom))


def resize_fit(img: Image.Image, target_size: Tuple[int, int],
               bg_color: Tuple[int, int, int] = (255, 255, 255)) -> Image.Image:
    """
    等比缩放留白模式：等比缩放到目标尺寸内，剩余空间用背景色填充
    """
    target_w, target_h = target_size
    img_copy = img.copy()
    img_copy.thumbnail((target_w, target_h), Image.LANCZOS)

    # 创建背景
    background = Image.new("RGB", (target_w, target_h), bg_color)
    # 居中粘贴
    offset = ((target_w - img_copy.size[0]) // 2, (target_h - img_copy.size[1]) // 2)
    background.paste(img_copy, offset)
    return background


def add_watermark(img: Image.Image, text: str, position: str = "bottom-right",
                   font_size: int = 30, opacity: int = 128) -> Image.Image:
    """
    添加文字水印

    position: top-left, top-right, bottom-left, bottom-right, center
    """
    img = img.convert("RGBA")
    overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    # 尝试加载字体
    try:
        font = ImageFont.truetype("msyh.ttc", font_size)  # 微软雅黑
    except (IOError, OSError):
        try:
            font = ImageFont.truetype("simhei.ttf", font_size)  # 黑体
        except (IOError, OSError):
            font = ImageFont.load_default()

    # 计算文字大小
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # 计算位置
    margin = 20
    if position == "top-left":
        x, y = margin, margin
    elif position == "top-right":
        x, y = img.size[0] - text_w - margin, margin
    elif position == "bottom-left":
        x, y = margin, img.size[1] - text_h - margin
    elif position == "center":
        x, y = (img.size[0] - text_w) // 2, (img.size[1] - text_h) // 2
    else:  # bottom-right
        x, y = img.size[0] - text_w - margin, img.size[1] - text_h - margin

    # 绘制文字阴影
    draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, opacity // 2))
    # 绘制文字
    draw.text((x, y), text, font=font, fill=(255, 255, 255, opacity))

    return Image.alpha_composite(img, overlay).convert("RGB")


def process_single_image(input_path: str, output_path: str, platform: str,
                         watermark: str = None, quality: int = None) -> bool:
    """
    处理单张图片
    """
    platform_config = PLATFORM_SIZES.get(platform)
    if not platform_config:
        logger.error(f"不支持的平台: {platform}")
        return False

    try:
        img = Image.open(input_path)
        # 处理EXIF旋转信息
        img = ImageOps.exif_transpose(img)

        # 调整尺寸
        if platform_config["mode"] == "crop":
            img = resize_crop(img, platform_config["size"])
        elif platform_config["mode"] == "fit_width":
            img = resize_crop(img, platform_config["size"])
        else:
            img = resize_fit(img, platform_config["size"])

        # 添加水印
        if watermark:
            img = add_watermark(img, watermark)

        # 保存
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        save_quality = quality if quality else platform_config["quality"]
        save_format = platform_config["format"]

        if save_format == "JPEG" and img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        img.save(output_path, save_format, quality=save_quality)
        logger.info(f"处理完成: {os.path.basename(input_path)} -> {output_path} "
                     f"({img.size[0]}×{img.size[1]})")
        return True

    except Exception as e:
        logger.error(f"处理失败 {input_path}: {e}")
        return False


def batch_process(input_dir: str, output_dir: str, platforms: list,
                  watermark: str = None) -> int:
    """
    批量处理文件夹中的图片
    """
    if not os.path.exists(input_dir):
        logger.error(f"输入目录不存在: {input_dir}")
        return 0

    image_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif')
    image_files = [f for f in os.listdir(input_dir)
                   if f.lower().endswith(image_extensions)]

    if not image_files:
        logger.warning(f"输入目录中没有图片: {input_dir}")
        return 0

    logger.info(f"找到{len(image_files)}张图片，平台: {platforms}")

    success_count = 0
    for platform in platforms:
        platform_output = os.path.join(output_dir, platform) if len(platforms) > 1 else output_dir
        os.makedirs(platform_output, exist_ok=True)

        for img_file in image_files:
            input_path = os.path.join(input_dir, img_file)
            # 输出文件名（统一转为jpg）
            base_name = os.path.splitext(img_file)[0]
            output_path = os.path.join(platform_output, f"{base_name}.jpg")
            if process_single_image(input_path, output_path, platform, watermark):
                success_count += 1

    logger.info(f"批量处理完成: 成功{success_count}/{len(image_files) * len(platforms)}张")
    return success_count


def generate_cover(title: str, platform: str, output_path: str,
                   bg_color: Tuple[int, int, int] = (30, 40, 80),
                   text_color: Tuple[int, int, int] = (255, 255, 255)):
    """
    生成简单封面图（纯色背景+文字）
    """
    platform_config = PLATFORM_SIZES.get(platform)
    if not platform_config:
        logger.error(f"不支持的平台: {platform}")
        return

    size = platform_config["size"]
    if size[1] == 0:
        size = (size[0], int(size[0] * 0.75))

    img = Image.new("RGB", size, bg_color)
    draw = ImageDraw.Draw(img)

    # 尝试加载大字体
    try:
        font_large = ImageFont.truetype("msyh.ttc", size[0] // 12)
        font_small = ImageFont.truetype("msyh.ttc", size[0] // 25)
    except (IOError, OSError):
        try:
            font_large = ImageFont.truetype("simhei.ttf", size[0] // 12)
            font_small = ImageFont.truetype("simhei.ttf", size[0] // 25)
        except (IOError, OSError):
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()

    # 标题自动换行
    def wrap_text(text, font, max_width):
        words = list(text)
        lines = []
        current_line = ""
        for char in words:
            test_line = current_line + char
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = char
        if current_line:
            lines.append(current_line)
        return lines

    max_width = size[0] - 100
    lines = wrap_text(title, font_large, max_width)

    # 计算总高度
    line_height = font_large.size + 20
    total_height = len(lines) * line_height

    # 垂直居中
    y_start = (size[1] - total_height) // 2

    # 绘制标题
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font_large)
        text_w = bbox[2] - bbox[0]
        x = (size[0] - text_w) // 2
        y = y_start + i * line_height
        draw.text((x, y), line, font=font_large, fill=text_color)

    # 底部小字
    footer = "AI工具箱 · 干货分享"
    bbox = draw.textbbox((0, 0), footer, font=font_small)
    footer_w = bbox[2] - bbox[0]
    draw.text(((size[0] - footer_w) // 2, size[1] - 80),
              footer, font=font_small, fill=(200, 200, 200))

    # 保存
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "JPEG", quality=95)
    logger.info(f"封面图已生成: {output_path} ({size[0]}×{size[1]})")


def main():
    parser = argparse.ArgumentParser(description="图片处理脚本")
    parser.add_argument("--input", type=str, help="输入图片或文件夹路径")
    parser.add_argument("--output", type=str, help="输出路径")
    parser.add_argument("--platform", type=str, default="all",
                        help="目标平台: xiaohongshu/zhihu/bilibili/wechat_mp/wechat_channels/all")
    parser.add_argument("--watermark", type=str, default=None, help="水印文字")
    parser.add_argument("--quality", type=int, default=None, help="输出质量(1-100)")
    parser.add_argument("--generate-cover", action="store_true", help="生成封面图模式")
    parser.add_argument("--title", type=str, help="封面标题（配合--generate-cover使用）")
    parser.add_argument("--list-sizes", action="store_true", help="列出各平台尺寸")

    args = parser.parse_args()

    if args.list_sizes:
        print("\n各平台图片尺寸:")
        print("-" * 50)
        for key, cfg in PLATFORM_SIZES.items():
            size = cfg["size"]
            size_str = f"{size[0]}×{size[1]}" if size[1] > 0 else f"宽{size[0]}（等比）"
            print(f"  {key:20s} {cfg['name']:10s} {size_str:15s} {cfg['mode']}")
        print()
        return

    # 解析平台列表
    if args.platform == "all":
        platforms = ["xiaohongshu", "zhihu", "bilibili", "wechat_mp", "wechat_channels"]
    else:
        platforms = [args.platform] if args.platform in PLATFORM_SIZES else []
        if not platforms:
            logger.error(f"不支持的平台: {args.platform}")
            return

    if args.generate_cover:
        if not args.title or not args.output:
            logger.error("生成封面图需要指定 --title 和 --output")
            return
        generate_cover(args.title, platforms[0], args.output)
        return

    if not args.input or not args.output:
        parser.print_help()
        print("\n常用命令:")
        print("  # 批量处理为小红书尺寸")
        print("  python scripts/03_image_process.py --input ./images/raw --output ./images/xhs --platform xiaohongshu")
        print("  # 处理所有平台尺寸")
        print("  python scripts/03_image_process.py --input ./images/raw --output ./images --platform all")
        print("  # 添加水印")
        print('  python scripts/03_image_process.py --input ./images/raw --output ./images/wm --watermark "AI工具箱"')
        print("  # 生成封面图")
        print('  python scripts/03_image_process.py --generate-cover --title "Codex安装教程" --platform xiaohongshu --output ./images/cover.jpg')
        print("  # 列出各平台尺寸")
        print("  python scripts/03_image_process.py --list-sizes")
        return

    # 批量处理
    if os.path.isdir(args.input):
        batch_process(args.input, args.output, platforms, args.watermark)
    else:
        # 单张图片
        for platform in platforms:
            if len(platforms) > 1:
                output_path = os.path.join(args.output, platform, os.path.basename(args.input))
            else:
                output_path = args.output
            process_single_image(args.input, output_path, platform, args.watermark, args.quality)


if __name__ == "__main__":
    main()
