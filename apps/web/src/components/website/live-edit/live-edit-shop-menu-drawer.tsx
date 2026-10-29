"use client";

import { useEffect, useId, useMemo, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { toast } from "sonner";
import {
  AgainDrawerControlBar,
  AgainDrawerLayout,
  AgainDrawerPanel,
  AgainDrawerScrollBody,
  AGAIN_DRAWER_ACTION_BTN,
  AGAIN_DRAWER_FIELD_SHEET_CLASS,
  AGAIN_DRAWER_MODULE_LABEL_CLASS,
  AGAIN_DRAWER_PRIMARY_BTN,
  AGAIN_DRAWER_PRIMARY_COLOR,
  AGAIN_DRAWER_RECORD_LABEL_CLASS,
} from "@/components/again/again-drawer";
import { AgainFormRow } from "@/components/again/again-form-sheet";
import { CatalogAutoMenuTree } from "@/components/website/menus/catalog-auto-menu-tree";
import { CustomMenuTree } from "@/components/website/menus/custom-menu-tree";
import { Button } from "@/components/ui/button";
import { LiveEditDrawerBackButton } from "@/components/website/live-edit/live-edit-drawer-back-button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useCatalogBrands } from "@/lib/api/use-catalog-brands";
import { useCatalogCategories } from "@/lib/api/use-catalog-categories";
import { useWebsiteMenus } from "@/lib/api/use-website-menus";
import { useWebsitePages } from "@/lib/api/use-website-pages";
import { fetchWebsiteMenu } from "@/lib/api/website-menus";
import { cn } from "@/lib/utils";
import type {
  MenuAutoType,
  MenuNavStyle,
  MenuSource,
  WebsiteMenu,
  WebsiteMenuItem,
} from "@/lib/website/website-menus";
import { autoTypeLabel } from "@/lib/website/website-menus";

const SHOP_SLOT = "catalog.shop";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Return to Sections list (Live Edit). */
  onBack?: () => void;
  /** After slot / menu applied — reload storefront + open SHOP megamenu. */
  onApplied?: () => void;
  onSave?: () => void | Promise<void>;
  saving?: boolean;
};

export function LiveEditShopMenuDrawer({
  open,
  onOpenChange,
  onBack,
  onApplied,
  onSave,
  saving = false,
}: Props) {
  const titleId = useId();
  const { menus, slots, loading, refetch, saveSlots, update } = useWebsiteMenus();
  const { categories } = useCatalogCategories({ channel: "dropshipping" });
  const { brands } = useCatalogBrands({ channel: "dropshipping" });
  const { pages } = useWebsitePages();
  const pageOptions = pages.map((p) => ({ id: p.id, name: p.name, url: p.url }));

  const [menuId, setMenuId] = useState("");
  const [triggerTitle, setTriggerTitle] = useState("SHOP");
  const [navStyle, setNavStyle] = useState<MenuNavStyle>("megamenu");
  const [editingMenu, setEditingMenu] = useState<WebsiteMenu | null>(null);
  const [name, setName] = useState("");
  const [source, setSource] = useState<MenuSource>("custom");
  const [autoType, setAutoType] = useState<MenuAutoType>("category");
  const [autoShowNew, setAutoShowNew] = useState(true);
  const [items, setItems] = useState<WebsiteMenuItem[]>([]);
  const [menuLoading, setMenuLoading] = useState(false);
  const [applying, setApplying] = useState(false);

  const shopSlot = useMemo(
    () => slots.find((s) => s.slotKey === SHOP_SLOT),
    [slots],
  );

  const loadMenuIntoEditor = async (id: string) => {
    setMenuLoading(true);
    try {
      const full = await fetchWebsiteMenu(id);
      setEditingMenu(full);
      setName(full.name);
      setSource(full.source);
      setAutoType(full.autoType || "category");
      setAutoShowNew(full.autoShowNew !== false);
      const tree =
        full.source === "auto"
          ? full.items.length > 0
            ? full.items
            : full.autoPreview
          : full.items;
      setItems(tree);
    } catch (err) {
      setEditingMenu(null);
      setItems([]);
      toast.error(err instanceof Error ? err.message : "Failed to load menu");
    } finally {
      setMenuLoading(false);
    }
  };

  useEffect(() => {
    if (!open) {
      setEditingMenu(null);
      setItems([]);
      return;
    }
    void refetch();
  }, [open, refetch]);

  useEffect(() => {
    if (!open) return;
    setMenuId(shopSlot?.menuId ?? "");
    setTriggerTitle((shopSlot?.title || "SHOP").trim() || "SHOP");
    setNavStyle(shopSlot?.navStyle === "dropdown" ? "dropdown" : "megamenu");
  }, [open, shopSlot?.menuId, shopSlot?.title, shopSlot?.navStyle]);

  useEffect(() => {
    if (!open || !menuId) {
      setEditingMenu(null);
      setItems([]);
      return;
    }
    void loadMenuIntoEditor(menuId);
    // Intentionally only when open/menuId changes — not on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- loadMenuIntoEditor is stable enough via menuId
  }, [open, menuId]);

  const writeShopSlot = async (patch: {
    menuId?: string;
    title?: string;
    navStyle?: MenuNavStyle;
  }) => {
    const nextMenuId = patch.menuId ?? menuId;
    if (!nextMenuId) return;
    const title = (patch.title ?? triggerTitle).trim() || "SHOP";
    const style = patch.navStyle ?? navStyle;
    const next = slots.map((s) =>
      s.slotKey === SHOP_SLOT
        ? {
            slotKey: s.slotKey,
            menuId: nextMenuId,
            title,
            navStyle: style,
          }
        : { slotKey: s.slotKey, menuId: s.menuId },
    );
    if (!next.some((s) => s.slotKey === SHOP_SLOT)) {
      next.push({
        slotKey: SHOP_SLOT,
        menuId: nextMenuId,
        title,
        navStyle: style,
      });
    }
    await saveSlots(next);
  };

  const persistShopSlot = async (patch: {
    menuId?: string;
    title?: string;
    navStyle?: MenuNavStyle;
  }) => {
    setApplying(true);
    try {
      await writeShopSlot(patch);
      onApplied?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setApplying(false);
    }
  };

  const handleSaveMenu = async () => {
    if (!editingMenu) {
      toast.error("No menu loaded");
      return;
    }
    const trimmed = name.trim();
    if (!trimmed) {
      toast.error("Menu name is required");
      return;
    }
    setApplying(true);
    try {
      await update(editingMenu.id, {
        name: trimmed,
        source,
        autoType,
        autoShowNew,
        items,
      });
      await writeShopSlot({});
      await refetch();
      await loadMenuIntoEditor(editingMenu.id);
      onApplied?.();
      if (onSave) await onSave();
      toast.success("Shop menu saved");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Save failed");
    } finally {
      setApplying(false);
    }
  };

  const busy = loading || menuLoading || applying || saving;

  return (
    <AgainDrawerPanel
      open={open}
      onOpenChange={onOpenChange}
      title="Main menu"
      resizable
      defaultWidth={560}
      widthStorageKey="website-live-edit-drawer-width"
    >
      <AgainDrawerLayout>
        <AgainDrawerControlBar>
            <LiveEditDrawerBackButton
              onBack={() => (onBack ? onBack() : onOpenChange(false))}
            />
          <span className={AGAIN_DRAWER_MODULE_LABEL_CLASS}>Website</span>
          <span className="text-muted-foreground">/</span>
          <span className={AGAIN_DRAWER_RECORD_LABEL_CLASS} id={titleId}>
            Main menu
          </span>
          <div className="ml-auto flex shrink-0 items-center gap-1.5">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className={cn(AGAIN_DRAWER_ACTION_BTN, "h-7")}
              onClick={() => onOpenChange(false)}
              disabled={busy}
            >
              Discard
            </Button>
            <Button
              type="button"
              size="sm"
              className={cn(AGAIN_DRAWER_PRIMARY_BTN, "h-7")}
              style={{ backgroundColor: AGAIN_DRAWER_PRIMARY_COLOR }}
              onClick={() => void handleSaveMenu()}
              disabled={busy || !editingMenu}
            >
              {applying ? "Saving…" : "Save"}
            </Button>
          </div>
        </AgainDrawerControlBar>

        <AgainDrawerScrollBody className={AGAIN_DRAWER_FIELD_SHEET_CLASS}>
          <div className="space-y-4">
            <div className="space-y-3 rounded-md border border-border bg-card p-2.5">
              <p className="text-[12px] leading-snug text-muted-foreground">
                This menu appears in the All Categories drawer and on category page side menus.
              </p>
              <div className="grid grid-cols-2 gap-2.5">
                <AgainFormRow label="Button label">
                  <Input
                    value={triggerTitle}
                    onChange={(e) => setTriggerTitle(e.target.value)}
                    onBlur={() => {
                      const next = triggerTitle.trim() || "SHOP";
                      setTriggerTitle(next);
                      if (menuId && next !== (shopSlot?.title || "SHOP")) {
                        void persistShopSlot({ title: next });
                      }
                    }}
                    className="h-8 text-[13px]"
                    placeholder="SHOP"
                    disabled={busy}
                  />
                </AgainFormRow>
                <AgainFormRow label="Style">
                  <Select
                    value={navStyle}
                    onValueChange={(v) => {
                      const next = v as MenuNavStyle;
                      setNavStyle(next);
                      if (menuId) void persistShopSlot({ navStyle: next });
                    }}
                    disabled={busy || !menuId}
                  >
                    <SelectTrigger className="h-8 text-[13px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="z-[400]">
                      <SelectItem value="megamenu">Megamenu</SelectItem>
                      <SelectItem value="dropdown">Dropdown</SelectItem>
                    </SelectContent>
                  </Select>
                </AgainFormRow>
              </div>

              <AgainFormRow label="Menu">
                <Select
                  value={menuId || undefined}
                  onValueChange={(id) => {
                    setMenuId(id);
                    void persistShopSlot({ menuId: id });
                  }}
                  disabled={busy}
                >
                  <SelectTrigger className="h-8 text-[13px]">
                    <SelectValue
                      placeholder={loading ? "Loading…" : "Select menu"}
                    />
                  </SelectTrigger>
                  <SelectContent className="z-[400]">
                    {menus.map((m) => (
                      <SelectItem key={m.id} value={m.id}>
                        {m.name}
                        {m.source === "auto"
                          ? ` · Auto · ${autoTypeLabel(m.autoType)}`
                          : " · Custom"}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </AgainFormRow>

              {editingMenu ? (
                <>
                  <AgainFormRow label="Menu name">
                    <Input
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      className="h-8 text-[13px]"
                      placeholder="Menu name"
                      disabled={busy}
                    />
                  </AgainFormRow>
                  <AgainFormRow label="Source">
                    <div className="flex h-8 items-center gap-2">
                      <span
                        className={cn(
                          "text-[12px]",
                          source === "custom"
                            ? "font-medium text-foreground"
                            : "text-muted-foreground",
                        )}
                      >
                        Custom
                      </span>
                      <Switch
                        checked={source === "auto"}
                        onCheckedChange={(checked) => {
                          setSource(checked ? "auto" : "custom");
                        }}
                        disabled={busy}
                      />
                      <span
                        className={cn(
                          "text-[12px]",
                          source === "auto"
                            ? "font-medium text-foreground"
                            : "text-muted-foreground",
                        )}
                      >
                        Auto
                      </span>
                      <button
                        type="button"
                        disabled={source !== "auto" || busy}
                        className={cn(
                          "inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md",
                          source === "auto"
                            ? "text-foreground hover:bg-muted"
                            : "cursor-not-allowed text-muted-foreground/40",
                        )}
                        aria-label={
                          autoShowNew
                            ? "New synced items auto-visible"
                            : "New synced items start hidden"
                        }
                        title={
                          autoShowNew
                            ? "New items appear visible"
                            : "New items start hidden"
                        }
                        onClick={() => setAutoShowNew((v) => !v)}
                      >
                        {autoShowNew ? (
                          <Eye className="h-3.5 w-3.5" />
                        ) : (
                          <EyeOff className="h-3.5 w-3.5" />
                        )}
                      </button>
                    </div>
                  </AgainFormRow>
                  {source === "auto" ? (
                    <AgainFormRow label="Auto from">
                      <Select
                        value={autoType}
                        onValueChange={(value) =>
                          setAutoType(value as MenuAutoType)
                        }
                        disabled={busy}
                      >
                        <SelectTrigger className="h-8 text-[13px]">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="z-[400]">
                          <SelectItem value="category">Category</SelectItem>
                          <SelectItem value="brand">Brand</SelectItem>
                          <SelectItem value="page">Page</SelectItem>
                        </SelectContent>
                      </Select>
                    </AgainFormRow>
                  ) : null}
                </>
              ) : null}
            </div>

            {menuLoading ? (
              <p className="py-10 text-center text-[12px] text-muted-foreground">
                Loading menu…
              </p>
            ) : !menuId ? (
              <p className="py-10 text-center text-[12px] text-muted-foreground">
                Select a menu to edit its items.
              </p>
            ) : source === "auto" ? (
              <div className="space-y-2">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {autoTypeLabel(autoType)} tree
                </p>
                <CatalogAutoMenuTree
                  key={`${editingMenu?.id ?? "shop"}-auto-${autoType}`}
                  items={items}
                  onChange={setItems}
                  autoType={autoType}
                  newItemsHidden={!autoShowNew}
                />
              </div>
            ) : (
              <div className="space-y-2">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Menu items
                </p>
                <CustomMenuTree
                  key={`${editingMenu?.id ?? "shop"}-custom`}
                  items={items}
                  onChange={setItems}
                  pages={pageOptions}
                  categories={categories}
                  brands={brands}
                />
              </div>
            )}
          </div>
        </AgainDrawerScrollBody>
      </AgainDrawerLayout>
    </AgainDrawerPanel>
  );
}
