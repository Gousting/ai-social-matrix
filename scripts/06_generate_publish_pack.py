#!/usr/bin/env python3
"""
一键发布包生成脚本 (06_generate_publish_pack.py)

方案A（半自动模式）核心脚本：
  1. 读取待审核的草稿
  2. 生成HTML格式的发布包，包含：
     - 标题（一键复制）
     - 正文（一键复制，包含标签）
     - 图片列表（处理好的图片）
     - 发布说明（平台、最佳发布时间、标签建议、AI标识提醒）
  3. 在浏览器中打开发布包，方便用户复制粘贴到小红书APP/网页发布

用法：
  # 生成所有待审核草稿的发布包
  python scripts/06_generate_publish_pack.py

  # 生成指定草稿的发布包
  python scripts/06_generate_publish_pack.py --draft <草稿文件名>

  # 生成指定平台的发布包
  python scripts/06_generate_publish_pack.py --platform xiaohongshu

  # 生成后自动在浏览器打开
  python scripts/06_generate_publish_pack.py --open
"""
import sys
import os
import json
import argparse
import webbrowser
from datetime import datetime
from typing import Dict, List

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from scripts.utils.config_loader import config
from scripts.utils.logger import logger


def load_pending_drafts(platform: str = None) -> List[Dict]:
    """加载待审核草稿"""
    draft_dir = config.get_path("drafted_pending")
    if not os.path.exists(draft_dir):
        return []

    drafts = []
    for filename in os.listdir(draft_dir):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(draft_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                draft = json.load(f)
            draft["_filename"] = filename
            draft["_filepath"] = filepath
            if platform is None or draft.get("platform") == platform:
                drafts.append(draft)
        except Exception as e:
            logger.error(f"读取草稿失败 {filename}: {e}")

    return drafts


def generate_html_pack(draft: Dict, output_dir: str) -> str:
    """
    生成HTML格式的发布包

    Args:
        draft: 草稿字典
        output_dir: 输出目录

    Returns:
        HTML文件路径
    """
    title = draft.get("title", "")
    content = draft.get("content", "")
    tags = draft.get("tags", [])
    platform = draft.get("platform", "xiaohongshu")
    platform_name = draft.get("platform_name", platform)
    images = draft.get("images", [])
    similarity = draft.get("similarity", 0)
    compliance = draft.get("compliance", {})
    human_mod_note = draft.get("human_modification_note", "")

    # 标签文本
    tags_text = " ".join(tags) if tags else ""

    # 正文+标签（用于复制）
    content_with_tags = content
    if tags_text:
        content_with_tags = content.rstrip() + "\n\n" + tags_text

    # 合规状态
    compliance_passed = compliance.get("passed", True)
    compliance_issues = compliance.get("issues", [])

    # 最佳发布时间
    publish_times = ["12:00-13:00", "19:00-22:00"]

    # 生成HTML
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = title[:20].replace("/", "_").replace("\\", "_").replace(" ", "_")
    html_filename = f"publish_pack_{timestamp}_{safe_title}.html"
    html_path = os.path.join(output_dir, html_filename)

    # 图片HTML
    images_html = ""
    if images:
        images_html = '<div class="section"><h3>📷 图片</h3><div class="images">'
        for i, img in enumerate(images, 1):
            if os.path.exists(img):
                # 转换为file URI
                img_uri = "file:///" + img.replace("\\", "/")
                images_html += f'<div class="image-item"><img src="{img_uri}" alt="图片{i}"><p>图片{i}</p></div>'
            else:
                images_html += f'<div class="image-item"><p>❌ 图片{i}不存在: {img}</p></div>'
        images_html += '</div></div>'
    else:
        images_html = '<div class="section warning"><h3>⚠️ 没有图片</h3><p>小红书图文笔记需要至少1张图片，请先运行图片处理脚本生成封面和配图。</p></div>'

    # 合规问题HTML
    compliance_html = ""
    if compliance_issues:
        compliance_html = '<div class="section error"><h3>❌ 合规问题</h3><ul>'
        for issue in compliance_issues:
            compliance_html += f'<li>{issue}</li>'
        compliance_html += '</ul><p><strong>请修改后再发布！</strong></p></div>'
    else:
        compliance_html = '<div class="section success"><h3>✅ 合规检查通过</h3></div>'

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>发布包 - {title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; padding: 20px; max-width: 800px; margin: 0 auto; }}
        .header {{ background: linear-gradient(135deg, #ff2442, #ff6b6b); color: white; padding: 20px; border-radius: 12px; margin-bottom: 20px; }}
        .header h1 {{ font-size: 20px; margin-bottom: 10px; }}
        .header .meta {{ font-size: 14px; opacity: 0.9; }}
        .section {{ background: white; border-radius: 12px; padding: 20px; margin-bottom: 15px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }}
        .section h3 {{ font-size: 16px; margin-bottom: 12px; color: #333; display: flex; align-items: center; gap: 8px; }}
        .copy-btn {{ background: #ff2442; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 14px; margin-bottom: 10px; transition: background 0.2s; }}
        .copy-btn:hover {{ background: #e01e3c; }}
        .copy-btn:active {{ background: #c01a35; }}
        .content-box {{ background: #f9f9f9; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; font-size: 14px; line-height: 1.8; white-space: pre-wrap; word-break: break-word; max-height: 400px; overflow-y: auto; }}
        .title-box {{ background: #fff5f5; border: 2px solid #ff2442; border-radius: 8px; padding: 12px; font-size: 18px; font-weight: bold; color: #333; }}
        .images {{ display: flex; flex-wrap: wrap; gap: 15px; }}
        .image-item {{ flex: 0 0 calc(33.333% - 10px); text-align: center; }}
        .image-item img {{ width: 100%; border-radius: 8px; border: 1px solid #e0e0e0; }}
        .image-item p {{ font-size: 12px; color: #666; margin-top: 5px; }}
        .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 14px; }}
        .info-item {{ background: #f9f9f9; padding: 10px; border-radius: 6px; }}
        .info-item .label {{ color: #999; font-size: 12px; margin-bottom: 4px; }}
        .info-item .value {{ color: #333; font-weight: 500; }}
        .warning {{ background: #fff8e1; border-left: 4px solid #ff9800; }}
        .error {{ background: #ffebee; border-left: 4px solid #f44336; }}
        .success {{ background: #e8f5e9; border-left: 4px solid #4caf50; }}
        .tags {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }}
        .tag {{ background: #ff2442; color: white; padding: 4px 10px; border-radius: 12px; font-size: 12px; }}
        .footer {{ text-align: center; color: #999; font-size: 12px; margin-top: 20px; padding: 20px; }}
        .ai-notice {{ background: #e3f2fd; border: 1px solid #2196f3; border-radius: 8px; padding: 12px; margin-top: 10px; font-size: 13px; color: #1565c0; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📝 一键发布包</h1>
        <div class="meta">
            平台：{platform_name} | 生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | 相似度：{similarity}%
        </div>
    </div>

    <div class="section">
        <h3>📌 标题</h3>
        <button class="copy-btn" onclick="copyText('title-text')">📋 复制标题</button>
        <div class="title-box" id="title-text">{title}</div>
    </div>

    <div class="section">
        <h3>📄 正文（含标签）</h3>
        <button class="copy-btn" onclick="copyText('content-text')">📋 复制正文</button>
        <div class="content-box" id="content-text">{content_with_tags}</div>
        <div class="tags">
            {''.join(f'<span class="tag">{t}</span>' for t in tags)}
        </div>
    </div>

    {images_html}

    {compliance_html}

    <div class="section">
        <h3>📊 发布信息</h3>
        <div class="info-grid">
            <div class="info-item">
                <div class="label">平台</div>
                <div class="value">{platform_name}</div>
            </div>
            <div class="info-item">
                <div class="label">最佳发布时间</div>
                <div class="value">{', '.join(publish_times)}</div>
            </div>
            <div class="info-item">
                <div class="label">内容相似度</div>
                <div class="value">{similarity}%</div>
            </div>
            <div class="info-item">
                <div class="label">标签数量</div>
                <div class="value">{len(tags)}个</div>
            </div>
        </div>
        <div class="ai-notice">
            ⚠️ <strong>AI内容标识提醒</strong>：发布时请主动勾选"AI合成内容"，正文已包含"人工智能生成"标识。2026年新规：未标识会被限流，首次漏标限流7天，二次禁言30天。
        </div>
        {f'<div class="ai-notice" style="margin-top: 8px;">💡 <strong>人工修改提醒</strong>：{human_mod_note}</div>' if human_mod_note else ''}
    </div>

    <div class="section warning">
        <h3>📋 发布步骤</h3>
        <ol style="margin-left: 20px; line-height: 2; font-size: 14px;">
            <li>打开小红书APP或创作者中心（需要国内IP/节点）</li>
            <li>点击"发布"，选择"上传图文"</li>
            <li>上传上面的图片（建议第1张为封面）</li>
            <li>复制标题粘贴到标题输入框</li>
            <li>复制正文粘贴到正文输入框</li>
            <li>确认标签已正确添加</li>
            <li>勾选"AI合成内容"声明</li>
            <li>选择最佳发布时间，点击发布</li>
        </ol>
    </div>

    <div class="footer">
        AI社交媒体矩阵管理运营系统 - 方案A半自动模式<br>
        生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    </div>

    <script>
        function copyText(elementId) {{
            const element = document.getElementById(elementId);
            const text = element.innerText;
            navigator.clipboard.writeText(text).then(() => {{
                const btn = event.target;
                const originalText = btn.innerText;
                btn.innerText = '✅ 已复制！';
                btn.style.background = '#4caf50';
                setTimeout(() => {{
                    btn.innerText = originalText;
                    btn.style.background = '#ff2442';
                }}, 1500);
            }}).catch(err => {{
                alert('复制失败，请手动复制');
            }});
        }}
    </script>
</body>
</html>"""

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    logger.info(f"发布包已生成: {html_path}")
    return html_path


def main():
    parser = argparse.ArgumentParser(description="一键发布包生成脚本（方案A半自动模式）")
    parser.add_argument("--draft", type=str, help="指定草稿文件名")
    parser.add_argument("--platform", type=str, default=None, help="指定平台过滤")
    parser.add_argument("--open", action="store_true", help="生成后自动在浏览器打开")
    parser.add_argument("--output-dir", type=str, default=None, help="输出目录（默认data/publish_packs）")

    args = parser.parse_args()

    # 输出目录
    output_dir = args.output_dir or os.path.join(PROJECT_ROOT, "data", "publish_packs")
    os.makedirs(output_dir, exist_ok=True)

    # 加载草稿
    drafts = load_pending_drafts(args.platform)

    if args.draft:
        drafts = [d for d in drafts if args.draft in d.get("_filename", "")]

    if not drafts:
        print("\n❌ 没有找到待审核的草稿\n")
        print("请先运行AI改写脚本生成草稿：")
        print("  python scripts/02_ai_rewrite.py --top 5 --platform xiaohongshu")
        return

    print(f"\n找到 {len(drafts)} 篇待审核草稿，开始生成发布包...\n")

    generated_packs = []
    for i, draft in enumerate(drafts, 1):
        title = draft.get("title", "未命名")[:40]
        print(f"[{i}/{len(drafts)}] 生成发布包: {title}...")
        html_path = generate_html_pack(draft, output_dir)
        generated_packs.append(html_path)
        print(f"  ✅ {html_path}")

    print(f"\n{'='*60}")
    print(f"  发布包生成完成！共生成 {len(generated_packs)} 个发布包")
    print(f"  输出目录: {output_dir}")
    print(f"{'='*60}\n")

    # 在浏览器打开
    if args.open and generated_packs:
        print("正在浏览器打开第一个发布包...")
        webbrowser.open("file:///" + generated_packs[0].replace("\\", "/"))

    # 列出生成的发布包
    print("生成的发布包列表：")
    for i, pack in enumerate(generated_packs, 1):
        print(f"  {i}. {os.path.basename(pack)}")


if __name__ == "__main__":
    main()
