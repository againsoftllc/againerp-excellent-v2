"use client";

import { useState } from "react";
import { Eye, EyeOff, Plus, Trash2 } from "lucide-react";
import {
  AgainDrawerControlBar,
  AgainDrawerLayout,
  AgainDrawerPanel,
  AgainDrawerScrollBody,
  AGAIN_DRAWER_FIELD_SHEET_CLASS,
  AGAIN_DRAWER_MODULE_LABEL_CLASS,
  AGAIN_DRAWER_RECORD_LABEL_CLASS,
} from "@/components/again/again-drawer";
import { AgainFormRow } from "@/components/again/again-form-sheet";
import { LiveEditDrawerBackButton } from "@/components/website/live-edit/live-edit-drawer-back-button";
import { LiveEditDrawerSaveButton } from "@/components/website/live-edit/live-edit-drawer-save-button";
import { LiveEditExcellentKindCards } from "@/components/website/live-edit/live-edit-excellent-hero-cards";
import { LiveEditExcellentCollection } from "@/components/website/live-edit/live-edit-excellent-collection";
import { LiveEditExcellentCategoryTiles } from "@/components/website/live-edit/live-edit-excellent-category-tiles";
import { MediaLibraryModal } from "@/components/media/media-library-modal";
import { MediaPickTile } from "@/components/media/media-pick-tile";
import { AgaincartClassicEditor } from "@/components/products/againcart-classic-editor";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { createCatalogMediaBatch, uploadCatalogMediaFiles, useCatalogMedia } from "@/lib/api/use-catalog-media";
import { getExcellent, obj, patchExcellent, sectionLabel, type Json } from "@/lib/website/excellent-home";
import { getStorefrontBaseUrl } from "@/lib/website/live-edit";
import type { HomepageContent } from "@/lib/website/website-homepage";

type Props = {
  open: boolean;
  /** Return to the Sections list (falls back to closing the drawer). */
  onBack?: () => void;
  onOpenChange: (open: boolean) => void;
  /** Which Excellent section: notice, trust, categories, deals, banners, collection, why or seo. */
  section: string;
  content: HomepageContent;
  onChange: (content: HomepageContent) => void;
  /** Saved-row keys the typed model has no slot for (`seo`, a section's heading, …). */
  extra: Json;
  onExtraChange: (extra: Json) => void;
  onSave?: () => void | Promise<void>;
  saving?: boolean;
};

type Row = Record<string, unknown>;
const list = (v: unknown): Row[] => (Array.isArray(v) ? (v as Row[]).filter((r) => r && typeof r === "object") : []);
const text = (v: unknown) => (typeof v === "string" ? v : "");

export function Field({ label, value, onChange, multiline, placeholder }: { label: string; value: unknown; onChange: (v: string) => void; multiline?: boolean; placeholder?: string }) {
  return (
    <AgainFormRow label={label}>
      {multiline ? (
        <Textarea value={text(value)} onChange={(e) => onChange(e.target.value)} className="min-h-[72px] text-[13px]" placeholder={placeholder} />
      ) : (
        <Input value={text(value)} onChange={(e) => onChange(e.target.value)} className="h-8 text-[13px]" placeholder={placeholder} />
      )}
    </AgainFormRow>
  );
}

/** Storefront images (`/images/...`) live on the storefront, not this admin — point previews at it. */
export function previewUrl(url: string): string {
  const u = url.trim();
  if (u.startsWith("/images/")) return `${getStorefrontBaseUrl().replace(/\/$/, "")}${u}`;
  return u;
}

/** Repeating rows (trust items, promo banners): edit, hide, remove, add. A field marked `image` is a picture tile (library / upload). */
export function RowList({
  rows,
  fields,
  blank,
  noun,
  onChange,
}: {
  rows: Row[];
  fields: { key: string; label: string; multiline?: boolean; image?: boolean }[];
  blank: Row;
  noun: string;
  onChange: (rows: Row[]) => void;
}) {
  const [pick, setPick] = useState<{ index: number; key: string } | null>(null);
  const { items: mediaItems, refetch: refetchMedia } = useCatalogMedia();
  const set = (i: number, patch: Row) => onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <div className="space-y-3">
      {rows.map((row, i) => (
        <div key={text(row.id) || i} className="space-y-2 rounded-md border border-border bg-card p-2.5">
          <div className="flex items-center justify-between">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              {noun} {i + 1}
              {row.hidden ? " · hidden" : ""}
            </p>
            <div className="flex gap-1">
              <Button type="button" variant="ghost" size="icon" className="h-7 w-7" title={row.hidden ? "Show" : "Hide"} onClick={() => set(i, { hidden: !row.hidden })}>
                {row.hidden ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
              </Button>
              <Button type="button" variant="ghost" size="icon" className="h-7 w-7" title="Remove" onClick={() => onChange(rows.filter((_, j) => j !== i))}>
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
          {fields.map((f) =>
            f.image ? (
              <AgainFormRow key={f.key} label={f.label}>
                <MediaPickTile
                  url={previewUrl(text(row[f.key]))}
                  alt={f.label}
                  onChange={(next) => set(i, { [f.key]: next })}
                  onPick={() => {
                    void refetchMedia();
                    setPick({ index: i, key: f.key });
                  }}
                />
              </AgainFormRow>
            ) : (
              <Field key={f.key} label={f.label} multiline={f.multiline} value={row[f.key]} onChange={(v) => set(i, { [f.key]: v })} />
            )
          )}
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" className="h-8" onClick={() => onChange([...rows, { ...blank, id: `${noun.toLowerCase()}-${Date.now().toString(36)}` }])}>
        <Plus className="mr-1 h-3.5 w-3.5" />
        Add {noun.toLowerCase()}
      </Button>

      <MediaLibraryModal
        open={pick !== null}
        onOpenChange={(next) => {
          if (!next) setPick(null);
          else void refetchMedia();
        }}
        items={mediaItems}
        mode="single"
        title="Image"
        accept={["image"]}
        onSelect={(items) => {
          const next = items.find((item) => item.type === "image")?.url;
          if (next && pick) set(pick.index, { [pick.key]: next });
        }}
        onUploadFiles={async (files) => {
          const uploaded = await uploadCatalogMediaFiles(files);
          await refetchMedia();
          return uploaded;
        }}
        onImportItems={async (items) => {
          const saved = await createCatalogMediaBatch(items);
          await refetchMedia();
          return saved;
        }}
      />
    </div>
  );
}

export function LiveEditExcellentDrawer({ onBack, open, onOpenChange, section, content, onChange, extra, onExtraChange, onSave, saving = false }: Props) {
  const ex = getExcellent(content);
  const setEx = (patch: Json) => onChange(patchExcellent(content, patch));
  const setExtraSection = (key: string, patch: Json) => onExtraChange({ ...extra, [key]: { ...obj(extra[key]), ...patch } });

  const body = (() => {
    switch (section) {
      case "notice": {
        const n = obj(ex.notice);
        return (
          <div className="space-y-3 rounded-md border border-border bg-card p-2.5">
            <Field label="Scrolling notice" multiline value={n.text} onChange={(v) => setEx({ notice: { ...n, text: v } })} placeholder="Use {date} for today's date" />
            <AgainFormRow label="Hide notice">
              <div className="flex h-8 items-center">
                <Switch checked={Boolean(n.hidden)} onCheckedChange={(v) => setEx({ notice: { ...n, hidden: v } })} />
              </div>
            </AgainFormRow>
          </div>
        );
      }
      case "hero-cards":
        return (
          <LiveEditExcellentKindCards
            ex={ex}
            setEx={setEx}
            listKey="promo_cards"
            noun="Card"
            fullImageKey="image"
            customFields={[
              { key: "icon", label: "Icon (Material name)" },
              { key: "title", label: "Title" },
              { key: "text", label: "Text", multiline: true },
              { key: "button", label: "Button" },
              { key: "href", label: "Link" },
            ]}
            blank={{ kind: "card", icon: "bolt", title: "", text: "", button: "Learn more", href: "/", image: "", alt: "" }}
            sizeHint="About 820 × 445 px fits best."
            note={<>The first two cards show beside the slider. In a custom card, write {"{branches}"} in a title or text to show the live number of branches (e.g. “Visit Our {"{branches}"} Branches”).</>}
          />
        );
      case "trust":
        return (
          <RowList
            noun="Item"
            rows={list(ex.trust)}
            blank={{ icon: "verified", title: "", text: "", href: "" }}
            fields={[
              { key: "icon", label: "Icon (Material name)" },
              { key: "title", label: "Title" },
              { key: "text", label: "Text" },
              { key: "href", label: "Link (optional)" },
            ]}
            onChange={(rows) => setEx({ trust: rows })}
          />
        );
      case "categories": {
        const c = obj(extra.categories);
        return (
          <div className="space-y-4">
            <div className="space-y-3 rounded-md border border-border bg-card p-2.5">
              <Field label="Heading" value={c.title} onChange={(v) => setExtraSection("categories", { title: v })} />
              <Field label="Sub heading" value={c.subtitle} onChange={(v) => setExtraSection("categories", { subtitle: v })} />
            </div>
            <LiveEditExcellentCategoryTiles ex={ex} setEx={setEx} />
          </div>
        );
      }
      case "deals": {
        const d = obj(ex.deals);
        return (
          <div className="space-y-3 rounded-md border border-border bg-card p-2.5">
            <Field label="Heading" value={d.title} onChange={(v) => setEx({ deals: { ...d, title: v } })} />
            <Field label="Sub heading" value={d.subtitle} onChange={(v) => setEx({ deals: { ...d, subtitle: v } })} />
            <p className="text-[11px] text-muted-foreground">The products come from the running Happy Hour (or sale products).</p>
          </div>
        );
      }
      case "banners":
        return (
          <LiveEditExcellentKindCards
            ex={ex}
            setEx={setEx}
            listKey="banners"
            noun="Banner"
            fullImageKey="banner_image"
            customFields={[
              { key: "badge", label: "Badge" },
              { key: "title", label: "Title" },
              { key: "text", label: "Text", multiline: true },
              { key: "button", label: "Button" },
              { key: "href", label: "Link" },
              { key: "image", label: "Picture (right side)", image: true },
            ]}
            blank={{ kind: "card", badge: "", title: "", text: "", button: "Shop now", href: "/", image: "", banner_image: "", alt: "" }}
            sizeHint="About 1264 × 550 px fits best."
            note="The first two banners show side by side."
          />
        );
      case "collection":
        return <LiveEditExcellentCollection ex={ex} setEx={setEx} />;
      case "why": {
        const w = obj(ex.why);
        return (
          <div className="space-y-3 rounded-md border border-border bg-card p-2.5">
            <Field label="Heading" value={w.title} onChange={(v) => setEx({ why: { ...w, title: v } })} />
            <Field label="Text" multiline value={w.text} onChange={(v) => setEx({ why: { ...w, text: v } })} />
          </div>
        );
      }
      case "seo": {
        const s = obj(extra.seo);
        // One rich-text field. Text saved earlier as plain "intro text" shows as the first paragraph until it is edited.
        const intro = text(s.intro_text).trim();
        const html = text(ex.seo_html) || (intro ? `<p>${intro.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")}</p>` : "");
        return (
          <div className="space-y-3">
            <div className="space-y-3 rounded-md border border-border bg-card p-2.5">
              <Field label="Heading" value={s.heading} onChange={(v) => setExtraSection("seo", { heading: v })} />
              <AgainFormRow label="Hide section">
                <div className="flex h-8 items-center">
                  <Switch checked={Boolean(s.hidden)} onCheckedChange={(v) => setExtraSection("seo", { hidden: v })} />
                </div>
              </AgainFormRow>
            </div>
            <AgaincartClassicEditor
              value={html}
              onChange={(v) => {
                if (v === html) return;
                // The editor's text is the only source now, so the old plain intro text goes.
                setEx({ seo_html: v });
                if (intro) setExtraSection("seo", { intro_text: "" });
              }}
              fieldLabel="SEO Content"
              placeholder="SEO content…"
              minRows={8}
              aiContext="generic"
              aiVariables={{ section_title: text(s.heading), current_content: html }}
            />
          </div>
        );
      }
      default:
        return <p className="text-sm text-muted-foreground">Nothing to edit here.</p>;
    }
  })();

  return (
    <AgainDrawerPanel open={open} onOpenChange={onOpenChange} title={sectionLabel(section)} resizable defaultWidth={420} widthStorageKey="website-live-edit-drawer-width">
      <AgainDrawerLayout>
        <AgainDrawerControlBar trailing={<LiveEditDrawerSaveButton onSave={onSave} saving={saving} />}>
          <LiveEditDrawerBackButton onBack={() => (onBack ? onBack() : onOpenChange(false))} />
          <span className={AGAIN_DRAWER_MODULE_LABEL_CLASS}>Website</span>
          <span className="text-muted-foreground">/</span>
          <span className={AGAIN_DRAWER_RECORD_LABEL_CLASS}>{sectionLabel(section)}</span>
        </AgainDrawerControlBar>
        <AgainDrawerScrollBody className={AGAIN_DRAWER_FIELD_SHEET_CLASS}>{body}</AgainDrawerScrollBody>
      </AgainDrawerLayout>
    </AgainDrawerPanel>
  );
}
