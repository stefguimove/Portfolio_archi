# Portfolio — Architecture

Site web du portfolio d'architecture.

## Mise en route

```bash
npm install
npm run dev        # http://localhost:4321
npm run build      # site statique dans dist/
npm run preview    # prévisualisation du build
```

## Modifier le contenu

Les textes et les images vivent dans `content/`, en clair, et se modifient sans InDesign :

```
content/
  site.json                 # titre, auteur, année, école, description, couverture
  presentation.md           # texte de la page Présentation
  transition.md             # texte de la section Transition
  images/couverture.webp
  projets/
    02-habiter-la-transition/
      projet.md             # métadonnées, texte et liste des images
      images/
        01-plan-etage-courant.webp
        02-seuil-diagramme.webp
```

Les images d'origine ont été converties en WebP (2400 px) et versionnées. Un fichier
`pdf`, `png`, `jpg`, `tif` ou `webp` peut être déposé directement dans `images/`.

### Un projet

`projet.md` contient un front matter YAML puis le texte, un paragraphe par bloc séparé par
une ligne vide :

```markdown
---
slug: habiter-la-transition
label: '02'
title: Habiter la transition
meta: P32 · réalisé seul, avec Ingrid Taillandier
statut: terminé
images:
- fichier: 01-plan-etage-courant.webp
  source: plan étage courant.pdf
  orientation: auto
- fichier: 07-photo-maquette.webp
  legende: Maquette du projet
  orientation: portrait
  rotation: 90
modeles:
- slug: mode-base-v1
  titre: Maquette 3D
  meta: Modèle interactif : rotation, zoom, vue en réalité augmentée
---

Premier paragraphe.

Second paragraphe.
```

| Champ | Rôle |
|---|---|
| `slug` | identifiant d'URL (`/projets/<slug>/`) |
| `label`, `title`, `meta` | libellé, titre et ligne d'informations |
| `statut` | `terminé` (défaut) ou `en cours` (affiche le badge) |
| `images[].fichier` | fichier déposé dans `images/` |
| `images[].legende` | légende affichée ; vide = aucune légende, absente = déduite du nom de fichier |
| `images[].source` | nom d'origine, utilisé pour la légende par défaut (facultatif) |
| `images[].orientation` | `auto` (défaut), `paysage`, `portrait` ou `pleine-largeur` |
| `images[].rotation` | `0`, `90`, `180` ou `270` degrés, appliquée à la conversion |
| `modeles[]` | modèles 3D rattachés (voir plus bas) |

L'ordre des images est celui de la liste. Les dossiers de projets sont triés par nom : le
préfixe `01-`, `02-` fixe l'ordre d'affichage.

### Gestes courants

| Besoin | Geste |
|---|---|
| Corriger un texte | éditer le `projet.md` concerné |
| Remplacer une image | déposer le nouveau fichier dans `images/` et mettre à jour `fichier` |
| Changer l'orientation | `orientation: portrait` / `pleine-largeur`, ou `rotation: 90` |
| Ajouter une image | ajouter une entrée dans `images:` |
| Créer un projet | `npm run content:new -- "Titre du projet"` |

Après une modification :

```bash
npm run content      # recompile le contenu (instantané si les images n'ont pas changé)
npm run dev          # ou recharger l'onglet si le serveur tourne déjà
```

Pour recompiler automatiquement à chaque sauvegarde, lancer dans un second terminal :

```bash
npm run content:watch
```

Les images ne sont reconverties que lorsqu'elles changent ; le cache vit dans
`content/.cache/`.

### Vérifier le contenu

```bash
npm run content:check
```

Signale une image déclarée absente, un format ou une orientation invalide, ou un fichier
présent dans `images/` mais non déclaré.

## Chaîne de production

```bash
python3 tools/build_content.py       # content/       ->  src/data/site.json + public/assets/
python3 tools/build_3d.py            # design/models/ ->  public/models/, src/data/models.json
```

| Outil | Rôle |
|---|---|
| `build_content.py` | Compile `content/` en `src/data/site.json` et convertit les images (WebP 2400 px + vignette 720 px). |
| `build_3d.py` | Convertit `design/models/` en GLB optimisé (Draco) et copie le décodeur local. |
| `import_content.py` | Migration : amorce `content/` depuis un `site.json` produit par l'ancienne chaîne. |
| `extract.py` | Extraction brute de l'IDML vers `content/manifest.json` (archive, hors build). |

Prérequis : Python 3 avec PyYAML (`pip install -r tools/requirements.txt`), ImageMagick
(`magick`), poppler (`pdftocairo`), et pour la 3D `assimp` et `npx`.

### Fichiers générés

`src/data/site.json`, `src/data/models.json`, `public/assets/`, `public/models/`,
`public/draco/` et `content/.cache/` sont générés et ne sont pas versionnés.

### Fichiers éditoriaux

- `content/` — textes, images et métadonnées (voir « Modifier le contenu »).
- `src/lib/content.js` — accès aux données, chemins d'actifs, légendes par défaut.
- `src/styles/global.css` — système de design (couleurs prélevées sur le PDF, échelles
  typographiques, mise en page).

## Modèles 3D

Déposer les fichiers dans `design/models/` puis lancer `python3 tools/build_3d.py`.

**Format à privilégier : GLB (glTF 2.0 binaire)**, exporté directement depuis le logiciel
de modélisation — c'est le format natif du web, il transporte matériaux et textures dans un
fichier unique et donne le meilleur rendu. Si le logiciel ne l'exporte pas, **FBX 7.x
binaire** est la meilleure alternative pour l'architecture (matériaux, hiérarchie et échelle
conservés) ; viennent ensuite OBJ, DAE (Collada), 3DS, STL, PLY et BLEND.

Il est inutile de compresser soi-même : la chaîne s'en charge (voir ci-dessous). Fournir un
glTF déjà compressé en Draco est même contre-productif, assimp ne le décode pas.

| | Formats |
|---|---|
| Recommandé | `.glb` |
| Fiable | `.fbx` `.obj` `.dae` `.3ds` `.stl` `.ply` `.blend` |
| À tester au cas par cas | `.ifc` `.step`/`.stp` — lus par assimp, mais le support d'IFC (BIM) est partiel |
| **Illisible** | `.max` (3ds Max), `.c4d` (Cinema 4D), `.skp` (SketchUp) — exporter en FBX, OBJ ou GLB depuis le logiciel d'origine |

Bonnes pratiques à l'export : **unités en mètres** et **Y vers le haut** (sinon le modèle
apparaît à la mauvaise échelle), textures en PNG ou JPEG de 2048 px maximum placées **à côté**
du fichier pour OBJ et FBX (le GLB, lui, les embarque), et viser moins de ~150 000 triangles
par modèle pour rester fluide sur mobile.

La chaîne convertit en GLB optimisé (assimp puis gltf-transform, **compression Draco**) et
copie le décodeur Draco dans `public/draco/`, hébergé localement — aucun appel à un CDN
externe. Vérifié : les textures traversent l'aller-retour OBJ → FBX → GLB et la compression
Draco sans perte.

### Rattacher un modèle à un projet

Le rattachement se déclare dans le `projet.md` concerné — c'est là que vivent le titre et
la description affichés, tandis que `models.json` ne contient que les faits techniques
(chemin, taille, fichier source).

```yaml
modeles:
- slug: mode-base-v1
  titre: Maquette 3D
  meta: Modèle interactif : rotation, zoom, vue en réalité augmentée
```

Le `slug` doit correspondre au nom du fichier source sans extension (minuscules, espaces et
accents transposés) : `Modé Base v1.fbx` devient `mode-base-v1`. En cas de référence erronée,
le build affiche un avertissement et ignore l'entrée plutôt que d'échouer.

Un modèle ainsi déclaré apparaît **à deux endroits** : dans la section 3D de la page du
projet, et sur la page `/modeles`, où il porte un lien vers son projet. Un modèle non
rattaché reste visible sur `/modeles` uniquement.

Après modification :

```bash
python3 tools/build_3d.py && npm run build
```

### Plusieurs modèles

Un fichier par modèle. Le nom du fichier devient l'identifiant de l'entrée dans
`src/data/models.json` ; le titre affiché vient de `titre` dans le `projet.md`, ou du nom du
fichier à défaut.

## Points ouverts

- **Le PDF de `design/` est une version antérieure du document.** Il compte 24 pages alors
  que l'IDML en compte 42 : sa page 24 correspond à la page 42 de l'IDML. Les pages 25 à 41
  n'ont donc pas de référence visuelle. Un réexport complet (42 pages, 300 dpi, sans
  sous-échantillonnage) est nécessaire pour valider la fidélité des dessins concernés.
- **Polices.** Le document utilise MODERNIZ, Arial Narrow, Arial, Minion Pro et Myriad Pro.
  MODERNIZ est « All rights reserved » (Eko Bimantara, 2024) et n'est donc pas embarquée ;
  Minion Pro et Myriad Pro sont des polices Adobe, Arial Narrow une police Microsoft. Le
  site utilise des piles système, à remplacer par des webfonts si les licences le permettent.
- **Légendes.** Chaque image peut recevoir une `legende` explicite dans son `projet.md` ;
  à défaut, elle est déduite du nom de fichier source.
