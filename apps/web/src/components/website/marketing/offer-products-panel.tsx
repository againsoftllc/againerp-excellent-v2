"use client";

import "@/components/providers/ag-grid-provider";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { toast } from "sonner";
import { ArrowRightLeft, Trash2 } from "lucide-react";
import {
  deleteOfferDeal,
  fetchOfferDeals,
  patchOfferDeal,
  type ApiOfferDeal,
  type DealKind,
  type DealPatch,
} from "@/lib/api/marketing-offer-deals";
import { fetchMarketingOffers } from "@/lib/api/marketing-offers";
import { fetchMarketingHappyHours } from "@/lib/api/marketing-happy-hours";
import { useAdminCanWrite } from "@/lib/hooks/use-admin-can-write";
import { getApiBaseUrl } from "@/lib/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { Select } from "@/components/ui/native-select";
import * as SwitchPrimitive from "@radix-ui/react-switch";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { confirmDialog } from "@/components/shared/confirm-dialog";
import { useUserScopedState } from "@/lib/hooks/use-user-scoped-state";
import { MarketingListGrid, StatusBadge, type StatusTone } from "@/components/website/marketing/marketing-list-grid";

/** The columns the admin can tick on/off (the Columns button), like the Products list. */
const COLUMN_LABELS = {
  model: "Model",
  sku: "SKU",
  offer: "Offer",
  in: "In offers",
  cstatus: "Offer status",
  regular: "Regular price",
  price: "Offer price",
  disc: "Discount %",
  priority: "Priority",
  qty: "Quantity",
  on: "On / Off",
  state: "Now (live / winning)",
  window: "Runs (dates)",
  brand: "Brand",
  category: "Category",
} as const;
type ColKey = keyof typeof COLUMN_LABELS;
const COLUMN_KEYS = Object.keys(COLUMN_LABELS) as ColKey[];
// every column is on, except the SKU (the Model is what the table shows; the SKU can be ticked on in Columns)
const DEFAULT_VISIBLE = { ...Object.fromEntries(COLUMN_KEYS.map((k) => [k, true])), sku: false } as Record<ColKey, boolean>;

/** A plain on/off switch (the shared Switch draws a bordered box around itself, which does not fit in a table cell). */
function Switch({ checked, disabled, onCheckedChange, ...rest }: { checked: boolean; disabled?: boolean; onCheckedChange: (v: boolean) => void; "aria-label"?: string }) {
  return (
    <SwitchPrimitive.Root
      checked={checked}
      disabled={disabled}
      onCheckedChange={onCheckedChange}
      className="peer inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-primary data-[state=unchecked]:bg-input"
      {...rest}
    >
      <SwitchPrimitive.Thumb className="pointer-events-none block h-4 w-4 rounded-full bg-background shadow-lg ring-0 transition-transform data-[state=checked]:translate-x-4 data-[state=unchecked]:translate-x-0" />
    </SwitchPrimitive.Root>
  );
}

type Campaign = { kind: DealKind; id: string; title: string; sections: { id: string; label: string }[] };

/** Where a deal can go: every other offer, and its own offer too when that has another section to move it to. */
function targetsFor(row: ApiOfferDeal, campaigns: Campaign[]): Campaign[] {
  return campaigns.filter((c) => !(c.kind === row.kind && c.id === row.campaign_id) || c.sections.length > 1);
}

/** The sections of the chosen target the deal can go to (never the one it is in already). */
function sectionsFor(row: ApiOfferDeal, c: Campaign | undefined) {
  return (c?.sections ?? []).filter((s) => s.id !== row.section_id);
}

/** "Move to ..." - the target offer, and (when it has several sections) the section of it the product goes into. */
function MoveTargetPicker({ row, campaigns, target, sectionId, onChange }: { row: ApiOfferDeal; campaigns: Campaign[]; target: string; sectionId: string; onChange: (target: string, sectionId: string) => void }) {
  const list = targetsFor(row, campaigns);
  const chosen = list.find((c) => `${c.kind}:${c.id}` === target);
  const sections = sectionsFor(row, chosen);
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-2">
      <Select
        className="min-w-0 flex-1"
        value={target}
        onChange={(e) => {
          const c = list.find((x) => `${x.kind}:${x.id}` === e.target.value);
          onChange(e.target.value, sectionsFor(row, c)[0]?.id ?? "");
        }}
        aria-label="Move to offer"
      >
        <option value="">Move to another offer…</option>
        {list.map((c) => (
          <option key={`${c.kind}:${c.id}`} value={`${c.kind}:${c.id}`}>
            {c.title}
            {c.kind === row.kind && c.id === row.campaign_id ? " (another section)" : ""}
          </option>
        ))}
      </Select>
      {chosen && chosen.sections.length > 1 ? (
        <Select className="min-w-0 flex-1" value={sectionId} onChange={(e) => onChange(target, e.target.value)} aria-label="Move to section">
          {sections.map((s) => (
            <option key={s.id} value={s.id}>
              Section: {s.label}
            </option>
          ))}
        </Select>
      ) : null}
    </div>
  );
}

const STATUS_TONE: Record<string, StatusTone> = { draft: "muted", scheduled: "warning", running: "success", ended: "outline", disabled: "muted" };
const money = (n: number | null | undefined) => (n == null ? "—" : `৳${Number(n).toLocaleString("en-US")}`);
const img = (u: string | null) => (!u ? "" : /^https?:\/\//i.test(u) ? u : `${getApiBaseUrl()}${u.startsWith("/") ? "" : "/"}${u}`);
const day = (iso: string | null) => (iso ? iso.slice(0, 10) : "…");
const span = (a: string | null, b: string | null) => (a && b && Number(a.slice(0, 4)) <= 2000 && Number(b.slice(0, 4)) >= 2099 ? "Always" : `${day(a)} → ${day(b)}`);

/** A number cell: type, then Enter or leave the box to save; Esc puts the old value back. */
function NumCell({ value, disabled, placeholder, onSave, width = "w-20" }: { value: number | null; disabled: boolean; placeholder?: string; width?: string; onSave: (v: number | null) => void }) {
  const [text, setText] = useState(value == null ? "" : String(value));
  useEffect(() => setText(value == null ? "" : String(value)), [value]);
  const commit = () => {
    const t = text.trim();
    const next = t === "" ? null : Number(t);
    if (next !== null && !Number.isFinite(next)) return setText(value == null ? "" : String(value));
    if (next !== value) onSave(next);
  };
  return (
    <input
      className={`h-6 ${width} rounded-none border border-input bg-background px-1.5 text-xs disabled:opacity-60`}
      inputMode="decimal"
      value={text}
      disabled={disabled}
      placeholder={placeholder}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        if (e.key === "Escape") setText(value == null ? "" : String(value));
      }}
    />
  );
}


type SaveFn = (row: ApiOfferDeal, patch: DealPatch, done?: string) => Promise<void>;

/** One offer of the product inside the drawer: every value can be changed here. */
function DealCard({ row, campaigns, canWrite, onSave, onRemove }: { row: ApiOfferDeal; campaigns: Campaign[]; canWrite: boolean; onSave: SaveFn; onRemove: (row: ApiOfferDeal) => Promise<void> }) {
  const [target, setTarget] = useState("");
  const [targetSection, setTargetSection] = useState("");
  const bad = row.regular_price != null && row.offer_price >= row.regular_price;
  const lbl = "text-[10px] uppercase tracking-wide text-muted-foreground";
  return (
    <div className={`space-y-2 border border-border p-3 ${row.enabled ? "" : "opacity-70"}`}>
      <div className="flex items-center gap-2">
        <span className="flex min-w-0 flex-1 items-center gap-2">
          <span className="truncate text-sm font-medium">{row.campaign_title}</span>
          {row.winner ? (
            <span className="relative flex h-2.5 w-2.5 shrink-0" title="This price is showing on the store now">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-500 opacity-75" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
            </span>
          ) : null}
        </span>
        {row.kind === "happy_hour" ? <Badge variant="outline" className="shrink-0 text-[10px] leading-4">Happy Hour</Badge> : null}
        <StatusBadge label={row.campaign_status} tone={STATUS_TONE[row.campaign_status] ?? "muted"} />
      </div>
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{span(row.starts_at, row.ends_at)}{row.daily_start_hour != null ? ` · ${row.daily_start_hour}–${row.daily_end_hour}h` : ""}</span>
        <StatusBadge label={row.winner ? "Winning" : row.live ? "Live, beaten" : "Not live"} tone={row.winner ? "success" : row.live ? "warning" : "muted"} />
      </div>
      <div className="grid grid-cols-4 items-end gap-2">
        <div>
          <div className={lbl}>Offer price</div>
          <NumCell width="w-full" value={row.offer_price} disabled={!canWrite} onSave={(v) => (v && v > 0 ? void onSave(row, { offer_price: v }, "Price updated") : toast.error("Enter a price above 0"))} />
        </div>
        <div>
          <div className={lbl}>Priority</div>
          <NumCell width="w-full" value={row.priority} disabled={!canWrite} onSave={(v) => void onSave(row, { priority: Math.round(v ?? 0) }, "Priority updated")} />
        </div>
        <div>
          <div className={lbl}>Quantity ({row.quantity_sold} sold)</div>
          <NumCell width="w-full" value={row.quantity} placeholder="∞" disabled={!canWrite} onSave={(v) => void onSave(row, { quantity: v == null ? null : Math.max(0, Math.round(v)) }, "Quantity updated")} />
        </div>
        <div>
          <div className={lbl}>On</div>
          <div className="flex h-6 items-center">
            <Switch checked={row.enabled} disabled={!canWrite} onCheckedChange={(v) => void onSave(row, { enabled: v }, v ? "Deal on" : "Deal off")} aria-label="Deal on/off" />
          </div>
        </div>
      </div>
      <div className="text-[11px] text-muted-foreground">
        Regular {money(row.regular_price)}{row.regular_price ? ` · ${Math.round((1 - row.offer_price / row.regular_price) * 100)}% off` : ""}
        {bad ? <span className="ml-1 text-amber-600">! Offer price is not below the regular price, so it is not applied.</span> : null}
      </div>
      {canWrite ? (
        <div className="flex items-start gap-2 border-t border-border pt-2">
          <MoveTargetPicker row={row} campaigns={campaigns} target={target} sectionId={targetSection} onChange={(t, s) => { setTarget(t); setTargetSection(s); }} />
          <Button size="sm" variant="outline" className="rounded-none" disabled={!target} onClick={() => { const [k, id] = target.split(":") as [DealKind, string]; void onSave(row, { move_to_kind: k, move_to_campaign_id: id, ...(targetSection ? { move_to_section_id: targetSection } : {}) }, "Moved"); }}>
            <ArrowRightLeft className="mr-1 h-3 w-3" />Move
          </Button>
          <Button size="sm" variant="outline" className="rounded-none text-destructive" onClick={() => void onRemove(row)}>
            <Trash2 className="mr-1 h-3 w-3" />Remove
          </Button>
        </div>
      ) : null}
    </div>
  );
}

/** The drawer of a product: all of its offers, one row each (Happy Hour, Year End ...), top to bottom. */
function ProductDealsDrawer({ slug, deals, campaigns, canWrite, onClose, onSave, onRemove }: { slug: string | null; deals: ApiOfferDeal[]; campaigns: Campaign[]; canWrite: boolean; onClose: () => void; onSave: SaveFn; onRemove: (row: ApiOfferDeal) => Promise<void> }) {
  const first = deals[0];
  return (
    <Sheet open={!!slug} onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent side="right" resizable closeButton="chevron" className="flex w-[600px] min-w-[320px] max-w-[900px] flex-col rounded-none p-0">
        <SheetHeader className="border-b border-border px-4 py-3">
          <SheetTitle className="flex items-center gap-3 text-sm font-semibold">
            {first?.thumbnail ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={img(first.thumbnail)} alt="" className="h-10 w-10 shrink-0 object-contain" />
            ) : null}
            <span className="min-w-0">
              <span className="block truncate">{first?.product_name ?? slug}</span>
              <span className="block truncate text-xs font-normal text-muted-foreground">{first?.sku ?? slug} · {deals.length} {deals.length === 1 ? "offer" : "offers"}</span>
            </span>
          </SheetTitle>
        </SheetHeader>
        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-4">
          {deals.length === 0 ? <p className="text-xs text-muted-foreground">This product is not in any offer now.</p> : null}
          {deals.map((d) => (
            <DealCard key={d.key} row={d} campaigns={campaigns} canWrite={canWrite} onSave={onSave} onRemove={onRemove} />
          ))}
        </div>
      </SheetContent>
    </Sheet>
  );
}

/** Website → Promotions → Offer Products: every deal of every Offer and Happy Hour in one catalog-style table. */
export function OfferProductsPanel() {
  const canWrite = useAdminCanWrite();
  const [rows, setRows] = useState<ApiOfferDeal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [search, setSearch] = useState("");
  const [campaignF, setCampaignF] = useState("all");
  const [stateF, setStateF] = useState("all");
  const [moving, setMoving] = useState<ApiOfferDeal | null>(null);
  const [target, setTarget] = useState("");
  const [targetSection, setTargetSection] = useState("");
  const [openSlug, setOpenSlug] = useState<string | null>(null);
  const [columnSheetOpen, setColumnSheetOpen] = useState(false);
  const [visibleSaved, setVisible] = useUserScopedState("offer-products-grid:columns", DEFAULT_VISIBLE);
  const vis = useMemo(() => ({ ...DEFAULT_VISIBLE, ...visibleSaved }), [visibleSaved]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows(await fetchOfferDeals());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void load();
    void (async () => {
      try {
        const [o, h] = await Promise.all([fetchMarketingOffers(), fetchMarketingHappyHours()]);
        setCampaigns([
          ...o.filter((c) => !c.custom_link).map((c) => ({ kind: "offer" as const, id: c.id, title: c.title, sections: (c.sections ?? []).filter((s) => s.id).map((s) => ({ id: s.id as string, label: s.label })) })),
          ...h.map((c) => ({ kind: "happy_hour" as const, id: c.id, title: `${c.title} (Happy Hour)`, sections: (c.sections ?? []).filter((s) => s.id).map((s) => ({ id: s.id as string, label: s.label })) })),
        ]);
      } catch {
        /* the move list stays empty */
      }
    })();
  }, [load]);

  const save = useCallback(
    async (row: ApiOfferDeal, patch: DealPatch, done = "Saved") => {
      try {
        await patchOfferDeal(row.kind, row.deal_id, patch);
        toast.success(done);
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Could not save");
      }
      await load();
    },
    [load],
  );

  const inOffers = useMemo(() => {
    const m = new Map<string, number>();
    rows.forEach((r) => m.set(r.product_slug, (m.get(r.product_slug) ?? 0) + 1));
    return m;
  }, [rows]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) => {
      if (campaignF !== "all" && `${r.kind}:${r.campaign_id}` !== campaignF) return false;
      if (stateF === "on" && !r.enabled) return false;
      if (stateF === "off" && r.enabled) return false;
      if (stateF === "live" && !r.live) return false;
      if (stateF === "winner" && !r.winner) return false;
      if (!q) return true;
      return [r.product_name, r.model, r.sku, r.product_slug, r.brand, r.category, r.campaign_title].some((v) => (v ?? "").toLowerCase().includes(q));
    });
  }, [rows, search, campaignF, stateF]);

  const columns = useMemo<ColDef<ApiOfferDeal>[]>(
    () => [
      {
        colId: "product",
        headerName: "Product",
        flex: 2,
        minWidth: 240,
        sort: "asc",
        valueGetter: (p) => p.data?.product_name,
        cellRenderer: (p: ICellRendererParams<ApiOfferDeal>) => {
          const r = p.data;
          if (!r) return null;
          return (
            <button type="button" className="flex h-full w-full items-center gap-2 overflow-hidden text-left" title="Open all offers of this product" onClick={() => setOpenSlug(r.product_slug)}>
              {r.thumbnail ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={img(r.thumbnail)} alt="" className="h-7 w-7 shrink-0 object-contain" />
              ) : (
                <span className="h-7 w-7 shrink-0 bg-muted" />
              )}
              <span className="min-w-0">
                <span className="block truncate text-xs font-medium leading-4">{r.product_name}</span>
              </span>
            </button>
          );
        },
      },
      { colId: "model", hide: !vis.model, headerName: "Model", width: 190, valueGetter: (p) => p.data?.model ?? "" },
      { colId: "sku", hide: !vis.sku, headerName: "SKU", width: 150, valueGetter: (p) => p.data?.sku ?? p.data?.product_slug },
      {
        colId: "offer",  hide: !vis.offer,
        headerName: "Offer",
        flex: 1.4,
        minWidth: 170,
        valueGetter: (p) => p.data?.campaign_title,
        cellRenderer: (p: ICellRendererParams<ApiOfferDeal>) =>
          p.data ? (
            <div className="flex h-full items-center gap-1.5 overflow-hidden">
              <span className="truncate text-xs">{p.data.campaign_title}</span>
              {p.data.kind === "happy_hour" ? <Badge variant="outline" className="shrink-0 text-[10px] leading-4">Happy Hour</Badge> : null}
            </div>
          ) : null,
      },
      { colId: "in",  hide: !vis.in, headerName: "In offers", width: 84, valueGetter: (p) => (p.data ? inOffers.get(p.data.product_slug) ?? 1 : 0) },
      {
        colId: "cstatus",  hide: !vis.cstatus,
        headerName: "Offer status",
        width: 110,
        valueGetter: (p) => p.data?.campaign_status,
        cellRenderer: (p: ICellRendererParams<ApiOfferDeal>) => (p.data ? <StatusBadge label={p.data.campaign_status} tone={STATUS_TONE[p.data.campaign_status] ?? "muted"} /> : null),
      },
      { colId: "regular",  hide: !vis.regular, headerName: "Regular", width: 92, valueGetter: (p) => p.data?.regular_price, valueFormatter: (p) => money(p.value) },
      {
        colId: "price",  hide: !vis.price,
        headerName: "Offer price",
        width: 112,
        valueGetter: (p) => p.data?.offer_price,
        cellRenderer: (p: ICellRendererParams<ApiOfferDeal>) => {
          const r = p.data;
          if (!r) return null;
          const bad = r.regular_price != null && r.offer_price >= r.regular_price;
          return (
            <div className="flex h-full items-center gap-1" title={bad ? "Offer price is not below the regular price: it lowers nothing, so it is not applied." : undefined}>
              <NumCell value={r.offer_price} disabled={!canWrite} onSave={(v) => (v && v > 0 ? void save(r, { offer_price: v }, "Price updated") : toast.error("Enter a price above 0"))} />
              {bad ? <span className="text-amber-600">!</span> : null}
            </div>
          );
        },
      },
      {
        colId: "disc",  hide: !vis.disc,
        headerName: "Off",
        width: 64,
        valueGetter: (p) => (p.data && p.data.regular_price ? Math.round((1 - p.data.offer_price / p.data.regular_price) * 100) : null),
        valueFormatter: (p) => (p.value == null ? "—" : `${p.value}%`),
      },
      {
        colId: "priority",  hide: !vis.priority,
        headerName: "Priority",
        width: 90,
        valueGetter: (p) => p.data?.priority,
        cellRenderer: (p: ICellRendererParams<ApiOfferDeal>) =>
          p.data ? (
            <div className="flex h-full items-center" title="Lowest number wins when a product is in several live offers">
              <NumCell width="w-14" value={p.data.priority} disabled={!canWrite} onSave={(v) => void save(p.data!, { priority: Math.round(v ?? 0) }, "Priority updated")} />
            </div>
          ) : null,
      },
      {
        colId: "qty",  hide: !vis.qty,
        headerName: "Quantity",
        width: 130,
        valueGetter: (p) => p.data?.quantity,
        cellRenderer: (p: ICellRendererParams<ApiOfferDeal>) =>
          p.data ? (
            <div className="flex h-full items-center gap-1" title="Deal quota at the offer price. Empty = unlimited. When it sells out the deal turns off.">
              <NumCell width="w-16" value={p.data.quantity} placeholder="∞" disabled={!canWrite} onSave={(v) => void save(p.data!, { quantity: v == null ? null : Math.max(0, Math.round(v)) }, "Quantity updated")} />
              <span className="text-[10px] text-muted-foreground">{p.data.quantity_sold} sold</span>
            </div>
          ) : null,
      },
      {
        colId: "on",  hide: !vis.on,
        headerName: "On",
        width: 70,
        valueGetter: (p) => p.data?.enabled,
        cellRenderer: (p: ICellRendererParams<ApiOfferDeal>) =>
          p.data ? (
            <div className="flex h-full items-center">
              <Switch checked={p.data.enabled} disabled={!canWrite} onCheckedChange={(v) => void save(p.data!, { enabled: v }, v ? "Deal on" : "Deal off")} aria-label="Deal on/off" />
            </div>
          ) : null,
      },
      {
        colId: "state",  hide: !vis.state,
        headerName: "Now",
        width: 120,
        valueGetter: (p) => (p.data?.winner ? "Winning" : p.data?.live ? "Live" : "Not live"),
        cellRenderer: (p: ICellRendererParams<ApiOfferDeal>) =>
          p.data ? (
            <StatusBadge
              label={p.data.winner ? "Winning" : p.data.live ? "Live, beaten" : "Not live"}
              tone={p.data.winner ? "success" : p.data.live ? "warning" : "muted"}
            />
          ) : null,
      },
      {
        colId: "window",  hide: !vis.window,
        headerName: "Runs",
        width: 240,
        valueGetter: (p) => (p.data ? `${span(p.data.starts_at, p.data.ends_at)}${p.data.daily_start_hour != null ? ` · ${p.data.daily_start_hour}–${p.data.daily_end_hour}h` : ""}` : ""),
      },
      { field: "brand", hide: !vis.brand, headerName: "Brand", width: 110 },
      { field: "category", hide: !vis.category, headerName: "Category", width: 130 },
    ],
    [canWrite, inOffers, save, vis],
  );

  const rowMenu = useCallback(
    (row: ApiOfferDeal) =>
      canWrite ? (
        <>
          <DropdownMenuItem
            onClick={() => {
              setMoving(row);
              setTarget("");
              setTargetSection("");
            }}
          >
            <ArrowRightLeft className="mr-1.5 h-3 w-3" />
            Move to another offer…
          </DropdownMenuItem>
          <DropdownMenuItem
            className="text-destructive"
            onClick={async () => {
              if (!(await confirmDialog({ title: "Remove from offer", message: `Remove ${row.product_name} from “${row.campaign_title}”?`, confirmLabel: "Remove", danger: true }))) return;
              try {
                await deleteOfferDeal(row.kind, row.deal_id);
                toast.success("Removed from the offer");
                await load();
              } catch (e) {
                toast.error(e instanceof Error ? e.message : "Could not remove");
              }
            }}
          >
            <Trash2 className="mr-1.5 h-3 w-3" />
            Remove from this offer
          </DropdownMenuItem>
        </>
      ) : null,
    [canWrite, load],
  );

  const filtersActive = search !== "" || campaignF !== "all" || stateF !== "all";

  return (
    <MarketingListGrid<ApiOfferDeal>
      title="Offer Products"
      rows={filtered}
      loading={loading}
      error={error}
      columns={columns}
      rowMenu={rowMenu}
      onRefresh={() => void load()}
      search={{ value: search, onChange: setSearch, placeholder: "Search product, model, SKU, brand, offer…" }}
      statusFilter={{
        value: stateF,
        onChange: setStateF,
        label: "State filter",
        options: [
          { value: "all", label: "All deals" },
          { value: "on", label: "On" },
          { value: "off", label: "Off" },
          { value: "live", label: "Live now" },
          { value: "winner", label: "Winning now" },
        ],
      }}
      extraFilters={
        <Select className="w-[200px] shrink-0" value={campaignF} onChange={(e) => setCampaignF(e.target.value)} aria-label="Offer filter">
          <option value="all">All offers</option>
          {campaigns.map((c) => (
            <option key={`${c.kind}:${c.id}`} value={`${c.kind}:${c.id}`}>
              {c.title}
            </option>
          ))}
        </Select>
      }
      filtersActive={filtersActive}
      onResetFilters={() => {
        setSearch("");
        setCampaignF("all");
        setStateF("all");
      }}
      emptyTitle="No offer products yet"
      emptyHint="Add products to an Offer or a Happy Hour first."
      layoutKey="grid-layout:marketing-offer-products-v2"
      onOpenColumns={() => setColumnSheetOpen(true)}
    >
      <Sheet open={columnSheetOpen} onOpenChange={setColumnSheetOpen}>
        <SheetContent side="right" title="Columns" resizable closeButton="inside" className="w-[200px] min-w-[160px] max-w-[720px] gap-2 rounded-none p-3">
          <h2 className="border-b border-border pb-2 pr-8 text-sm font-semibold">Columns</h2>
          <div className="mt-1 flex-1 space-y-1.5 overflow-y-auto">
            {COLUMN_KEYS.map((key) => (
              <label key={key} className="flex cursor-pointer items-center gap-2 text-xs text-foreground">
                <input
                  type="checkbox"
                  checked={vis[key]}
                  onChange={(e) => setVisible((v) => ({ ...DEFAULT_VISIBLE, ...v, [key]: e.target.checked }))}
                  className="h-3.5 w-3.5 shrink-0 cursor-pointer appearance-none rounded-none border border-input bg-background checked:border-primary checked:bg-primary"
                />
                {COLUMN_LABELS[key]}
              </label>
            ))}
          </div>
          <Button variant="outline" size="sm" className="mt-3 h-7 rounded-none text-xs" onClick={() => setVisible(DEFAULT_VISIBLE)}>
            Reset columns
          </Button>
        </SheetContent>
      </Sheet>
      <ProductDealsDrawer
        slug={openSlug}
        deals={openSlug ? rows.filter((r) => r.product_slug === openSlug).sort((a, b) => Number(b.winner) - Number(a.winner) || Number(b.live) - Number(a.live) || Number(b.enabled) - Number(a.enabled) || a.priority - b.priority) : []}
        campaigns={campaigns}
        canWrite={canWrite}
        onClose={() => setOpenSlug(null)}
        onSave={save}
        onRemove={async (row) => {
          if (!(await confirmDialog({ title: "Remove from offer", message: `Remove ${row.product_name} from “${row.campaign_title}”?`, confirmLabel: "Remove", danger: true }))) return;
          try {
            await deleteOfferDeal(row.kind, row.deal_id);
            toast.success("Removed from the offer");
          } catch (e) {
            toast.error(e instanceof Error ? e.message : "Could not remove");
          }
          await load();
        }}
      />
      {moving ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setMoving(null)}>
          <div className="w-[380px] max-w-[92vw] space-y-3 border border-border bg-background p-4 shadow-lg" onClick={(e) => e.stopPropagation()}>
            <p className="text-sm font-medium">Move “{moving.product_name}”</p>
            <p className="text-xs text-muted-foreground">
              From “{moving.campaign_title}”. The price, priority, quantity and on/off go with it; the old offer no longer has this product.
            </p>
            <MoveTargetPicker row={moving} campaigns={campaigns} target={target} sectionId={targetSection} onChange={(t, s) => { setTarget(t); setTargetSection(s); }} />
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" className="rounded-none" onClick={() => setMoving(null)}>
                Cancel
              </Button>
              <Button
                size="sm"
                className="rounded-none"
                disabled={!target}
                onClick={async () => {
                  const [k, id] = target.split(":") as [DealKind, string];
                  const row = moving;
                  setMoving(null);
                  await save(row, { move_to_kind: k, move_to_campaign_id: id, ...(targetSection ? { move_to_section_id: targetSection } : {}) }, "Moved");
                }}
              >
                Move
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </MarketingListGrid>
  );
}
