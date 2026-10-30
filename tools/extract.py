#!/usr/bin/env python3
"""Extrait le contenu du portfolio InDesign (IDML + PDF) vers un modele de contenu exploitable.

Le texte vient de l'IDML (source autoritative, couvre toutes les pages du document).
Le texte du PDF est conserve separement : il ne couvre que les pages exportees et
sert de controle croise.

Sortie :
  content/manifest.json   structure des pages, des textes et des images placees
  content/pages/pNN.txt   texte de chaque page
"""

import json
import math
import re
import subprocess
import urllib.parse
import zipfile
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parent.parent
DESIGN = ROOT / "design"
IDML = DESIGN / "Portfolio 2026.idml"
PDF = DESIGN / "Portfolio 2026.pdf"
OUT = ROOT / "content"

# A4 paysage, en points PostScript (unites internes du document InDesign)
PAGE_W = 841.889763778
PAGE_H = 595.275590551

PLACED_ELEMENTS = {
    "Image": "raster",
    "PDF": "vector",
    "EPS": "vector",
}


def local_name(tag):
    return tag.split("}")[-1]


def parse_transform(value):
    """Matrice IDML [a b c d e f]."""
    if not value:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    return tuple(float(x) for x in value.split())


def apply_transform(matrix, x, y):
    a, b, c, d, e, f = matrix
    return (a * x + c * y + e, b * x + d * y + f)


def element_bbox(element):
    """Boite englobante d'un element de page, dans le repere du spread."""
    if element is None:
        return None
    points = []
    geometry = element.find("Properties/PathGeometry")
    if geometry is None:
        geometry = element.find(".//PathGeometry")
    if geometry is not None:
        for point in geometry.iter("PathPointType"):
            for anchor in ("Anchor", "LeftDirection", "RightDirection"):
                raw = point.get(anchor)
                if raw:
                    try:
                        points.append(tuple(float(v) for v in raw.split()))
                    except ValueError:
                        pass
    if not points:
        return None
    matrix = parse_transform(element.get("ItemTransform"))
    xs, ys = [], []
    for x, y in points:
        tx, ty = apply_transform(matrix, x, y)
        xs.append(tx)
        ys.append(ty)
    return (min(xs), min(ys), max(xs), max(ys))


def page_bbox(page):
    """Rectangle de la page dans le repere du spread."""
    y1, x1, y2, x2 = [float(v) for v in page.get("GeometricBounds").split()]
    matrix = parse_transform(page.get("ItemTransform"))
    xs, ys = [], []
    for x, y in ((x1, y1), (x2, y1), (x2, y2), (x1, y2)):
        tx, ty = apply_transform(matrix, x, y)
        xs.append(tx)
        ys.append(ty)
    return (min(xs), min(ys), max(xs), max(ys))


def overlap_area(a, b):
    dx = min(a[2], b[2]) - max(a[0], b[0])
    dy = min(a[3], b[3]) - max(a[1], b[1])
    return dx * dy if dx > 0 and dy > 0 else 0.0


def frame_of(link):
    """Remonte du lien jusqu'au cadre (page item) qui le porte."""
    node = link.getparent()
    while node is not None:
        if node.find("Properties/PathGeometry") is not None:
            return node
        node = node.getparent()
    return None


def story_text(archive, story_id):
    """Texte d'un story, paragraphe par paragraphe."""
    try:
        root = etree.fromstring(archive.read(f"Stories/Story_{story_id}.xml"))
    except KeyError:
        return ""

    paragraphs = []
    for para in root.iter("ParagraphStyleRange"):
        text = "".join(node.text or "" for node in para.iter("Content"))
        if text.strip():
            paragraphs.append(text.strip())
    if not paragraphs:
        text = "".join(node.text or "" for node in root.iter("Content"))
        if text.strip():
            paragraphs.append(text.strip())
    return "\n".join(paragraphs)


def read_idml():
    """Parcourt les spreads dans l'ordre du designmap : pages, textes, images."""
    archive = zipfile.ZipFile(IDML)
    designmap = archive.read("designmap.xml").decode("utf-8", "replace")
    spread_order = re.findall(r'<idPkg:Spread[^>]*src="([^"]+)"', designmap)

    story_cache = {}
    pages = {}
    anomalies = []
    seen_stories = set()

    for index, name in enumerate(spread_order, start=1):
        spread = etree.fromstring(archive.read(name))
        spread_el = spread[0] if len(spread) else spread
        page_rects = []
        for page in spread_el.iter("Page"):
            number = int(page.get("Name"))
            page_rects.append((number, page_bbox(page)))
            pages[number] = {
                "number": number,
                "spread": Path(name).stem,
                "spread_index": index,
                "placed": [],
                "blocks": [],
            }

        def owning_page(rect):
            if not page_rects:
                return None, None
            if rect is None:
                return page_rects[0][0], page_rects[0][1]
            target = max(page_rects, key=lambda pr: overlap_area(rect, pr[1]))
            if overlap_area(rect, target[1]) <= 0:
                return None, None
            return target[0], target[1]

        for link in spread_el.iter("Link"):
            kind = local_name(link.getparent().tag)
            if kind not in PLACED_ELEMENTS:
                continue
            frame = frame_of(link)
            rect = element_bbox(frame)
            source = urllib.parse.unquote(link.get("LinkResourceURI") or "").split("/")[-1]
            target, page_rect = owning_page(rect)
            if target is None:
                anomalies.append(f"{Path(name).stem}: image hors page ({source})")
                continue
            box = None
            if rect is not None and page_rect is not None:
                box = {
                    "x": round(rect[0] - page_rect[0], 1),
                    "y": round(rect[1] - page_rect[1], 1),
                    "w": round(rect[2] - rect[0], 1),
                    "h": round(rect[3] - rect[1], 1),
                }
            angle = 0.0
            if frame is not None:
                a, b = parse_transform(frame.get("ItemTransform"))[:2]
                angle = round(math.degrees(math.atan2(b, a)), 1)
            pages[target]["placed"].append({
                "kind": PLACED_ELEMENTS[kind],
                "source": source,
                "state": link.get("StoredState"),
                "format": (link.get("LinkResourceFormat") or "").replace("$ID/", ""),
                "box": box,
                "angle": angle or 0.0,
            })

        for frame in spread_el.iter("TextFrame"):
            story_id = frame.get("ParentStory")
            if not story_id:
                continue
            if story_id not in story_cache:
                story_cache[story_id] = story_text(archive, story_id)
            text = story_cache[story_id]
            if not text:
                continue
            rect = element_bbox(frame)
            target, page_rect = owning_page(rect)
            if target is None:
                anomalies.append(f"{Path(name).stem}: texte hors page ({story_id})")
                continue
            seen_stories.add(story_id)
            pages[target]["blocks"].append({
                "story": story_id,
                "box": {
                    "x": round(rect[0] - page_rect[0], 1),
                    "y": round(rect[1] - page_rect[1], 1),
                    "w": round(rect[2] - rect[0], 1),
                    "h": round(rect[3] - rect[1], 1),
                } if rect and page_rect else None,
                "text": text,
            })

    for page in pages.values():
        page["blocks"].sort(
            key=lambda b: (b["box"]["y"] if b["box"] else 0, b["box"]["x"] if b["box"] else 0)
        )

    return {
        "pages": pages,
        "spreads": len(spread_order),
        "anomalies": anomalies,
        "stories_used": len(seen_stories),
        "stories_total": sum(1 for n in archive.namelist() if n.startswith("Stories/")),
    }


def read_pdf_text():
    """Texte page par page du PDF exporte, via pdftotext (le PDF est tague)."""
    info = subprocess.run(["pdfinfo", str(PDF)], capture_output=True, text=True, check=True).stdout
    total = int(re.search(r"Pages:\s+(\d+)", info).group(1))
    texts = {}
    for number in range(1, total + 1):
        result = subprocess.run(
            ["pdftotext", "-f", str(number), "-l", str(number), "-layout", str(PDF), "-"],
            capture_output=True, text=True, check=True,
        )
        texts[number] = result.stdout.replace("\f", "").strip()
    return texts, total


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pages").mkdir(parents=True, exist_ok=True)
    idml = read_idml()
    pdf_texts, exported = read_pdf_text()

    numbers = sorted(idml["pages"])
    pages = []
    for number in numbers:
        entry = idml["pages"][number]
        text = "\n\n".join(b["text"] for b in entry["blocks"])
        (OUT / "pages" / f"p{number:02d}.txt").write_text(text + "\n", encoding="utf-8")
        title = next((line.strip() for line in text.splitlines() if line.strip()), "")
        pages.append({
            "number": number,
            "spread": entry["spread"],
            "exported": number <= exported,
            "title": title,
            "text": text,
            "blocks": entry["blocks"],
            "pdf_text": pdf_texts.get(number),
            "placed": entry["placed"],
            "raster": sum(1 for p in entry["placed"] if p["kind"] == "raster"),
            "vector": sum(1 for p in entry["placed"] if p["kind"] == "vector"),
        })

    manifest = {
        "source_idml": IDML.name,
        "page_size": {"width": PAGE_W, "height": PAGE_H},
        "source_pdf": PDF.name,
        "document_pages": len(numbers),
        "exported_pages": exported,
        "spread_count": idml["spreads"],
        "stories_used": idml["stories_used"],
        "stories_total": idml["stories_total"],
        "pages": pages,
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    lines = [f"pages du document: {len(numbers)} | exportees en PDF: {exported}"]
    if len(numbers) > exported:
        lines.append(
            f"ATTENTION: {len(numbers) - exported} pages absentes du PDF "
            f"(n° {exported + 1} a {len(numbers)})"
        )
    lines.append(f"stories utilisees: {idml['stories_used']} / {idml['stories_total']}")
    if idml["anomalies"]:
        lines.append(f"anomalies de placement: {len(idml['anomalies'])}")
        for item in idml["anomalies"][:8]:
            lines.append(f"   {item}")
    unique = {p["source"] for page in pages for p in page["placed"]}
    lines.append(
        f"liens uniques: {len(unique)} | placements: {sum(len(p['placed']) for p in pages)}"
    )
    for page in pages:
        flag = " " if page["exported"] else "!"
        lines.append(
            f" {flag}p{page['number']:02d} raster={page['raster']:2d} vector={page['vector']:2d}"
            f" txt={len(page['text']):5d}c  {page['title'][:56]}"
        )
    print("\n".join(lines))


if __name__ == "__main__":
    main()
