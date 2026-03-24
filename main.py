def build_html(papers: list[dict], summaries: list[str], config: dict) -> str:
    sc = config["search"]
    tz = get_search_timezone(config)
    now = datetime.now(tz)
    date_str = now.strftime("%Y年%m月%d日")
    weekday_str = WEEKDAY_NAMES.get(now.weekday(), "")

    keywords = normalize_list(sc.get("keywords", []))
    keyword_mode = sc.get("keyword_mode", "none")
    categories = normalize_list(sc.get("categories", []))

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

        # ★ 把复制数据转义后存进 data 属性
        safe_title = p["title"].replace('"', '&quot;').replace("'", "&#39;")
        safe_cn_title = chinese_title.replace('"', '&quot;').replace("'", "&#39;")
        safe_one_line = one_line.replace('"', '&quot;').replace("'", "&#39;")
        safe_url = p["url"].replace('"', '&quot;')

        cards += f"""
    <div class="paper-card" style="background:#fff;border-radius:12px;padding:24px;margin-bottom:20px;
                box-shadow:0 2px 12px rgba(0,0,0,0.08);border-left:4px solid #667eea;">

        <!-- ★ 复选框 + 英文标题 -->
        <div style="display:flex;align-items:flex-start;gap:10px;margin-bottom:2px;">
            <input type="checkbox" class="paper-cb" id="cb-{i}"
                   data-index="{i}"
                   data-title="{safe_title}"
                   data-cn-title="{safe_cn_title}"
                   data-one-line="{safe_one_line}"
                   data-url="{safe_url}"
                   onchange="updateCounter()"
                   style="width:20px;height:20px;margin-top:3px;cursor:pointer;
                          accent-color:#667eea;flex-shrink:0;">
            <div style="font-size:17px;font-weight:bold;color:#1a1a2e;">
                <span style="display:inline-block;background:linear-gradient(135deg,#667eea,#764ba2);
                             color:#fff;width:28px;height:28px;border-radius:50%;text-align:center;
                             line-height:28px;font-size:13px;font-weight:bold;margin-right:8px;">{i}</span>
                {title_html}
            </div>
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

    # ★ CSS + 浮动工具栏
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

        /* 复选框选中时卡片高亮 */
        .paper-card.selected {
            border-left-color: #4caf50 !important;
            background: #f8fff8 !important;
        }

        /* 浮动工具栏 */
        .copy-toolbar {
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: #fff;
            padding: 12px 24px;
            border-radius: 50px;
            box-shadow: 0 4px 20px rgba(102,126,234,0.5);
            display: flex;
            align-items: center;
            gap: 16px;
            z-index: 999;
            font-size: 14px;
        }
        .copy-toolbar button {
            background: rgba(255,255,255,0.2);
            color: #fff;
            border: 1px solid rgba(255,255,255,0.3);
            padding: 8px 16px;
            border-radius: 25px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 600;
            transition: all 0.2s;
        }
        .copy-toolbar button:hover {
            background: rgba(255,255,255,0.35);
        }
        .copy-toolbar button:active {
            transform: scale(0.95);
        }
        .copy-toolbar .counter {
            font-size: 13px;
            opacity: 0.9;
            min-width: 80px;
            text-align: center;
        }

        /* 复制成功提示 */
        .copy-toast {
            position: fixed;
            top: 20px;
            left: 50%;
            transform: translateX(-50%) translateY(-100px);
            background: #4caf50;
            color: #fff;
            padding: 12px 28px;
            border-radius: 8px;
            font-size: 15px;
            font-weight: 600;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
            z-index: 9999;
            transition: transform 0.3s ease;
        }
        .copy-toast.show {
            transform: translateX(-50%) translateY(0);
        }
    </style>
    """

    # ★ JavaScript
    script_block = """
    <script>
    function updateCounter() {
        const cbs = document.querySelectorAll('.paper-cb');
        const checked = document.querySelectorAll('.paper-cb:checked');
        const counter = document.getElementById('select-counter');
        const selectAllCb = document.getElementById('select-all');

        counter.textContent = '已选 ' + checked.length + ' / ' + cbs.length + ' 篇';

        // 卡片高亮
        cbs.forEach(cb => {
            const card = cb.closest('.paper-card');
            if (cb.checked) {
                card.classList.add('selected');
            } else {
                card.classList.remove('selected');
            }
        });

        // 全选按钮状态
        selectAllCb.checked = (checked.length === cbs.length);
        selectAllCb.indeterminate = (checked.length > 0 && checked.length < cbs.length);
    }

    function toggleAll() {
        const selectAll = document.getElementById('select-all');
        const cbs = document.querySelectorAll('.paper-cb');
        cbs.forEach(cb => { cb.checked = selectAll.checked; });
        updateCounter();
    }

    function copySelected() {
        const checked = document.querySelectorAll('.paper-cb:checked');
        if (checked.length === 0) {
            showToast('⚠️ 请先勾选要复制的论文', '#ff9800');
            return;
        }

        let text = '';
        checked.forEach((cb, idx) => {
            const i = cb.dataset.index;
            const title = cb.dataset.title;
            const cnTitle = cb.dataset.cnTitle;
            const oneLine = cb.dataset.oneLine;
            const url = cb.dataset.url;

            if (idx > 0) text += '\\n---\\n\\n';
            text += i + '. ' + title + '\\n';
            if (cnTitle) text += '📌 ' + cnTitle + '\\n';
            if (oneLine) text += '💡 ' + oneLine + '\\n';
            text += '🔗 ' + url + '\\n';
        });

        navigator.clipboard.writeText(text).then(() => {
            showToast('✅ 已复制 ' + checked.length + ' 篇论文信息');
        }).catch(() => {
            // fallback
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.left = '-9999px';
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
            showToast('✅ 已复制 ' + checked.length + ' 篇论文信息');
        });
    }

    function showToast(msg, color) {
        const toast = document.getElementById('copy-toast');
        toast.textContent = msg;
        toast.style.background = color || '#4caf50';
        toast.classList.add('show');
        setTimeout(() => { toast.classList.remove('show'); }, 2500);
    }

    // 初始化计数器
    document.addEventListener('DOMContentLoaded', updateCounter);
    </script>
    """

    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
{style_block}
</head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'PingFang SC',
             'Microsoft YaHei',sans-serif;background:#f4f5f7;margin:0;padding:20px;padding-bottom:80px;">
<div style="max-width:780px;margin:0 auto;">

    <!-- 头部 -->
    <div style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;
                padding:36px 32px;border-radius:12px;text-align:center;margin-bottom:24px;">
        <h1 style="margin:0;font-size:28px;font-weight:700;">📚 每日 ArXiv 论文精选</h1>
        <p style="margin:12px 0 0;opacity:.9;font-size:16px;">
            {date_str} {weekday_str} · 共 {len(papers)} 篇论文
        </p>
        <p style="margin:8px 0 0;font-size:12px;opacity:.65;">🔍 {search_info}</p>
    </div>

    <!-- 论文卡片 -->
    {cards}

    <!-- 尾部 -->
    <div style="text-align:center;color:#aaa;font-size:11px;margin-top:30px;padding:16px;">
        🤖 由 <strong>ArXiv Daily Digest</strong> 自动生成<br>
        Powered by GitHub Actions + LLM
    </div>
</div>

<!-- ★ 浮动工具栏 -->
<div class="copy-toolbar">
    <label style="display:flex;align-items:center;gap:6px;cursor:pointer;">
        <input type="checkbox" id="select-all" onchange="toggleAll()"
               style="width:18px;height:18px;accent-color:#fff;cursor:pointer;">
        <span>全选</span>
    </label>
    <span class="counter" id="select-counter">已选 0 / {len(papers)} 篇</span>
    <button onclick="copySelected()">📋 复制选中</button>
</div>

<!-- ★ 复制成功提示 -->
<div class="copy-toast" id="copy-toast"></div>

{script_block}
</body></html>"""

    return html