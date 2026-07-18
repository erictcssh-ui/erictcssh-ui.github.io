#!/usr/bin/env python3
"""從臉書粉專匯出檔（fb-export/）產生網站文章頁。

用法：python3 generate.py
輸入：../fb-export/this_profile's_activity_across_facebook/posts/profile_posts_1.json
輸出：articles/*.html（含 cat-*/tag-* 專頁）、index.html、sitemap.xml、robots.txt、
      feed.xml、404.html、images/posts/（複製時自動壓縮至最長邊 1600px）
"""
import json
import html
import shutil
import datetime
from pathlib import Path

from PIL import Image, ImageOps

SITE = Path(__file__).parent
EXPORT = SITE.parent / "fb-export"
POSTS_JSON = EXPORT / "this_profile's_activity_across_facebook/posts/profile_posts_1.json"
MEDIA_OUT = SITE / "images/posts"
ARTICLES = SITE / "articles"

SITE_URL = "https://erictcssh-ui.github.io"  # 換自有網域時改這裡再重跑
SITE_TITLE = "中醫師 黃彥鈞"
SUBTITLE = "中醫徒手・內針傷整合・精準全人醫療"
COPYRIGHT = "© 2026 中醫師 黃彥鈞・本站內容為衛教知識分享，不能取代實際診療"
COVER = "images/cover.jpg"
LINE_URL = "https://lin.ee/9DUnnrf"
FB_URL = "https://www.facebook.com/profile.php?id=100078069915625"
IG_URL = "https://www.instagram.com/tcmdrerichuang"

MAX_IMG_EDGE = 1600     # 圖片壓縮：最長邊
JPEG_QUALITY = "80"
COMPRESS_MIN_BYTES = 200_000  # 小於此大小不重壓

# 時效性門診公告（停診、時段異動）：不留存（2026-07-17 醫師指示）
ANNOUNCE_WORDS = ["停診", "休診", "門診時間異動", "門診異動", "看診時間調整", "診所公告"]

CATEGORIES = [
    ("醫案分享", ["診間", "患者", "病人", "個案", "來診", "主訴", "治療後", "復診", "初診"]),
    ("課程與進修", ["工作坊", "課程", "學員", "講師", "研習", "助教", "上課", "進修",
                    "筆記", "Module", "SCS", "CounterStrain", "Scar work", "PAK", "研討"]),
    ("中醫衛教", ["衛教", "保養", "建議", "日常", "飲食", "睡眠", "中暑", "養生", "預防", "注意"]),
]
FALLBACK_CATEGORY = "隨筆"

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
# 首頁「依症狀找文章」只列症狀類標籤（排除療法/主題類）
SYMPTOM_TAGS = ["下背痛", "頭痛・偏頭痛", "耳鳴", "膝蓋痛", "肩頸・落枕", "骨盆・薦髂關節",
                "腸胃・胃食道逆流", "鼻炎・過敏", "婦科・產後", "皮膚", "失眠"]


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
    """相關性計分：關鍵詞出現次數＋標題命中加權，每篇最多取 3 個主軸標籤。"""
    title_line = text.split("\n", 1)[0]
    scored = []
    for name, words in TAGS.items():
        occurrences = sum(text.count(w) for w in words)
        if occurrences == 0:
            continue
        score = occurrences + (5 if any(w in title_line for w in words) else 0)
        scored.append((score, name))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [name for _, name in scored[:3]]


def make_title(text, date):
    first = text.split("\n", 1)[0].strip()
    if first.startswith("【") and "】" in first:
        first = first[1 : first.index("】")].strip()
    if len(first) > 40:
        first = first[:40] + "…"
    return first or f"{date} 貼文"


def paragraphs(text):
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    return "\n".join(
        "<p>" + html.escape(b).replace("\n", "<br>\n") + "</p>" for b in blocks
    )


def img_dims(path):
    try:
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


def compress_image(dest):
    """就地壓縮：EXIF 轉正、最長邊縮到 MAX_IMG_EDGE、JPEG 品質 75。"""
    try:
        with Image.open(dest) as im:
            im = ImageOps.exif_transpose(im)
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            im.thumbnail((MAX_IMG_EDGE, MAX_IMG_EDGE))
            im.save(dest, "JPEG", quality=75, optimize=True, progressive=True)
    except Exception:
        pass


def footer_html(p):
    return f"""  <footer class="site-footer">
    <nav class="footer-nav">
      <a href="{p}index.html">首頁</a>
      <a href="{p}articles/index.html">文章</a>
      <a href="{p}clinic.html">門診資訊</a>
      <a href="{p}about.html">關於醫師</a>
      <a href="{p}feed.xml">RSS</a>
    </nav>
    <p class="footer-contact">太初中醫 02-2777-5800・東門中醫 02-2343-2000
      <a class="cta line" href="{LINE_URL}" target="_blank" rel="noopener">LINE 線上預約</a></p>
    <p class="footer-social">
      <a href="{FB_URL}" target="_blank" rel="noopener">Facebook</a>・
      <a href="{IG_URL}" target="_blank" rel="noopener">Instagram</a></p>
    <p>{COPYRIGHT}</p>
  </footer>"""


def page(title, body, css_prefix="../", current="articles", desc=None,
         url_path=None, og_image=None, extra_head=""):
    nav = {
        "index": (f"{css_prefix}index.html", "首頁"),
        "articles": (f"{css_prefix}articles/index.html", "文章"),
        "clinic": (f"{css_prefix}clinic.html", "門診資訊"),
        "about": (f"{css_prefix}about.html", "關於醫師"),
    }
    cur_attr = ' aria-current="page"'
    nav_html = "\n      ".join(
        f'<a href="{href}"{cur_attr if key == current else ""}>{label}</a>'
        for key, (href, label) in nav.items()
    )
    full_title = f"{title}｜{SITE_TITLE}"
    head_extra = []
    if desc:
        head_extra.append(f'<meta name="description" content="{html.escape(desc)}">')
    og_url = f"{SITE_URL}/{url_path}" if url_path is not None else SITE_URL + "/"
    og_img = f"{SITE_URL}/{og_image or COVER}"
    head_extra += [
        f'<link rel="canonical" href="{html.escape(og_url)}">',
        '<meta property="og:type" content="article">' if css_prefix == "../"
        else '<meta property="og:type" content="website">',
        f'<meta property="og:title" content="{html.escape(full_title)}">',
        f'<meta property="og:description" content="{html.escape(desc or SUBTITLE)}">',
        f'<meta property="og:url" content="{html.escape(og_url)}">',
        f'<meta property="og:image" content="{html.escape(og_img)}">',
        f'<meta property="og:site_name" content="{SITE_TITLE}">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<link rel="icon" type="image/svg+xml" href="{css_prefix}favicon.svg">',
        f'<link rel="alternate" type="application/rss+xml" title="{SITE_TITLE}" href="{css_prefix}feed.xml">',
    ]
    head_html = "\n  ".join(head_extra)
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(full_title)}</title>
  {head_html}{extra_head}
  <link rel="stylesheet" href="{css_prefix}css/style.css">
</head>
<body>
  <header class="site-header">
    <h1 class="site-title"><a href="{css_prefix}index.html">{SITE_TITLE}</a></h1>
    <p class="site-subtitle">{SUBTITLE}</p>
    <nav class="site-nav">
      {nav_html}
    </nav>
  </header>

  <main>
{body}
  </main>

{footer_html(css_prefix)}
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


def related_entries(entry, entries, n=4):
    scored = []
    for other in entries:
        if other["slug"] == entry["slug"]:
            continue
        score = 2 * len(set(entry["tags"]) & set(other["tags"]))
        if other["category"] == entry["category"]:
            score += 1
        if score > 0:
            scored.append((score, other["date"], other))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [s[2] for s in scored[:n]]


def article_jsonld(e, first_image):
    img = f"{SITE_URL}/{first_image}" if first_image else f"{SITE_URL}/{COVER}"
    data = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": e["title"],
        "datePublished": e["date"],
        "inLanguage": "zh-Hant",
        "image": img,
        "url": f"{SITE_URL}/articles/{e['slug']}.html",
        "author": {"@type": "Person", "name": "黃彥鈞",
                   "url": f"{SITE_URL}/about.html", "jobTitle": "中醫師"},
        "publisher": {"@type": "Person", "name": "黃彥鈞"},
        "description": e["excerpt"],
    }
    crumbs = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "首頁", "item": f"{SITE_URL}/"},
            {"@type": "ListItem", "position": 2, "name": e["category"],
             "item": f"{SITE_URL}/articles/cat-{e['category']}.html"},
            {"@type": "ListItem", "position": 3, "name": e["title"]},
        ],
    }
    return ("\n  <script type=\"application/ld+json\">"
            + json.dumps(data, ensure_ascii=False)
            + "</script>\n  <script type=\"application/ld+json\">"
            + json.dumps(crumbs, ensure_ascii=False) + "</script>")


def main():
    with open(POSTS_JSON) as f:
        posts = fix(json.load(f))

    MEDIA_OUT.mkdir(parents=True, exist_ok=True)
    ARTICLES.mkdir(exist_ok=True)

    # 第一輪：整理資料
    entries = []
    skipped = 0
    day_counter = {}
    for post in sorted(posts, key=lambda p: p.get("timestamp", 0)):
        ts = post.get("timestamp")
        text = get_text(post)
        media = get_media(post)
        if not ts or not text:
            skipped += 1
            continue
        if "shared" in post.get("title", "").lower():
            skipped += 1
            continue
        if len(text) < 300 and any(w in text for w in ANNOUNCE_WORDS):
            skipped += 1
            continue
        date = datetime.date.fromtimestamp(ts).isoformat()
        day_counter[date] = day_counter.get(date, 0) + 1
        slug = f"post-{date}" + (f"-{day_counter[date]}" if day_counter[date] > 1 else "")
        entries.append(
            dict(
                date=date, slug=slug, text=text, media=media,
                title=make_title(text, date),
                excerpt=text.replace("\n", " ")[:80] + ("…" if len(text) > 80 else ""),
                category=classify(text), tags=find_tags(text),
            )
        )

    # 第二輪：寫文章頁（媒體複製＋壓縮、麵包屑、JSON-LD、CTA、延伸閱讀）
    compressed = 0
    for e in entries:
        media_html, first_image = [], None
        for uri, is_video in e["media"]:
            src = EXPORT / uri
            if not src.exists():
                continue
            dest = MEDIA_OUT / src.name
            if not dest.exists():
                shutil.copy2(src, dest)
                if not is_video and dest.stat().st_size > COMPRESS_MIN_BYTES:
                    compress_image(dest)
                    compressed += 1
            rel = f"../images/posts/{src.name}"
            if is_video:
                media_html.append(
                    f'<video controls preload="metadata" src="{rel}"></video>'
                )
            else:
                dims = img_dims(dest)
                size_attr = f' width="{dims[0]}" height="{dims[1]}"' if dims else ""
                media_html.append(
                    f'<img src="{rel}" alt="{html.escape(e["title"])}"{size_attr} loading="lazy">'
                )
                if first_image is None:
                    first_image = f"images/posts/{src.name}"

        related = related_entries(e, entries)
        related_html = ""
        if related:
            items = "\n".join(
                f'        <li><a href="{r["slug"]}.html">{html.escape(r["title"])}</a>'
                f'<span class="meta">{r["date"]}</span></li>'
                for r in related
            )
            related_html = f"""
    <section class="related">
      <h2>延伸閱讀</h2>
      <ul>
{items}
      </ul>
    </section>"""

        body = f"""    <nav class="breadcrumb"><a href="../index.html">首頁</a> › <a href="cat-{e['category']}.html">{e['category']}</a> › <span>{html.escape(e['title'])}</span></nav>

    <article class="post">
      <h1>{html.escape(e['title'])}</h1>
      <p class="post-meta">{e['date']}　{chip_links(e['category'], e['tags'])}</p>
{paragraphs(e['text'])}
{chr(10).join(media_html)}
    </article>

    <div class="cta-box">
      <p>有類似的困擾想諮詢？</p>
      <p><a class="cta" href="../clinic.html">📅 門診時間・預約掛號</a>
      <a class="cta line" href="{LINE_URL}" target="_blank" rel="noopener">💬 LINE 線上預約</a></p>
    </div>{related_html}"""
        (ARTICLES / f"{e['slug']}.html").write_text(
            page(e["title"], body, desc=e["excerpt"],
                 url_path=f"articles/{e['slug']}.html", og_image=first_image,
                 extra_head=article_jsonld(e, first_image)),
            encoding="utf-8",
        )

    entries.sort(key=lambda e: e["date"], reverse=True)
    latest_date = entries[0]["date"] if entries else datetime.date.today().isoformat()

    # 分類頁
    cat_names = [c[0] for c in CATEGORIES] + [FALLBACK_CATEGORY]
    cat_counts = {}
    for name in cat_names:
        subset = [e for e in entries if e["category"] == name]
        cat_counts[name] = len(subset)
        if not subset:
            continue
        (ARTICLES / f"cat-{name}.html").write_text(
            page(f"{name}（分類）", listing_page(f"分類：{name}", subset),
                 desc=f"黃彥鈞中醫師「{name}」分類文章，共 {len(subset)} 篇。",
                 url_path=f"articles/cat-{name}.html"),
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
            page(f"{name}（主題）", listing_page(f"主題：{name}", subset),
                 desc=f"黃彥鈞中醫師關於「{name}」的文章，共 {len(subset)} 篇。",
                 url_path=f"articles/tag-{name}.html"),
            encoding="utf-8",
        )

    # 文章總列表
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
        page("文章列表", browse + "\n" + listing_page("全部文章", entries),
             desc="黃彥鈞中醫師全部文章：醫案分享、中醫衛教、課程與進修心得。",
             url_path="articles/index.html"),
        encoding="utf-8",
    )

    # 首頁（含「依症狀找文章」）
    symptom_chips = "".join(
        f'<a class="tag" href="articles/tag-{n}.html">{n}（{tag_counts[n]}）</a>'
        for n in SYMPTOM_TAGS if tag_counts.get(n)
    )
    home_items = listing_items(entries[:5], link_prefix="articles/")
    home_body = f"""    <section class="cover">
      <img src="{COVER}" alt="黃彥鈞 中醫師——{SUBTITLE}" width="2000" height="875">
    </section>

    <section class="hero">
      <h1>望聞問切，醫理相傳</h1>
      <p>這裡是我在臨床與讀書之間的思考——中醫衛教、醫案心得與養生知識。</p>
      <p><a class="cta" href="clinic.html">📅 門診時間表・掛號方式</a></p>
    </section>

    <section>
      <h2>依症狀找文章</h2>
      <div class="browse"><p>{symptom_chips}</p></div>
    </section>

    <section>
      <h2>最新文章</h2>
      <ul class="article-list">
{home_items}
      </ul>
      <p><a href="articles/index.html">查看全部 {len(entries)} 篇文章 →</a></p>
    </section>"""
    (SITE / "index.html").write_text(
        page("首頁", home_body, css_prefix="", current="index",
             desc=f"{SITE_TITLE}個人網站：{SUBTITLE}。中醫衛教文章、醫案分享與門診資訊。",
             url_path=""),
        encoding="utf-8",
    )

    # 404（GitHub Pages 會對任何路徑套用，連結需用根絕對路徑）
    (SITE / "404.html").write_text(f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>找不到頁面｜{SITE_TITLE}</title>
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <link rel="stylesheet" href="/css/style.css">
</head>
<body>
  <header class="site-header">
    <h1 class="site-title"><a href="/">{SITE_TITLE}</a></h1>
    <p class="site-subtitle">{SUBTITLE}</p>
  </header>
  <main style="text-align:center">
    <h1>🌿 找不到這個頁面</h1>
    <p>網址可能打錯了，或這篇文章已移除。</p>
    <p><a class="cta" href="/">回首頁</a>　<a class="cta" href="/articles/index.html">看全部文章</a></p>
  </main>
  <footer class="site-footer"><p>{COPYRIGHT}</p></footer>
</body>
</html>
""", encoding="utf-8")

    # RSS（最新 20 篇）
    rss_items = []
    for e in entries[:20]:
        rss_items.append(f"""    <item>
      <title>{html.escape(e['title'])}</title>
      <link>{SITE_URL}/articles/{e['slug']}.html</link>
      <guid>{SITE_URL}/articles/{e['slug']}.html</guid>
      <pubDate>{datetime.datetime.fromisoformat(e['date']).strftime('%a, %d %b %Y')} 00:00:00 +0800</pubDate>
      <description>{html.escape(e['excerpt'])}</description>
    </item>""")
    (SITE / "feed.xml").write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>{SITE_TITLE}</title>
    <link>{SITE_URL}/</link>
    <description>{SUBTITLE}——中醫衛教、醫案分享與課程心得</description>
    <language>zh-Hant</language>
{chr(10).join(rss_items)}
  </channel>
</rss>
""", encoding="utf-8")

    # sitemap.xml（含 lastmod）＋robots.txt
    def url_tag(loc, lastmod):
        return f"  <url><loc>{html.escape(loc)}</loc><lastmod>{lastmod}</lastmod></url>"

    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for p in ["", "articles/index.html", "clinic.html", "about.html"]:
        sitemap.append(url_tag(f"{SITE_URL}/{p}", latest_date))
    for e in entries:
        sitemap.append(url_tag(f"{SITE_URL}/articles/{e['slug']}.html", e["date"]))
    for n in cat_names:
        if cat_counts[n]:
            sub = [e["date"] for e in entries if e["category"] == n]
            sitemap.append(url_tag(f"{SITE_URL}/articles/cat-{n}.html", max(sub)))
    for n, c in tag_counts.items():
        if c:
            sub = [e["date"] for e in entries if n in e["tags"]]
            sitemap.append(url_tag(f"{SITE_URL}/articles/tag-{n}.html", max(sub)))
    sitemap.append("</urlset>")
    (SITE / "sitemap.xml").write_text("\n".join(sitemap), encoding="utf-8")
    (SITE / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n", encoding="utf-8"
    )

    print(f"文章數：{len(entries)}（略過 {skipped} 篇）")
    print(f"本次新壓縮圖片：{compressed} 張")
    print("分類：", {k: v for k, v in cat_counts.items()})
    print(f"媒體檔：{len(list(MEDIA_OUT.iterdir()))} 個")


if __name__ == "__main__":
    main()
