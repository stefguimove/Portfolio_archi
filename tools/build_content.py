#!/usr/bin/env python3
"""Compile le contenu editable de content/ vers src/data/site.json.

Sources (versionnees) :
  content/site.json                      informations generales + couverture
  content/presentation.md                texte de la page Presentation
  content/transition.md                  texte de la section Transition
  content/projets/<dossier>/projet.md    metadonnees, texte, legendes, orientation
  content/projets/<dossier>/images/      images (webp, pdf, png, jpg...)

Sortie (generee) :
  src/data/site.json
  public/assets/<projet>/<image>/{full,thumb}.webp

Usage :
  python3 tools/build_content.py            compile le site
  python3 tools/build_content.py --check    verifie le contenu sans rien ecrire
  python3 tools/build_content.py --watch    recompile a chaque modification
  python3 tools/build_content.py --new "Titre du projet"
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
PROJETS = CONTENT / "projets"
OUT = ROOT / "public" / "assets"
DATA = ROOT / "src" / "data" / "site.json"
CACHE = CONTENT / ".cache" / "assets.json"
TMP = CONTENT / ".cache" / "tmp"

FULL_LONG = 2400
THUMB_LONG = 720
ORIENTATIONS = {"auto", "paysage", "portrait", "pleine-largeur"}
ROTATIONS = {0, 90, 180, 270}
SUPPORTED = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}


def slugify(value):
    value = Path(value).stem
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return re.sub(r"-{2,}", "-", value)


def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{cmd[0]} a echoue : {result.stderr.strip()[:300]}")
    return result.stdout


def read_document(path):
    """Retourne (front matter, corps) ; le front matter est optionnel."""
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return yaml.safe_load(parts[1]) or {}, parts[2]
    return {}, text


def paragraphs(body):
    blocks = re.split(r"\n\s*\n", body.strip())
    return [" ".join(block.split()) for block in blocks if block.strip()]


def leading_number(name):
    match = re.match(r"^(\d+)", name)
    return match.group(1) if match else ""


def fingerprint(path, rotation):
    stat = path.stat()
    raw = f"{path.relative_to(ROOT)}:{stat.st_size}:{stat.st_mtime_ns}:{rotation}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def load_cache():
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {}


def save_cache(cache):
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def render(source, folder, rotation):
    """Produit full.webp et thumb.webp, retourne les dimensions finales."""
    folder.mkdir(parents=True, exist_ok=True)
    full = folder / "full.webp"
    thumb = folder / "thumb.webp"
    TMP.mkdir(parents=True, exist_ok=True)

    if source.suffix.lower() == ".webp" and rotation == 0:
        shutil.copy2(source, full)
    else:
        temporary = None
        if source.suffix.lower() == ".pdf":
            temporary = TMP / f"{folder.parent.name}-{folder.name}.png"
            run([
                "pdftocairo", "-png", "-scale-to", str(FULL_LONG), "-f", "1", "-l", "1",
                "-singlefile", str(source), str(temporary.with_suffix("")),
            ])
            argument = str(temporary)
            alpha = []
        else:
            argument = f"{source}[0]"
            alpha = ["-background", "white", "-alpha", "remove", "-alpha", "on"]
        try:
            run([
                "magick", argument, *alpha, "-rotate", str(rotation),
                "-resize", f"{FULL_LONG}x{FULL_LONG}>", "-quality", "82",
                "-define", "webp:method=5", "-strip", str(full),
            ])
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

    run([
        "magick", str(full), "-resize", f"{THUMB_LONG}x{THUMB_LONG}>", "-quality", "78",
        "-define", "webp:method=5", "-strip", str(thumb),
    ])
    width, height = run(["identify", "-format", "%w %h", str(full)]).split()
    return int(width), int(height)


def image_asset(folder, entry):
    if isinstance(entry, str):
        entry = {"fichier": entry}
    fichier = entry.get("fichier")
    if not fichier:
        raise SystemExit(f"{folder.name} : image sans 'fichier' dans le front matter.")

    source = folder / "images" / fichier
    if not source.exists():
        raise SystemExit(f"image introuvable : {source.relative_to(ROOT)}")
    if source.suffix.lower() not in SUPPORTED:
        raise SystemExit(
            f"{source.relative_to(ROOT)} : format non pris en charge "
            f"({', '.join(sorted(SUPPORTED))})"
        )

    orientation = str(entry.get("orientation") or "auto")
    if orientation not in ORIENTATIONS:
        raise SystemExit(
            f"{source.relative_to(ROOT)} : orientation '{orientation}' inconnue "
            f"({', '.join(sorted(ORIENTATIONS))})"
        )
    rotation = int(entry.get("rotation") or 0)
    if rotation not in ROTATIONS:
        raise SystemExit(f"{source.relative_to(ROOT)} : rotation '{rotation}' invalide (0, 90, 180, 270)")

    return {
        "fichier": fichier,
        "source": source,
        "orientation": orientation,
        "rotation": rotation,
        "legende": entry.get("legende"),
        "origine": str(entry.get("source") or fichier),
    }


def build_project(folder, cache, produced, used_keys, warnings, dry_run):
    meta, body = read_document(folder / "projet.md")
    if not meta.get("title"):
        raise SystemExit(f"{folder.relative_to(ROOT)} : 'title' manquant dans le front matter.")

    slug = str(meta.get("slug") or re.sub(r"^\d+[-_ ]*", "", folder.name))
    label = str(meta.get("label") or leading_number(folder.name))

    assets = []
    used = set()
    declared = set()
    for index, entry in enumerate(meta.get("images") or [], 1):
        spec = image_asset(folder, entry)
        declared.add(spec["fichier"])

        base = slugify(spec["fichier"]) or f"image-{index}"
        asset_slug = base
        suffix = 1
        while asset_slug in used:
            suffix += 1
            asset_slug = f"{base}-{suffix}"
        used.add(asset_slug)

        destination = OUT / slug / asset_slug
        key = fingerprint(spec["source"], spec["rotation"])
        used_keys.add(key)
        cached = cache.get(key)
        outputs = (destination / "full.webp").exists() and (destination / "thumb.webp").exists()

        if cached and outputs:
            width, height = cached["width"], cached["height"]
        elif dry_run:
            width = height = 0
        else:
            width, height = render(spec["source"], destination, spec["rotation"])
            cache[key] = {"width": width, "height": height}
        produced.add(slug)

        asset = {
            "slug": f"{slug}/{asset_slug}",
            "source": spec["origine"],
            "width": width,
            "height": height,
            "orientation": spec["orientation"],
        }
        if spec["legende"] is not None:
            asset["caption"] = str(spec["legende"])
        assets.append(asset)

    images_dir = folder / "images"
    if images_dir.is_dir():
        for file in sorted(images_dir.iterdir()):
            if file.is_file() and file.name not in declared:
                warnings.append(f"{file.relative_to(ROOT)} : image non declaree dans les legendes")

    return {
        "slug": slug,
        "label": label,
        "title": str(meta["title"]),
        "meta": str(meta.get("meta") or ""),
        "complete": str(meta.get("statut") or "terminé").strip().lower() != "en cours",
        "paragraphs": [{"text": text} for text in paragraphs(body)],
        "assets": assets,
        "models": [
            {
                "slug": model["slug"],
                "title": model.get("titre") or model.get("title") or model["slug"],
                "meta": model.get("meta") or "",
            }
            for model in (meta.get("modeles") or [])
        ],
    }


def build_cover(raw, cache, produced, used_keys, dry_run):
    relative = raw.get("cover") or "images/couverture.webp"
    source = CONTENT / relative
    if not source.exists():
        return {}
    key = fingerprint(source, 0)
    used_keys.add(key)
    destination = OUT / "couverture"
    cached = cache.get(key)
    outputs = (destination / "full.webp").exists() and (destination / "thumb.webp").exists()
    if cached and outputs:
        width, height = cached["width"], cached["height"]
    elif dry_run:
        width = height = 0
    else:
        width, height = render(source, destination, 0)
        cache[key] = {"width": width, "height": height}
    produced.add("couverture")
    return {"image": "couverture"}


def section(name):
    path = CONTENT / name
    if not path.exists():
        return {"paragraphs": []}
    _, body = read_document(path)
    return {"paragraphs": [{"text": text} for text in paragraphs(body)]}


def build(dry_run=False):
    config = CONTENT / "site.json"
    if not config.exists():
        raise SystemExit(f"{config.relative_to(ROOT)} manquant.")
    raw = json.loads(config.read_text(encoding="utf-8"))
    cache = load_cache()
    produced = set()
    warnings = []
    used_keys = set()

    projects = []
    if PROJETS.is_dir():
        for folder in sorted(PROJETS.iterdir()):
            if (folder / "projet.md").exists():
                projects.append(
                    build_project(folder, cache, produced, used_keys, warnings, dry_run)
                )

    slugs = [project["slug"] for project in projects]
    duplicates = {slug for slug in slugs if slugs.count(slug) > 1}
    if duplicates:
        raise SystemExit(f"slug(s) de projet en double : {', '.join(sorted(duplicates))}")

    keys_before = len(cache)
    for key in list(cache):
        if key not in used_keys:
            del cache[key]

    cover = build_cover(raw, cache, produced, used_keys, dry_run)
    site = {
        key: raw[key]
        for key in ("title", "author", "year", "school", "description", "level")
        if key in raw
    }
    data = {
        "site": site,
        "cover": cover,
        "presentation": section("presentation.md"),
        "transition": section("transition.md"),
        "projects": projects,
    }

    images = sum(len(project["assets"]) for project in projects)
    if dry_run:
        print(f"contenu valide : {len(projects)} projet(s), {images} image(s)")
    else:
        OUT.mkdir(parents=True, exist_ok=True)
        for child in OUT.iterdir():
            if child.is_dir() and child.name not in produced:
                shutil.rmtree(child)
        DATA.parent.mkdir(parents=True, exist_ok=True)
        DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        save_cache(cache)
        if TMP.is_dir() and not any(TMP.iterdir()):
            TMP.rmdir()
        print(f"contenu compile : {len(projects)} projet(s), {images} image(s) -> {DATA.relative_to(ROOT)}")
        if len(cache) < keys_before:
            print(f"cache : {keys_before - len(cache)} entree(s) obsolète(s) retirée(s)")

    for warning in warnings:
        print(f"  ATTENTION {warning}")
    return data


def new_project(title):
    PROJETS.mkdir(parents=True, exist_ok=True)
    numbers = []
    for folder in PROJETS.iterdir():
        if (folder / "projet.md").exists():
            meta, _ = read_document(folder / "projet.md")
            label = str(meta.get("label") or leading_number(folder.name))
            if label.isdigit():
                numbers.append(int(label))
    label = f"{max(numbers, default=0) + 1:02d}"
    folder = PROJETS / f"{label}-{slugify(title)}"
    if folder.exists():
        sys.exit(f"{folder.relative_to(ROOT)} existe deja.")
    (folder / "images").mkdir(parents=True)
    meta = {
        "slug": slugify(title),
        "label": label,
        "title": title,
        "meta": "",
        "statut": "terminé",
        "images": [],
    }
    document = "---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip() + "\n---\n\n"
    (folder / "projet.md").write_text(document, encoding="utf-8")
    print(f"projet cree : {folder.relative_to(ROOT)}")
    print("  deposer les images dans images/ puis les declarer dans projet.md")


def snapshot():
    state = {}
    for path in CONTENT.rglob("*"):
        if path.is_file() and ".cache" not in path.parts:
            state[str(path)] = path.stat().st_mtime_ns
    return state


def watch():
    build()
    state = snapshot()
    print("surveillance de content/ (Ctrl+C pour arreter)")
    try:
        while True:
            time.sleep(1)
            current = snapshot()
            if current != state:
                try:
                    build()
                except SystemExit as error:
                    print(f"  ECHEC {error}")
                state = current
    except KeyboardInterrupt:
        pass


def main():
    parser = argparse.ArgumentParser(description="Compile le contenu editable du portfolio.")
    parser.add_argument("--check", action="store_true", help="verifie le contenu sans rien ecrire")
    parser.add_argument("--watch", action="store_true", help="recompile a chaque modification")
    parser.add_argument("--new", metavar="TITRE", help="cree un nouveau projet")
    args = parser.parse_args()

    if args.new:
        new_project(args.new)
    elif args.watch:
        watch()
    else:
        build(dry_run=args.check)


if __name__ == "__main__":
    main()
