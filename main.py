#!/usr/bin/env python3
"""
ArXiv Daily Paper Digest
抓取 arXiv 论文 → LLM 翻译总结 → 邮件推送

调度逻辑：
  - 每天凌晨运行，抓取「昨天」的论文
  - 周日、周一自动跳过（arXiv 周末不更新）
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

# arXiv 不更新的日子：周六(5) 和 周日(6)
# 因此，次日（周日和周一）没有新论文可抓
ARXIV_NO_UPDATE_NEXT_DAYS = {0, 6}  # 周一(0)=前天是周六无更新, 周日(6)=前天是周五但昨天周六无更新
# 更准确地说：周日跳过是因为昨天(周六)arXiv没更新；周一跳过是因为昨天(周日)arXiv没更新


# ══════════════════════════════════════════════════
#  1. 加载配置 & 工具函数
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


# ══════════════════════════════════════════════════
#  2. ★ 调度判断：今天是否应该运行
# ══════════════════════════════════════════════════
def should_run_today(config: dict) -> tuple[bool, str]:
    """
    判断今天是否应该运行

    返回: (是否运行, 原因说明)

    逻辑：
      - 周日跳过：昨天是周六，arXiv 不更新
      - 周一跳过：昨天是周日，arXiv 不更新
      - 其他日子正常运行
    """
    sc = config.get("search", {})
    skip_enabled = sc.get("skip_no_arxiv_days", True)

    # 如果没开启跳过，始终运行
    if not skip_enabled:
        return True, "skip_no_arxiv_days 未开启，始终运行"

    # 环境变量强制运行（手动触发时可用）
    force_run = os.environ.get("FORCE_RUN", "false").lower()
    if force_run == "true":
        return True, "FORCE_RUN=true，强制运行"

    tz = get_search_timezone(config)
    now = datetime.now(tz)
    weekday = now.weekday()  # 0=周一, 6=周日
    day_name = WEEKDAY_NAMES.get(weekday, str(weekday))

    if weekday == 6:  # 周日
        return False, f"今天是{day_name}，昨天(周六)arXiv 不更新，跳过"
    elif weekday == 0:  # 周一
        return False, f"今天是{day_name}，昨天(周日)arXiv 不更新，跳过"
    else:
        return True, f"今天是{day_name}，正常运行"


# ══════════════════════════════════════════════════
#  3. ★ 计算目标日期范围
# ══════════════════════════════════════════════════
def get_target_date_range(config: dict) -> tuple[date, date]:
    """
    根据 fetch_mode 计算要抓取的日期范围 [start_date, end_date]

    fetch_mode:
      - "yesterday": 只抓昨天
      - "today":     只抓今天
      - "custom":    使用 days_back
    """
    sc = config.get("search", {})
    tz = get_search_timezone(config)
    now = datetime.now(tz)
    today = now.date()

    fetch_mode = sc.get("fetch_mode", "yesterday")

    if fetch_mode == "yesterday":
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday

    elif fetch_mode == "today":
        return today, today

    elif fetch_mode == "custom":
        days_back = int(os.environ.get("DAYS_BACK", sc.get("days_back", 1)))
        start = today - timedelta(days=days_back)
        return start, today

    else:
        logger.warning(f"⚠️ 未知 fetch_mode: {fetch_mode}，默认使用 yesterday")
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday


# ══════════════════════════════════════════════════
#  4. 抓取 arXiv 论文
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
    return [kw for kw in keywords if kw.lower() in text]


def fetch_papers(config: dict) -> list[dict]:
    sc = config["search"]

    keywords = normalize_list(sc.get("keywords", []))
    categories = normalize_list(sc.get("categories", []))
    max_papers = int(sc.get("max_papers", 10))
    keyword_mode = sc.get("keyword_mode", "none")
    tz = get_search_timezone(config)

    query = build_query(keywords, categories, keyword_mode)

    # ★ 使用新的日期范围计算
    start_date, end_date = get_target_date_range(config)

    logger.info(f"🔍 arXiv query: {query}")
    logger.info(f"📅 目标日期范围 ({tz}): {start_date} ~ {end_date}")
    logger.info(f"🔧 关键字模式: {keyword_mode}")
    logger.info(f"📌 最大论文数: {max_papers}")
    if keyword_mode == "filter" and keywords:
        logger.info(f"🔑 本地过滤关键字: {keywords}")

    fetch_limit = max(300, max_papers * (20 if keyword_mode == "filter" else 10))
    logger.info(f"📥 API 最大抓取数: {fetch_limit}")

    search = arxiv.Search(
        query=query,
        max_results=fetch_limit,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    client = arxiv.Client(page_size=100, delay_seconds=3.0, num_retries=3)

    seen = set()
    papers = []

    skipped_by_date = 0
    skipped_by_keyword = 0
    skipped_by_duplicate = 0
    total_scanned = 0

    for result in client.results(search):
        total_scanned += 1

        pid = result.entry_id
        if pid in seen:
            skipped_by_duplicate += 1
            continue
        seen.add(pid)

        pub = result.published
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)

        pub_local = pub.astimezone(tz)
        pub_date = pub_local.date()

        # ★ 精确日期范围过滤
        if pub_date > end_date:
            # 比目标范围还新，跳过（理论上不太会出现）
            continue

        if pub_date < start_date:
            skipped_by_date += 1
            logger.info(
                f"⏹️ 遇到早于目标范围的论文，停止: {pub_date} < {start_date}"
            )
            break

        paper = {
            "title": result.title.replace("\n", " "),
            "abstract": result.summary.replace("\n", " "),
            "authors": [a.name for a in result.authors],
            "published": pub_local.strftime("%Y-%m-%d"),
            "updated": (
                result.updated.astimezone(tz).strftime("%Y-%m-%d")
                if result.updated
                else ""
            ),
            "url": result.entry_id,
            "pdf_url": result.pdf_url,
            "categories": result.categories,
            "matched_keywords": [],
        }

        if keyword_mode == "filter" and keywords:
            matched = keyword_matches(paper, keywords)
            if not matched:
                skipped_by_keyword += 1
                continue
            paper["matched_keywords"] = matched

        papers.append(paper)
        logger.info(f"  ✅ 收录: {paper['published']} | {paper['title'][:80]}")

        if len(papers) >= max_papers:
            logger.info(f"📌 已达到 max_papers={max_papers} 上限")
            break

    logger.info(
        f"📊 扫描统计: 总扫描={total_scanned}, "
        f"跳过(日期)={skipped_by_date}, "
        f"跳过(关键字)={skipped_by_keyword}, "
        f"跳过(重复)={skipped_by_duplicate}"
    )
    logger.info(f"✅ 最终获取 {len(papers)} 篇论文")

    return papers


# ══════════════════════════════════════════════════
#  5. LLM 翻译 & 总结
# ══════════════════════════════════════════════════
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
                logger.info(f"  ✅ 总结完整 (第{attempt}次)")
                return content
            else:
                logger.warning(f"  ⚠️ 第{attempt}次不完整，缺少: {missing}")
                if attempt < max_retries:
                    time.sleep(2 * attempt)
                    continue
                else:
                    logger.warning("  ⚠️ 已达最大重试次数，使用不完整结果")
                    return content

        except Exception as e:
            err_text = str(e)
            is_rate_limit = "429" in err_text or "Too Many Requests" in err_text

            if is_rate_limit:
                wait_seconds = min(60, 5 * (2 ** (attempt - 1)))
                logger.warning(f"  ⚠️ 第{attempt}次限流: {e}")
                if attempt < max_retries:
                    logger.info(f"  ⏳ 限流退避 {wait_seconds}s")
                    time.sleep(wait_seconds)
                    continue
            else:
                logger.error(f"  ❌ 第{attempt}次失败: {e}")
                if attempt < max_retries:
                    time.sleep(3 * attempt)
                    continue

            return f"""### 📌 中文标题\n生成失败\n\n### 💡 一句话总结\n总结生成失败（已重试{max_retries}次）\n\n### 📋 摘要中文全文\n错误：{e}"""

    return "⚠️ 总结生成失败"


# ══════════════════════════════════════════════════
#  6. 解析 & 构建 HTML
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
        pattern = re.compile(re.escape(kw), re.IGNORECASE)
        text = pattern.sub(
            lambda m: (
                f'<mark style="background:#fff3cd;padding:1px 3px;'
                f'border-radius:3px;">{m.group()}</mark>'
            ),
            text,
        )
    return text


def text_to_html_paragraphs(text: str) -> str:
    if not text:
        return ""
    paragraphs = [p.strip() for p in text.strip().split("\n") if p.strip()]
    if not paragraphs:
        return ""
    return "\n".join(
        f"<p style='margin:6px 0;line-height:1.85;color:#333;'>{p}</p>"
        for p in paragraphs
    )


def build_html(papers: list[dict], summaries: list[str], config: dict) -> str:
    sc = config["search"]
    tz = get_search_timezone(config)
    now = datetime.now(tz)
    date_str = now.strftime("%Y年%m月%d日")
    weekday_str = WEEKDAY_NAMES.get(now.weekday(), "")

    keywords = normalize_list(sc.get("keywords", []))
    keyword_mode = sc.get("keyword_mode", "none")
    categories = normalize_list(sc.get("categories", []))
    fetch_mode = sc.get("fetch_mode", "yesterday")

    # ★ 显示实际抓取的目标日期
    start_date, end_date = get_target_date_range(config)
    if start_date == end_date:
        date_range_str = f"论文日期: {start_date}"
    else:
        date_range_str = f"论文日期: {start_date} ~ {end_date}"

    search_info_parts = [date_range_str]
    if categories:
        search_info_parts.append(f"分类: {', '.join(categories)}")
    if keyword_mode == "filter" and keywords:
        search_info_parts.append(f"过滤: {', '.join(keywords)}")
    search_info = " | ".join(search_info_parts)

    cards = ""
    for i, (p, s) in enumerate(zip(papers, summaries), 1):
        authors = ", ".join(p["authors"][:3])
        if len(p["authors"]) > 3:
            authors += f' 等{len(p["authors"])}人'
        cats = ", ".join(p["categories"][:3])

        parsed = parse_summary(s)
        chinese_title = parsed["chinese_title"]
        one_line = parsed["one_line"]
        abstract_cn = parsed["abstract_cn"]

        title_html = p["title"]
        matched_kw = p.get("matched_keywords", [])
        if matched_kw:
            title_html = highlight_keywords(title_html, matched_kw)

        kw_tags = ""
        if matched_kw:
            kw_tags = " ".join(
                f'<span style="background:#e8f5e9;color:#2e7d32;font-size:11px;'
                f'padding:2px 6px;border-radius:4px;margin-right:4px;">🔑 {kw}</span>'
                for kw in matched_kw
            )
            kw_tags = f'<div style="margin-top:6px;">{kw_tags}</div>'

        cn_title_html = ""
        if chinese_title:
            cn_title_html = (
                f'<div style="font-size:15px;color:#555;margin-top:6px;'
                f'margin-left:36px;font-weight:500;">'
                f'📌 {chinese_title}</div>'
            )

        one_line_html = ""
        if one_line:
            one_line_html = (
                f'<div style="background:linear-gradient(135deg,#f0f4ff,#f5f0ff);'
                f'border-radius:8px;padding:12px 16px;margin:14px 0 10px;'
                f'font-size:14px;color:#333;line-height:1.6;">'
                f'<strong style="color:#667eea;">💡 一句话总结：</strong>{one_line}'
                f'</div>'
            )

        abstract_html = ""
        if abstract_cn:
            abstract_html = text_to_html_paragraphs(abstract_cn)

        cards += f"""
    <div style="background:#fff;border-radius:12px;padding:24px;margin-bottom:20px;
                box-shadow:0 2px 12px rgba(0,0,0,0.08);border-left:4px solid #667eea;">

        <div style="font-size:17px;font-weight:bold;color:#1a1a2e;margin-bottom:2px;">
            <span style="display:inline-block;background:linear-gradient(135deg,#667eea,#764ba2);
                         color:#fff;width:28px;height:28px;border-radius:50%;text-align:center;
                         line-height:28px;font-size:13px;font-weight:bold;margin-right:8px;">{i}</span>
            {title_html}
        </div>

        {cn_title_html}
        {kw_tags}

        <div style="color:#888;font-size:12px;margin-bottom:14px;padding-bottom:12px;
                    border-bottom:1px solid #f0f0f0;margin-top:10px;">
            👤 {authors} &nbsp;|&nbsp; 📅 {p['published']} &nbsp;|&nbsp; 🏷️ {cats}<br>
            🔗 <a href="{p['url']}" style="color:#667eea;text-decoration:none;">arXiv</a>
            &nbsp;·&nbsp;
            📄 <a href="{p['pdf_url']}" style="color:#667eea;text-decoration:none;">PDF</a>
        </div>

        {one_line_html}

        <details style="cursor:pointer;margin-top:8px;">
            <summary style="font-size:14px;font-weight:600;color:#667eea;
                            padding:8px 0;user-select:none;outline:none;
                            list-style:none;">
                <span style="display:inline-flex;align-items:center;gap:6px;">
                    📋 展开摘要全文
                </span>
            </summary>
            <div style="font-size:14px;line-height:1.8;color:#333;
                        margin-top:12px;padding:14px;background:#fafbfc;
                        border-radius:8px;border:1px solid #f0f0f0;">
                {abstract_html}
            </div>
        </details>
    </div>"""

    style_block = """
    <style>
        details summary::-webkit-details-marker { display: none; }
        details summary::before {
            content: "▶ ";
            font-size: 12px;
            margin-right: 4px;
        }
        details[open] summary::before {
            content: "▼ ";
        }
        details[open] summary {
            color: #764ba2 !important;
        }
    </style>
    """

    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
{style_block}
</head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'PingFang SC',
             'Microsoft YaHei',sans-serif;background:#f4f5f7;margin:0;padding:20px;">
<div style="max-width:780px;margin:0 auto;">

    <div style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;
                padding:36px 32px;border-radius:12px;text-align:center;margin-bottom:24px;">
        <h1 style="margin:0;font-size:28px;font-weight:700;">📚 每日 ArXiv 论文精选</h1>
        <p style="margin:12px 0 0;opacity:.9;font-size:16px;">
            {date_str} {weekday_str} · 共 {len(papers)} 篇论文
        </p>
        <p style="margin:8px 0 0;font-size:12px;opacity:.65;">🔍 {search_info}</p>
    </div>

    {cards}

    <div style="text-align:center;color:#aaa;font-size:11px;margin-top:30px;padding:16px;">
        🤖 由 <strong>ArXiv Daily Digest</strong> 自动生成<br>
        Powered by GitHub Actions + LLM
    </div>
</div>
</body></html>"""

    return html


# ══════════════════════════════════════════════════
#  7. 发送邮件
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
        logger.info(f"✅ 邮件已发送至 {to}")
        return True
    except Exception as e:
        logger.error(f"❌ 邮件发送失败: {e}")
        return False


# ══════════════════════════════════════════════════
#  8. ★ 主函数（含调度判断）
# ══════════════════════════════════════════════════
def main():
    logger.info("=" * 55)
    logger.info("   📚 ArXiv Daily Paper Digest — 启动")
    logger.info("=" * 55)

    config = load_config()
    tz = get_search_timezone(config)
    now = datetime.now(tz)

    logger.info(f"⏰ 当前时间: {now.strftime('%Y-%m-%d %H:%M %Z')} ({WEEKDAY_NAMES.get(now.weekday(), '')})")

    # ── ★ Step 0: 检查今天是否应该运行 ──
    run_ok, reason = should_run_today(config)
    logger.info(f"📋 调度判断: {reason}")

    if not run_ok:
        logger.info("🛌 今天不需要运行，退出")
        logger.info("=" * 55)
        return

    # ── Step 1: 计算目标日期 ──
    start_date, end_date = get_target_date_range(config)
    logger.info(f"🎯 抓取目标: {start_date} ~ {end_date}")

    # ── Step 2: 抓取论文 ──
    papers = fetch_papers(config)

    if not papers:
        logger.warning("📭 未找到匹配的论文")
        sc = config["search"]
        keyword_mode = sc.get("keyword_mode", "none")

        info_text = f"分类: {', '.join(normalize_list(sc.get('categories', [])))}"
        info_text += f"<br>目标日期: {start_date} ~ {end_date}"
        if keyword_mode == "filter":
            info_text += f"<br>关键词过滤: {', '.join(normalize_list(sc.get('keywords', [])))}"

        empty_html = f"""<html><body style="font-family:Arial;padding:40px;text-align:center;">
        <h2>📭 {start_date} 暂无匹配论文</h2>
        <p>{info_text}</p>
        <p style="color:#999;font-size:12px;">arXiv 周末不更新，节假日也可能延迟</p>
        </body></html>"""
        send_email(empty_html, config)
        return

    # ── Step 3: LLM 总结 ──
    lc = config["llm"]
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", lc.get("base_url"))

    if not api_key:
        logger.error("❌ 未设置 OPENAI_API_KEY")
        sys.exit(1)

    client_kw = {"api_key": api_key}
    if base_url:
        client_kw["base_url"] = base_url
        logger.info(f"🔗 使用自定义 API: {base_url}")

    llm = OpenAI(**client_kw)
    model = lc.get("model", "gpt-4o-mini")
    lang = lc.get("language", "中文")

    logger.info(f"🤖 模型: {model}, 语言: {lang}")
    logger.info(f"📝 开始处理 {len(papers)} 篇论文...")

    summaries = []
    llm_interval = int(os.environ.get("LLM_INTERVAL_SECONDS", "5"))

    for i, p in enumerate(papers, 1):
        logger.info(f"  [{i}/{len(papers)}] {p['title'][:60]}...")
        s = summarize_paper(llm, p, model, lang)
        summaries.append(s)

        if i < len(papers):
            logger.info(f"  ⏳ 等待 {llm_interval}s")
            time.sleep(llm_interval)

    # ── Step 4: 生成 HTML ──
    html = build_html(papers, summaries, config)

    os.makedirs("output", exist_ok=True)
    out_path = f"output/digest_{start_date.strftime('%Y%m%d')}.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"💾 已保存至 {out_path}")

    # ── Step 5: 发送邮件 ──
    send_email(html, config)

    logger.info("🎉 全部完成！")


if __name__ == "__main__":
    main()