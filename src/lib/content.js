import siteData from '../data/site.json';
import modelData from '../data/models.json';

export const meta = siteData.site;
export const cover = siteData.cover;
export const presentation = siteData.presentation;
export const transition = siteData.transition;

/** Tous les projets du document. */
const rawProjects = siteData.projects;

const modelBySlug = new Map(modelData.map((model) => [model.slug, model]));

/** Nom lisible deduit du fichier source, quand aucun titre n'est declare. */
function fallbackTitle(model) {
  const base = (model.source ?? model.slug).replace(/\.[a-z0-9]+$/i, '').replace(/[_-]+/g, ' ');
  return base.charAt(0).toUpperCase() + base.slice(1);
}

/** Rattachements declares dans content/structure.json, sous chaque projet. */
const modelSpecs = rawProjects.flatMap((project) =>
  (project.models ?? []).map((spec) => ({ project, spec })),
);

/** Modeles convertis, avec leur titre et les projets auxquels ils sont rattaches. */
export const models = modelData.map((model) => {
  const specs = modelSpecs.filter(({ spec }) => spec.slug === model.slug);
  return {
    ...model,
    title: specs[0]?.spec.title || fallbackTitle(model),
    meta: specs[0]?.spec.meta || '',
    projects: specs.map(({ project }) => project),
  };
});

/** Projets, avec leurs modeles 3D resolus (titre et description compris). */
export const projects = rawProjects.map((project) => ({
  ...project,
  models: (project.models ?? [])
    .map((spec) => {
      const technical = modelBySlug.get(spec.slug);
      if (!technical) {
        console.warn(
          `[content] Le projet "${project.slug}" reference le modele "${spec.slug}", ` +
            `absent de design/models/.`,
        );
        return null;
      }
      return { ...technical, ...spec };
    })
    .filter(Boolean),
}));

/** Chemin public d'un actif converti. */
export function assetUrl(slug, variant = 'full') {
  return `/assets/${slug}/${variant}.webp`;
}

/** Projet precedent et suivant, pour la navigation de bas de page. */
export function neighbours(slug) {
  const index = projects.findIndex((project) => project.slug === slug);
  return {
    previous: index > 0 ? projects[index - 1] : null,
    next: index >= 0 && index < projects.length - 1 ? projects[index + 1] : null,
  };
}

/** Nombre de dessins d'un projet, sans doublon de source. */
export function drawingCount(project) {
  return new Set(project.assets.map((asset) => asset.slug)).size;
}

/** « 1 dessin » / « 9 dessins ». */
export function drawingLabel(project) {
  const count = drawingCount(project);
  return `${count} dessin${count > 1 ? 's' : ''}`;
}

const UNHELPFUL = [
  /^sans titre/i,
  /^img[ _-]?\d/i,
  /^capture d.écran/i,
  /^fichier_?\d/i,
  /^pdf final/i,
  /^[0-9a-f]{8}-[0-9a-f]{4}/i,
];

/**
 * Legende lisible deduite du nom du fichier source. Les noms generiques
 * (exports d'ecran, fichiers temporaires) ne donnent pas de legende plutot
 * qu'une legende trompeuse.
 */
export function captionFor(asset) {
  const base = asset.source
    .replace(/\.[a-z0-9]+$/i, '')
    .replace(/\s*\(\d+\)$/, '')
    .replace(/[_-]+/g, ' ')
    .replace(/\s{2,}/g, ' ')
    .trim();

  if (!base || base.length < 4 || UNHELPFUL.some((pattern) => pattern.test(base))) return '';

  const cleaned = base.replace(/\bpdf\b/gi, '').replace(/\s{2,}/g, ' ').trim();
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}
