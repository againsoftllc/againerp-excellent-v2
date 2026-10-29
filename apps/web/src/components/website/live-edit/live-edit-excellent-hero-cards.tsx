"use client";

import { useState } from "react";
import { DndContext, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, arrayMove, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { ChevronDown, Copy, Eye, EyeOff, GripVertical, ImageIcon, Plus, Trash2 } from "lucide-react";
import { AgainFormRow } from "@/components/again/again-form-sheet";
import { MediaLibraryModal } from "@/components/media/media-library-modal";
import { MediaPickTile } from "@/components/media/media-pick-tile";
import { Field, previewUrl } from "@/components/website/live-edit/live-edit-excellent-drawer";
import { Button } from "@/components/ui/button";
import { createCatalogMediaBatch, uploadCatalogMediaFiles, useCatalogMedia } from "@/lib/api/use-catalog-media";
import { publicMediaUrl } from "@/lib/media/public-media-url";
import { cn } from "@/lib/utils";
import { type Json } from "@/lib/website/excellent-home";

type Row = Record<string, unknown>;
const text = (v: unknown) => (typeof v === "string" ? v : "");

type CustomField = { key: string; label: string; multiline?: boolean; /** A small picture tile instead of a text box. */ image?: boolean };

type Props = {
  ex: Json;
  setEx: (patch: Json) => void;
  /** Which list in `blocks.excellent`: "promo_cards" (hero side cards) or "banners" (promo banners). */
  listKey: string;
  /** "Card" / "Banner". */
  noun: string;
  /** The fields of a custom card / banner (words, button, link, and any small picture). */
  customFields: CustomField[];
  /** Key of the picture that fills the whole card in "Banner image" mode. */
  fullImageKey: string;
  /** A new row's values. */
  blank: Row;
  /** What size picture fits ("about 820 × 445"). */
  sizeHint: string;
  /** Note under the list. */
  note: React.ReactNode;
};

function Kind({ active, label, onSelect }: { active: boolean; label: string; onSelect: () => void }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={active}
      className={cn("flex flex-1 items-center justify-center gap-2 rounded-md border px-2 py-1.5 text-[12px] font-medium transition-colors", active ? "border-[#00a09d] bg-[#00a09d]/5" : "border-border text-muted-foreground hover:bg-muted/40")}
    >
      <span className={cn("flex h-3.5 w-3.5 items-center justify-center rounded-full border", active ? "border-[#00a09d]" : "border-border")} aria-hidden>
        {active ? <span className="h-1.5 w-1.5 rounded-full bg-[#00a09d]" /> : null}
      </span>
      {label}
    </button>
  );
}

/** One collapsed row (grip, picture, name, open / duplicate / hide / remove); the fields show when it is opened. */
export function SortableRow({
  id,
  open,
  thumb,
  title,
  subtitle,
  hidden,
  onToggle,
  onDuplicate,
  onHide,
  onRemove,
  children,
}: {
  id: string;
  open: boolean;
  /** The row's picture; leave out for a row with no picture. */
  thumb?: string;
  title: string;
  subtitle: string;
  hidden: boolean;
  onToggle: () => void;
  onDuplicate: () => void;
  onHide: () => void;
  onRemove: () => void;
  children: React.ReactNode;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn("overflow-hidden rounded-md border border-border bg-card", isDragging && "z-10 shadow-md", hidden && "opacity-60")}
    >
      <div className="flex items-center gap-1.5 p-1.5">
        <button type="button" className="inline-flex h-8 w-5 shrink-0 cursor-grab items-center justify-center text-muted-foreground hover:text-foreground" aria-label="Drag to reorder" {...attributes} {...listeners}>
          <GripVertical className="h-4 w-4" />
        </button>
        <button type="button" onClick={onToggle} aria-expanded={open} className="flex min-w-0 flex-1 items-center gap-2.5 text-left">
          {thumb !== undefined ? (
            <span className="flex h-10 w-16 shrink-0 items-center justify-center overflow-hidden rounded border border-border bg-muted/40">
              {thumb ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={thumb} alt="" className="h-full w-full object-cover" />
              ) : (
                <ImageIcon className="h-4 w-4 text-muted-foreground" />
              )}
            </span>
          ) : null}
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[13px] font-medium">{title}</span>
            <span className="block truncate text-[11px] text-muted-foreground">{subtitle}</span>
          </span>
          <ChevronDown className={cn("h-4 w-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
        </button>
        <div className="flex shrink-0 gap-0.5">
          <Button type="button" variant="ghost" size="icon" className="h-7 w-7" title="Duplicate" onClick={onDuplicate}>
            <Copy className="h-3.5 w-3.5" />
          </Button>
          <Button type="button" variant="ghost" size="icon" className="h-7 w-7" title={hidden ? "Show" : "Hide"} onClick={onHide}>
            {hidden ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
          </Button>
          <Button type="button" variant="ghost" size="icon" className="h-7 w-7" title="Remove" onClick={onRemove}>
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
      {open ? <div className="space-y-2.5 border-t border-border p-2.5">{children}</div> : null}
    </div>
  );
}

/**
 * A list of cards / banners — collapsed rows you click to open, drag to reorder —
 * where each one is either a **custom** one (words, button, link, maybe a small
 * picture) or a **banner image** (one picture that fills it and links somewhere).
 * `kind` on each row is "card" or "image".
 */
export function LiveEditExcellentKindCards({ ex, setEx, listKey, noun, customFields, fullImageKey, blank, sizeHint, note }: Props) {
  const rows: Row[] = Array.isArray(ex[listKey]) ? (ex[listKey] as Row[]).filter((r) => r && typeof r === "object") : [];
  const ids = rows.map((r, i) => text(r.id) || `${noun.toLowerCase()}-${i}`);
  const [openId, setOpenId] = useState<string | null>(null);
  const [pick, setPick] = useState<{ index: number; key: string } | null>(null);
  const { items: mediaItems, refetch: refetchMedia } = useCatalogMedia();
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  /** Rows saved before they had ids get one now, so they can be dragged. */
  const withIds = (list: Row[]) => list.map((r, i) => (text(r.id) ? r : { ...r, id: ids[i] ?? `${noun.toLowerCase()}-${Date.now().toString(36)}-${i}` }));
  const commit = (next: Row[]) => setEx({ [listKey]: next });
  const set = (i: number, patch: Row) => commit(withIds(rows).map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const openPicker = (index: number, key: string) => {
    void refetchMedia();
    setPick({ index, key });
  };

  const onDragEnd = (e: DragEndEvent) => {
    if (!e.over || e.active.id === e.over.id) return;
    const from = ids.indexOf(String(e.active.id));
    const to = ids.indexOf(String(e.over.id));
    if (from < 0 || to < 0) return;
    commit(arrayMove(withIds(rows), from, to));
  };

  const duplicate = (i: number) => {
    const list = withIds(rows);
    const copy = { ...list[i], id: `${noun.toLowerCase()}-${Date.now().toString(36)}` };
    commit([...list.slice(0, i + 1), copy, ...list.slice(i + 1)]);
    setOpenId(String(copy.id));
  };

  return (
    <div className="space-y-3">
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={ids} strategy={verticalListSortingStrategy}>
          <div className="space-y-2">
            {rows.map((row, i) => {
              const image = row.kind === "image";
              const smallKey = customFields.find((f) => f.image)?.key;
              const thumbSrc = image ? text(row[fullImageKey]) : smallKey ? text(row[smallKey]) : "";
              return (
                <SortableRow
                  key={ids[i]}
                  id={ids[i]}
                  open={openId === ids[i]}
                  thumb={thumbSrc ? publicMediaUrl(previewUrl(thumbSrc)) : ""}
                  title={`${noun} ${i + 1}${i > 1 ? " · not shown" : ""}`}
                  subtitle={image ? text(row.alt) || text(row.href) || "Banner image" : text(row.title) || text(row.href) || "Custom"}
                  hidden={Boolean(row.hidden)}
                  onToggle={() => setOpenId((cur) => (cur === ids[i] ? null : ids[i]))}
                  onDuplicate={() => duplicate(i)}
                  onHide={() => set(i, { hidden: !row.hidden })}
                  onRemove={() => commit(rows.filter((_, j) => j !== i))}
                >
                  <div className="flex gap-2">
                    <Kind active={!image} label={`Custom ${noun.toLowerCase()}`} onSelect={() => set(i, { kind: "card" })} />
                    <Kind active={image} label="Banner image" onSelect={() => set(i, { kind: "image" })} />
                  </div>

                  {image ? (
                    <>
                      <AgainFormRow label="Image" help={`Fills the whole ${noun.toLowerCase()}. ${sizeHint}`}>
                        <MediaPickTile className="w-full" url={previewUrl(text(row[fullImageKey]))} alt="Banner" onChange={(next) => set(i, { [fullImageKey]: next })} onPick={() => openPicker(i, fullImageKey)} />
                      </AgainFormRow>
                      <Field label="Link" value={row.href} onChange={(v) => set(i, { href: v })} placeholder="/offers" />
                      <Field label="Description" value={row.alt} onChange={(v) => set(i, { alt: v })} placeholder="For screen readers" />
                    </>
                  ) : (
                    customFields.map((f) =>
                      f.image ? (
                        <AgainFormRow key={f.key} label={f.label}>
                          <MediaPickTile url={previewUrl(text(row[f.key]))} alt={f.label} onChange={(next) => set(i, { [f.key]: next })} onPick={() => openPicker(i, f.key)} />
                        </AgainFormRow>
                      ) : (
                        <Field key={f.key} label={f.label} multiline={f.multiline} value={row[f.key]} onChange={(v) => set(i, { [f.key]: v })} />
                      )
                    )
                  )}
                </SortableRow>
              );
            })}
          </div>
        </SortableContext>
      </DndContext>

      <Button
        type="button"
        variant="outline"
        size="sm"
        className="h-8"
        onClick={() => {
          const id = `${noun.toLowerCase()}-${Date.now().toString(36)}`;
          commit([...withIds(rows), { ...blank, id }]);
          setOpenId(id);
        }}
      >
        <Plus className="mr-1 h-3.5 w-3.5" />
        Add {noun.toLowerCase()}
      </Button>
      <p className="text-[11px] text-muted-foreground">{note}</p>

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
