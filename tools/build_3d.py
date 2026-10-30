#!/usr/bin/env python3
"""Prepare les modeles 3D pour le web.

- convertit tout fichier depose dans design/models/ en GLB optimise (assimp puis
  gltf-transform avec compression Draco)
- supprime les GLB dont la source a disparu

Les titres affiches et le rattachement aux projets ne sont pas geres ici : ils vivent
dans content/structure.json.

Sortie :
  public/models/<slug>.glb
  src/data/models.json
"""

import json
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "design" / "models"
OUT = ROOT / "public" / "models"
DATA = ROOT / "src" / "data" / "models.json"

SUPPORTED = {".obj", ".fbx", ".dae", ".3ds", ".stl", ".glb", ".gltf", ".ply", ".blend"}


def slugify(value):
    value = Path(value).stem
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return re.sub(r"-{2,}", "-", value) or "modele"


def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{cmd[0]} a echoue : {result.stderr.strip()[:300]}")
    return result.stdout


def copy_decoder():
    """Heberge localement le decodeur Draco de three.js.

    model-viewer charge par defaut ce decodeur depuis un CDN Google ; on le sert
    nous-memes pour eviter toute dependance externe au chargement de la page.
    """
    source = ROOT / "node_modules" / "three" / "examples" / "jsm" / "libs" / "draco"
    target = ROOT / "public" / "draco"
    if not source.exists():
        print("  ATTENTION decodeur Draco introuvable dans three ; "
              "model-viewer utilisera son CDN par defaut")
        return
    target.mkdir(parents=True, exist_ok=True)
    for name in ("draco_decoder.js", "draco_decoder.wasm", "draco_wasm_wrapper.js"):
        shutil.copy2(source / name, target / name)
    gltf = source / "gltf"
    if gltf.exists():
        shutil.copytree(gltf, target / "gltf", dirs_exist_ok=True)
    print(f"  decodeur Draco copie -> {target.relative_to(ROOT)}")


def optimise(source, target):
    intermediate = OUT / f".{target.stem}.raw.glb"
    run(["assimp", "export", str(source), str(intermediate)])
    run(["npx", "--yes", "@gltf-transform/cli", "optimize", str(intermediate),
         str(target), "--compress", "draco"])
    intermediate.unlink(missing_ok=True)
    return target.stat().st_size


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    DATA.parent.mkdir(parents=True, exist_ok=True)
    copy_decoder()

    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    sources = sorted(
        path for path in SOURCE_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED
    )

    entries = []
    for source in sources:
        target = OUT / f"{slugify(source.name)}.glb"
        try:
            size = optimise(source, target)
        except RuntimeError as exc:
            print(f"  ECHEC {source.name}: {exc}")
            continue
        entries.append({
            "slug": target.stem,
            "src": f"/models/{target.name}",
            "bytes": size,
            "source": source.name,
        })
        print(f"  {target.name:38s} {size / 1048576:6.2f} Mo  <- {source.name}")

    # les titres et le rattachement aux projets vivent dans content/structure.json
    known = {entry["slug"] for entry in entries}
    for stale in OUT.glob("*.glb"):
        if stale.stem not in known:
            stale.unlink()
            print(f"  retire (source disparue): {stale.name}")

    DATA.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"modeles prets: {len(entries)} -> {DATA.relative_to(ROOT)}")

    if not entries:
        print("  aucun modele dans design/models/ : la page 3D affichera son message d'accueil")


if __name__ == "__main__":
    main()
