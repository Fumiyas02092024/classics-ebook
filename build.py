#!/usr/bin/env python3
"""src/*.txt から EPUB（縦書き・横書き）と単体HTMLを生成する。"""
import html
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
DIST = ROOT / "dist"

TITLE = "三つの旅"
SUBTITLE = "ホメロス・プラトン・ダンテ　現代語再話"
FULL_TITLE = f"{TITLE}　ホメロス・プラトン・ダンテ"
CREATORS = ["ホメロス", "プラトン", "ダンテ・アリギエーリ"]
BOOK_ID = "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, "mittsu-no-tabi-homer-plato-dante"))

# (部の見出し, 部の副題, ファイル群)。見出しが None なら部に属さない
PARTS = [
    (None, None, ["00_front.txt"]),
    ("第一部　ホメロス", "イリアス　／　オデュッセイア", ["10_homer_intro.txt", "11_iliad.txt", "12_odyssey.txt"]),
    ("第二部　プラトン", "饗宴　／　国家　／　ソクラテスの弁明　／　クリトン　／　パイドン",
     ["20_plato_intro.txt", "21_symposium.txt", "22_cave.txt", "23_apology.txt", "24_crito_phaedo.txt"]),
    ("第三部　ダンテ", "神曲　地獄篇　／　煉獄篇　／　天国篇",
     ["30_dante_intro.txt", "31_inferno.txt", "32_purgatorio.txt", "33_paradiso.txt"]),
    (None, None, ["90_afterword.txt"]),
]

PART_EPIGRAPHS = {
    "第一部　ホメロス": "怒りを歌え、女神よ。",
    "第二部　プラトン": "吟味のない生活は、人間にとって生きるに値しない。",
    "第三部　ダンテ": "人生の道のなかばで、気がつくと私は、暗い森のなかにいた。",
}


# ---------- テキスト → HTML断片 ----------

def esc(s):
    return html.escape(s, quote=False)


def inline(s):
    return esc(s)


def parse_chapters(text):
    """'# ' 見出しごとに (title, body_lines) へ分割する。"""
    chapters, cur = [], None
    for line in text.splitlines():
        if line.startswith("# "):
            cur = [line[2:].strip(), []]
            chapters.append(cur)
        elif cur is not None:
            cur[1].append(line)
    return chapters


def body_to_html(lines, sec_prefix):
    out, verse, items = [], [], []
    sec_ids = []
    first_block = True

    def flush():
        if verse:
            out.append('<div class="verse">' + "".join(f"<p>{inline(v)}</p>" for v in verse) + "</div>")
            verse.clear()
        if items:
            out.append("<ul>" + "".join(f"<li>{inline(i)}</li>" for i in items) + "</ul>")
            items.clear()

    for raw in lines:
        line = raw.rstrip()
        if line.startswith("> "):
            if items:
                flush()
            verse.append(line[2:])
            continue
        if line.startswith("- "):
            if verse:
                flush()
            items.append(line[2:])
            continue
        flush()
        if not line.strip():
            continue
        if line.startswith("## "):
            sid = f"{sec_prefix}-s{len(sec_ids) + 1}"
            sec_ids.append((sid, line[3:].strip()))
            out.append(f'<h2 id="{sid}">{inline(line[3:].strip())}</h2>')
        elif line.startswith("### "):
            out.append(f"<h3>{inline(line[4:].strip())}</h3>")
        elif line.strip() == "---":
            out.append('<p class="scene">◇</p>')
        elif line.startswith("【"):
            m = re.match(r"【(.+?)】(.*)", line)
            out.append(f'<p class="dlg"><span class="spk">{inline(m.group(1))}</span>　{inline(m.group(2))}</p>')
        elif line.startswith("〔"):
            out.append(f'<p class="summary">{inline(line)}</p>')
        elif line.startswith("※"):
            cls = "source" if first_block else "note"
            out.append(f'<p class="{cls}">{inline(line)}</p>')
        else:
            out.append(f"<p>{inline(line)}</p>")
        first_block = False
    flush()
    return "\n".join(out), sec_ids


def build_book():
    """部・章の構造を作る。"""
    book = []  # [{part, sub, chapters:[{id,title,html,sections}]}]
    n = 0
    for part, sub, files in PARTS:
        chaps = []
        for f in files:
            for title, lines in parse_chapters((SRC / f).read_text(encoding="utf-8")):
                n += 1
                cid = f"c{n:02d}"
                body, secs = body_to_html(lines, cid)
                chaps.append({"id": cid, "title": title, "html": body, "sections": secs})
        book.append({"part": part, "sub": sub, "chapters": chaps})
    return book


# ---------- 表紙 ----------

def find_font():
    for p in ["/System/Library/Fonts/ヒラギノ明朝 ProN.ttc",
              "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/99517f5220d46dff05d0dbb2a22d0036afefb089.asset/AssetData/YuMincho.ttc"]:
        if Path(p).exists():
            return p
    raise SystemExit("日本語フォントが見つかりません")


def draw_vertical(d, text, x, y, font, fill, spacing=1.08):
    size = font.size
    for ch in text:
        if ch == "　":
            y += size * spacing
            continue
        w = d.textlength(ch, font=font)
        d.text((x - w / 2, y), ch, font=font, fill=fill)
        y += size * spacing
    return y


def make_cover(path):
    W, H = 1600, 2560
    bg, gold, ink = (18, 24, 44), (201, 168, 96), (232, 224, 205)
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    fp = find_font()
    d.rectangle([70, 70, W - 70, H - 70], outline=gold, width=4)
    d.rectangle([92, 92, W - 92, H - 92], outline=gold, width=1)

    # 三つの円（帰郷・上昇・巡礼）
    cx, cy, r = W // 2, 560, 150
    for i, dx in enumerate((-190, 0, 190)):
        d.ellipse([cx + dx - r, cy - r, cx + dx + r, cy + r], outline=gold, width=3)

    title_font = ImageFont.truetype(fp, 230, index=1 if fp.endswith(".ttc") else 0)
    draw_vertical(d, TITLE, W // 2 + 160, 900, title_font, ink)

    sub_font = ImageFont.truetype(fp, 64)
    draw_vertical(d, "ホメロス", W // 2 - 140, 960, sub_font, gold)
    draw_vertical(d, "プラトン", W // 2 - 270, 1100, sub_font, gold)
    draw_vertical(d, "ダンテ", W // 2 - 400, 1240, sub_font, gold)

    small = ImageFont.truetype(fp, 52)
    label = "現代語再話"
    w = d.textlength(label, font=small)
    d.line([W // 2 - 300, H - 330, W // 2 + 300, H - 330], fill=gold, width=2)
    d.text((W // 2 - w / 2, H - 290), label, font=small, fill=ink)
    img.save(path, "PNG", optimize=True)


# ---------- CSS ----------

CSS_COMMON = """
@charset "utf-8";
body { font-family: "Hiragino Mincho ProN", "YuMincho", "Yu Mincho", "Noto Serif JP", serif; line-height: 1.8; margin: 0; padding: 0; }
p { margin: 0; text-indent: 1em; }
h1 { font-size: 1.45em; font-weight: bold; line-height: 1.5; }
h2 { font-size: 1.15em; font-weight: bold; }
h3 { font-size: 1.0em; font-weight: bold; }
.spk { font-weight: bold; }
.summary { text-indent: 0; font-size: 0.9em; color: #5b5346; }
.note { text-indent: 0; font-size: 0.85em; color: #6b6458; }
.source { text-indent: 0; font-size: 0.85em; color: #8a7a55; }
.scene { text-indent: 0; text-align: center; color: #9a8a60; }
.dlg { text-indent: -1em; }
ul { list-style: none; padding: 0; margin: 0; }
li { text-indent: -1em; }
li::before { content: "・"; }
.parttitle { font-size: 2em; font-weight: bold; }
.partsub, .epigraph { text-indent: 0; color: #6b6458; }
.titlepage h1 { font-size: 2.4em; }
.center { text-indent: 0; text-align: center; }
nav ol { list-style: none; padding: 0; }
nav a { color: inherit; text-decoration: none; }
"""

CSS_VERTICAL = CSS_COMMON + """
html { writing-mode: vertical-rl; -webkit-writing-mode: vertical-rl; -epub-writing-mode: vertical-rl; }
body { margin: 0; }
h1 { margin: 0 0 0 2em; padding-top: 2em; }
h2 { margin: 0 1.5em 0 1em; padding-top: 1em; }
h3 { margin: 0 1em 0 0.5em; padding-top: 1em; }
.summary { margin: 0.6em 0.8em 0.6em 0.8em; margin-top: 1em; }
.note, .source { margin: 0.5em 0.6em; margin-top: 2em; }
.source { margin-left: 1.5em; }
.verse { margin: 0 1em; padding-top: 2em; }
.verse p { text-indent: -1em; padding-top: 1em; }
.dlg { margin-top: 1em; }
.scene { margin: 0 1em; }
ul { margin: 0 0.5em; padding-top: 1em; }
.part { padding-top: 15%; }
.parttitle { margin-left: 1.5em; }
.titlepage { padding-top: 20%; }
nav ol ol { padding-top: 1em; }
"""

CSS_HORIZONTAL = CSS_COMMON + """
body { margin: 0 4%; }
p { text-align: justify; }
h1 { margin: 2.5em 0 1.5em; }
h2 { margin: 2em 0 0.8em; }
h3 { margin: 1.5em 0 0.5em; }
.summary { margin: 0.8em 0 0.8em 1em; padding-left: 0.8em; border-left: 2px solid #d9cfb8; }
.note { margin: 0.8em 0 0.8em 2em; }
.source { margin: -0.8em 0 1.5em; text-align: right; }
.verse { margin: 1.2em 0 1.2em 2em; }
.verse p { text-indent: -1em; padding-left: 1em; }
.dlg { margin-left: 1em; margin-top: 0.3em; }
.scene { margin: 1.2em 0; }
ul { margin: 0.8em 0 0.8em 1em; }
.part { margin-top: 30%; text-align: center; }
.part p { text-align: center; }
.titlepage { margin-top: 30%; text-align: center; }
nav ol ol { padding-left: 1.2em; }
"""


# ---------- EPUB ----------

def xhtml(title, body, lang="ja", epub_type=None, body_class=None):
    bc = f' class="{body_class}"' if body_class else ""
    et = f' epub:type="{epub_type}"' if epub_type else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{lang}" lang="{lang}">
<head>
<meta charset="UTF-8"/>
<title>{esc(title)}</title>
<link rel="stylesheet" type="text/css" href="../style.css"/>
</head>
<body{bc}{et}>
{body}
</body>
</html>
"""


def build_epub(book, vertical, out_path, cover_png):
    docs = []  # (filename, title, content, in_toc)
    docs.append(("cover.xhtml", "表紙",
                 xhtml("表紙", '<div class="center"><img src="../images/cover.png" alt="三つの旅" style="height:100%;max-width:100%"/></div>',
                       epub_type="cover"), False))
    title_body = f"""<div class="titlepage">
<h1 class="center">{TITLE}</h1>
<p class="center">ホメロス　プラトン　ダンテ</p>
<p class="center">　</p>
<p class="center">現代語再話</p>
</div>"""
    docs.append(("title.xhtml", "扉", xhtml("扉", title_body, epub_type="titlepage"), False))

    toc_tree = []  # [(href, label, children)]
    part_no = 0
    for part in book:
        children = []
        if part["part"]:
            part_no += 1
            fn = f"part{part_no}.xhtml"
            works = "".join(f'<p class="partsub">{esc(w.strip())}</p>' for w in part["sub"].split("／"))
            body = f"""<div class="part">
<h1 class="parttitle">{esc(part["part"])}</h1>
{works}
<p class="epigraph">　</p>
<p class="epigraph">{esc(PART_EPIGRAPHS[part["part"]])}</p>
</div>"""
            docs.append((fn, part["part"], xhtml(part["part"], body, epub_type="part"), True))
            toc_tree.append((f"text/{fn}", part["part"], children))
            target = children
        else:
            target = toc_tree
        for ch in part["chapters"]:
            fn = f"{ch['id']}.xhtml"
            body = f'<section epub:type="chapter">\n<h1>{esc(ch["title"])}</h1>\n{ch["html"]}\n</section>'
            docs.append((fn, ch["title"], xhtml(ch["title"], body), True))
            secs = [(f"text/{fn}#{sid}", stitle, []) for sid, stitle in ch["sections"]]
            target.append((f"text/{fn}", ch["title"], secs))

    colophon = f"""<div class="titlepage">
<p class="center">{TITLE}</p>
<p class="center">ホメロス・プラトン・ダンテ　現代語再話</p>
<p class="center">　</p>
<p class="center">原作　ホメロス『イリアス』『オデュッセイア』</p>
<p class="center">プラトン『饗宴』『国家』『ソクラテスの弁明』『クリトン』『パイドン』</p>
<p class="center">ダンテ『神曲』</p>
<p class="center">　</p>
<p class="center">{datetime.now().strftime('%Y年%-m月%-d日')}　作成</p>
</div>"""
    docs.append(("colophon.xhtml", "奥付", xhtml("奥付", colophon, epub_type="colophon"), True))
    toc_tree.append(("text/colophon.xhtml", "奥付", []))

    # nav.xhtml
    def nav_ol(nodes, prefix):
        items = []
        for href, label, kids in nodes:
            inner = f'<a href="{prefix}{href}">{esc(label)}</a>'
            if kids:
                inner += "\n<ol>" + nav_ol(kids, prefix) + "</ol>"
            items.append(f"<li>{inner}</li>")
        return "\n".join(items)

    # 目次ページ（本文内表示用）は章までの2階層にとどめる
    def shallow(nodes, depth=0):
        return [(h, l, shallow(k, depth + 1) if depth == 0 else []) for h, l, k in nodes]

    nav_body = f"""<nav epub:type="toc" id="toc">
<h1>目次</h1>
<ol>
{nav_ol(shallow(toc_tree), "")}
</ol>
</nav>
<nav epub:type="landmarks" hidden="hidden">
<ol>
<li><a epub:type="cover" href="text/cover.xhtml">表紙</a></li>
<li><a epub:type="toc" href="nav.xhtml">目次</a></li>
<li><a epub:type="bodymatter" href="text/{book[0]['chapters'][0]['id']}.xhtml">本文</a></li>
</ol>
</nav>"""
    nav = xhtml("目次", nav_body).replace('href="../style.css"', 'href="style.css"')

    # toc.ncx（古いリーダー向け）
    play = [0]

    def ncx_points(nodes):
        s = []
        for href, label, kids in nodes:
            play[0] += 1
            s.append(f'<navPoint id="np{play[0]}" playOrder="{play[0]}"><navLabel><text>{esc(label)}</text></navLabel>'
                     f'<content src="{href}"/>{ncx_points(kids)}</navPoint>')
        return "".join(s)

    ncx = f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" xml:lang="ja">
<head><meta name="dtb:uid" content="{BOOK_ID}"/><meta name="dtb:depth" content="3"/></head>
<docTitle><text>{esc(FULL_TITLE)}</text></docTitle>
<navMap>{ncx_points(toc_tree)}</navMap>
</ncx>"""

    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    creators = "\n".join(f'<dc:creator id="cr{i}">{esc(c)}</dc:creator>' for i, c in enumerate(CREATORS))
    manifest = [
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
        '<item id="css" href="style.css" media-type="text/css"/>',
        '<item id="cover-image" href="images/cover.png" media-type="image/png" properties="cover-image"/>',
    ]
    spine = []
    for fn, _, _, _ in docs:
        iid = "x-" + fn.replace(".xhtml", "")
        props = ' properties="svg"' if False else ""
        manifest.append(f'<item id="{iid}" href="text/{fn}" media-type="application/xhtml+xml"{props}/>')
        spine.append(f'<itemref idref="{iid}"/>')
        if fn == "title.xhtml":
            spine.append('<itemref idref="nav"/>')
    ppd = ' page-progression-direction="rtl"' if vertical else ""
    wm = '<meta name="primary-writing-mode" content="vertical-rl"/>' if vertical else ""
    opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="ja">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="bookid">{BOOK_ID}{'-v' if vertical else '-h'}</dc:identifier>
<dc:title>{esc(FULL_TITLE)}</dc:title>
<dc:language>ja</dc:language>
{creators}
<meta property="dcterms:modified">{modified}</meta>
<meta name="cover" content="cover-image"/>
{wm}
</metadata>
<manifest>
{chr(10).join(manifest)}
</manifest>
<spine toc="ncx"{ppd}>
{chr(10).join(spine)}
</spine>
</package>"""

    container = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""

    with zipfile.ZipFile(out_path, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/nav.xhtml", nav, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/toc.ncx", ncx, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/style.css", CSS_VERTICAL if vertical else CSS_HORIZONTAL, compress_type=zipfile.ZIP_DEFLATED)
        z.write(cover_png, "OEBPS/images/cover.png", compress_type=zipfile.ZIP_STORED)
        for fn, _, content, _ in docs:
            z.writestr(f"OEBPS/text/{fn}", content, compress_type=zipfile.ZIP_DEFLATED)
    return docs


# ---------- 単体HTML（ブラウザでオフライン閲覧） ----------

HTML_TEMPLATE = (ROOT / "reader_template.html")


def build_html(book, out_path):
    toc, content = [], []
    part_no = 0
    for part in book:
        if part["part"]:
            part_no += 1
            pid = f"part{part_no}"
            works = "".join(f'<p class="partsub">{esc(w.strip())}</p>' for w in part["sub"].split("／"))
            content.append(f'<section class="part" id="{pid}"><h1 class="parttitle">{esc(part["part"])}</h1>{works}'
                           f'<p class="epigraph">{esc(PART_EPIGRAPHS[part["part"]])}</p></section>')
            toc.append(f'<li class="toc-part"><a href="#{pid}">{esc(part["part"])}</a></li>')
        for ch in part["chapters"]:
            content.append(f'<section class="chapter" id="{ch["id"]}"><h1>{esc(ch["title"])}</h1>\n{ch["html"]}</section>')
            cls = "toc-ch" + (" in-part" if part["part"] else "")
            toc.append(f'<li class="{cls}"><a href="#{ch["id"]}">{esc(ch["title"])}</a></li>')
    tpl = HTML_TEMPLATE.read_text(encoding="utf-8")
    out = (tpl.replace("{{TITLE}}", esc(TITLE))
              .replace("{{TOC}}", "\n".join(toc))
              .replace("{{CONTENT}}", "\n".join(content)))
    out_path.write_text(out, encoding="utf-8")


def main():
    DIST.mkdir(exist_ok=True)
    book = build_book()
    cover = DIST / "cover.png"
    make_cover(cover)
    build_epub(book, True, DIST / "三つの旅_縦書き.epub", cover)
    build_epub(book, False, DIST / "三つの旅_横書き.epub", cover)
    build_html(book, DIST / "三つの旅.html")
    nchars = sum(len(re.sub(r"<[^>]+>", "", c["html"])) for p in book for c in p["chapters"])
    print(f"chapters={sum(len(p['chapters']) for p in book)} chars≈{nchars}")


if __name__ == "__main__":
    main()
