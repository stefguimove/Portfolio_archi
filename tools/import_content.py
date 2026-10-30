#!/usr/bin/env python3
"""Amorce le contenu editable de content/ a partir du modele genere.

Outil de migration : convertit `src/data/site.json` (produit par l'ancienne
chaine InDesign) en dossiers editables :

  content/site.json                  informations generales + couverture
  content/presentation.md            texte de la page Presentation
  content/transition.md              texte de la section Transition
  content/projets/<NN-slug>/projet.md  metadonnees, texte et legendes
  content/projets/<NN-slug>/images/    images webp optimisees

Les images proviennent de public/assets/<slug>/full.webp. Les originaux
(design/Links, non versionnes) ne sont pas copies.

Usage :
  python3 tools/import_content.py [--force]
"""

import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "src" / "data" / "site.json"
ASSETS = ROOT / "public" / "assets"
CONTENT = ROOT / "content"
PROJETS = CONTENT / "projets"


def slugify(value):
    value = Path(value).stem
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return re.sub(r"-{2,}", "-", value) or "projet"


def paragraphs(items):
    return "\n\n".join(item["text"].strip() for item in items if item.get("text", "").strip())


def front_matter(data):
    body = yaml.safe_dump(data, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{body}\n---\n"


def copy_full(asset_slug, target):
    source = ASSETS / asset_slug / "full.webp"
    if not source.exists():
        sys.exit(f"image introuvable : {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def main():
    force = "--force" in sys.argv
    if (CONTENT / "site.json").exists() and not force:
        sys.exit("content/site.json existe deja ; relancer avec --force pour ecraser.")

    data = json.loads(SITE.read_text(encoding="utf-8"))
    PROJETS.mkdir(parents=True, exist_ok=True)

    cover_slug = data["cover"]["image"]
    copy_full(cover_slug, CONTENT / "images" / "couverture.webp")

    site = {
        **data["site"],
        "cover": "images/couverture.webp",
    }
    (CONTENT / "site.json").write_text(
        json.dumps(site, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    (CONTENT / "presentation.md").write_text(
        paragraphs(data["presentation"]["paragraphs"]) + "\n", encoding="utf-8"
    )
    (CONTENT / "transition.md").write_text(
        paragraphs(data["transition"]["paragraphs"]) + "\n", encoding="utf-8"
    )

    for project in data["projects"]:
        label = project.get("label") or ""
        folder = PROJETS / f"{label}-{project['slug']}" if label else PROJETS / project["slug"]
        (folder / "images").mkdir(parents=True, exist_ok=True)

        images = []
        for index, asset in enumerate(project.get("assets", []), 1):
            name = f"{index:02d}-{slugify(asset['slug'])}.webp"
            copy_full(asset["slug"], folder / "images" / name)
            images.append({
                "fichier": name,
                "source": asset["source"],
                "orientation": "auto",
            })

        meta = {
            "slug": project["slug"],
            "label": label,
            "title": project["title"],
            "meta": project.get("meta", ""),
            "statut": "terminé" if project.get("complete", True) else "en cours",
        }
        if images:
            meta["images"] = images
        if project.get("models"):
            meta["modeles"] = [
                {"slug": model["slug"], "titre": model["title"], "meta": model.get("meta", "")}
                for model in project["models"]
            ]

        document = front_matter(meta) + "\n" + paragraphs(project.get("paragraphs", [])) + "\n"
        (folder / "projet.md").write_text(document, encoding="utf-8")
        print(f"  {folder.relative_to(ROOT)}  ({len(images)} image(s))")

    print(f"contenu editable pret dans {CONTENT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
