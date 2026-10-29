"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Eye, EyeOff, Lock, Monitor, Plus, Smartphone, Tablet, Unlock, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { LiveEditBrandsDrawer } from "@/components/website/live-edit/live-edit-brands-drawer";
import { LiveEditExcellentDrawer } from "@/components/website/live-edit/live-edit-excellent-drawer";
import { LiveEditFeaturedDrawer } from "@/components/website/live-edit/live-edit-featured-drawer";
import { LiveEditExcellentFooterDrawer, type FooterMenuItem, type FooterMenuState } from "@/components/website/live-edit/live-edit-excellent-footer-drawer";
import { LiveEditExcellentHeaderDrawer } from "@/components/website/live-edit/live-edit-excellent-header-drawer";
import { LiveEditHeroDrawer } from "@/components/website/live-edit/live-edit-hero-drawer";
import { LiveEditExcellentSectionPicker } from "@/components/website/live-edit/live-edit-excellent-section-picker";
import { LiveEditShopMenuDrawer } from "@/components/website/live-edit/live-edit-shop-menu-drawer";
import { apiFetch } from "@/lib/api/client";
import { fetchWebsiteHomepage } from "@/lib/api/website-homepage";
import { useAdminAuth } from "@/lib/store/admin-auth-store";
import {
  applyExcellentLayoutAction,
  excellentLayoutOf,
  isExcellentSection,
  mergeHomepagePayload,
  sectionLabel,
  type Json,
  type SiteDefaults,
} from "@/lib/website/excellent-home";
import {
  HERO_SECTION_ASPECT,
  defaultHomepageContent,
  homepageContentToStorefrontPayload,
  type HomepageContent,
} from "@/lib/website/website-homepage";
import { getStorefrontBaseUrl, isLiveEditAuthMessage, LIVE_EDIT_MSG, storefrontEmbedOrigins } from "@/lib/website/live-edit";

/** Storefront chrome blocks that are not homepage body sections. */
const CHROME: [id: string, label: string][] = [
  ["header-top", "Header top"],
  ["header", "Header"],
  ["hero-cards", "Hero side cards"],
  ["menu", "Main menu"],
  ["footer", "Footer & newsletter"],
];
const CHROME_IDS = new Set(CHROME.map(([id]) => id));
/** Excellent sections edited by the shared typed drawers (the rest use the Excellent drawer). */
const TYPED_IDS = new Set(["hero", "featured", "brands"]);

const LOCK_STORAGE_KEY = "website-live-edit-embed-page-locked";

type DeviceId = "desktop" | "tablet" | "mobile";
const DEVICES: { id: DeviceId; label: string; icon: typeof Monitor; width: number }[] = [
  { id: "desktop", label: "Desktop", icon: Monitor, width: 1320 },
  { id: "tablet", label: "Tablet", icon: Tablet, width: 768 },
  { id: "mobile", label: "Mobile", icon: Smartphone, width: 390 },
];

/**
 * The admin's Live Edit for Excellent. Two ways to host it, same editing
 * surface and same message protocol with the storefront page:
 *  - `shell`: the full-screen editor (toolbar on top — Save, lock, Section, device
 *    switcher — with the storefront in an iframe below); the admin session is used.
 *  - default: the chrome-less panel the storefront itself shows on the right when
 *    opened directly at `/?liveEdit=1`; the session comes from the page.
 * Either way it applies every click / toolbar action the page sends, pushes the
 * unsaved draft back as a live preview and saves the homepage row.
 */
export function ExcellentLiveEditEmbedPanel({ shell = false }: { shell?: boolean }) {
  const router = useRouter();
  const setSession = useAdminAuth((s) => s.setSession);
  const authToken = useAdminAuth((s) => s.token);
  const authUser = useAdminAuth((s) => s.user);
  const [authReady, setAuthReady] = useState(shell);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState<HomepageContent>(() => defaultHomepageContent());
  const [extra, setExtra] = useState<Json>({});
  const draftRef = useRef(draft);
  const extraRef = useRef(extra);
  const frameRef = useRef<HTMLIFrameElement>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [locked, setLockedState] = useState(false);
  const [addAfter, setAddAfter] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [device, setDevice] = useState<DeviceId>("desktop");
  const [sectionsOpen, setSectionsOpen] = useState(false);
  /** Bumped when the page (re)loads and asks for the draft, so the preview is sent again. */
  const [syncTick, setSyncTick] = useState(0);
  /** The footer's Customer Care links (Website → Menus → the footer slot): loaded when the footer drawer first opens, saved with the page. */
  const [footerMenu, setFooterMenu] = useState<FooterMenuState>(null);
  const [footerMenuDirty, setFooterMenuDirty] = useState(false);
  /** The shop's own phone numbers and logo, shown in the header drawers until something else is typed. */
  const [siteDefaults, setSiteDefaults] = useState<SiteDefaults>({ phones: [], logo: "", hours: "", copyright: "", social: {} });

  const sectionSize = useMemo(() => {
    const width = DEVICES.find((d) => d.id === device)?.width ?? 1320;
    return { width, height: Math.round(width / HERO_SECTION_ASPECT) };
  }, [device]);

  useEffect(() => {
    draftRef.current = draft;
    extraRef.current = extra;
  }, [draft, extra]);

  useEffect(() => {
    try {
      setLockedState(window.sessionStorage.getItem(LOCK_STORAGE_KEY) === "1");
    } catch {
      /* ignore */
    }
  }, []);

  /** Message to the storefront page: the iframe in `shell`, the embedding window otherwise. */
  const toPage = useCallback(
    (message: Record<string, unknown>) => {
      if (typeof window === "undefined") return;
      const target = shell ? frameRef.current?.contentWindow : window.parent === window ? null : window.parent;
      if (!target) return;
      for (const origin of storefrontEmbedOrigins()) {
        try {
          target.postMessage(message, origin);
        } catch {
          /* ignore */
        }
      }
    },
    [shell]
  );

  // Embedded panel only: tell the page we are ready, then wait for its session (retry while it wires up).
  useEffect(() => {
    if (shell) return;
    let got = false;
    const onMessage = (event: MessageEvent) => {
      if (!storefrontEmbedOrigins().includes(event.origin)) return;
      if (!isLiveEditAuthMessage(event.data)) return;
      got = true;
      setSession({ user: event.data.user, token: event.data.token, expiresAt: event.data.expiresAt, permissions: {} });
      setAuthReady(true);
    };
    window.addEventListener("message", onMessage);
    const ping = () => {
      if (got || window.parent === window) return;
      window.parent.postMessage({ type: LIVE_EDIT_MSG.ready }, "*");
    };
    ping();
    const timer = window.setInterval(ping, 400);
    return () => {
      window.removeEventListener("message", onMessage);
      window.clearInterval(timer);
    };
    // Mount-once handshake.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load the saved homepage once signed in: typed content for the drawers + the raw row for everything else.
  useEffect(() => {
    if (!authReady) return;
    let live = true;
    (async () => {
      try {
        const [typed, rawRes] = await Promise.all([fetchWebsiteHomepage(), apiFetch<{ data: { content: Json } }>("/api/v1/website/homepage")]);
        if (!live) return;
        setDraft(typed.content);
        setExtra(rawRes.data.content ?? {});
        // The shop's own phone numbers and logo (what the site shows until something is typed in the drawers).
        try {
          const res = await apiFetch<{ data?: Record<string, unknown> } & Record<string, unknown>>("/api/v1/storefront/settings");
          const s = (res.data ?? res) as Record<string, unknown>;
          const str = (v: unknown) => (typeof v === "string" ? v : "");
          const phones = [str(s.contact_phone), str(s.whatsapp_number)]
            .flatMap((p) => p.split(/[,|]/))
            .map((p) => p.trim())
            .filter((p, i, all) => p && all.indexOf(p) === i);
          const social: Record<string, string> = {};
          for (const [k, v] of Object.entries((s.social ?? {}) as Record<string, unknown>)) if (str(v).trim()) social[k.toLowerCase()] = str(v).trim();
          if (live) setSiteDefaults({ phones, logo: str(s.logo_url).trim(), hours: str(s.business_hours).trim(), copyright: str(s.copyright_text).trim(), social });
        } catch {
          /* the drawers just start empty */
        }
      } catch (err) {
        if (live) setError(err instanceof Error ? err.message : "Failed to load the homepage");
      } finally {
        if (live) setReady(true);
      }
    })();
    return () => {
      live = false;
    };
  }, [authReady]);

  /** Everything the storefront / the API needs: the saved row with this draft's typed sections laid over it. */
  const payloadOf = useCallback((content: HomepageContent, rawExtra: Json) => mergeHomepagePayload(rawExtra, homepageContentToStorefrontPayload(content) as Json), []);

  // Live preview of unsaved edits (debounced).
  useEffect(() => {
    if (!ready) return;
    const t = window.setTimeout(() => toPage({ type: LIVE_EDIT_MSG.preview, content: payloadOf(draft, extra) }), 120);
    return () => window.clearTimeout(t);
  }, [draft, extra, ready, syncTick, toPage, payloadOf]);

  const highlight = useCallback((id: string | null) => toPage({ type: LIVE_EDIT_MSG.highlight, sectionId: id }), [toPage]);

  const openEditor = useCallback(
    (id: string) => {
      if (!CHROME_IDS.has(id) && !isExcellentSection(id)) return;
      setSelected(id);
      highlight(id);
      setDrawerOpen(true);
      setSectionsOpen(false);
    },
    [highlight]
  );

  const closeDrawer = (open: boolean) => {
    setDrawerOpen(open);
    if (!open) {
      setSelected(null);
      highlight(null);
    }
  };

  /** The drawers' Back button: close this editor and show the Sections list again. */
  const backToSections = () => {
    closeDrawer(false);
    window.setTimeout(() => setSectionsOpen(true), 0);
  };

  const setLocked = (next: boolean) => {
    setLockedState(next);
    try {
      window.sessionStorage.setItem(LOCK_STORAGE_KEY, next ? "1" : "0");
    } catch {
      /* ignore */
    }
    toPage({ type: LIVE_EDIT_MSG.lock, locked: next });
    if (next) closeDrawer(false);
  };

  useEffect(() => {
    if (ready) toPage({ type: LIVE_EDIT_MSG.lock, locked });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, syncTick]);

  const layoutAction = useCallback((action: "moveUp" | "moveDown" | "toggleHidden" | "hide" | "show", id: string, after?: string | null) => {
    setDraft((d) => applyExcellentLayoutAction(d, action, id, after));
  }, []);

  // Clicks and toolbar actions arrive from the page.
  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (!storefrontEmbedOrigins().includes(event.origin)) return;
      if (shell && event.source !== frameRef.current?.contentWindow) return;
      const data = event.data as { type?: string; sectionId?: string; action?: string; instanceId?: string } | null;
      if (!data || typeof data !== "object") return;
      if (data.type === LIVE_EDIT_MSG.ready) {
        // The page (re)loaded and wants the draft.
        if (shell) setSyncTick((t) => t + 1);
        return;
      }
      if (data.type === LIVE_EDIT_MSG.close) {
        if (shell) router.back();
        return;
      }
      if (locked) return;
      if (data.type === LIVE_EDIT_MSG.select && typeof data.sectionId === "string") {
        openEditor(data.sectionId);
        return;
      }
      if (data.type !== LIVE_EDIT_MSG.layoutAction || typeof data.instanceId !== "string") return;
      const id = data.instanceId;
      switch (data.action) {
        case "edit":
          openEditor(id);
          break;
        case "moveUp":
        case "moveDown":
        case "toggleHidden":
          layoutAction(data.action, id);
          break;
        case "delete":
          // The set of sections is fixed, so removing one hides it (it can be added back).
          layoutAction("hide", id);
          if (selected === id) closeDrawer(false);
          break;
        case "add":
          setAddAfter(id);
          setAddOpen(true);
          break;
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shell, locked, openEditor, layoutAction, selected]);

  useEffect(() => {
    if (selected !== "footer" || !drawerOpen || footerMenu) return;
    void (async () => {
      try {
        const slots = await apiFetch<{ data: { slot_key: string; menu_id: string }[] }>("/api/v1/website/menu-slots");
        const id = slots.data.find((s) => s.slot_key === "footer.links")?.menu_id;
        if (!id) return setFooterMenu({ error: "No menu is assigned to the footer links slot (Website → Menus)." });
        const res = await apiFetch<{ data: { id: string; items: FooterMenuItem[] } }>(`/api/v1/website/menus/${id}`);
        setFooterMenu({ id: res.data.id, items: res.data.items ?? [] });
      } catch (err) {
        setFooterMenu({ error: err instanceof Error ? err.message : "Could not load the footer links" });
      }
    })();
  }, [selected, drawerOpen, footerMenu]);

  const save = async () => {
    setSaving(true);
    try {
      if (footerMenuDirty && footerMenu && "id" in footerMenu) {
        const menu = await apiFetch<{ data: { id: string; items: FooterMenuItem[] } }>(`/api/v1/website/menus/${footerMenu.id}`, { method: "PATCH", body: JSON.stringify({ items: footerMenu.items }) });
        setFooterMenu({ id: menu.data.id, items: menu.data.items ?? [] });
        setFooterMenuDirty(false);
      }
      const content = payloadOf(draftRef.current, extraRef.current);
      await apiFetch("/api/v1/website/homepage", { method: "PATCH", body: JSON.stringify({ content }) });
      toPage({ type: LIVE_EDIT_MSG.reload });
      toast.success("Saved");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  if (!authReady || !authToken || !ready) {
    return (
      <div className="flex h-screen min-h-0 flex-col items-center justify-center gap-2 bg-background text-foreground">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-foreground" aria-hidden />
        <p className="text-xs text-muted-foreground">Connecting…</p>
      </div>
    );
  }

  const layout = excellentLayoutOf(draft);
  const hiddenSections = layout.filter((b) => b.hidden);
  const open = !locked && drawerOpen;
  const excellentSection = selected && ((isExcellentSection(selected) && !TYPED_IDS.has(selected)) || selected === "hero-cards") ? selected : null;
  const frameWidth = DEVICES.find((d) => d.id === device)?.width ?? 1320;
  // This admin's own storefront (env) first: the saved site URLs can still point at another local stack.
  const storefrontBase = (process.env.NEXT_PUBLIC_STOREFRONT_URL?.trim() || getStorefrontBaseUrl()).replace(/\/$/, "");
  const frameSrc = `${storefrontBase}/?liveEdit=1`;

  const sectionButtons = (
    <>
      <p className="mb-1 mt-1 px-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Site</p>
      {CHROME.map(([id, label]) => (
        <Button key={id} type="button" variant="ghost" className={cn("h-9 w-full justify-start", selected === id && "bg-muted")} disabled={locked} onClick={() => openEditor(id)}>
          {label}
        </Button>
      ))}
      <p className="mb-1 mt-2 px-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Homepage sections</p>
      {layout.map((b) => (
        <div key={b.id} className="flex items-center gap-1">
          <Button type="button" variant="ghost" className={cn("h-9 flex-1 justify-start", selected === b.id && "bg-muted", b.hidden && "opacity-50")} disabled={locked} onClick={() => openEditor(b.id)}>
            {sectionLabel(b.id)}
            {b.hidden ? " · hidden" : ""}
          </Button>
          <Button type="button" variant="ghost" size="icon" className="h-9 w-9" title={b.hidden ? "Show" : "Hide"} onClick={() => layoutAction("toggleHidden", b.id)}>
            {b.hidden ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </Button>
        </div>
      ))}
    </>
  );

  return (
    <div className="flex h-screen min-h-0 flex-col bg-background text-foreground">
      <header className="relative z-20 flex h-11 shrink-0 items-center border-b border-border px-3">
        <div className="z-10 flex items-center gap-1.5">
          <Button type="button" size="sm" className="h-8 bg-[#00a09d] px-3 text-[13px] text-white hover:bg-[#008f8c]" disabled={saving} onClick={() => void save()}>
            {saving ? "Saving…" : "Save"}
          </Button>
          <Button
            type="button"
            size="icon"
            variant="outline"
            className={cn("h-8 w-8", locked ? "border-amber-500/50 bg-amber-500/10 text-amber-700 dark:text-amber-400" : "text-muted-foreground")}
            title={locked ? "Unlock page — allow section editing" : "Lock page — browse without opening drawers"}
            aria-pressed={locked}
            onClick={() => setLocked(!locked)}
          >
            {locked ? <Lock className="h-4 w-4" /> : <Unlock className="h-4 w-4" />}
          </Button>
          {shell && (
            <LiveEditExcellentSectionPicker layout={layout} selectedSection={selected} pageLocked={locked} onSelect={openEditor} open={sectionsOpen} onOpenChange={setSectionsOpen} />
          )}
        </div>

        {shell && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <div className="pointer-events-auto flex items-center gap-0.5 rounded-md border border-border bg-muted/40 p-0.5">
              {DEVICES.map((item) => {
                const Icon = item.icon;
                const active = device === item.id;
                return (
                  <Button
                    key={item.id}
                    type="button"
                    size="icon"
                    variant="ghost"
                    className={cn("h-8 w-8 text-muted-foreground", active && "bg-background text-foreground shadow-sm")}
                    title={item.label}
                    aria-label={item.label}
                    aria-pressed={active}
                    onClick={() => setDevice(item.id)}
                  >
                    <Icon className="h-4 w-4" />
                  </Button>
                );
              })}
            </div>
          </div>
        )}

        <div className="z-10 ml-auto flex items-center gap-2">
          <span className="hidden truncate text-xs text-muted-foreground sm:inline">{authUser?.name}</span>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            aria-label="Close live edit"
            onClick={() => (shell ? router.back() : toPage({ type: LIVE_EDIT_MSG.close }))}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </header>

      {error && (
        <div className="border-b border-destructive/30 bg-destructive/10 px-3 py-2">
          <p className="text-xs text-destructive">{error}</p>
        </div>
      )}

      {shell ? (
        <div className="flex min-h-0 flex-1 justify-center overflow-hidden bg-[#dcdcdc] dark:bg-neutral-800">
          <iframe
            ref={frameRef}
            title="Storefront"
            src={frameSrc}
            className="h-full border-0 bg-white"
            style={{ width: device === "desktop" ? "100%" : frameWidth, maxWidth: "100%" }}
            onLoad={() => setSyncTick((t) => t + 1)}
          />
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-3">
          <p className="mb-3 text-xs text-muted-foreground">Click a section on the site to edit it here, or pick one below.</p>
          <div className="grid gap-0.5">{sectionButtons}</div>
        </div>
      )}

      <LiveEditHeroDrawer onBack={backToSections} open={open && selected === "hero"} onOpenChange={closeDrawer} content={draft} sectionSize={sectionSize} onChange={setDraft} onSave={() => void save()} saving={saving} />
      <LiveEditFeaturedDrawer onBack={backToSections} open={open && selected === "featured"} onOpenChange={closeDrawer} content={draft} onChange={setDraft} onSave={() => void save()} saving={saving} />
      <LiveEditBrandsDrawer onBack={backToSections} open={open && selected === "brands"} onOpenChange={closeDrawer} content={draft} onChange={setDraft} onSave={() => void save()} saving={saving} />
      <LiveEditExcellentHeaderDrawer onBack={backToSections} open={open && selected === "header-top"} onOpenChange={closeDrawer} mode="top" defaults={siteDefaults} content={draft} onChange={setDraft} onSave={() => void save()} saving={saving} />
      <LiveEditExcellentHeaderDrawer onBack={backToSections} open={open && selected === "header"} onOpenChange={closeDrawer} mode="main" defaults={siteDefaults} content={draft} onChange={setDraft} onSave={() => void save()} saving={saving} />
      <LiveEditExcellentFooterDrawer
        onBack={backToSections}
        open={open && selected === "footer"}
        onOpenChange={closeDrawer}
        content={draft}
        onChange={setDraft}
        extra={extra}
        onExtraChange={setExtra}
        footerMenu={footerMenu}
        onFooterItems={(items) => {
          setFooterMenu((m) => (m && "id" in m ? { ...m, items } : m));
          setFooterMenuDirty(true);
        }}
        defaults={siteDefaults}
        onSave={() => void save()}
        saving={saving}
      />
      <LiveEditShopMenuDrawer open={open && selected === "menu"} onOpenChange={closeDrawer} onBack={backToSections} onApplied={() => toPage({ type: LIVE_EDIT_MSG.reload })} onSave={() => void save()} saving={saving} />
      <LiveEditExcellentDrawer
        onBack={backToSections}
        open={open && Boolean(excellentSection)}
        onOpenChange={closeDrawer}
        section={excellentSection ?? ""}
        content={draft}
        onChange={setDraft}
        extra={extra}
        onExtraChange={setExtra}
        onSave={() => void save()}
        saving={saving}
      />

      <Sheet open={addOpen} onOpenChange={setAddOpen}>
        <SheetContent className="w-full border-border bg-background text-foreground sm:max-w-md">
          <SheetHeader>
            <SheetTitle>Add section</SheetTitle>
          </SheetHeader>
          <div className="mt-4 grid gap-1.5">
            {hiddenSections.length === 0 ? (
              <p className="text-sm text-muted-foreground">Every section is already on the page. Hide one first to add it back later.</p>
            ) : (
              hiddenSections.map((b) => (
                <Button
                  key={b.id}
                  type="button"
                  variant="outline"
                  className="h-10 justify-start"
                  onClick={() => {
                    layoutAction("show", b.id, addAfter);
                    setAddOpen(false);
                    setAddAfter(null);
                  }}
                >
                  <Plus className="mr-2 h-4 w-4" />
                  {sectionLabel(b.id)}
                </Button>
              ))
            )}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
