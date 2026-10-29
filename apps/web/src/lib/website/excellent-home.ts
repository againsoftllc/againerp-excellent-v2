import type { HomepageContent } from "@/lib/website/website-homepage";

/**
 * Excellent's homepage body: a fixed set of sections whose order / visibility
 * live in the homepage row's free-form `blocks.excellent.layout`, next to the
 * copy the typed schema has no slot for (notice, trust strip, banners, …).
 * Mirrors `HOME_SECTIONS` / `toHomeLayout` in the storefront.
 */
export const EXCELLENT_SECTIONS = [
  { id: "hero", label: "Hero slider & side cards" },
  { id: "notice", label: "Notice ticker" },
  { id: "trust", label: "Trust strip" },
  { id: "categories", label: "Shop by category" },
  { id: "deals", label: "Deals of the day" },
  { id: "featured", label: "Featured product tabs" },
  { id: "banners", label: "Promo banners" },
  { id: "collection", label: "Category product rail" },
  { id: "brands", label: "Brands" },
  { id: "why", label: "Why us & branches" },
  { id: "seo", label: "SEO text" },
] as const;

export type ExcellentSectionId = (typeof EXCELLENT_SECTIONS)[number]["id"];
export type ExcellentLayoutBlock = { id: ExcellentSectionId; hidden: boolean };
export type Json = Record<string, unknown>;

/** What the site shows today when nothing is typed in the drawers: the shop's own settings. */
export type SiteDefaults = { phones: string[]; logo: string; hours: string; copyright: string; social: Record<string, string> };

export const obj = (v: unknown): Json => (v && typeof v === "object" && !Array.isArray(v) ? (v as Json) : {});

export function isExcellentSection(id: string): id is ExcellentSectionId {
  return EXCELLENT_SECTIONS.some((s) => s.id === id);
}

export function sectionLabel(id: string): string {
  if (id === "hero-cards") return "Hero side cards";
  return EXCELLENT_SECTIONS.find((s) => s.id === id)?.label ?? id;
}

/** Saved order (unknown ids dropped); a section not saved yet slots in after the one it follows by default. */
export function toExcellentLayout(raw: unknown): ExcellentLayoutBlock[] {
  const known = new Set<string>(EXCELLENT_SECTIONS.map((x) => x.id));
  const saved = (Array.isArray(raw) ? raw : [])
    .filter((x): x is Json => Boolean(x) && typeof x === "object")
    .filter((x) => typeof x.id === "string" && known.has(x.id as string))
    .map((x) => ({ id: x.id as ExcellentSectionId, hidden: Boolean(x.hidden) }));
  const out = saved.filter((x, i) => saved.findIndex((y) => y.id === x.id) === i);
  EXCELLENT_SECTIONS.forEach((s, i) => {
    if (out.some((x) => x.id === s.id)) return;
    const prev = i > 0 ? out.findIndex((x) => x.id === EXCELLENT_SECTIONS[i - 1].id) : -1;
    out.splice(prev + 1, 0, { id: s.id, hidden: false });
  });
  return out;
}

export function getExcellent(content: HomepageContent): Json {
  return obj(obj(content.blocks).excellent);
}

export function setExcellent(content: HomepageContent, next: Json): HomepageContent {
  return { ...content, blocks: { ...obj(content.blocks), excellent: next } };
}

export function patchExcellent(content: HomepageContent, patch: Json): HomepageContent {
  return setExcellent(content, { ...getExcellent(content), ...patch });
}

export function excellentLayoutOf(content: HomepageContent): ExcellentLayoutBlock[] {
  return toExcellentLayout(getExcellent(content).layout);
}

export type ExcellentLayoutAction = "moveUp" | "moveDown" | "toggleHidden" | "hide" | "show";

/** Move / hide / show one section. (The set of sections is fixed, so "remove" hides and "add" shows.) */
export function applyExcellentLayoutAction(content: HomepageContent, action: ExcellentLayoutAction, id: string, afterId?: string | null): HomepageContent {
  const list = excellentLayoutOf(content);
  const i = list.findIndex((x) => x.id === id);
  if (i < 0) return content;
  if (action === "moveUp" || action === "moveDown") {
    const j = i + (action === "moveUp" ? -1 : 1);
    if (j < 0 || j >= list.length) return content;
    [list[i], list[j]] = [list[j], list[i]];
  } else if (action === "toggleHidden") {
    list[i] = { ...list[i], hidden: !list[i].hidden };
  } else if (action === "hide") {
    list[i] = { ...list[i], hidden: true };
  } else {
    const [item] = list.splice(i, 1);
    const at = afterId ? list.findIndex((x) => x.id === afterId) : -1;
    list.splice(at + 1, 0, { ...item, hidden: false });
  }
  return patchExcellent(content, { layout: list });
}

/**
 * The saved row, with the typed sections the admin edits laid over it one
 * level deep — so keys the admin's typed model does not know (a section's
 * heading, `seo`, `notice`, …) survive a save instead of being reset.
 */
export function mergeHomepagePayload(raw: Json, payload: Json): Json {
  const out: Json = { ...raw };
  for (const [key, value] of Object.entries(payload)) {
    const base = raw[key];
    out[key] =
      value && typeof value === "object" && !Array.isArray(value) && base && typeof base === "object" && !Array.isArray(base)
        ? { ...(base as Json), ...(value as Json) }
        : value;
  }
  return out;
}
