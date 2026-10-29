"use client";

import { useState } from "react";
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
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { createCatalogMediaBatch, uploadCatalogMediaFiles, useCatalogMedia } from "@/lib/api/use-catalog-media";
import { getExcellent, obj, patchExcellent, type Json } from "@/lib/website/excellent-home";
import type { HomepageContent } from "@/lib/website/website-homepage";
import { defaultHeaderSection } from "@/lib/website/website-homepage";

type Props = {
  open: boolean;
  /** Return to the Sections list (falls back to closing the drawer). */
  onBack?: () => void;
  onOpenChange: (open: boolean) => void;
  /** "top" = the blue bar above the header; "main" = logo, search and the header buttons. */
  mode: "top" | "main";
  content: HomepageContent;
  onChange: (content: HomepageContent) => void;
  onSave?: () => void | Promise<void>;
  saving?: boolean;
  /** What the site shows today when nothing is typed here: the shop's own phone numbers and logo. */
  defaults?: { phones: string[]; logo: string };
};

/** What the storefront shows when a label / link is left empty (mirrors `HEADER_ITEMS` there). */
const DEFAULTS: Record<string, { label: string; sublabel: string; href: string }> = {
  branches: { label: "Branches", sublabel: "", href: "/branches" },
  track_order: { label: "Track Order", sublabel: "", href: "/track-order" },
  our_branches: { label: "Our Branches", sublabel: "", href: "/branches" },
  pc_builder: { label: "PC Builder", sublabel: "", href: "/pc-builder" },
  wishlist: { label: "Offers", sublabel: "Hot Deals", href: "/offers" },
  account: { label: "Account", sublabel: "", href: "/account" },
  cart: { label: "My Cart", sublabel: "", href: "/cart" },
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

function Toggle({ label, checked, onChange, help }: { label: string; checked: boolean; onChange: (v: boolean) => void; help?: string }) {
  return (
    <AgainFormRow label={label} help={help}>
      <div className="flex h-8 items-center">
        <Switch checked={checked} onCheckedChange={onChange} />
      </div>
    </AgainFormRow>
  );
}

export function LiveEditExcellentHeaderDrawer({ onBack, open, onOpenChange, mode, content, onChange, onSave, saving = false, defaults }: Props) {
  const [libraryOpen, setLibraryOpen] = useState(false);
  const { items: mediaItems, refetch: refetchMedia } = useCatalogMedia();

  const header = getExcellent(content).header;
  const hx = obj(header);
  const topbar = obj(hx.topbar);

  const setHeader = (next: Json) => onChange(patchExcellent(content, { header: next }));
  const setTopbar = (patch: Json) => setHeader({ ...hx, topbar: { ...topbar, ...patch } });
  const setItem = (where: "root" | "topbar", key: string, patch: Json) => {
    const holder = where === "topbar" ? topbar : hx;
    const item = { ...obj(holder[key]), ...patch };
    if (where === "topbar") setTopbar({ [key]: item });
    else setHeader({ ...hx, [key]: item });
  };

  const typed = content.header ?? defaultHeaderSection();
  const setTyped = (patch: Partial<typeof typed>) => onChange({ ...content, header: { ...typed, ...patch } });

  const item = (where: "root" | "topbar", key: string, title: string) => {
    const holder = where === "topbar" ? topbar : hx;
    const row = obj(holder[key]);
    const d = DEFAULTS[key];
    return (
      <Card key={`${where}-${key}`} title={title}>
        <Toggle label={`Show ${title}`} checked={!row.hidden} onChange={(v) => setItem(where, key, { hidden: !v })} />
        <AgainFormRow label="Label">
          <Input value={text(row.label) || d.label} onChange={(e) => setItem(where, key, { label: e.target.value })} className="h-8 text-[13px]" placeholder={d.label} />
        </AgainFormRow>
        {d.sublabel ? (
          <AgainFormRow label="Small text above">
            <Input value={text(row.sublabel) || d.sublabel} onChange={(e) => setItem(where, key, { sublabel: e.target.value })} className="h-8 text-[13px]" placeholder={d.sublabel} />
          </AgainFormRow>
        ) : null}
        <AgainFormRow label="Link">
          <Input value={text(row.href) || d.href} onChange={(e) => setItem(where, key, { href: e.target.value })} className="h-8 text-[13px]" placeholder={d.href} />
        </AgainFormRow>
      </Card>
    );
  };

  const title = mode === "top" ? "Header top" : "Header";

  return (
    <>
      <AgainDrawerPanel open={open} onOpenChange={onOpenChange} title={title} resizable defaultWidth={420} widthStorageKey="website-live-edit-drawer-width">
        <AgainDrawerLayout>
          <AgainDrawerControlBar trailing={<LiveEditDrawerSaveButton onSave={onSave} saving={saving} />}>
            <LiveEditDrawerBackButton onBack={() => (onBack ? onBack() : onOpenChange(false))} />
            <span className={AGAIN_DRAWER_MODULE_LABEL_CLASS}>Website</span>
            <span className="text-muted-foreground">/</span>
            <span className={AGAIN_DRAWER_RECORD_LABEL_CLASS}>{title}</span>
          </AgainDrawerControlBar>
          <AgainDrawerScrollBody className={AGAIN_DRAWER_FIELD_SHEET_CLASS}>
            <div className="space-y-4">
              {mode === "top" ? (
                <>
                  <Card title="Top bar">
                    <Toggle label="Show the top bar" checked={!topbar.hidden} onChange={(v) => setTopbar({ hidden: !v })} />
                    <Toggle label="Show phone numbers" checked={!topbar.hide_phones} onChange={(v) => setTopbar({ hide_phones: !v })} />
                    <AgainFormRow label="Phone number 1" help="Shows the shop's numbers from Website → Configuration until you type your own.">
                      <Input value={text(topbar.phone_1) || defaults?.phones[0] || ""} onChange={(e) => setTopbar({ phone_1: e.target.value })} className="h-8 text-[13px]" placeholder="Phone number" />
                    </AgainFormRow>
                    <AgainFormRow label="Phone number 2">
                      <Input value={text(topbar.phone_2) || defaults?.phones[1] || ""} onChange={(e) => setTopbar({ phone_2: e.target.value })} className="h-8 text-[13px]" placeholder="Phone number" />
                    </AgainFormRow>
                    <Toggle label="Show the dark mode switch" checked={!topbar.hide_theme_toggle} onChange={(v) => setTopbar({ hide_theme_toggle: !v })} />
                  </Card>
                  {item("topbar", "branches", "Branches")}
                  {item("topbar", "track_order", "Track Order")}
                  {item("topbar", "our_branches", "Our Branches")}
                </>
              ) : (
                <>
                  <Card title="Logo & search">
                    <AgainFormRow label="Logo" help="Shows the Site Settings logo until you pick another.">
                      <MediaPickTile
                        url={typed.logoUrl || defaults?.logo || ""}
                        alt="Logo"
                        onChange={(next) => setTyped({ logoUrl: next })}
                        onPick={() => {
                          void refetchMedia();
                          setLibraryOpen(true);
                        }}
                      />
                    </AgainFormRow>
                    <AgainFormRow label="Search box placeholder">
                      <Input value={typed.searchPlaceholder} onChange={(e) => setTyped({ searchPlaceholder: e.target.value })} className="h-8 text-[13px]" placeholder="Search Products" />
                    </AgainFormRow>
                  </Card>
                  {item("root", "pc_builder", "PC Builder")}
                  {item("root", "wishlist", "Offers")}
                  {item("root", "account", "Account")}
                  {item("root", "cart", "Cart")}
                  <p className="text-[11px] text-muted-foreground">Turning off PC Builder, Account or Cart also hides it in the mobile menu and bottom bar.</p>
                </>
              )}
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
        title="Logo"
        accept={["image"]}
        onSelect={(items) => {
          const next = items.find((i) => i.type === "image")?.url;
          if (next) setTyped({ logoUrl: next });
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
