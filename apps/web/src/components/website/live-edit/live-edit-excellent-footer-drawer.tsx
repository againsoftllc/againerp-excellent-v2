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
import { MediaLibraryModal } from "@/components/media/media-library-modal";
import { MediaPickTile } from "@/components/media/media-pick-tile";
import { LiveEditDrawerBackButton } from "@/components/website/live-edit/live-edit-drawer-back-button";
import { LiveEditDrawerSaveButton } from "@/components/website/live-edit/live-edit-drawer-save-button";
import { Field, RowList } from "@/components/website/live-edit/live-edit-excellent-drawer";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { createCatalogMediaBatch, uploadCatalogMediaFiles, useCatalogMedia } from "@/lib/api/use-catalog-media";
import { getExcellent, obj, patchExcellent, type Json, type SiteDefaults } from "@/lib/website/excellent-home";
import type { HomepageContent } from "@/lib/website/website-homepage";

/** One link of the Customer Care column (a Website → Menus item). */
export type FooterMenuItem = { id: string; label: string; href: string; link_type?: string; link_ref_id?: string | null; hidden?: boolean; children?: FooterMenuItem[] };
/** The Customer Care menu while editing: loaded on first use, saved with the page. */
export type FooterMenuState = { id: string; items: FooterMenuItem[] } | { error: string } | null;

type Props = {
  open: boolean;
  /** Return to the Sections list (falls back to closing the drawer). */
  onBack?: () => void;
  onOpenChange: (open: boolean) => void;
  content: HomepageContent;
  onChange: (content: HomepageContent) => void;
  /** Saved-row keys the typed model has no slot for (the footer blurb lives in `footer.about_text`). */
  extra: Json;
  onExtraChange: (extra: Json) => void;
  footerMenu: FooterMenuState;
  onFooterItems: (items: FooterMenuItem[]) => void;
  defaults: SiteDefaults;
  onSave?: () => void | Promise<void>;
  saving?: boolean;
};

const text = (v: unknown) => (typeof v === "string" ? v : "");

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-3 rounded-md border border-border bg-card p-2.5">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{title}</p>
      {children}
    </div>
  );
}

const SOCIALS: [key: string, label: string][] = [
  ["facebook", "Facebook"],
  ["youtube", "YouTube"],
  ["instagram", "Instagram"],
  ["tiktok", "TikTok"],
  ["whatsapp", "WhatsApp"],
];

export function LiveEditExcellentFooterDrawer({ onBack, open, onOpenChange, content, onChange, extra, onExtraChange, footerMenu, onFooterItems, defaults, onSave, saving = false }: Props) {
  const [libraryOpen, setLibraryOpen] = useState(false);
  const { items: mediaItems, refetch: refetchMedia } = useCatalogMedia();

  const ex = getExcellent(content);
  const footer = obj(ex.footer);
  const socials = obj(footer.socials);
  const setFooter = (patch: Json) => onChange(patchExcellent(content, { footer: { ...footer, ...patch } }));
  const setEx = (patch: Json) => onChange(patchExcellent(content, patch));
  const newsletter = obj(ex.newsletter);
  const rawFooter = obj(extra.footer);
  const setAbout = (v: string) => onExtraChange({ ...extra, footer: { ...rawFooter, about_text: v } });

  const val = (v: unknown, fallback: string) => text(v) || fallback;
  const items = footerMenu && "items" in footerMenu ? footerMenu.items : null;
  const setItem = (i: number, patch: Partial<FooterMenuItem>) => onFooterItems((items ?? []).map((it, j) => (j === i ? { ...it, ...patch } : it)));

  return (
    <>
      <AgainDrawerPanel open={open} onOpenChange={onOpenChange} title="Footer" resizable defaultWidth={440} widthStorageKey="website-live-edit-drawer-width">
        <AgainDrawerLayout>
          <AgainDrawerControlBar trailing={<LiveEditDrawerSaveButton onSave={onSave} saving={saving} />}>
            <LiveEditDrawerBackButton onBack={() => (onBack ? onBack() : onOpenChange(false))} />
            <span className={AGAIN_DRAWER_MODULE_LABEL_CLASS}>Website</span>
            <span className="text-muted-foreground">/</span>
            <span className={AGAIN_DRAWER_RECORD_LABEL_CLASS}>Footer</span>
          </AgainDrawerControlBar>
          <AgainDrawerScrollBody className={AGAIN_DRAWER_FIELD_SHEET_CLASS}>
            <div className="space-y-4">
              <Card title="Newsletter">
                <Field label="Heading" value={newsletter.title} onChange={(v) => setEx({ newsletter: { ...newsletter, title: v } })} />
                <Field label="Text" multiline value={newsletter.text} onChange={(v) => setEx({ newsletter: { ...newsletter, text: v } })} />
              </Card>

              <Card title="Logo & about">
                <AgainFormRow label="Logo" help="Shows the Site Settings logo until you pick another.">
                  <MediaPickTile
                    url={text(footer.logo_url) || defaults.logo}
                    alt="Footer logo"
                    onChange={(next) => setFooter({ logo_url: next })}
                    onPick={() => {
                      void refetchMedia();
                      setLibraryOpen(true);
                    }}
                  />
                </AgainFormRow>
                <Field label="About text" multiline value={rawFooter.about_text} onChange={setAbout} />
              </Card>

              <Card title="Hotline">
                <AgainFormRow label="Show the hotline">
                  <div className="flex h-8 items-center">
                    <Switch checked={!footer.hide_hotline} onCheckedChange={(v) => setFooter({ hide_hotline: !v })} />
                  </div>
                </AgainFormRow>
                <Field label="Small text" value={val(footer.hotline_label, `Hotline${defaults.hours ? ` (${defaults.hours})` : ""}`)} onChange={(v) => setFooter({ hotline_label: v })} />
                {(["phone_1", "phone_2", "phone_3"] as const).map((key, i) => (
                  <Field key={key} label={`Phone number ${i + 1}`} value={val(footer[key], defaults.phones[i] ?? "")} onChange={(v) => setFooter({ [key]: v })} />
                ))}
                <p className="text-[11px] text-muted-foreground">Shows the shop&apos;s numbers (Website → Configuration) until you type your own.</p>
              </Card>

              <Card title="Social links">
                {SOCIALS.map(([key, label]) => (
                  <Field key={key} label={label} value={val(socials[key], defaults.social[key] ?? "")} onChange={(v) => setFooter({ socials: { ...socials, [key]: v } })} placeholder="https://" />
                ))}
                <p className="text-[11px] text-muted-foreground">An empty one shows as a plain icon (no link).</p>
              </Card>

              <Card title="Quick links">
                <Field label="Column heading" value={val(footer.quick_links_title, "Quick Links")} onChange={(v) => setFooter({ quick_links_title: v })} />
                <RowList
                  noun="Link"
                  rows={Array.isArray(ex.quick_links) ? (ex.quick_links as Record<string, unknown>[]) : []}
                  blank={{ label: "", href: "/" }}
                  fields={[
                    { key: "label", label: "Label" },
                    { key: "href", label: "Link" },
                  ]}
                  onChange={(rows) => setEx({ quick_links: rows })}
                />
              </Card>

              <Card title="Customer care">
                <Field label="Column heading" value={val(footer.care_title, "Customer Care")} onChange={(v) => setFooter({ care_title: v })} />
                {footerMenu === null ? (
                  <p className="text-[12px] text-muted-foreground">Loading links…</p>
                ) : "error" in footerMenu ? (
                  <p className="text-[12px] text-destructive">{footerMenu.error}</p>
                ) : (
                  <div className="space-y-2">
                    {(items ?? []).map((it, i) => (
                      <div key={it.id} className="space-y-2 rounded-md border border-border p-2">
                        <div className="flex items-center justify-between">
                          <span className={`text-[11px] font-semibold uppercase tracking-wide text-muted-foreground ${it.hidden ? "line-through" : ""}`}>Link {i + 1}</span>
                          <div className="flex gap-1">
                            <Button type="button" variant="ghost" size="icon" className="h-7 w-7" title={it.hidden ? "Show" : "Hide"} onClick={() => setItem(i, { hidden: !it.hidden })}>
                              {it.hidden ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                            </Button>
                            <Button type="button" variant="ghost" size="icon" className="h-7 w-7" title="Remove" onClick={() => onFooterItems((items ?? []).filter((_, j) => j !== i))}>
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        </div>
                        <Input value={it.label} onChange={(e) => setItem(i, { label: e.target.value })} className="h-8 text-[13px]" placeholder="Label" />
                        <Input value={it.href} onChange={(e) => setItem(i, { href: e.target.value })} className="h-8 text-[13px]" placeholder="/link" />
                      </div>
                    ))}
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-8"
                      onClick={() => onFooterItems([...(items ?? []), { id: `link-${Date.now().toString(36)}`, label: "New link", href: "/", link_type: "custom", link_ref_id: null, hidden: false, children: [] }])}
                    >
                      <Plus className="mr-1 h-3.5 w-3.5" />
                      Add link
                    </Button>
                    <p className="text-[11px] text-muted-foreground">These are the links of the Footer menu (Website → Menus). They show on the page after Save.</p>
                  </div>
                )}
              </Card>

              <Card title="Our branches">
                <Field label="Column heading" value={val(footer.branches_title, "Our Branches")} onChange={(v) => setFooter({ branches_title: v })} />
                <p className="text-[11px] text-muted-foreground">The branches themselves (name, address) are managed in Settings → Shipping.</p>
              </Card>

              <Card title="Bottom bar">
                <Field label="Copyright text" multiline value={val(footer.copyright, defaults.copyright)} onChange={(v) => setFooter({ copyright: v })} />
                <AgainFormRow label="Show “Developed By”">
                  <div className="flex h-8 items-center">
                    <Switch checked={!footer.hide_dev} onCheckedChange={(v) => setFooter({ hide_dev: !v })} />
                  </div>
                </AgainFormRow>
                <Field label="Developer name" value={val(footer.dev_name, "Againsoft")} onChange={(v) => setFooter({ dev_name: v })} />
                <Field label="Developer link" value={val(footer.dev_url, "https://www.againsoft.com")} onChange={(v) => setFooter({ dev_url: v })} />
              </Card>
            </div>
          </AgainDrawerScrollBody>
        </AgainDrawerLayout>
      </AgainDrawerPanel>

      <MediaLibraryModal
        open={libraryOpen}
        onOpenChange={(next) => {
          setLibraryOpen(next);
          if (next) void refetchMedia();
        }}
        items={mediaItems}
        mode="single"
        title="Footer logo"
        accept={["image"]}
        onSelect={(items) => {
          const next = items.find((i) => i.type === "image")?.url;
          if (next) setFooter({ logo_url: next });
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
    </>
  );
}
