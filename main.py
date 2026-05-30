#!/usr/bin/env python3
"""
ArXiv Daily Paper Digest
稳健版：时间窗 + ID去重 + LLM学科过滤 + 分流式seen记录

流程：
抓取 arXiv 论文
→ ID去重
→ 时间窗过滤
→ 关键词过滤
→ LLM学科判定
   - 不属于目标学科：立即记录 seen
   - 属于目标学科：LLM总结
→ 邮件推送
   - 邮件成功：记录已发送论文 seen
   - 邮件失败：不记录已发送论文 seen（下次可重试）
"""

import os
import re
import sys
import time
import yaml
import arxiv
import logging
import smtplib
from datetime import datetime, timedelta, timezone, date
from zoneinfo import ZoneInfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from openai import OpenAI

# ── 日志 ──────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── 星期名映射（用于日志） ──
WEEKDAY_NAMES = {
    0: "周一 Monday",
    1: "周二 Tuesday",
    2: "周三 Wednesday",
    3: "周四 Thursday",
    4: "周五 Friday",
    5: "周六 Saturday",
    6: "周日 Sunday",
}

SEEN_FILE = "seen_papers.txt"

# ══════════════════════════════════════════════════
#  1. 状态管理 (已抓取 ID 去重)
# ══════════════════════════════════════════════════
def load_seen_papers() -> set:
    """加载已经处理过的论文 ID（剥离版本号）"""
    if not os.path.exists(SEEN_FILE):
        return set()
    with open(SEEN_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def save_seen_papers(new_ids: list):
    """追加保存新的论文 ID"""
    if not new_ids:
        return
    unique_ids = list(dict.fromkeys(new_ids))
    with open(SEEN_FILE, "a", encoding="utf-8") as f:
        for pid in unique_ids:
            f.write(f"{pid}\n")
    logger.info(f"💾 已写入 {len(unique_ids)} 个论文 ID 到 {SEEN_FILE}")

def get_base_id(entry_id: str) -> str:
    """从URL中提取纯ID，去掉版本号"""
    match = re.search(r"abs/(\d+\.\d+)(v\d+)?", entry_id)
    if match:
        return match.group(1)
    return entry_id.split('/')[-1].split('v')[0]


# ══════════════════════════════════════════════════
#  2. 加载配置 & 工具函数
# ══════════════════════════════════════════════════
def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def normalize_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]

def get_search_timezone(config: dict):
    tz_name = config.get("search", {}).get("timezone", "UTC")
    try:
        return ZoneInfo(tz_name)
    except Exception:
        logger.warning(f"⚠️ 无法识别时区 {tz_name}，回退到 UTC")
        return timezone.utc

def paper_in_target_categories(paper: dict, target_categories: list[str]) -> bool:
    return any(cat in target_categories for cat in paper.get("categories", []))


# ══════════════════════════════════════════════════
#  3. 抓取 arXiv 论文 (漏斗过滤机制)
# ══════════════════════════════════════════════════
def build_query(keywords: list[str], categories: list[str], keyword_mode: str = "none") -> str:
    if not categories:
        raise ValueError("必须指定至少一个分类 (categories)")

    cat_query = " OR ".join(f"cat:{c}" for c in categories)

    if keyword_mode in ("none", "filter") or not keywords:
        return cat_query

    kw_parts = []
    for kw in keywords:
        kw_parts.append(f'ti:"{kw}"')
        kw_parts.append(f'abs:"{kw}"')
    kw_query = " OR ".join(kw_parts)

    return f"({kw_query}) AND ({cat_query})"

def keyword_matches(paper: dict, keywords: list[str]) -> list[str]:
    if not keywords:
        return []
    text = (paper["title"] + " " + paper["abstract"]).lower()
    matched = []
    for kw in keywords:
        pattern = rf"\b{re.escape(kw.lower())}\b"
        if re.search(pattern, text):
            matched.append(kw)
    return matched

def fetch_papers(config: dict) -> tuple[list[dict], date, date]:
    sc = config["search"]

    keywords = normalize_list(sc.get("keywords", []))
    categories = normalize_list(sc.get("categories", []))
    max_papers = int(sc.get("max_papers", 10))
    keyword_mode = sc.get("keyword_mode", "none")
    days_back = int(sc.get("days_back", 4))
    tz = get_search_timezone(config)

    now = datetime.now(tz)
    today_date = now.date()
    cutoff_date = today_date - timedelta(days=days_back)

    seen_ids = load_seen_papers()
    query = build_query(keywords, categories, keyword_mode)

    logger.info(f"🔍 arXiv query: {query}")
    logger.info(f"📅 目标时间窗 ({tz}): {cutoff_date} ~ 至今")
    logger.info(f"🔧 关键字模式: {keyword_mode}")
    logger.info(f"📌 最大候选论文数: {max_papers}")

    fetch_limit = max(500, max_papers * 50)
    logger.info(f"📥 API 最大抓取上限: {fetch_limit}")

    search = arxiv.Search(
        query=query,
        max_results=fetch_limit,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    client = arxiv.Client(page_size=50, delay_seconds=20.0, num_retries=3)

    papers = []

    skipped_by_date = 0
    skipped_by_keyword = 0
    skipped_by_seen = 0
    total_scanned = 0

    for result in client.results(search):
        total_scanned += 1
        base_id = get_base_id(result.entry_id)

        if base_id in seen_ids:
            skipped_by_seen += 1
            continue

        pub = result.published
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)

        pub_local = pub.astimezone(tz)
        pub_date = pub_local.date()

        if pub_date < cutoff_date:
            skipped_by_date += 1
            continue

        paper = {
            "title": result.title.replace("\n", " "),
            "abstract": result.summary.replace("\n", " "),
            "authors": [a.name for a in result.authors],
            "published": pub_local.strftime("%Y-%m-%d"),
            "updated": (
                result.updated.astimezone(tz).strftime("%Y-%m-%d")
                if result.updated else ""
            ),
            "url": result.entry_id,
            "pdf_url": result.pdf_url,
            "categories": result.categories,
            "base_id": base_id,
            "matched_keywords": [],
        }

        if keyword_mode == "filter" and keywords:
            exempt_cats = normalize_list(sc.get("filter_exempt_categories", []))
            is_exempt = any(cat in exempt_cats for cat in paper["categories"])

            if is_exempt:
                logger.info(f"  🔓 豁免分类放行: {paper['categories']} -> {paper['title'][:40]}")
                paper["matched_keywords"] = []
            else:
                matched = keyword_matches(paper, keywords)
                if not matched:
                    skipped_by_keyword += 1
                    continue
                paper["matched_keywords"] = matched

        papers.append(paper)
        logger.info(f"  ✅ 命中候选论文: {paper['published']} | {paper['title'][:60]}")

        if len(papers) >= max_papers:
            logger.info(f"📌 已达到 max_papers={max_papers} 候选上限，停止扫描。")
            break

    logger.info(
        f"📊 扫描统计: 总扫描={total_scanned}, "
        f"跳过(历史已读)={skipped_by_seen}, "
        f"跳过(早于时间窗)={skipped_by_date}, "
        f"跳过(无关键词)={skipped_by_keyword}"
    )
    logger.info(f"✅ 最终筛选出 {len(papers)} 篇候选论文")

    return papers, cutoff_date, today_date


# ══════════════════════════════════════════════════
#  4. LLM 学科判定 + 翻译总结
# ══════════════════════════════════════════════════
CLASSIFY_PROMPT = """请判断下面这篇 arXiv 论文，从研究内容上是否属于以下任一范畴：

1. 软件工程（Software Engineering, cs.SE）
2. 分布式计算 / 并行计算 / 高性能计算（Distributed, Parallel, or High Performance Computing, cs.DC）

判断标准：
- “属于”包括：软件开发、测试、调试、程序分析、代码生成、代码理解、程序修复、构建系统、软件维护、工程实践；
- 也包括：并行计算、分布式系统、任务调度、资源管理、集群、MPI、OpenMP、GPU/HPC、性能优化、benchmarking 等；
- 如果论文只是使用代码/软件作为应用背景，但核心研究不属于上述方向，则判为 NO；
- 如果论文主要是 NLP、通用 AI、机器学习方法，而不是聚焦软件工程或分布式/并行/HPC问题，也判为 NO。

你只能输出一行，且只能是以下两种之一：
YES
NO

标题：{title}

摘要：{abstract}
"""

SUMMARY_PROMPT = """请你作为一位资深 AI 研究员，用{language}对以下学术论文进行分析。

请严格按照以下格式输出，每个板块都必须完整，不要遗漏，不要添加多余板块：

### 📌 中文标题
[准确翻译英文标题，一行即可]

### 💡 一句话总结
[用一句话概括：这篇论文针对什么问题，提出了什么方法来解决。控制在 50 字以内。]

### 📋 摘要中文全文
[将英文摘要完整翻译为通顺的中文，要求尽量忠实原文，不要省略，不要缩写，不要额外发挥。]

---

**英文标题：** {title}

**摘要原文：** {abstract}
"""

REQUIRED_SECTIONS = ["中文标题", "一句话总结", "摘要中文全文"]

def llm_category_check(client: OpenAI, paper: dict, model: str) -> bool:
    prompt = CLASSIFY_PROMPT.format(
        title=paper["title"],
        abstract=paper["abstract"],
    )

    max_retries = 3

    for attempt in range(1, max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是一个严格的论文分类器。"
                            "你只能输出 YES 或 NO，不要输出任何其他内容。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=10,
            )

            content = (resp.choices[0].message.content or "").strip().upper()

            if content == "YES":
                logger.info("    🟢 LLM判定: 属于 cs.SE/cs.DC 范畴")
                return True
            if content == "NO":
                logger.info("    🔴 LLM判定: 不属于 cs.SE/cs.DC 范畴")
                return False

            logger.warning(f"    ⚠️ LLM分类输出异常: {content!r}")
            if attempt < max_retries:
                time.sleep(2 * attempt)
                continue

        except Exception as e:
            logger.warning(f"    ⚠️ LLM分类失败(第{attempt}次): {e}")
            if attempt < max_retries:
                time.sleep(2 * attempt)
                continue

    logger.warning("    ⚠️ LLM分类最终失败，默认跳过该论文")
    return False

def summarize_paper(client: OpenAI, paper: dict, model: str, language: str) -> str:
    prompt = SUMMARY_PROMPT.format(
        language=language,
        title=paper["title"],
        abstract=paper["abstract"],
    )

    max_retries = 5

    for attempt in range(1, max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"你是一位专业的 AI 学术论文分析助手。"
                            f"请用{language}输出。"
                            f"只能输出三个板块：中文标题、一句话总结、摘要中文全文。"
                            f"不要添加其他解释、前言、结尾。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=3000,
            )

            content = resp.choices[0].message.content or ""

            missing = [s for s in REQUIRED_SECTIONS if s not in content]
            if not missing:
                logger.info(f"    ✅ 总结完整 (第{attempt}次)")
                return content
            else:
                logger.warning(f"    ⚠️ 第{attempt}次不完整，缺少: {missing}")
                if attempt < max_retries:
                    time.sleep(2 * attempt)
                    continue
                else:
                    logger.warning("    ⚠️ 已达最大重试次数，使用不完整结果")
                    return content

        except Exception as e:
            err_text = str(e)
            is_rate_limit = "429" in err_text or "Too Many Requests" in err_text

            if is_rate_limit:
                wait_seconds = min(60, 5 * (2 ** (attempt - 1)))
                logger.warning(f"    ⚠️ 第{attempt}次限流: {e}")
                if attempt < max_retries:
                    logger.info(f"    ⏳ 限流退避 {wait_seconds}s")
                    time.sleep(wait_seconds)
                    continue
            else:
                logger.error(f"    ❌ 第{attempt}次失败: {e}")
                if attempt < max_retries:
                    time.sleep(3 * attempt)
                    continue

            return f"""### 📌 中文标题
生成失败

### 💡 一句话总结
总结生成失败（已重试{max_retries}次）

### 📋 摘要中文全文
错误：{e}"""

    return "⚠️ 总结生成失败"


# ══════════════════════════════════════════════════
#  5. 解析 & 构建 HTML
# ══════════════════════════════════════════════════
def extract_section(text: str, emoji_and_name: str) -> str:
    pattern = rf"###\s*{re.escape(emoji_and_name)}\s*\n+(.*?)(?=\n\s*###|\Z)"
    m = re.search(pattern, text, re.DOTALL)
    if m:
        result = m.group(1).strip()
        result = re.sub(r"^\[?\s*|\s*\]?$", "", result)
        return result
    return ""

def parse_summary(summary_text: str) -> dict:
    return {
        "chinese_title": extract_section(summary_text, "📌 中文标题"),
        "one_line": extract_section(summary_text, "💡 一句话总结"),
        "abstract_cn": extract_section(summary_text, "📋 摘要中文全文"),
    }

def highlight_keywords(text: str, keywords: list[str]) -> str:
    if not keywords:
        return text
    for kw in keywords:
        pattern = re.compile(rf"\b({re.escape(kw)})\b", re.IGNORECASE)
        text = pattern.sub(
            lambda m: (
                f'<mark style="background:#fff3cd;padding:1px 3px;'
                f'border-radius:3px;">{m.group(1)}</mark>'
            ),
            text,
        )
    return text

def text_to_html_paragraphs(text: str) -> str:
    if not text:
        return ""
    paragraphs = [p.strip() for p in text.strip().split("\n") if p.strip()]
    return "\n".join(
        f"<p style='margin:3px 0;line-height:1.5;color:#333;'>{p}</p>"
        for p in paragraphs
    )

def build_html(papers: list[dict], summaries: list[str], config: dict, cutoff_date: date, today_date: date) -> str:
    sc = config["search"]
    tz = get_search_timezone(config)
    now = datetime.now(tz)
    date_str = now.strftime("%Y年%m月%d日")
    weekday_str = WEEKDAY_NAMES.get(now.weekday(), "")

    keywords = normalize_list(sc.get("keywords", []))
    keyword_mode = sc.get("keyword_mode", "none")
    target_categories = normalize_list(sc.get("categories", []))

    if cutoff_date == today_date:
        date_range_str = f"时间窗: {today_date}"
    else:
        date_range_str = f"时间窗: {cutoff_date} ~ 至今"

    search_info_parts = [date_range_str]
    if target_categories:
        search_info_parts.append(f"分类: {', '.join(target_categories)}")
    if keyword_mode == "filter" and keywords:
        search_info_parts.append(f"过滤: {', '.join(keywords)}")
    search_info = " | ".join(search_info_parts)

    all_parsed = [parse_summary(s) for s in summaries]

    groups = {}
    for paper, parsed in zip(papers, all_parsed):
        matched_cat = "Other"
        for cat in paper["categories"]:
            if cat in target_categories:
                matched_cat = cat
                break
        groups.setdefault(matched_cat, []).append((paper, parsed))

    cat_names = {
        'cs.SE': '软件工程 (cs.SE)',
        'cs.CL': '计算与语言 (cs.CL)',
        'cs.DC': '分布式与并行计算 (cs.DC)',
        'cs.AI': '人工智能 (cs.AI)',
        'cs.LG': '机器学习 (cs.LG)',
        'Other': '其他相关论文'
    }

    group_html = ""
    sorted_cats = sorted(groups.keys(), key=lambda x: target_categories.index(x) if x in target_categories else 999)
    global_idx = 1

    for cat in sorted_cats:
        items = groups[cat]
        cat_display = cat_names.get(cat, cat)

        group_html += f"""
<details style="margin-bottom:24px;">
    <summary style="padding:8px 12px; cursor:pointer; font-size:14px; font-weight:600; color:#4a5568; background-color:#edf2f7; border-radius:6px; user-select:none; list-style:none; margin-bottom:12px;">
        🏷️ <span style="margin-left:4px;">{cat_display}</span> 
        <span style="margin-left:6px; font-size:12px; color:#718096; font-weight:normal;">({len(items)} 篇)</span>
    </summary>
    <div>
"""
        for paper, parsed in items:
            authors = ", ".join(paper["authors"][:3])
            if len(paper["authors"]) > 3:
                authors += f' 等{len(paper["authors"])}人'
            cats = ", ".join(paper["categories"][:3])

            chinese_title = parsed["chinese_title"]
            one_line = parsed["one_line"]
            abstract_cn = parsed["abstract_cn"]

            title_html = paper["title"]
            matched_kw = paper.get("matched_keywords", [])
            if matched_kw:
                title_html = highlight_keywords(title_html, matched_kw)

            kw_tags = ""
            if matched_kw:
                kw_tags = " ".join(
                    f'<span style="background:#e8f5e9;color:#2e7d32;font-size:11px;'
                    f'padding:2px 6px;border-radius:4px;margin-right:4px;">🔑 {kw}</span>'
                    for kw in matched_kw
                )
                kw_tags = f'<div style="margin-top:4px;">{kw_tags}</div>'

            cn_title_html = ""
            if chinese_title:
                cn_title_html = (
                    f'<div style="font-size:14px;color:#555;margin-top:4px;'
                    f'margin-left:36px;font-weight:500;">'
                    f'📌 {chinese_title}</div>'
                )

            one_line_html = ""
            if one_line:
                one_line_html = (
                    f'<div style="background:linear-gradient(135deg,#f0f4ff,#f5f0ff);'
                    f'border-radius:8px;padding:10px 14px;margin:8px 0 6px;'
                    f'font-size:13px;color:#333;line-height:1.5;">'
                    f'<strong style="color:#667eea;">💡 </strong>{one_line}'
                    f'</div>'
                )

            abstract_html = text_to_html_paragraphs(abstract_cn) if abstract_cn else ""
            copy_text = f"{paper['title']}\n📌 {chinese_title}\n💡 {one_line}\n🔗 {paper['url']}"

            group_html += f"""
    <div style="background:#fff;border-radius:8px;padding:16px;margin-bottom:16px;
                border:1px solid #e2e8f0; border-left:4px solid #667eea;">

        <div style="font-size:15px;font-weight:bold;color:#2d3748;margin-bottom:2px;line-height:1.4;">
            <span style="display:inline-block;background:#ebf4ff;
                         color:#4c51bf;width:24px;height:24px;border-radius:50%;text-align:center;
                         line-height:24px;font-size:12px;font-weight:bold;margin-right:6px;">{global_idx}</span>
            {title_html}
        </div>

        {cn_title_html}
        {kw_tags}

        <div style="color:#718096;font-size:11px;margin:8px 0;padding-bottom:8px;
                    border-bottom:1px dashed #edf2f7;">
            👤 {authors} &nbsp;|&nbsp; 📅 {paper['published']} &nbsp;|&nbsp; 🏷️ {cats}<br>
            🔗 <a href="{paper['url']}" style="color:#4299e1;text-decoration:none;">arXiv</a>
            &nbsp;·&nbsp;
            📄 <a href="{paper['pdf_url']}" style="color:#4299e1;text-decoration:none;">PDF</a>
        </div>

        {one_line_html}

        <details style="cursor:pointer;margin-top:6px;">
            <summary style="font-size:13px;font-weight:600;color:#667eea;
                            padding:4px 0;user-select:none;outline:none;
                            list-style:none;">
                <span>📋 展开中文摘要</span>
            </summary>
            <div style="font-size:13px;line-height:1.6;color:#4a5568;
                        margin-top:8px;padding:12px;background:#f7fafc;
                        border-radius:6px;border:1px solid #edf2f7;">
                {abstract_html}
            </div>
        </details>

        <details style="cursor:pointer;margin-top:2px;">
            <summary style="font-size:12px;font-weight:600;color:#a0aec0;
                            padding:4px 0;user-select:none;outline:none;
                            list-style:none;">
                <span>📎 复制卡片文本</span>
            </summary>
            <pre style="background:#f7fafc;border:1px solid #edf2f7;border-radius:6px;
                        padding:10px;margin-top:6px;font-size:12px;line-height:1.5;
                        font-family:Consolas,'Microsoft YaHei',monospace;
                        white-space:pre-wrap;word-wrap:break-word;
                        color:#4a5568;user-select:all;cursor:text;">{copy_text}</pre>
        </details>
    </div>"""
            global_idx += 1
        group_html += """
    </div>
</details>
"""

    style_block = """
    <style>
        details summary::-webkit-details-marker { display: none; }
        details summary::before { content: "▶ "; font-size: 11px; margin-right: 4px; color:#a0aec0; }
        details[open] summary::before { content: "▼ "; }
        details[open] summary { color: #2b6cb0 !important; }
    </style>
    """

    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
{style_block}
</head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'PingFang SC',
             'Microsoft YaHei',sans-serif;background:#f4f5f7;margin:0;padding:16px;">
<div style="max-width:780px;margin:0 auto;">

    <div style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;
                padding:24px;border-radius:10px;text-align:center;margin-bottom:20px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
        <h1 style="margin:0;font-size:22px;font-weight:700;letter-spacing:0.5px;">📚 每日 ArXiv 论文精选</h1>
        <p style="margin:8px 0 0;opacity:.9;font-size:13px;">
            {date_str} {weekday_str} · 共精选 {len(papers)} 篇论文
        </p>
        <p style="margin:6px 0 0;font-size:11px;opacity:.7;">🔍 {search_info}</p>
    </div>

    {group_html}

    <div style="text-align:center;color:#a0aec0;font-size:11px;margin-top:30px;padding:10px;">
        🤖 由 <strong>ArXiv Daily Digest</strong> 自动精选生成
    </div>
</div>
</body></html>"""

    return html


# ══════════════════════════════════════════════════
#  6. 发送邮件
# ══════════════════════════════════════════════════
def send_email(html: str, config: dict) -> bool:
    ec = config["email"]
    sender = os.environ.get("EMAIL_ADDRESS", "")
    password = os.environ.get("EMAIL_PASSWORD", "")
    to = os.environ.get("TO_EMAIL", sender)
    smtp_srv = os.environ.get("SMTP_SERVER", ec.get("smtp_server", "smtp.gmail.com"))
    smtp_port = int(os.environ.get("SMTP_PORT", ec.get("smtp_port", 587)))

    if not sender or not password:
        logger.error("❌ 未设置 EMAIL_ADDRESS 或 EMAIL_PASSWORD")
        return False

    subject = f"{ec.get('subject_prefix', '📚 论文日报')} - {datetime.now().strftime('%Y-%m-%d')}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = sender
    msg["To"] = to
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_srv, smtp_port)
        else:
            server = smtplib.SMTP(smtp_srv, smtp_port)
            server.starttls()
        server.login(sender, password)
        server.sendmail(sender, [a.strip() for a in to.split(",")], msg.as_string())
        server.quit()
        logger.info(f"✅ 邮件已成功发送至 {to}")
        return True
    except Exception as e:
        logger.error(f"❌ 邮件发送失败: {e}")
        return False


# ══════════════════════════════════════════════════
#  7. 主函数
# ══════════════════════════════════════════════════
def main():
    logger.info("=" * 60)
    logger.info("   🚀 ArXiv Daily Paper Digest (分流seen策略版) 启动")
    logger.info("=" * 60)

    config = load_config()

    # ── 阶段 1：本地极速初筛与去重 ──
    papers, cutoff_date, today_date = fetch_papers(config)

    if not papers:
        logger.warning("📭 今天没有发现符合条件的新论文，任务结束。")
        return

    # ── 阶段 2：初始化 LLM ──
    lc = config["llm"]
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", lc.get("base_url"))

    if not api_key:
        logger.error("❌ 未设置 OPENAI_API_KEY")
        sys.exit(1)

    client_kw = {"api_key": api_key}
    if base_url:
        client_kw["base_url"] = base_url

    llm = OpenAI(**client_kw)
    model = os.environ.get("LLM_MODEL", lc.get("model", "gpt-4o-mini"))
    lang = lc.get("language", "中文")
    llm_interval = int(os.environ.get("LLM_INTERVAL_SECONDS", "0"))

    logger.info(f"🤖 LLM 启动 | 模型: {model} | 语言: {lang}")

    # ── 阶段 3：LLM 学科过滤 + 总结 ──
    llm_filter_cfg = config.get("llm_filter", {})
    llm_filter_enabled = llm_filter_cfg.get("enabled", True)
    target_categories_for_llm = normalize_list(
        llm_filter_cfg.get("target_categories", ["cs.SE", "cs.DC"])
    )

    logger.info(f"📝 开始处理 {len(papers)} 篇候选论文...")
    logger.info(f"🎯 LLM目标范畴: {', '.join(target_categories_for_llm)}")

    filtered_papers = []
    summaries = []

    rejected_ids = []   # LLM判定不属于目标学科，必须写入 seen
    accepted_ids = []   # LLM判定通过，只有邮件成功后才写入 seen
    skipped_by_llm_scope = 0

    for i, p in enumerate(papers, 1):
        logger.info(f"  [{i}/{len(papers)}] {p['title'][:60]}...")

        should_summarize = True

        if llm_filter_enabled:
            if paper_in_target_categories(p, target_categories_for_llm):
                logger.info("    ✅ 官方分类命中目标范围，直接总结")
                should_summarize = True
            else:
                logger.info("    🔎 官方分类未命中目标范围，交给 LLM 二次判定")
                should_summarize = llm_category_check(llm, p, model)

        if not should_summarize:
            skipped_by_llm_scope += 1
            rejected_ids.append(p["base_id"])
            logger.info("    ⏭️ 跳过：不属于 cs.SE/cs.DC 范畴，已加入 seen 待记录")
            if i < len(papers) and llm_interval > 0:
                time.sleep(llm_interval)
            continue

        s = summarize_paper(llm, p, model, lang)
        filtered_papers.append(p)
        summaries.append(s)
        accepted_ids.append(p["base_id"])

        if i < len(papers) and llm_interval > 0:
            time.sleep(llm_interval)

    logger.info(f"📊 LLM学科过滤后保留 {len(filtered_papers)} 篇，跳过 {skipped_by_llm_scope} 篇")

    # ── 阶段 4：先记录被 LLM 拒绝的论文 ──
    if rejected_ids:
        save_seen_papers(rejected_ids)
        logger.info("🗂️ 已记录 LLM 判定不相关的论文，下次不会再重复判断")

    if not filtered_papers:
        logger.warning("📭 经过 LLM 学科过滤后，没有可发送的论文，任务结束。")
        return

    # ── 阶段 5：组装 HTML ──
    html = build_html(filtered_papers, summaries, config, cutoff_date, today_date)

    os.makedirs("output", exist_ok=True)
    out_path = f"output/digest_{today_date.strftime('%Y%m%d')}.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"💾 网页副本已保存至 {out_path}")

    # ── 阶段 6：发送邮件 ──
    if send_email(html, config):
        save_seen_papers(accepted_ids)
        logger.info("📬 邮件发送成功，已记录本次成功发送的论文 ID")
    else:
        logger.error("🚨 邮件发送失败！本次准备发送的论文不会写入 seen，下次会重试。")

    logger.info("🎉 全部流程执行完毕！")


if __name__ == "__main__":
    main()