#!/usr/bin/env python3
"""從臉書粉專匯出檔（fb-export/）產生網站文章頁。

用法：python3 generate.py
輸入：../fb-export/this_profile's_activity_across_facebook/posts/profile_posts_1.json
輸出：articles/*.html（含分類頁 cat-*.html、標籤頁 tag-*.html）、articles/index.html、
      index.html、images/posts/ 媒體檔
"""
import json
import html
import shutil
import datetime
from pathlib import Path

SITE = Path(__file__).parent
EXPORT = SITE.parent / "fb-export"
POSTS_JSON = EXPORT / "this_profile's_activity_across_facebook/posts/profile_posts_1.json"
MEDIA_OUT = SITE / "images/posts"
ARTICLES = SITE / "articles"

SITE_URL = "https://erictcssh-ui.github.io"  # 換自有網域時改這裡再重跑
SITE_TITLE = "中醫師 黃彥鈞"
SUBTITLE = "中醫徒手・內針傷整合・精準全人醫療"
FOOTER = "© 2026 中醫師 黃彥鈞・本站內容為衛教知識分享，不能取代實際診療"

# 時效性門診公告（停診、時段異動）：不留存（2026-07-17 醫師指示）
ANNOUNCE_WORDS = ["停診", "休診", "門診時間異動", "門診異動", "看診時間調整", "診所公告"]

# 大分類：依關鍵字命中數計分，取最高分；都沒中歸「隨筆」
CATEGORIES = [
    ("醫案分享", ["診間", "患者", "病人", "個案", "來診", "主訴", "治療後", "復診", "初診"]),
    ("課程與進修", ["工作坊", "課程", "學員", "講師", "研習", "助教", "上課", "進修",
                    "筆記", "Module", "SCS", "CounterStrain", "Scar work", "PAK", "研討"]),
    ("中醫衛教", ["衛教", "保養", "建議", "日常", "飲食", "睡眠", "中暑", "養生", "預防", "注意"]),
]
FALLBACK_CATEGORY = "隨筆"

# 主題標籤（可多個）：對搜尋最有價值的症狀／主題入口
TAGS = {
    "下背痛": ["下背痛", "腰痛"],
    "頭痛・偏頭痛": ["偏頭痛", "頭痛"],
    "耳鳴": ["耳鳴"],
    "膝蓋痛": ["膝蓋痛", "膝痛"],
    "肩頸・落枕": ["肩頸", "落枕", "頸椎"],
    "骨盆・薦髂關節": ["骨盆", "薦髂"],
    "乾針": ["乾針"],
    "徒手治療": ["徒手"],
    "疤痕鬆解": ["疤痕"],
    "顱頸整合": ["顱頸", "顱初"],
    "美顏針": ["美顏針", "F.A.C.E"],
    "腸胃・胃食道逆流": ["胃食道逆流", "脹氣", "腸胃", "胃痛"],
    "鼻炎・過敏": ["鼻炎", "過敏", "鼻塞"],
    "婦科・產後": ["經痛", "月經", "產後", "孕"],
    "皮膚": ["皮膚癢", "蕁麻疹", "濕疹"],
    "失眠": ["失眠"],
    "表面解剖": ["表面解剖"],
    "經典・內經": ["黃帝內經", "內經", "傷寒論", "經方"],
}


def fix(s):
    """臉書匯出檔的 UTF-8 被誤存成 latin-1，逐字串修正。"""
    if isinstance(s, str):
        try:
            return s.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return s
    if isinstance(s, list):
        return [fix(x) for x in s]
    if isinstance(s, dict):
        return {k: fix(v) for k, v in s.items()}
    return s


def get_text(post):
    for d in post.get("data", []):
        if "post" in d:
            return d["post"].strip()
    return ""


def get_media(post):
    """回傳 [(uri, is_video), ...]"""
    out = []
    for att in post.get("attachments", []):
        for a in att.get("data", []):
            m = a.get("media")
            if m and m.get("uri"):
                uri = m["uri"]
                out.append((uri, uri.lower().endswith((".mp4", ".mov"))))
    return out


def classify(text):
    best, best_score = FALLBACK_CATEGORY, 0
    for name, words in CATEGORIES:
        score = sum(1 for w in words if w in text)
        if score > best_score:
            best, best_score = name, score
    return best


def find_tags(text):
    return [name for name, words in TAGS.items() if any(w in text for w in words)]


def make_title(text, date):
    first = text.split("\n", 1)[0].strip()
    # 展開全形括號標題【...】
    if first.startswith("【") and "】" in first:
        first = first[1 : first.index("】")].strip()
    if len(first) > 40:
        first = first[:40] + "…"
    return first or f"{date} 貼文"


def paragraphs(text):
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    out = []
    for b in blocks:
        out.append("<p>" + html.escape(b).replace("\n", "<br>\n") + "</p>")
    return "\n".join(out)


def page(title, body, css_prefix="../", current="articles", desc=None):
    nav = {
        "index": ("../index.html" if css_prefix == "../" else "index.html", "首頁"),
        "articles": (
            "index.html" if css_prefix == "../" else "articles/index.html",
            "文章",
        ),
        "clinic": (
            "../clinic.html" if css_prefix == "../" else "clinic.html",
            "門診資訊",
        ),
        "about": ("../about.html" if css_prefix == "../" else "about.html", "關於醫師"),
    }
    cur_attr = ' aria-current="page"'
    nav_html = "\n      ".join(
        f'<a href="{href}"{cur_attr if key == current else ""}>{label}</a>'
        for key, (href, label) in nav.items()
    )
    desc_tag = (
        f'\n  <meta name="description" content="{html.escape(desc)}">' if desc else ""
    )
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}｜{SITE_TITLE}</title>{desc_tag}
  <link rel="stylesheet" href="{css_prefix}css/style.css">
</head>
<body>
  <header class="site-header">
    <h1 class="site-title"><a href="{'../' if css_prefix == '../' else ''}index.html">{SITE_TITLE}</a></h1>
    <p class="site-subtitle">{SUBTITLE}</p>
    <nav class="site-nav">
      {nav_html}
    </nav>
  </header>

  <main>
{body}
  </main>

  <footer class="site-footer">
    {FOOTER}
  </footer>
</body>
</html>
"""


def chip_links(category=None, tags=(), prefix=""):
    parts = []
    if category:
        parts.append(f'<a class="tag" href="{prefix}cat-{category}.html">{category}</a>')
    for t in tags:
        parts.append(f'<a class="tag" href="{prefix}tag-{t}.html">{t}</a>')
    return "".join(parts)


def listing_items(entries, link_prefix=""):
    out = []
    for e in entries:
        out.append(
            f"""      <li>
        <a href="{link_prefix}{e['slug']}.html">{html.escape(e['title'])}</a>
        <span class="meta">{e['date']}{chip_links(e['category'], e['tags'], prefix=link_prefix)}</span>
        <p class="excerpt">{html.escape(e['excerpt'])}</p>
      </li>"""
        )
    return "\n".join(out)


def listing_page(title, entries, intro=""):
    body = [f"    <h1>{html.escape(title)}</h1>"]
    if intro:
        body.append(f"    <p>{intro}</p>")
    by_year = {}
    for e in entries:
        by_year.setdefault(e["date"][:4], []).append(e)
    for year in sorted(by_year, reverse=True):
        body.append(f"    <h2>{year} 年（{len(by_year[year])} 篇）</h2>")
        body.append('    <ul class="article-list">')
        body.append(listing_items(by_year[year]))
        body.append("    </ul>")
    return "\n".join(body)


def main():
    with open(POSTS_JSON) as f:
        posts = fix(json.load(f))

    MEDIA_OUT.mkdir(parents=True, exist_ok=True)
    ARTICLES.mkdir(exist_ok=True)

    entries = []
    skipped = 0
    day_counter = {}

    for post in sorted(posts, key=lambda p: p.get("timestamp", 0)):
        ts = post.get("timestamp")
        text = get_text(post)
        media = get_media(post)
        # 沒有文字的貼文（無字幕影片/純照片）不收錄：網站上只會是空卡片
        if not ts or not text:
            skipped += 1
            continue
        # 轉發類貼文一律略過（多為他人文字，無留存意義）
        if "shared" in post.get("title", "").lower():
            skipped += 1
            continue
        # 時效性門診公告（短篇且含停診/異動等字樣）不留存
        if text and len(text) < 300 and any(w in text for w in ANNOUNCE_WORDS):
            skipped += 1
            continue
        date = datetime.date.fromtimestamp(ts).isoformat()
        day_counter[date] = day_counter.get(date, 0) + 1
        slug = f"post-{date}" + (
            f"-{day_counter[date]}" if day_counter[date] > 1 else ""
        )
        title = make_title(text, date)
        excerpt = text.replace("\n", " ")[:80] + ("…" if len(text) > 80 else "")
        category = classify(text)
        tags = find_tags(text)

        media_html = []
        for uri, is_video in media:
            src = EXPORT / uri
            if not src.exists():
                continue
            dest = MEDIA_OUT / src.name
            if not dest.exists():
                shutil.copy2(src, dest)
            rel = f"../images/posts/{src.name}"
            if is_video:
                media_html.append(
                    f'<video controls preload="metadata" src="{rel}"></video>'
                )
            else:
                media_html.append(f'<img src="{rel}" alt="" loading="lazy">')

        body = f"""    <article class="post">
      <h1>{html.escape(title)}</h1>
      <p class="post-meta">{date}　{chip_links(category, tags)}</p>
{paragraphs(text)}
{chr(10).join(media_html)}
    </article>"""
        (ARTICLES / f"{slug}.html").write_text(
            page(title, body, desc=excerpt), encoding="utf-8"
        )
        entries.append(
            dict(date=date, slug=slug, title=title, excerpt=excerpt,
                 category=category, tags=tags)
        )

    entries.sort(key=lambda e: e["date"], reverse=True)

    # 分類頁
    cat_names = [c[0] for c in CATEGORIES] + [FALLBACK_CATEGORY]
    cat_counts = {}
    for name in cat_names:
        subset = [e for e in entries if e["category"] == name]
        cat_counts[name] = len(subset)
        if not subset:
            continue
        (ARTICLES / f"cat-{name}.html").write_text(
            page(
                f"{name}（分類）",
                listing_page(f"分類：{name}", subset),
                desc=f"黃彥鈞中醫師「{name}」分類文章，共 {len(subset)} 篇。",
            ),
            encoding="utf-8",
        )

    # 標籤頁
    tag_counts = {}
    for name in TAGS:
        subset = [e for e in entries if name in e["tags"]]
        tag_counts[name] = len(subset)
        if not subset:
            continue
        (ARTICLES / f"tag-{name}.html").write_text(
            page(
                f"{name}（主題）",
                listing_page(f"主題：{name}", subset),
                desc=f"黃彥鈞中醫師關於「{name}」的文章，共 {len(subset)} 篇。",
            ),
            encoding="utf-8",
        )

    # 文章總列表：分類導覽＋主題標籤雲＋年份列表
    nav_cats = "".join(
        f'<a class="tag" href="cat-{n}.html">{n}（{cat_counts[n]}）</a>'
        for n in cat_names if cat_counts[n]
    )
    nav_tags = "".join(
        f'<a class="tag" href="tag-{n}.html">{n}（{c}）</a>'
        for n, c in sorted(tag_counts.items(), key=lambda x: -x[1]) if c
    )
    browse = f"""    <div class="browse">
      <p><strong>分類</strong>　{nav_cats}</p>
      <p><strong>主題</strong>　{nav_tags}</p>
    </div>"""
    (ARTICLES / "index.html").write_text(
        page(
            "文章列表",
            browse + "\n" + listing_page("全部文章", entries),
            desc="黃彥鈞中醫師全部文章：醫案分享、中醫衛教、課程與進修心得。",
        ),
        encoding="utf-8",
    )

    # 首頁最新 5 篇
    home_items = listing_items(entries[:5], link_prefix="articles/")
    home_body = f"""    <section class="cover">
      <img src="images/cover.png" alt="黃彥鈞 中醫師——{SUBTITLE}">
    </section>

    <section class="hero">
      <h1>望聞問切，醫理相傳</h1>
      <p>這裡是我在臨床與讀書之間的思考——中醫衛教、醫案心得與養生知識。</p>
      <p><a class="cta" href="clinic.html">📅 門診時間表・掛號方式</a></p>
    </section>

    <section>
      <h2>最新文章</h2>
      <ul class="article-list">
{home_items}
      </ul>
      <p><a href="articles/index.html">查看全部 {len(entries)} 篇文章 →</a></p>
    </section>"""
    (SITE / "index.html").write_text(
        page(
            "首頁", home_body, css_prefix="", current="index",
            desc=f"{SITE_TITLE}個人網站：{SUBTITLE}。中醫衛教文章、醫案分享與門診資訊。",
        ),
        encoding="utf-8",
    )

    # sitemap.xml＋robots.txt（搜尋引擎收錄用）
    urls = [f"{SITE_URL}/", f"{SITE_URL}/articles/index.html",
            f"{SITE_URL}/clinic.html", f"{SITE_URL}/about.html"]
    urls += [f"{SITE_URL}/articles/{e['slug']}.html" for e in entries]
    urls += [f"{SITE_URL}/articles/cat-{n}.html" for n in cat_names if cat_counts[n]]
    urls += [f"{SITE_URL}/articles/tag-{n}.html" for n, c in tag_counts.items() if c]
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sitemap += [f"  <url><loc>{html.escape(u)}</loc></url>" for u in urls]
    sitemap.append("</urlset>")
    (SITE / "sitemap.xml").write_text("\n".join(sitemap), encoding="utf-8")
    (SITE / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n", encoding="utf-8"
    )

    print(f"文章數：{len(entries)}（略過 {skipped} 篇）")
    print(f"sitemap：{len(urls)} 個網址")
    print("分類：", {k: v for k, v in cat_counts.items()})
    print("標籤：", dict(sorted(tag_counts.items(), key=lambda x: -x[1])))
    print(f"媒體檔：{len(list(MEDIA_OUT.iterdir()))} 個")


if __name__ == "__main__":
    main()
