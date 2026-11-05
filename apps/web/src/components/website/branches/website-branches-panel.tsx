"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { ArrowDown, ArrowUp, ExternalLink, Eye, EyeOff, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { MediaLibraryModal } from "@/components/media/media-library-modal";
import { MediaPickTile } from "@/components/media/media-pick-tile";
import { DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { NUMERIC_CELL, NUMERIC_HEADER } from "@/components/shared/again-list-grid";
import { MarketingListGrid, StatusBadge } from "@/components/website/marketing/marketing-list-grid";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { fetchBranches, saveBranches, type ApiBranch } from "@/lib/api/website-branches";
import { createCatalogMediaBatch, uploadCatalogMediaFiles, useCatalogMedia } from "@/lib/api/use-catalog-media";
import { useAdminCanWrite } from "@/lib/hooks/use-admin-can-write";

type BranchRow = ApiBranch & { id: string; index: number };

const BLANK: ApiBranch = { key: "", label: "", address: "", phone: "", map_url: "", image: "", hours: "", whatsapp: "", email: "", visible: true };

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-muted-foreground">{label}</label>
      {children}
      {hint ? <p className="text-[11px] text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

/**
 * Website → Branches. The branches are the store-pickup counters (the same list checkout offers for Store Pickup), so
 * a branch is entered once and shows on the Branches page, in the footer and at checkout.
 */
export function WebsiteBranchesPanel() {
  const canWrite = useAdminCanWrite();
  const [rows, setRows] = useState<ApiBranch[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<{ index: number; branch: ApiBranch } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await fetchBranches());
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load branches");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  /** Every change is saved right away: the list is small and the storefront should never lag the admin. */
  const persist = async (next: ApiBranch[], done = "Branches saved") => {
    setSaving(true);
    try {
      setRows(await saveBranches(next));
      toast.success(done);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Save failed");
      await load();
    } finally {
      setSaving(false);
    }
  };

  const move = (index: number, dir: -1 | 1) => {
    const to = index + dir;
    if (to < 0 || to >= rows.length) return;
    const next = [...rows];
    [next[index], next[to]] = [next[to], next[index]];
    void persist(next, "Order saved");
  };

  // the table's menus are built once; they always read the latest list and actions through this
  const live = useRef({ rows, saving, persist, move, edit: setEditing });
  live.current = { rows, saving, persist, move, edit: setEditing };

  const gridRows = useMemo<BranchRow[]>(() => rows.map((r, index) => ({ ...r, id: r.key, index })), [rows]);

  const [search, setSearch] = useState("");
  const [onSite, setOnSite] = useState("all");
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return gridRows.filter((r) => {
      if (onSite === "listed" && !r.visible) return false;
      if (onSite === "hidden" && r.visible) return false;
      return !q || r.label.toLowerCase().includes(q) || r.address.toLowerCase().includes(q) || r.phone.toLowerCase().includes(q);
    });
  }, [gridRows, search, onSite]);

  const columns = useMemo<ColDef<BranchRow>[]>(
    () => [
      { colId: "no", headerName: "#", width: 56, valueGetter: (p) => (p.data ? p.data.index + 1 : ""), cellClass: NUMERIC_CELL, headerClass: NUMERIC_HEADER, sortable: false },
      { field: "label", headerName: "Branch", flex: 1, minWidth: 150, cellClass: "font-medium" },
      { field: "address", headerName: "Address", flex: 2, minWidth: 220, valueGetter: (p) => (p.data ? p.data.address.replace(/\s*\n\s*/g, " ") : "") },
      { field: "phone", headerName: "Phone", width: 140, valueFormatter: (p) => p.value || "—" },
      { field: "hours", headerName: "Hours", width: 150, valueFormatter: (p) => p.value || "Shop hours" },
      {
        field: "visible",
        headerName: "On site",
        width: 100,
        cellRenderer: (p: ICellRendererParams<BranchRow>) =>
          p.data ? <StatusBadge label={p.data.visible ? "Listed" : "Hidden"} tone={p.data.visible ? "success" : "muted"} /> : null,
      },
    ],
    [],
  );

  const rowMenu = useCallback(
    (row: BranchRow) => {
      const { rows: list, saving: busy } = live.current;
      const index = list.findIndex((r) => r.key === row.key);
      return (
        <>
          <DropdownMenuItem onClick={() => live.current.edit({ index, branch: list[index] })}>
            <Pencil className="mr-1.5 h-3 w-3" /> {canWrite ? "Edit" : "View"}
          </DropdownMenuItem>
          {canWrite ? (
            <>
              <DropdownMenuItem
                disabled={busy}
                onClick={() => void live.current.persist(list.map((r) => (r.key === row.key ? { ...r, visible: !r.visible } : r)))}
              >
                {row.visible ? <EyeOff className="mr-1.5 h-3 w-3" /> : <Eye className="mr-1.5 h-3 w-3" />}
                {row.visible ? "Hide from the Branches page" : "List on the Branches page"}
              </DropdownMenuItem>
              <DropdownMenuItem disabled={busy || index <= 0} onClick={() => live.current.move(index, -1)}>
                <ArrowUp className="mr-1.5 h-3 w-3" /> Move up
              </DropdownMenuItem>
              <DropdownMenuItem disabled={busy || index >= list.length - 1} onClick={() => live.current.move(index, 1)}>
                <ArrowDown className="mr-1.5 h-3 w-3" /> Move down
              </DropdownMenuItem>
              <DropdownMenuItem
                className="text-destructive"
                disabled={busy || list.length <= 1}
                onClick={() => {
                  if (!window.confirm(`Delete the branch "${row.label}"? It also stops being offered for Store Pickup.`)) return;
                  void live.current.persist(list.filter((r) => r.key !== row.key), "Branch deleted");
                }}
              >
                <Trash2 className="mr-1.5 h-3 w-3" /> Delete
              </DropdownMenuItem>
            </>
          ) : null}
        </>
      );
    },
    [canWrite],
  );

  const filtersActive = search.trim() !== "" || onSite !== "all";

  return (
    <MarketingListGrid<BranchRow>
      title="Branches"
      rows={filtered}
      loading={loading}
      columns={columns}
      rowMenu={rowMenu}
      onNew={canWrite ? () => setEditing({ index: -1, branch: BLANK }) : undefined}
      onRefresh={() => void load()}
      onOpen={(row) => {
        const list = live.current.rows;
        const index = list.findIndex((r) => r.key === row.key);
        if (index >= 0) setEditing({ index, branch: list[index] });
      }}
      search={{ value: search, onChange: setSearch, placeholder: "Search branch, address, phone…" }}
      statusFilter={{
        value: onSite,
        onChange: setOnSite,
        label: "On site filter",
        options: [{ value: "all", label: "All branches" }, { value: "listed", label: "Listed" }, { value: "hidden", label: "Hidden" }],
      }}
      filtersActive={filtersActive}
      onResetFilters={() => {
        setSearch("");
        setOnSite("all");
      }}
      emptyTitle="No branches yet"
      emptyHint="Add the first shop with New."
      layoutKey="grid-layout:website-branches"
      note="These are also the store-pickup counters at checkout. A branch kept hidden is still offered for pickup but not listed on the Branches page or in the footer."
      settingsMenu={
        <DropdownMenuItem asChild>
          <a href="/website/live-edit/branches" target="_blank" rel="noopener noreferrer">
            <ExternalLink className="mr-1.5 h-3 w-3" /> Edit the page in Live Edit
          </a>
        </DropdownMenuItem>
      }
      mobile={
        <div className="divide-y divide-border">
          {filtered.map((row) => (
            <button
              key={row.key}
              type="button"
              className="flex w-full items-center justify-between gap-3 px-3 py-3 text-left"
              onClick={() => setEditing({ index: row.index, branch: rows[row.index] })}
            >
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium">{row.label}</span>
                <span className="block truncate text-xs text-muted-foreground">{row.phone || row.address}</span>
              </span>
              <StatusBadge label={row.visible ? "Listed" : "Hidden"} tone={row.visible ? "success" : "muted"} />
            </button>
          ))}
        </div>
      }
    >
      <BranchFormSheet
        editing={editing}
        saving={saving}
        onClose={() => setEditing(null)}
        onSave={async (branch) => {
          if (!editing) return;
          const next = editing.index < 0 ? [...rows, branch] : rows.map((r, i) => (i === editing.index ? branch : r));
          await persist(next);
          setEditing(null);
        }}
      />
    </MarketingListGrid>
  );
}

function BranchFormSheet({
  editing,
  saving,
  onClose,
  onSave,
}: {
  editing: { index: number; branch: ApiBranch } | null;
  saving: boolean;
  onClose: () => void;
  onSave: (branch: ApiBranch) => Promise<void>;
}) {
  const { items: mediaItems, refetch: refetchMedia } = useCatalogMedia();
  const [form, setForm] = useState<ApiBranch>(BLANK);
  const [picking, setPicking] = useState(false);

  // Fill the form when the sheet opens (while rendering, so it never shows the previous branch first).
  const [loadedFor, setLoadedFor] = useState<typeof editing>(null);
  if (loadedFor !== editing) {
    setLoadedFor(editing);
    if (editing) setForm(editing.branch);
  }

  const set = (patch: Partial<ApiBranch>) => setForm((f) => ({ ...f, ...patch }));
  // The map is a place name (text) or a link; the saved value tells which.
  const [mapMode, setMapMode] = useState<"text" | "link">("text");
  const [modeFor, setModeFor] = useState<typeof editing>(null);
  if (modeFor !== editing) {
    setModeFor(editing);
    if (editing) setMapMode(/^https?:\/\//i.test(editing.branch.map_url) ? "link" : "text");
  }
  const pickMapMode = (mode: "text" | "link") => {
    if (mode === mapMode) return;
    setMapMode(mode);
    set({ map_url: "" });
  };

  return (
    <Sheet open={editing !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="flex w-full max-w-lg flex-col gap-0 p-0 sm:max-w-lg" aria-describedby={undefined}>
        <SheetHeader className="flex shrink-0 flex-row items-center justify-between border-b border-input px-5 py-3">
          <SheetTitle className="text-base">{editing && editing.index < 0 ? "New branch" : "Edit branch"}</SheetTitle>
          <Button
            size="sm"
            className="rounded-none"
            disabled={saving}
            onClick={() => {
              if (!form.label.trim()) {
                toast.error("Give the branch a name");
                return;
              }
              void onSave(form);
            }}
          >
            {saving ? "Saving…" : "Save"}
          </Button>
        </SheetHeader>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
          <Field label="Branch name">
            <Input className="rounded-none" value={form.label} onChange={(e) => set({ label: e.target.value })} placeholder="e.g. Mirpur Branch" />
          </Field>
          <Field label="Address" hint="One line per row of the address.">
            <Textarea className="min-h-[80px] rounded-none" value={form.address} onChange={(e) => set({ address: e.target.value })} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Phone">
              <Input className="rounded-none" value={form.phone} onChange={(e) => set({ phone: e.target.value })} />
            </Field>
            <Field label="WhatsApp">
              <Input className="rounded-none" value={form.whatsapp} onChange={(e) => set({ whatsapp: e.target.value })} placeholder="01XXXXXXXXX" />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Email">
              <Input className="rounded-none" value={form.email} onChange={(e) => set({ email: e.target.value })} />
            </Field>
            <Field label="Opening hours" hint="Empty = the shop's hours.">
              <Input className="rounded-none" value={form.hours} onChange={(e) => set({ hours: e.target.value })} placeholder="Sat–Thu 10 AM – 9 PM" />
            </Field>
          </div>
          <div className="space-y-2">
            <p className="text-xs font-medium text-muted-foreground">Map</p>
            <div className="inline-flex border border-border">
              {(["text", "link"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  aria-pressed={mapMode === mode}
                  onClick={() => pickMapMode(mode)}
                  className={`px-3 py-1.5 text-xs ${mapMode === mode ? "bg-primary text-primary-foreground" : "hover:bg-muted/50"}`}
                >
                  {mode === "text" ? "Place name" : "Google Maps link"}
                </button>
              ))}
            </div>
            {mapMode === "text" ? (
              <Field label="" hint="A place or address to search for, e.g. BCS Computer City IDB Bhaban Agargaon. Empty = the branch address.">
                <Input className="rounded-none" value={form.map_url} onChange={(e) => set({ map_url: e.target.value })} placeholder="BCS Computer City IDB Bhaban Agargaon Dhaka" />
              </Field>
            ) : (
              <Field
                label=""
                hint="The Directions button opens this link. The map inside the card shows this link only if it is an embed link (Google Maps → Share → Embed a map → copy the src=... link); any other link - e.g. maps.app.goo.gl - keeps the card map on the branch address."
              >
                <Input className="rounded-none" value={form.map_url} onChange={(e) => set({ map_url: e.target.value })} placeholder="https://maps.app.goo.gl/..." />
              </Field>
            )}
          </div>
          <Field label="Photo (optional)">
            <MediaPickTile url={form.image} alt="Branch photo" onChange={(next) => set({ image: next || "" })} onPick={() => { void refetchMedia(); setPicking(true); }} />
          </Field>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.visible} onChange={(e) => set({ visible: e.target.checked })} />
            List on the Branches page and in the footer
          </label>
        </div>

        <MediaLibraryModal
          open={picking}
          onOpenChange={(next) => {
            setPicking(next);
            if (next) void refetchMedia();
          }}
          items={mediaItems}
          mode="single"
          title="Branch photo"
          accept={["image"]}
          onSelect={(items) => {
            const url = items.find((item) => item.type === "image")?.url;
            if (url) set({ image: url });
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
      </SheetContent>
    </Sheet>
  );
}
