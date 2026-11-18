"use client";

import { useState, type PointerEvent as ReactPointerEvent } from "react";
import { useUserScopedState } from "@/lib/hooks/use-user-scoped-state";

/**
 * The columns of the deals table inside the Offers / Happy Hour section drawer, with their starting and smallest width (px).
 * Each can be dragged wider or narrower by the handle on its right edge (double-click puts the starting width back) - like the
 * columns of the Products table. The widths are saved per admin.
 */
const COLUMNS = [
  { id: "img", label: "", width: 36, min: 36, resizable: false },
  { id: "product", label: "Product", width: 250, min: 120, resizable: true },
  { id: "model", label: "Model", width: 110, min: 64, resizable: true },
  { id: "section", label: "Section", width: 96, min: 60, resizable: true },
  { id: "regular", label: "Regular", width: 72, min: 56, resizable: true },
  { id: "qty", label: "Qty", width: 40, min: 30, resizable: true },
  { id: "stock", label: "Stock", width: 92, min: 72, resizable: true },
  { id: "offer", label: "Offer ৳", width: 96, min: 64, resizable: true },
  { id: "priority", label: "Priority", width: 68, min: 52, resizable: true },
  { id: "quantity", label: "Quantity", width: 100, min: 72, resizable: true },
  { id: "enabled", label: "Enabled", width: 66, min: 52, resizable: true },
  { id: "remove", label: "", width: 36, min: 36, resizable: false },
] as const;

type Column = (typeof COLUMNS)[number];

export function useDealTableColumns(showSection: boolean) {
  // key ends in ":columns", so (like the grids' column layouts) it also follows the admin to other browsers
  const [saved, setSaved] = useUserScopedState<Record<string, number>>("deals-table:columns", {});
  const [drag, setDrag] = useState<{ id: string; width: number } | null>(null);

  const cols: readonly Column[] = COLUMNS.filter((c) => showSection || c.id !== "section");
  const widthOf = (c: Column) => (drag?.id === c.id ? drag.width : Math.max(c.min, saved[c.id] ?? c.width));
  const total = cols.reduce((n, c) => n + widthOf(c), 0);

  const startDrag = (c: Column, e: ReactPointerEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const startX = e.clientX;
    const startW = widthOf(c);
    let last = startW;
    const move = (ev: PointerEvent) => {
      last = Math.max(c.min, Math.round(startW + ev.clientX - startX));
      setDrag({ id: c.id, width: last });
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      setSaved((s) => ({ ...s, [c.id]: last }));
      setDrag(null);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const resetWidth = (c: Column) =>
    setSaved((s) => {
      const rest = { ...s };
      delete rest[c.id];
      return rest;
    });

  const colgroup = (
    <colgroup>
      {cols.map((c) => (
        <col key={c.id} style={{ width: widthOf(c) }} />
      ))}
    </colgroup>
  );

  const header = (
    <tr className="bg-muted/40 text-left">
      {cols.map((c) => (
        <th key={c.id} className="relative px-1.5 py-1 font-medium">
          <span className="block truncate">{c.label}</span>
          {c.resizable ? (
            <span
              role="separator"
              aria-orientation="vertical"
              title="Drag to resize · double-click to reset"
              onPointerDown={(e) => startDrag(c, e)}
              onDoubleClick={() => resetWidth(c)}
              className="absolute right-0 top-0 z-10 h-full w-1.5 cursor-col-resize touch-none select-none hover:bg-primary/40"
            />
          ) : null}
        </th>
      ))}
    </tr>
  );

  // the table is exactly as wide as its columns (a scrollbar shows when that is more than the drawer), and fills the drawer when it is less
  return { colgroup, header, tableStyle: { width: total, minWidth: "100%" } as const };
}
