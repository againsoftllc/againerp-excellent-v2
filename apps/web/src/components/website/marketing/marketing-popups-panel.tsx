"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { MediaLibraryModal } from "@/components/media/media-library-modal";
import { MediaPickTile } from "@/components/media/media-pick-tile";
import { DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { NUMERIC_CELL, NUMERIC_HEADER } from "@/components/shared/again-list-grid";
import { MarketingListGrid, StatusBadge, type StatusTone } from "@/components/website/marketing/marketing-list-grid";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import {
  createMarketingPopup,
  deleteMarketingPopup,
  fetchMarketingPopups,
  updateMarketingPopup,
  type ApiMarketingPopup,
  type PopupKind,
  type PopupWriteInput,
} from "@/lib/api/marketing-popups";
import { useMarketingHappyHours } from "@/lib/api/use-marketing-happy-hours";
import { useMarketingOffers } from "@/lib/api/use-marketing-offers";
import { createCatalogMediaBatch, uploadCatalogMediaFiles, useCatalogMedia } from "@/lib/api/use-catalog-media";
import { useAdminCanWrite } from "@/lib/hooks/use-admin-can-write";
import { cn } from "@/lib/utils";

const KINDS: { id: PopupKind; title: string; hint: string }[] = [
  { id: "happy_hour", title: "Happy Hour", hint: "A Happy Hour with its countdown (Starts in / Ends in)." },
  { id: "offer", title: "Offer", hint: "One offer page, counting down to its end." },
  { id: "notice", title: "Notice", hint: "A heading and some text, with an optional button." },
  { id: "image", title: "Image + link", hint: "A picture that opens a link." },
];

const BLANK: PopupWriteInput = {
  name: "",
  kind: "notice",
  status: "draft",
  title: "",
  body: "",
  image_url: null,
  button_label: "",
  link_url: "",
  campaign_slug: "",
  starts_at: null,
  ends_at: null,
  delay_seconds: 5,
  frequency: "session",
  frequency_days: 1,
  pages: "home",
  paths: [],
  devices: "all",
  priority: 0,
};

/** The API keeps UTC without a zone; the picker works in the browser's local time. */
function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function fromLocalInput(local: string): string | null {
  if (!local) return null;
  const d = new Date(local);
  return Number.isNaN(d.getTime()) ? null : d.toISOString().replace("Z", "");
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-muted-foreground">{label}</label>
      {children}
      {hint ? <p className="text-[11px] text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

const POPUP_TONE: Record<string, StatusTone> = { active: "success", draft: "warning", disabled: "muted" };

export function MarketingPopupsPanel() {
  const canWrite = useAdminCanWrite();
  const [rows, setRows] = useState<ApiMarketingPopup[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<ApiMarketingPopup | "new" | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await fetchMarketingPopups());
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load popups");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) => (statusFilter === "all" || r.status === statusFilter) && (!q || r.name.toLowerCase().includes(q) || r.title.toLowerCase().includes(q)));
  }, [rows, search, statusFilter]);

  const editRef = useRef(setEditing);
  editRef.current = setEditing;

  const columns = useMemo<ColDef<ApiMarketingPopup>[]>(
    () => [
      { field: "name", headerName: "Name", flex: 1.4, minWidth: 160, cellClass: "font-medium" },
      { colId: "kind", headerName: "Type", width: 130, valueGetter: (p) => (p.data ? (KINDS.find((k) => k.id === p.data!.kind)?.title ?? p.data.kind) : "") },
      {
        colId: "shown",
        headerName: "Shown on",
        flex: 1,
        minWidth: 150,
        valueGetter: (p) => (p.data ? `${p.data.pages === "home" ? "Home page" : p.data.pages === "all" ? "All pages" : `${p.data.paths.length} page(s)`} · ${p.data.devices}` : ""),
      },
      {
        colId: "when",
        headerName: "When",
        flex: 1.2,
        minWidth: 190,
        valueGetter: (p) =>
          p.data
            ? `after ${p.data.delay_seconds}s · ${p.data.frequency === "session" ? "once a session" : p.data.frequency === "days" ? `every ${p.data.frequency_days} day(s)` : "every visit"}`
            : "",
      },
      { field: "priority", headerName: "Priority", width: 90, cellClass: NUMERIC_CELL, headerClass: NUMERIC_HEADER },
      {
        field: "status",
        headerName: "Status",
        width: 110,
        cellRenderer: (p: ICellRendererParams<ApiMarketingPopup>) =>
          p.data ? <StatusBadge label={p.data.status} tone={POPUP_TONE[p.data.status] ?? "muted"} /> : null,
      },
      { field: "updated_at", headerName: "Updated", width: 150 },
    ],
    [],
  );

  const rowMenu = useCallback(
    (row: ApiMarketingPopup) => (
      <>
        <DropdownMenuItem onClick={() => editRef.current(row)}>
          <Pencil className="mr-1.5 h-3 w-3" /> Edit
        </DropdownMenuItem>
        {canWrite ? (
          <DropdownMenuItem
            className="text-destructive"
            onClick={() => {
              if (!window.confirm(`Delete the popup "${row.name}"?`)) return;
              void deleteMarketingPopup(row.id)
                .then(() => refetch())
                .catch((err) => toast.error(err instanceof Error ? err.message : "Delete failed"));
            }}
          >
            <Trash2 className="mr-1.5 h-3 w-3" /> Delete
          </DropdownMenuItem>
        ) : null}
      </>
    ),
    [canWrite, refetch],
  );

  const filtersActive = search.trim() !== "" || statusFilter !== "all";

  return (
    <MarketingListGrid<ApiMarketingPopup>
      title="Popups"
      rows={filtered}
      loading={loading}
      columns={columns}
      rowMenu={rowMenu}
      onNew={canWrite ? () => setEditing("new") : undefined}
      onRefresh={() => void refetch()}
      onOpen={(row) => setEditing(row)}
      search={{ value: search, onChange: setSearch, placeholder: "Search name, title…" }}
      statusFilter={{
        value: statusFilter,
        onChange: setStatusFilter,
        label: "Status filter",
        options: [{ value: "all", label: "All statuses" }, { value: "active", label: "Active" }, { value: "draft", label: "Draft" }, { value: "disabled", label: "Disabled" }],
      }}
      filtersActive={filtersActive}
      onResetFilters={() => {
        setSearch("");
        setStatusFilter("all");
      }}
      emptyTitle="No popups yet"
      emptyHint="One popup at most is shown per page; the higher priority goes first. A popup of an ended Happy Hour or Offer is skipped."
      layoutKey="grid-layout:marketing-popups"
      mobile={
        <div className="divide-y divide-border">
          {filtered.map((row) => (
            <button key={row.id} type="button" className="flex w-full items-center justify-between gap-3 px-3 py-3 text-left" onClick={() => setEditing(row)}>
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium">{row.name}</span>
                <span className="block truncate text-xs text-muted-foreground">{KINDS.find((k) => k.id === row.kind)?.title ?? row.kind}</span>
              </span>
              <StatusBadge label={row.status} tone={POPUP_TONE[row.status] ?? "muted"} />
            </button>
          ))}
        </div>
      }
    >
      <PopupFormSheet
        popup={editing}
        onClose={() => setEditing(null)}
        onSaved={async () => {
          setEditing(null);
          await refetch();
        }}
      />
    </MarketingListGrid>
  );
}

function PopupFormSheet({ popup, onClose, onSaved }: { popup: ApiMarketingPopup | "new" | null; onClose: () => void; onSaved: () => Promise<void> }) {
  const open = popup !== null;
  const { campaigns } = useMarketingHappyHours();
  const { offers } = useMarketingOffers();
  const { items: mediaItems, refetch: refetchMedia } = useCatalogMedia();
  const [form, setForm] = useState<PopupWriteInput>(BLANK);
  const [pathsText, setPathsText] = useState("");
  const [saving, setSaving] = useState(false);
  const [pickingImage, setPickingImage] = useState(false);

  // Fill the form when the sheet opens for a record (while rendering, so it never shows the previous one first).
  const [loadedFor, setLoadedFor] = useState<typeof popup>(null);
  if (loadedFor !== popup) {
    setLoadedFor(popup);
    if (popup && popup !== "new") {
      const { id: _id, created_at: _c, updated_at: _u, ...rest } = popup;
      void _id; void _c; void _u;
      setForm({ ...rest, starts_at: rest.starts_at, ends_at: rest.ends_at });
      setPathsText(rest.paths.join("\n"));
    } else if (popup === "new") {
      setForm(BLANK);
      setPathsText("");
    }
  }

  const set = (patch: Partial<PopupWriteInput>) => setForm((f) => ({ ...f, ...patch }));
  const isCampaign = form.kind === "happy_hour" || form.kind === "offer";
  const campaignOptions =
    form.kind === "happy_hour"
      ? campaigns.filter((c) => c.status !== "disabled" && c.status !== "draft").map((c) => ({ slug: c.slug, label: `${c.title} · ${c.status}` }))
      : offers.filter((o) => o.status !== "disabled" && o.status !== "draft").map((o) => ({ slug: o.slug, label: `${o.title} · ${o.status}` }));

  const save = async () => {
    if (!form.name.trim()) {
      toast.error("Give the popup a name");
      return;
    }
    if (isCampaign && !form.campaign_slug) {
      toast.error(form.kind === "happy_hour" ? "Pick the Happy Hour" : "Pick the offer");
      return;
    }
    if (form.kind === "image" && !form.image_url) {
      toast.error("Pick a picture");
      return;
    }
    const payload: PopupWriteInput = {
      ...form,
      name: form.name.trim(),
      campaign_slug: isCampaign ? form.campaign_slug : "",
      paths: form.pages === "paths" ? pathsText.split("\n").map((p) => p.trim()).filter(Boolean) : [],
    };
    setSaving(true);
    try {
      if (popup === "new") await createMarketingPopup(payload);
      else if (popup) await updateMarketingPopup(popup.id, payload);
      toast.success("Popup saved");
      await onSaved();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={(next) => !next && onClose()}>
      <SheetContent side="right" className="flex w-full max-w-xl flex-col gap-0 p-0 sm:max-w-xl" aria-describedby={undefined}>
        <SheetHeader className="flex shrink-0 flex-row items-center justify-between border-b border-input px-5 py-3">
          <SheetTitle className="text-base">{popup === "new" ? "New popup" : "Edit popup"}</SheetTitle>
          <Button size="sm" className="rounded-none" disabled={saving} onClick={() => void save()}>
            {saving ? "Saving…" : "Save"}
          </Button>
        </SheetHeader>

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-4">
          <Field label="Name (only you see it)">
            <Input className="rounded-none" value={form.name} onChange={(e) => set({ name: e.target.value })} placeholder="e.g. Happy Hour homepage popup" />
          </Field>

          <div className="space-y-2">
            <p className="text-xs font-medium text-muted-foreground">What it shows</p>
            <div className="grid grid-cols-2 gap-2">
              {KINDS.map((k) => (
                <button
                  key={k.id}
                  type="button"
                  aria-pressed={form.kind === k.id}
                  onClick={() => set({ kind: k.id, campaign_slug: "" })}
                  className={cn("border px-2.5 py-2 text-left transition-colors", form.kind === k.id ? "border-primary bg-primary/5" : "border-border hover:bg-muted/40")}
                >
                  <span className="block text-[13px] font-medium">{k.title}</span>
                  <span className="block text-[11px] text-muted-foreground">{k.hint}</span>
                </button>
              ))}
            </div>
          </div>

          {isCampaign ? (
            <Field label={form.kind === "happy_hour" ? "Happy Hour" : "Offer"} hint="Its name, countdown and link come from the campaign. Empty fields below use them; fill a field to override it.">
              <Select className="h-9 w-full rounded-none" value={form.campaign_slug} onChange={(e) => set({ campaign_slug: e.target.value })}>
                <option value="">{form.kind === "happy_hour" ? "Select a Happy Hour" : "Select an offer"}</option>
                {campaignOptions.map((c) => (
                  <option key={c.slug} value={c.slug}>{c.label}</option>
                ))}
              </Select>
            </Field>
          ) : null}

          <Field label="Heading">
            <Input className="rounded-none" value={form.title} onChange={(e) => set({ title: e.target.value })} />
          </Field>
          <Field label="Text">
            <Textarea className="min-h-[80px] rounded-none" value={form.body} onChange={(e) => set({ body: e.target.value })} />
          </Field>

          <Field label="Picture">
            <MediaPickTile url={form.image_url ?? ""} alt="Popup picture" onChange={(next) => set({ image_url: next || null })} onPick={() => { void refetchMedia(); setPickingImage(true); }} />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Button text">
              <Input className="rounded-none" value={form.button_label} onChange={(e) => set({ button_label: e.target.value })} placeholder={isCampaign ? "View deals" : "Shop now"} />
            </Field>
            <Field label="Link" hint={isCampaign ? "Empty = the campaign's page." : undefined}>
              <Input className="rounded-none" value={form.link_url} onChange={(e) => set({ link_url: e.target.value })} placeholder="/offers" />
            </Field>
          </div>

          <div className="space-y-3 border border-border p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">When and where</p>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Shown on">
                <Select className="h-9 w-full rounded-none" value={form.pages} onChange={(e) => set({ pages: e.target.value as PopupWriteInput["pages"] })}>
                  <option value="home">Home page only</option>
                  <option value="all">All pages</option>
                  <option value="paths">Chosen pages</option>
                </Select>
              </Field>
              <Field label="Devices">
                <Select className="h-9 w-full rounded-none" value={form.devices} onChange={(e) => set({ devices: e.target.value as PopupWriteInput["devices"] })}>
                  <option value="all">Desktop and mobile</option>
                  <option value="desktop">Desktop only</option>
                  <option value="mobile">Mobile only</option>
                </Select>
              </Field>
            </div>
            {form.pages === "paths" ? (
              <Field label="Pages (one path per line)" hint="e.g. /laptop or /happy-hour">
                <Textarea className="min-h-[70px] rounded-none" value={pathsText} onChange={(e) => setPathsText(e.target.value)} placeholder={"/laptop\n/monitor"} />
              </Field>
            ) : null}
            <div className="grid grid-cols-2 gap-3">
              <Field label="Show after (seconds)">
                <Input className="rounded-none" type="number" min={0} max={600} value={form.delay_seconds} onChange={(e) => set({ delay_seconds: Math.max(0, Number(e.target.value) || 0) })} />
              </Field>
              <Field label="How often">
                <Select className="h-9 w-full rounded-none" value={form.frequency} onChange={(e) => set({ frequency: e.target.value as PopupWriteInput["frequency"] })}>
                  <option value="session">Once a session</option>
                  <option value="days">Once every N days</option>
                  <option value="always">Every visit to the page</option>
                </Select>
              </Field>
            </div>
            {form.frequency === "days" ? (
              <Field label="Days between shows">
                <Input className="w-28 rounded-none" type="number" min={1} max={365} value={form.frequency_days} onChange={(e) => set({ frequency_days: Math.max(1, Number(e.target.value) || 1) })} />
              </Field>
            ) : null}
            <div className="grid grid-cols-2 gap-3">
              <Field label="Starts" hint="Empty = right away.">
                <Input className="rounded-none" type="datetime-local" value={toLocalInput(form.starts_at)} onChange={(e) => set({ starts_at: fromLocalInput(e.target.value) })} />
              </Field>
              <Field label="Ends" hint="Empty = no end.">
                <Input className="rounded-none" type="datetime-local" value={toLocalInput(form.ends_at)} onChange={(e) => set({ ends_at: fromLocalInput(e.target.value) })} />
              </Field>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Status" hint="Only Active popups are shown.">
              <Select className="h-9 w-full rounded-none" value={form.status} onChange={(e) => set({ status: e.target.value as PopupWriteInput["status"] })}>
                <option value="draft">Draft</option>
                <option value="active">Active</option>
                <option value="disabled">Disabled</option>
              </Select>
            </Field>
            <Field label="Priority" hint="Higher shows first.">
              <Input className="rounded-none" type="number" value={form.priority} onChange={(e) => set({ priority: Number(e.target.value) || 0 })} />
            </Field>
          </div>
        </div>

        <MediaLibraryModal
          open={pickingImage}
          onOpenChange={(next) => {
            setPickingImage(next);
            if (next) void refetchMedia();
          }}
          items={mediaItems}
          mode="single"
          title="Popup picture"
          accept={["image"]}
          onSelect={(items) => {
            const url = items.find((item) => item.type === "image")?.url;
            if (url) set({ image_url: url });
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
