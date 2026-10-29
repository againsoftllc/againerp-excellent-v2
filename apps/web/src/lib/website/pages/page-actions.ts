import { getStorefrontBaseUrl } from "@/lib/website/live-edit";
import type { WebsiteManagedPage } from "@/lib/website/pages/types";

/** Admin full-screen Live Edit for the Home page. */
export const HOME_LIVE_EDIT = "/website/live-edit/home";
export const CATEGORY_LIVE_EDIT = "/website/live-edit/category";
export const CONTENT_LIVE_EDIT = "/website/live-edit/content";

/** Sample category used when a menu row has no usable path. */
export const DEFAULT_CATEGORY_PREVIEW_PATH = "/laptops";

/** Menu href / CMS url / slug → category path on the storefront ("/category/laptops" → "/laptops"). */
export function normalizeCategoryStorefrontPath(raw: string | null | undefined): string {
  const value = (raw || "").trim();
  if (!value) return DEFAULT_CATEGORY_PREVIEW_PATH;
  let path = value.startsWith("/") ? value : `/${value}`;
  if (path.startsWith("/category/")) {
    const slug = path.slice("/category/".length).split("/")[0];
    path = slug ? `/${slug}` : DEFAULT_CATEGORY_PREVIEW_PATH;
  }
  if (path === "/" || path === "/category") return DEFAULT_CATEGORY_PREVIEW_PATH;
  return path;
}

/**
 * Where a menu row's category opens. Excellent's storefront has no category Live Edit
 * (the homepage one is the only editor), so this is the category's own page on the site.
 */
export function categoryLiveEditUrl(hrefOrSlug: string | null | undefined): string {
  const base = getStorefrontBaseUrl().replace(/\/$/, "");
  return `${base}${normalizeCategoryStorefrontPath(hrefOrSlug)}`;
}

export function isHomePage(page: WebsiteManagedPage) {
  return page.flags.isHome || page.url === "/" || page.slug === "" || page.slug === "home";
}

export function isCategoryPage(page: WebsiteManagedPage) {
  return page.pageType === "category";
}

/** Footer / legal / marketing pages with CMS body_html (not home). */
export function isContentPage(page: WebsiteManagedPage) {
  if (isHomePage(page) || isCategoryPage(page)) return false;
  if (page.flags.isSystem) return false;
  return (
    page.pageType === "website" ||
    page.pageType === "custom" ||
    page.pageType === "landing" ||
    page.pageType === "blog"
  );
}

export function supportsLiveEdit(page: WebsiteManagedPage) {
  // Storefront Live Edit is homepage-only (the working editor).
  return isHomePage(page);
}

/** Map CMS page URL to storefront path for Open storefront. */
export function storefrontPathForPage(page: WebsiteManagedPage): string {
  let path = page.url?.startsWith("/") ? page.url : `/${page.url || page.slug || ""}`;
  if (path.startsWith("/category/")) {
    const slug = path.slice("/category/".length).split("/")[0];
    path = slug ? `/${slug}` : "/laptops";
  }
  if (!path || path === "/") return isCategoryPage(page) ? "/laptops" : "/";
  return path;
}

/**
 * Live Edit entry URL.
 * Home → the admin's own full-screen Live Edit (`/website/live-edit/home`), which frames the
 * storefront in `?liveEdit=1` mode. The admin session is used, so there is no separate sign-in.
 */
export function liveEditAdminUrl(page: WebsiteManagedPage): string | null {
  if (isHomePage(page)) return HOME_LIVE_EDIT;
  return null;
}

export function storefrontUrlForPage(page: WebsiteManagedPage): string {
  const base = getStorefrontBaseUrl();
  const path = storefrontPathForPage(page);
  if (!base) return path;
  return `${base.replace(/\/$/, "")}${path}`;
}

export function canDeletePage(page: WebsiteManagedPage) {
  return !page.flags.deleteDisabled && !page.flags.isHome && !page.flags.isSystem;
}

export function slugifyPageName(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}
