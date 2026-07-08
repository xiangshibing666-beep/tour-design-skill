#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从旅游方案 MD 生成 网页版 HTML + A4 PDF。

依赖:
    pip install markdown

用法:
    python build_html_pdf.py --md "华东三城8日游详细方案.md" \
                             --name "华东三城8日游详细方案" \
                             --outdir "."

说明:
    - 网页版: <name>.html  (炫彩、含目录锚点、彩色表格，浏览器查看)
    - PDF 版 : <name>.pdf   (干净 A4 打印版, Chrome/Edge headless 渲染)
    - 找不到浏览器时跳过 PDF，并打印提示让用户用浏览器手动打印 _pdf.html
"""

import argparse
import markdown
import os
import shutil
import subprocess
import sys

# ---------- 网页版 CSS（炫彩）----------
WEB_CSS = """
:root{
  --green:#1a6b3c; --green2:#2e9e5b; --blue:#1f6fb2; --orange:#e0822b;
  --red:#b3402a; --bg:#f5f9f6; --card:#ffffff; --line:#d8e6dd;
}
*{box-sizing:border-box;}
body{font-family:"Microsoft YaHei","PingFang SC","Hiragino Sans GB",sans-serif;
  color:#1f2622; background:var(--bg); margin:0; line-height:1.75; font-size:15px;}
.wrap{max-width:960px; margin:0 auto; padding:32px 26px 60px;
  background:var(--card); box-shadow:0 2px 18px rgba(0,0,0,.06);}
h1{font-size:27px; color:var(--green); border-bottom:4px solid var(--green2);
  padding-bottom:12px; margin-top:8px;}
h2{font-size:20px; color:var(--green); margin-top:34px; padding-left:12px;
  border-left:6px solid var(--green2); background:linear-gradient(90deg,#eaf5ee,transparent);}
h3{font-size:16.5px; color:#173a26; margin-top:20px;}
h4{font-size:14.5px; color:#333; margin:14px 0 6px;}
table{border-collapse:collapse; width:100%; margin:14px 0; font-size:13.5px;
  box-shadow:0 1px 4px rgba(0,0,0,.05); border-radius:8px; overflow:hidden;}
th,td{border:1px solid var(--line); padding:8px 10px; text-align:left; vertical-align:top;}
th{background:linear-gradient(180deg,var(--green2),var(--green)); color:#fff; font-weight:700;}
tr:nth-child(even) td{background:#f3f8f4;}
blockquote{border-left:5px solid var(--orange); background:#fff7ec;
  margin:14px 0; padding:10px 16px; color:#7a4f12; border-radius:0 8px 8px 0;}
code{background:#eef3f0; padding:2px 6px; border-radius:4px; font-size:12.5px;}
strong{color:var(--red);}
ul,ol{padding-left:24px;}
a{color:var(--blue);}
hr{border:none; border-top:2px dashed var(--line); margin:30px 0;}
img{max-width:100%;}
.toc{background:#eaf5ee; border:1px solid var(--line); border-radius:10px;
  padding:14px 20px; margin:18px 0;}
.toc b{color:var(--green);}
"""

# ---------- A4 打印版 CSS（干净）----------
PRINT_CSS = """
@page{ size:A4; margin:16mm 14mm; }
*{box-sizing:border-box;}
body{font-family:"Microsoft YaHei","PingFang SC",sans-serif; color:#1a1a1a;
  font-size:12.5px; line-height:1.7;}
h1{font-size:21px; border-bottom:3px solid #1a6b3c; padding-bottom:8px; color:#1a6b3c;}
h2{font-size:16px; margin-top:22px; color:#14633a; border-left:5px solid #2e9e5b; padding-left:9px;}
h3{font-size:13.5px; margin-top:14px; color:#333;}
table{border-collapse:collapse; width:100%; margin:10px 0; font-size:11.5px;}
th,td{border:1px solid #c9d6cf; padding:5px 7px; text-align:left; vertical-align:top;}
th{background:#e8f3ec; font-weight:700;}
tr:nth-child(even) td{background:#f6faf8;}
blockquote{border-left:4px solid #e0a93b; background:#fdf6e8; margin:10px 0;
  padding:8px 12px; color:#7a5b16;}
code{background:#eef2f0; padding:1px 4px; border-radius:3px; font-size:11px;}
strong{color:#b3402a;}
ul,ol{padding-left:20px;}
h2,h3{break-after:avoid;}
tr{break-inside:avoid;}
"""

WEB_HEADER = '<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>{css}</style></head><body><div class="wrap">'
WEB_FOOTER = "</div></body></html>"
PRINT_HEADER = '<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><title>{title}</title><style>{css}</style></head><body>'
PRINT_FOOTER = "</body></html>"


def build_toc(md_text):
    """从二级/三级标题生成简单目录（锚点用标题文本 slug）。"""
    import re
    toc = ["<div class='toc'><b>目录</b><ul>"]
    for line in md_text.splitlines():
        m = re.match(r"^(#{2,3})\s+(.*)$", line)
        if m and m.group(2).strip():
            level = len(m.group(1))
            text = m.group(2).strip()
            anchor = (
                text.replace(" ", "-")
                .replace("（", "")
                .replace("）", "")
                .replace("、", "-")
                .replace("/", "-")
            )
            indent = "&nbsp;&nbsp;" * (level - 2)
            toc.append(f"{indent}<li><a href='#{anchor}'>{text}</a></li>")
    toc.append("</ul></div>")
    return "".join(toc)


def slugify(line):
    text = line.strip().lstrip("#").strip()
    return (
        text.replace(" ", "-")
        .replace("（", "")
        .replace("）", "")
        .replace("、", "-")
        .replace("/", "-")
    )


def add_anchors(body_html):
    """给 h2/h3 加 id 锚点，配合目录跳转。"""
    import re

    def repl(m):
        tag, text = m.group(1), m.group(2)
        anchor = slugify(text)
        return f"<{tag} id='{anchor}'>{text}</{tag}>"

    return re.sub(r"<(h[23])>(.*?)</\1>", repl, body_html, flags=re.S)


def find_browser():
    candidates = [
        r"C:/Program Files/Google/Chrome/Application/chrome.exe",
        r"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        r"C:/Program Files/Microsoft/Edge/Application/msedge.exe",
        r"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    # PATH 兜底
    found = shutil.which("chrome") or shutil.which("chromium") or shutil.which("msedge")
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", required=True, help="输入 MD 文件路径")
    ap.add_argument("--name", default=None, help="输出文件名（不含扩展名）")
    ap.add_argument("--outdir", default=".", help="输出目录")
    args = ap.parse_args()

    if not os.path.exists(args.md):
        print(f"[错误] 找不到 MD 文件: {args.md}")
        sys.exit(1)

    try:
        import markdown  # noqa
    except ImportError:
        print("[错误] 缺少依赖 markdown。请运行: pip install markdown")
        sys.exit(2)

    name = args.name or os.path.splitext(os.path.basename(args.md))[0]
    outdir = args.outdir
    os.makedirs(outdir, exist_ok=True)

    with open(args.md, encoding="utf-8") as f:
        md_text = f.read()

    body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    toc = build_toc(md_text)
    body_with_anchor = add_anchors(body)
    web_html = (
        WEB_HEADER.format(title=name, css=WEB_CSS)
        + toc
        + body_with_anchor
        + WEB_FOOTER
    )
    print_html = PRINT_HEADER.format(title=name, css=PRINT_CSS) + body + PRINT_FOOTER

    web_path = os.path.join(outdir, name + ".html")
    pdf_temp = os.path.join(outdir, name + "_pdf.html")
    with open(web_path, "w", encoding="utf-8") as f:
        f.write(web_html)
    with open(pdf_temp, "w", encoding="utf-8") as f:
        f.write(print_html)
    print(f"[OK] 网页版: {web_path}")

    browser = find_browser()
    if browser:
        pdf_path = os.path.join(outdir, name + ".pdf")
        cmd = [
            browser,
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}",
            "--print-to-pdf-no-header",
            "file:///" + pdf_temp,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
            os.remove(pdf_temp)
            print(f"[OK] PDF: {pdf_path}")
        except Exception as e:
            print(f"[警告] PDF 生成失败: {e}；保留 {pdf_temp} 供浏览器手动打印")
    else:
        print(f"[提示] 未找到 Chrome/Edge，跳过 PDF。请用浏览器打开 {pdf_temp} 并『打印→另存为 PDF』")


if __name__ == "__main__":
    main()
