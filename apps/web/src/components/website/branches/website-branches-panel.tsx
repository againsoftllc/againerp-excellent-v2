"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowDown, ArrowUp, Eye, EyeOff, Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { MediaLibraryModal } from "@/components/media/media-library-modal";
import { MediaPickTile } from "@/components/media/media-pick-tile";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { fetchBranches, saveBranches, type ApiBranch } from "@/lib/api/website-branches";
import { createCatalogMediaBatch, uploadCatalogMediaFiles, useCatalogMedia } from "@/lib/api/use-catalog-media";
import { useAdminCanWrite } from "@/lib/hooks/use-admin-can-write";

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

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex items-center gap-2">
        <p className="text-sm text-muted-foreground">
          These are also the store-pickup counters at checkout. A branch kept hidden is still offered for pickup but not listed on the Branches page or in the footer.
        </p>
        <Button asChild size="sm" variant="outline" className="ml-auto h-8 rounded-none">
          <a href="/website/live-edit/branches" target="_blank" rel="noopener noreferrer">Edit the page in Live Edit</a>
        </Button>
        {canWrite ? (
          <Button size="sm" className="h-8 rounded-none" disabled={saving} onClick={() => setEditing({ index: -1, branch: BLANK })}>
            <Plus className="mr-1 h-3.5 w-3.5" />
            New branch
          </Button>
        ) : null}
      </div>

      <div className="min-h-0 flex-1 overflow-auto border border-border">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-muted/60 text-left text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="w-10 px-3 py-2">#</th>
              <th className="px-3 py-2">Branch</th>
              <th className="px-3 py-2">Address</th>
              <th className="px-3 py-2">Phone</th>
              <th className="px-3 py-2">Hours</th>
              <th className="px-3 py-2">On site</th>
              <th className="w-36 px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {loading && rows.length === 0 ? (
              <tr><td colSpan={7} className="px-3 py-6 text-muted-foreground">Loading branches…</td></tr>
            ) : (
              rows.map((row, index) => (
                <tr key={row.key} className="border-t border-border hover:bg-muted/30">
                  <td className="px-3 py-2 text-muted-foreground">{index + 1}</td>
                  <td className="px-3 py-2 font-medium">
                    <button type="button" className="text-left hover:underline" onClick={() => setEditing({ index, branch: row })}>{row.label}</button>
                  </td>
                  <td className="max-w-[320px] truncate px-3 py-2 text-muted-foreground" title={row.address}>{row.address.replace(/\s*\n\s*/g, " ")}</td>
                  <td className="px-3 py-2 text-muted-foreground">{row.phone || "—"}</td>
                  <td className="px-3 py-2 text-muted-foreground">{row.hours || "Shop hours"}</td>
                  <td className="px-3 py-2">
                    <Badge variant={row.visible ? "default" : "secondary"} className="rounded-none">{row.visible ? "Listed" : "Hidden"}</Badge>
                  </td>
                  <td className="px-3 py-2">
                    {canWrite ? (
                      <div className="flex gap-0.5">
                        <Button type="button" variant="ghost" size="icon" className="h-7 w-7" title="Move up" disabled={saving || index === 0} onClick={() => move(index, -1)}>
                          <ArrowUp className="h-3.5 w-3.5" />
                        </Button>
                        <Button type="button" variant="ghost" size="icon" className="h-7 w-7" title="Move down" disabled={saving || index === rows.length - 1} onClick={() => move(index, 1)}>
                          <ArrowDown className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          title={row.visible ? "Hide from the Branches page" : "List on the Branches page"}
                          disabled={saving}
                          onClick={() => void persist(rows.map((r, i) => (i === index ? { ...r, visible: !r.visible } : r)))}
                        >
                          {row.visible ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
                        </Button>
                        <Button type="button" variant="ghost" size="icon" className="h-7 w-7" title="Edit" onClick={() => setEditing({ index, branch: row })}>
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-destructive"
                          title="Delete"
                          disabled={saving || rows.length <= 1}
                          onClick={() => {
                            if (!window.confirm(`Delete the branch "${row.label}"? It also stops being offered for Store Pickup.`)) return;
                            void persist(rows.filter((_, i) => i !== index), "Branch deleted");
                          }}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    ) : null}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

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
    </div>
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
