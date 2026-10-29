"use client";

import { useMemo } from "react";
import { ArrowDown, ArrowUp, Eye, EyeOff, RotateCcw, Trash2 } from "lucide-react";
import { AgainFormRow } from "@/components/again/again-form-sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CategoryCombobox } from "@/components/categories/category-combobox";
import { useCatalogCategories } from "@/lib/api/use-catalog-categories";
import { obj, type Json } from "@/lib/website/excellent-home";

type Row = Record<string, unknown>;
const text = (v: unknown) => (typeof v === "string" ? v : "");
const rowsOf = (v: unknown): Row[] => (Array.isArray(v) ? (v as Row[]).filter((r) => r && typeof r === "object") : []);

/**
 * "Shop by category" tiles: which categories, in what order, each with an
 * optional own title. Saved in `blocks.excellent.category_tiles.items`; with
 * nothing saved the storefront shows the first 16 top-level categories.
 */
export function LiveEditExcellentCategoryTiles({ ex, setEx }: { ex: Json; setEx: (patch: Json) => void }) {
  const { categories, loading } = useCatalogCategories({ channel: "catalog" });
  const ct = obj(ex.category_tiles);
  const saved = Array.isArray(ct.items) ? rowsOf(ct.items) : null;

  /** Active categories in tree order (a parent, then its children), with how deep each sits. */
  const activeCategories = useMemo(() => categories.filter((c) => c.active), [categories]);

  const ordered = useMemo(() => {
    const active = activeCategories;
    const out: { id: string; name: string; depth: number }[] = [];
    const walk = (parent: string | null, depth: number) => {
      active
        .filter((c) => (c.parentId ?? null) === parent)
        .sort((a, b) => a.sortOrder - b.sortOrder)
        .forEach((c) => {
          out.push({ id: c.id, name: c.name, depth });
          walk(c.id, depth + 1);
        });
    };
    walk(null, 0);
    return out;
  }, [activeCategories]);

  const automatic: Row[] = ordered
    .filter((c) => c.depth === 0)
    .slice(0, 16)
    .map((c) => ({ id: `tile-${c.id}`, category_id: c.id, title: "", hidden: false }));
  const rows = saved ?? automatic;

  const commit = (next: Row[]) => setEx({ category_tiles: { ...ct, items: next } });
  const set = (i: number, patch: Row) => commit(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const move = (i: number, dir: -1 | 1) => {
    const j = i + dir;
    if (j < 0 || j >= rows.length) return;
    const next = [...rows];
    [next[i], next[j]] = [next[j], next[i]];
    commit(next);
  };


  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Category tiles · {rows.length}</p>
        {saved && (
          <Button type="button" variant="ghost" size="sm" className="h-7 gap-1 text-[12px]" title="Go back to the first 16 top-level categories" onClick={() => setEx({ category_tiles: { ...ct, items: undefined } })}>
            <RotateCcw className="h-3 w-3" />
            Reset to automatic
          </Button>
        )}
      </div>
      {!saved && <p className="text-[11px] text-muted-foreground">Showing the first 16 top-level categories automatically. Change anything below to choose your own.</p>}
      {loading && <p className="text-[12px] text-muted-foreground">Loading categories…</p>}

      {rows.map((row, i) => {
        const current = text(row.category_id);
        const name = ordered.find((c) => c.id === current)?.name ?? "Category removed";
        return (
          <div key={text(row.id) || i} className="space-y-2 rounded-md border border-border bg-card p-2.5">
            <div className="flex items-center justify-between gap-2">
              <span className={`min-w-0 truncate text-[12px] font-medium ${row.hidden ? "text-muted-foreground line-through" : ""}`}>{name}</span>
              <div className="flex shrink-0 gap-0.5">
                <Button type="button" variant="ghost" size="icon" className="h-7 w-7" title="Move up" disabled={i === 0} onClick={() => move(i, -1)}>
                  <ArrowUp className="h-3.5 w-3.5" />
                </Button>
                <Button type="button" variant="ghost" size="icon" className="h-7 w-7" title="Move down" disabled={i === rows.length - 1} onClick={() => move(i, 1)}>
                  <ArrowDown className="h-3.5 w-3.5" />
                </Button>
                <Button type="button" variant="ghost" size="icon" className="h-7 w-7" title={row.hidden ? "Show" : "Hide"} onClick={() => set(i, { hidden: !row.hidden })}>
                  {row.hidden ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                </Button>
                <Button type="button" variant="ghost" size="icon" className="h-7 w-7" title="Remove" onClick={() => commit(rows.filter((_, j) => j !== i))}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
            <AgainFormRow label="Tile title">
              <Input value={text(row.title)} onChange={(e) => set(i, { title: e.target.value })} className="h-8 text-[13px]" placeholder={name} />
            </AgainFormRow>
            <AgainFormRow label="Category">
              <CategoryCombobox radio categories={activeCategories} value={current} onChange={(id) => set(i, { category_id: id })} placeholder="Select category" />
            </AgainFormRow>
          </div>
        );
      })}

      <CategoryCombobox
        radio
        categories={activeCategories}
        value=""
        onChange={(id) => id && commit([...rows, { id: `tile-${Date.now().toString(36)}`, category_id: id, title: "", hidden: false }])}
        placeholder="+ Add a category…"
      />
    </div>
  );
}
