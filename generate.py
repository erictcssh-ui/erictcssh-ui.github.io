#!/usr/bin/env python3
"""從臉書粉專匯出檔（fb-export/）產生網站文章頁。

用法：python3 generate.py
輸入：../fb-export/this_profile's_activity_across_facebook/posts/profile_posts_1.json
輸出：articles/*.html（含 cat-*/tag-* 專頁）、index.html、sitemap.xml、robots.txt、
      feed.xml、404.html、images/posts/（複製時自動壓縮至最長邊 1600px）
"""
import hashlib
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

SITE_URL = "https://tcmdrerichuang.com"
SITE_TITLE = "中醫師 黃彥鈞"
SUBTITLE = "中醫徒手・內針傷整合・精準全人醫療"
COPYRIGHT = "© 2026 中醫師 黃彥鈞・本站內容為衛教知識分享，不能取代實際診療"
COVER = "images/cover.jpg"
LINE_URL = "https://lin.ee/9DUnnrf"
GA_ID = "G-X33M4KHKF0"  # Google Analytics 4
GA_SNIPPET = f"""<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', '{GA_ID}');
  </script>"""
FB_URL = "https://www.facebook.com/profile.php?id=100078069915625"
IG_URL = "https://www.instagram.com/tcmdrerichuang"

# CSS 版本號：內容一變網址就變，訪客瀏覽器立即抓新版（避免快取舊樣式）
CSS_V = hashlib.md5((SITE / "css/style.css").read_bytes()).hexdigest()[:8]

MAX_IMG_EDGE = 1600     # 圖片壓縮：最長邊
JPEG_QUALITY = "80"
COMPRESS_MIN_BYTES = 200_000  # 小於此大小不重壓

# 時效性門診公告（停診、時段異動）：不留存（2026-07-17 醫師指示）
ANNOUNCE_WORDS = ["停診", "休診", "門診時間異動", "門診異動", "看診時間調整", "診所公告"]

CATEGORIES = [
    ("醫案分享", ["診間", "患者", "病人", "個案", "來診", "主訴", "治療後", "復診", "初診"]),
    ("教學與工作坊", ["工作坊", "講師", "助教", "學員", "授課", "教學", "梯次", "開課"]),
    ("進修筆記", ["進修", "上課", "課程", "筆記", "研習", "研討",
                  "Module", "SCS", "CounterStrain", "Scar work", "PAK"]),
    ("中醫衛教", ["衛教", "保養", "建議", "日常", "飲食", "睡眠", "中暑", "養生", "預防", "注意"]),
]
FALLBACK_CATEGORY = "隨筆"

# 標籤四維度：部位（區域）／症狀（主訴）／療法／主題
TAG_GROUPS = [
    ("部位", {
        "肩頸": ["肩頸", "頸椎", "脖子", "肩膀"],
        "下背・腰": ["下背", "腰痛", "腰椎", "閃到腰"],
        "骨盆": ["骨盆"],
        "薦髂關節": ["薦髂"],
        "尾椎": ["尾椎", "尾骨", "尾骶"],
        "膝蓋": ["膝蓋", "膝痛", "膝關節"],
        "手肘・手腕": ["網球肘", "高爾夫球肘", "媽媽手", "手腕", "手肘", "板機指"],
        "足・踝": ["足底筋膜", "腳踝", "足弓", "足跟", "拇趾"],
        "顳顎關節": ["顳顎"],
    }),
    ("症狀", {
        "落枕": ["落枕"],
        "頭痛・偏頭痛": ["頭痛", "偏頭痛"],
        "暈眩": ["暈眩", "頭暈", "眩暈"],
        "耳鳴・耳悶": ["耳鳴", "耳悶", "腦鳴"],
        "失眠": ["失眠"],
        "經痛・月經": ["經痛", "月經"],
        "產後・孕期": ["產後", "孕婦", "懷孕", "哺乳"],
        "腸胃・胃食道逆流": ["胃食道逆流", "脹氣", "腸胃", "胃痛", "便秘"],
        "鼻炎・過敏": ["鼻炎", "鼻塞", "過敏"],
        "皮膚": ["皮膚癢", "蕁麻疹", "濕疹"],
    }),
    ("療法", {
        "乾針／超音波針刀": ["乾針", "針刀"],
        "徒手治療": ["徒手"],
        "疤痕鬆解": ["疤痕"],
        "顱頸整合": ["顱頸", "顱初"],
        "美顏針": ["美顏針", "F.A.C.E"],
        "中藥調理": ["中藥", "方藥", "湯藥", "科學中藥", "水藥"],
    }),
    ("主題", {
        "表面解剖": ["表面解剖"],
        "經典・內經": ["黃帝內經", "內經", "傷寒論", "經方"],
    }),
]
TAGS = {name: words for _, group in TAG_GROUPS for name, words in group.items()}
MAX_TAGS = 4  # 每篇最多標籤數（部位＋症狀＋療法可共存）

# 人工核定標籤（2026-07-21 逐篇審核）：優先於自動關鍵字規則；空列表＝不掛任何標籤
TAG_OVERRIDES = {
    "post-2026-06-18": ["肩頸", "乾針／超音波針刀"],            # 顏面抽動案，耳鳴僅開頭回顧
    "post-2026-04-20": ["下背・腰", "乾針／超音波針刀"],        # 假性坐骨神經痛，誤標經痛
    "post-2026-01-15": ["下背・腰"],                            # 拉筋衛教講腰，誤標膝蓋
    "post-2024-03-10": ["顱頸整合", "徒手治療"],                # 大小臉/顱骨調整，失眠僅一句帶過
    "post-2025-12-17": ["肩頸", "腸胃・胃食道逆流"],            # 系統觀文，未引內經
    "post-2026-03-05": ["徒手治療"],                            # 以柔克剛，未引經典
    "post-2025-02-09": [],                                      # 中藥課程短貼文，無臨床內容
    "post-2024-07-20": ["顱頸整合"],                            # 複視/顱骨校正案，暈眩僅次要
    "post-2024-01-29": [],                                      # 新醫師加入公告
    "post-2024-10-15-2": ["肩頸", "耳鳴・耳悶", "乾針／超音波針刀", "徒手治療"],  # 多醫案合輯（醫師核可保留耳鳴）
    "post-2026-01-21": ["肩頸", "徒手治療", "乾針／超音波針刀"],  # 肩膀表現升級，誤標骨盆
    "post-2025-03-19": ["肩頸", "徒手治療"],                    # 手麻/肩胛案
    "post-2024-11-05": ["骨盆", "腸胃・胃食道逆流", "徒手治療"],  # 排便困擾因骨盆，補腸胃
    "post-2024-05-24": ["暈眩", "肩頸"],                        # 枕下肌群/眩暈，補肩頸
    "post-2023-05-23": ["顱頸整合", "頭痛・偏頭痛"],            # 顱骨/臉對稱案
    "post-2026-02-07": ["手肘・手腕", "產後・孕期"],            # 媽媽手，肩頸僅帶過
}

# 人工核定分類（2026-07-21 隨筆81篇逐篇審核）：優先於自動關鍵字規則
CATEGORY_OVERRIDES = {
    # → 醫案分享
    "post-2023-07-02": "醫案分享",       # 27歲媽媽治療後回饋
    "post-2024-04-25": "醫案分享",       # 但頭汗出：傷寒論＋斜方肌，東門聯合門診案
    "post-2024-10-15": "醫案分享",       # T3肋與胸骨柄交接處徒手調整
    "post-2024-10-26": "醫案分享",       # 治療老友母親多年疼痛＋傷寒論序感悟
    "post-2024-12-19-2": "醫案分享",     # 尾椎痛不調尾椎：產後薦髂失能案
    "post-2025-02-24-2": "醫案分享",     # 疤痕出奇蛋：剖腹產疤痕抑制核心案
    "post-2025-03-06": "醫案分享",       # 產後臉浮腫：肩頸筋膜與體液循環案
    "post-2025-11-07": "醫案分享",       # Scarwork 處理20年疤痕改善食指關節痛
    # → 進修筆記
    "post-2022-05-09": "進修筆記",       # 《傷寒解惑論述議》讀書心得
    "post-2023-08-12": "進修筆記",       # 腰椎骨盆薦椎課 Day2
    "post-2023-08-12-2": "進修筆記",     # 同課程請大師簽名
    "post-2024-03-16": "進修筆記",       # Neumann 肩關節書到貨
    "post-2024-11-19": "進修筆記",       # 中國古典針灸學大綱研讀
    "post-2024-12-02": "進修筆記",       # MET 祖師新書研讀
    "post-2025-03-01": "進修筆記",       # Neumann 髖關節課 Day1
    "post-2025-03-02": "進修筆記",       # Neumann 髖關節課重點筆記
    "post-2025-03-09": "進修筆記",       # 傅士豪肌動學讀書會
    "post-2025-03-28": "進修筆記",       # 瑞士 DGSA 徒手/乾針認證取得
    "post-2025-04-28-2": "進修筆記",     # 課程 Day3 花絮
    "post-2025-08-23": "進修筆記",       # OpenEvidence 實證文獻工具
    "post-2025-09-07-2": "進修筆記",     # 肌筋膜脈學讀書會33週完成
    "post-2025-09-28": "進修筆記",       # 中西醫整合讀書會開跑
    "post-2025-10-01": "進修筆記",       # 超音波新書
    "post-2025-10-05": "進修筆記",       # 中西醫整合討論會 case report 報告
    "post-2026-02-23": "進修筆記",       # 進階頸椎課程
    "post-2026-03-26": "進修筆記",       # Cranial Osteopathy 四日課
    "post-2026-04-24": "進修筆記",       # 布拉格內臟鬆動術報名
    "post-2026-05-03": "進修筆記",       # 內臟鬆弛術＋KUB判讀讀書會
    # → 教學與工作坊
    "post-2023-06-03": "教學與工作坊",   # 230618 徒手/骨傷分享會
    "post-2023-11-11": "教學與工作坊",   # 初玩傷科第一堂（仁愛學弟妹）
    "post-2024-06-07": "教學與工作坊",   # 主辦入門望診課（蔡易憲院長授課）
    "post-2025-12-29": "教學與工作坊",   # 取得臨床醫學指導教師資格
    "post-2026-03-18": "教學與工作坊",   # 返校園授課前導（素問引文）
    "post-2026-03-22": "教學與工作坊",   # 首訪長庚校園（授課行）
    # → 中醫衛教
    "post-2023-08-22": "中醫衛教",       # 整脊屬醫療行為之安全宣導
    "post-2024-03-23": "中醫衛教",       # 顱初結構還原：顱骨系統衛教長文
    "post-2025-05-07": "中醫衛教",       # 「喀」之前先排除風險之安全宣導
}

# 過期時效性公告，人工列管移除（依 2026-07-17 過濾原則；自動關鍵字未攔到）
EXCLUDE_POSTS = {
    "post-2023-03-04",   # 2023.03 月門診表
    "post-2026-02-13",   # 農曆年前最後看診日公告
    "post-2026-03-16",   # 週六門診地點異動公告（已生效，現行資訊在門診頁）
}

# 主題導言：萃取自醫師歷年文章中的治療觀念（醫師觀點，非診療建議）
TAG_INTROS = {
    "骨盆": "調骨盆，不是把骨頭「喬正」到某個絕對正確的位置——而是調「骨盆的回正能力」，把能隨日常活動變化調節的活動能力找回來。骨盆是身體的避震器與力量傳遞的中繼站，活動力喪失的原因可能在關節囊韌帶、肌肉筋膜張力或關節錯移，需要精密的檢查與診斷，而非一體適用的快速手法。以下是我在診間關於骨盆的觀察與紀錄。",
    "肩頸": "肩頸的問題，通常不只是肩頸的事。人是連貫的系統——胸廓、肩胛、甚至下背的失能，都可能讓肩頸代償受累；痛哪治哪往往不夠，得找出真正失能的源頭。肩頸的張力也會向上牽動顱骨與顏面，衍生頭痛、耳悶、失眠等看似無關的症狀。以下是相關的醫案與衛教紀錄。",
    "下背・腰": "腰椎的先天設計是「穩定軀幹」；當胸椎卡住、骨盆失能，本該穩定的腰就被迫代償活動，久了痠痛通通一起來。久坐不動會讓韌帶疲乏（潛變）、保護反射失靈——有一種「緊」其實是「累」，越拉筋反而越痛。修復失能的源頭，而不是只放鬆痛處，是我處理下背痛的核心思路。",
    "膝蓋": "膝關節是「穩定性關節」，位在髖—膝—踝力學連線的中段；會痛，常是因為它長期做了本不屬於它該做的事——鄰近關節的牽連、抑制與代償而來。影像上有骨刺、退化，不等於就是疼痛的原因，更不等於只能換關節。找出力學鏈上真正失能的環節，膝蓋才有機會真正休息。",
    "薦髂關節": "薦髂關節是承接上下半身力量的「大齒輪」——健康的骨盆不是只要「正」，更要「活」。走路、彎腰時它必須有極微小而滑順的點頭與滑動；一旦卡死，衝擊力往下丟給膝蓋、往上卡住腰椎，痛點看似到處跑，源頭卻是同一個。以下是關於薦髂關節的醫案與思考。",
    "尾椎": "尾椎痛,尾椎常常是無辜的。坐下時理想的受力點是兩側坐骨結節;當骨盆失衡翻轉,尾椎被迫代班去撞擊椅面——拿身體最脆弱的尾巴骨當避震器,壓迫感怎麼會不重?所以「尾椎痛不一定調尾椎」,先確認問題是不是出在骨盆與薦髂關節,才是有效率的處理方式。",
    "顳顎關節": "顳顎關節（TMJ）的痠痛，兇手常常不在關節本身。若張口順暢、路徑正直，「發炎」往往只是結果——真正的拉力可能來自顱骨排列、頸部肌群張力，甚至更遠端的結構。從全身大結構下手，而不是只盯著局部關節，是我處理顳顎問題的基本視角。",
    "頭痛・偏頭痛": "檢查都正常、卻反覆發作的頭痛，臨床上有很高比例與肌筋膜失能有關——高位頸椎、胸鎖乳突肌、枕下肌群的張力，都可能是幕後推手。看似內科的問題，實則是結構的問題；這也是許多患者驚訝的一句話：「原來長年頭痛，可以看中醫傷科！」",
    "暈眩": "排除器質性病變後，許多「浮浮的、像暈船」的暈眩，源自頸部本體感覺的紊亂。胸鎖乳突肌是頭部的「導航舵」，枕下肌群負責頭頸的微調穩定——當它們失能或高位頸椎錯位，大腦收到的「頭在哪裡」訊號就會失真。處理頸部結構，常是這類暈眩的關鍵。",
    "耳鳴・耳悶": "對於耳鳴，我始終不敢妄言「完全治癒」。但檢查正常、被告知「學著和平共處」的耳鳴耳悶，仍有可以努力的空間——耳道聽骨與耳周肌群連著顳骨，顱骨排列、頸椎筋膜張力都可能參與其中。透過內傷併治的整合處置，讓聲音變小、穩定在可忽略的日常，是我目前能盡的最大努力。",
    "產後・孕期": "懷孕與生產，是骨盆帶承受最大變化的時期。產後的腰痛、恥骨痛、尾椎不適，多與薦髂關節、恥骨聯合未回到該有的活動狀態有關；剖腹產的疤痕也可能抑制核心發力。我的處理方式是徒手與針灸並用，必要時與產後運動、震波等跨專業合作——複雜的問題，本來就需要整合的答案。",
    "乾針／超音波針刀": "乾針是針對激痛點與失能肌筋膜的精準治療——透過準確的評估找到真正的問題肌群，往往幾針就能截斷疼痛的惡性循環。慢性疼痛還會引發中樞敏感化，此時配合中藥的化學性調理雙管齊下更有效率；深層頑固的沾黏，則輔以超音波導引針刀精準處理。我持有瑞士 D.G.S.A 官方認證，以下是相關的臨床紀錄。",
    "徒手治療": "徒手治療是我最喜歡的治療方式，原因很簡單：只要有雙手，就能處理大部分筋骨疼痛的問題。從中醫骨傷科到 MET、SCS、PNF、顱薦與疤痕鬆解，各門各派殊途同歸——重點從來不是把骨頭「喬正」，而是恢復結構該有的功能與活動能力。以下是我的徒手治療紀錄與學習軌跡。",
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
        title_hit = any(w in title_line for w in words)
        # 相關門檻（避免「放射到腳踝」這類順帶一提的弱關聯誤標）：
        # 標題命中、或出現 3 次以上、或出現 2 次且首次出現在文章前 1/4（主題詞會早早登場）
        first_pos = min(text.find(w) for w in words if w in text)
        early = first_pos < len(text) * 0.25
        if not (title_hit or occurrences >= 3 or (occurrences >= 2 and early)):
            continue
        score = occurrences + (5 if title_hit else 0)
        scored.append((score, name))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [name for _, name in scored[:MAX_TAGS]]


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
  {GA_SNIPPET}
  {head_html}{extra_head}
  <link rel="stylesheet" href="{css_prefix}css/style.css?v={CSS_V}">
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


def listing_by_year(entries):
    body = []
    by_year = {}
    for e in entries:
        by_year.setdefault(e["date"][:4], []).append(e)
    for year in sorted(by_year, reverse=True):
        body.append(f"    <h2>{year} 年（{len(by_year[year])} 篇）</h2>")
        body.append('    <ul class="article-list">')
        body.append(listing_items(by_year[year]))
        body.append("    </ul>")
    return "\n".join(body)


def listing_page(title, entries, intro=""):
    body = [f"    <h1>{html.escape(title)}</h1>"]
    if intro:
        body.append(f"    <p>{intro}</p>")
    body.append(listing_by_year(entries))
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
        if slug in EXCLUDE_POSTS:
            skipped += 1
            continue
        entries.append(
            dict(
                date=date, slug=slug, text=text, media=media,
                title=make_title(text, date),
                excerpt=text.replace("\n", " ")[:80] + ("…" if len(text) > 80 else ""),
                category=CATEGORY_OVERRIDES.get(slug, classify(text)),
                tags=TAG_OVERRIDES.get(slug, find_tags(text)),
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
        intro = TAG_INTROS.get(name)
        intro_html = (
            f'    <div class="tag-intro"><p>{intro}</p>'
            '<p class="intro-note">—— 摘自黃彥鈞醫師的臨床文章；內容為衛教觀點分享，'
            '實際診斷與治療請以門診評估為準。</p></div>\n'
            if intro else ""
        )
        desc = (intro[:90] + "…") if intro else f"黃彥鈞中醫師關於「{name}」的文章，共 {len(subset)} 篇。"
        (ARTICLES / f"tag-{name}.html").write_text(
            page(f"{name}（主題）",
                 f"    <h1>主題：{name}</h1>\n" + intro_html
                 + listing_by_year(subset),
                 desc=desc,
                 url_path=f"articles/tag-{name}.html"),
            encoding="utf-8",
        )

    # 文章總列表
    nav_cats = "".join(
        f'<a class="tag" href="cat-{n}.html">{n}（{cat_counts[n]}）</a>'
        for n in cat_names if cat_counts[n]
    )
    # 全文搜尋索引（給站內搜尋用）
    search_index = [
        {"t": e["title"], "u": e["slug"], "d": e["date"],
         "g": e["tags"], "x": e["text"][:1500]}
        for e in entries
    ]
    (SITE / "search-index.json").write_text(
        json.dumps(search_index, ensure_ascii=False), encoding="utf-8"
    )

    search_ui = """    <div class="search-box">
      <input type="search" id="q" placeholder="🔍 搜尋文章：症狀、療法、關鍵字⋯" autocomplete="off">
    </div>
    <div id="sr"></div>
    <div id="listing">"""
    search_js = """    </div>
    <script>
    (function(){
      var q=document.getElementById('q'),sr=document.getElementById('sr'),
          listing=document.getElementById('listing'),idx=null,timer=null;
      function esc(s){return s.replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
      var loading=null;
      function load(){if(!loading){loading=fetch('../search-index.json').then(function(r){return r.json();}).then(function(d){idx=d;return d;});}return loading;}
      q.addEventListener('focus',load,{once:true});
      q.addEventListener('input',function(){clearTimeout(timer);timer=setTimeout(run,200);});
      function run(){
        var s=q.value.trim();
        if(!s){sr.innerHTML='';listing.style.display='';return;}
        var go=function(){
          var terms=s.toLowerCase().split(/\\s+/);
          var res=[];
          for(var i=0;i<idx.length;i++){
            var a=idx[i],hay=(a.t+'\\n'+a.g.join(' ')+'\\n'+a.x).toLowerCase(),score=0,ok=true;
            for(var j=0;j<terms.length;j++){
              var w=terms[j];
              if(hay.indexOf(w)===-1){ok=false;break;}
              if(a.t.toLowerCase().indexOf(w)>-1)score+=10;
              for(var k=0;k<a.g.length;k++){if(a.g[k].toLowerCase().indexOf(w)>-1){score+=5;break;}}
              score+=Math.min(a.x.toLowerCase().split(w).length-1,5);
            }
            if(ok)res.push({a:a,score:score});
          }
          res.sort(function(x,y){return y.score-x.score||(y.a.d<x.a.d?-1:1);});
          res=res.slice(0,50);
          listing.style.display='none';
          if(!res.length){sr.innerHTML='<p>沒有找到符合「'+esc(s)+'」的文章。</p>';return;}
          var h='<p>找到 '+res.length+' 篇：</p><ul class="article-list">';
          for(var m=0;m<res.length;m++){
            var a=res[m].a;
            h+='<li><a href="'+a.u+'.html">'+esc(a.t)+'</a><span class="meta">'+a.d+'</span><p class="excerpt">'+esc(a.x.slice(0,80))+'…</p></li>';
          }
          sr.innerHTML=h+'</ul>';
        };
        if(idx){go();}else{load().then(go);}
      }
    })();
    </script>"""
    group_rows = []
    for group_name, group in TAG_GROUPS:
        chips = "".join(
            f'<a class="tag" href="tag-{n}.html">{n}（{tag_counts[n]}）</a>'
            for n in sorted(group, key=lambda x: -tag_counts.get(x, 0))
            if tag_counts.get(n)
        )
        if chips:
            group_rows.append(f"      <p><strong>{group_name}</strong>　{chips}</p>")
    browse = ('    <div class="browse">\n'
              + f"      <p><strong>分類</strong>　{nav_cats}</p>\n"
              + "\n".join(group_rows) + "\n    </div>")
    (ARTICLES / "index.html").write_text(
        page("文章列表",
             search_ui + "\n" + browse + "\n"
             + listing_page("全部文章", entries) + "\n" + search_js,
             desc="黃彥鈞中醫師全部文章：醫案分享、中醫衛教、課程與進修心得。可搜尋症狀與主題關鍵字。",
             url_path="articles/index.html"),
        encoding="utf-8",
    )

    # 首頁（含「依症狀・部位找文章」：列症狀與部位兩個維度）
    home_tag_names = [n for gname, g in TAG_GROUPS if gname in ("症狀", "部位") for n in g]
    symptom_chips = "".join(
        f'<a class="tag" href="articles/tag-{n}.html">{n}（{tag_counts[n]}）</a>'
        for n in sorted(home_tag_names, key=lambda x: -tag_counts.get(x, 0))
        if tag_counts.get(n)
    )
    home_items = listing_items(entries[:5], link_prefix="articles/")
    home_body = f"""    <section class="cover">
      <img src="{COVER}" alt="黃彥鈞 中醫師——{SUBTITLE}" width="2000" height="875">
    </section>

    <section class="hero">
      <h1>治病，也醫人</h1>
      <p>以徒手、針刺與方藥，實踐全人診療的臨床紀錄。</p>
      <p><a class="cta" href="clinic.html">📅 門診時間表・掛號方式</a></p>
    </section>

    <section>
      <h2>依症狀・部位找文章</h2>
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

    # 靜態頁（about/clinic）的 CSS 連結同步帶上版本號
    import re
    for name in ["about.html", "clinic.html"]:
        fp = SITE / name
        if fp.exists():
            s = fp.read_text(encoding="utf-8")
            s2 = re.sub(r"css/style\.css(\?v=[a-f0-9]+)?", f"css/style.css?v={CSS_V}", s)
            if s2 != s:
                fp.write_text(s2, encoding="utf-8")

    print(f"文章數：{len(entries)}（略過 {skipped} 篇）")
    print(f"本次新壓縮圖片：{compressed} 張")
    print("分類：", {k: v for k, v in cat_counts.items()})
    print(f"媒體檔：{len(list(MEDIA_OUT.iterdir()))} 個")


if __name__ == "__main__":
    main()
