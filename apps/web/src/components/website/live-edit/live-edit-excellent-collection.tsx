"use client";

import { useMemo } from "react";
import { AgainFormRow } from "@/components/again/again-form-sheet";
import { CategoryCombobox } from "@/components/categories/category-combobox";
import { ProductMultiPicker } from "@/components/website/live-edit/live-edit-featured-drawer";
import { Input } from "@/components/ui/input";
import { useCatalogCategories } from "@/lib/api/use-catalog-categories";
import { cn } from "@/lib/utils";
import { obj, type Json } from "@/lib/website/excellent-home";

type Row = Record<string, unknown>;
const text = (v: unknown) => (typeof v === "string" ? v : "");

function Option({ active, title, hint, onSelect }: { active: boolean; title: string; hint: string; onSelect: () => void }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn("flex w-full items-start gap-2.5 rounded-md border px-2.5 py-2 text-left transition-colors", active ? "border-[#00a09d] bg-[#00a09d]/5" : "border-border hover:bg-muted/40")}
      aria-pressed={active}
    >
      <span className={cn("mt-0.5 flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border", active ? "border-[#00a09d]" : "border-border")} aria-hidden>
        {active ? <span className="h-1.5 w-1.5 rounded-full bg-[#00a09d]" /> : null}
      </span>
      <span className="min-w-0">
        <span className="block text-[13px] font-medium">{title}</span>
        <span className="block text-[11px] text-muted-foreground">{hint}</span>
      </span>
    </button>
  );
}

/**
 * "Category product rail": a heading, then products from ONE source — a
 * category (its first 5 products, automatic) or products picked by hand. Saved
 * in `blocks.excellent.collection`:
 * `{ title, subtitle, mode: "category" | "custom", category (slug), products: [{ key, id, hidden }] }`.
 */
export function LiveEditExcellentCollection({ ex, setEx }: { ex: Json; setEx: (patch: Json) => void }) {
  const { categories } = useCatalogCategories({ channel: "catalog" });
  const activeCategories = useMemo(() => categories.filter((c) => c.active), [categories]);

  const c = obj(ex.collection);
  const mode = c.mode === "custom" ? "custom" : "category";
  const picks: Row[] = Array.isArray(c.products) ? (c.products as Row[]).filter((p) => p && typeof p === "object") : [];
  const write = (patch: Json) => setEx({ collection: { ...c, ...patch } });

  /** The rail stores the category's slug; the picker works with ids. */
  const categoryId = activeCategories.find((x) => x.slug === text(c.category))?.id ?? "";

  return (
    <div className="space-y-3">
      <div className="space-y-3 rounded-md border border-border bg-card p-2.5">
        <AgainFormRow label="Heading">
          <Input value={text(c.title)} onChange={(e) => write({ title: e.target.value })} className="h-8 text-[13px]" />
        </AgainFormRow>
        <AgainFormRow label="Sub heading">
          <Input value={text(c.subtitle)} onChange={(e) => write({ subtitle: e.target.value })} className="h-8 text-[13px]" />
        </AgainFormRow>
      </div>

      <div className="space-y-2.5 rounded-md border border-border bg-card p-2.5">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Products</p>
        <Option active={mode === "category"} title="From a category" hint="Shows the category's first 5 products. “See All” opens the category." onSelect={() => write({ mode: "category" })} />
        <Option
          active={mode === "custom"}
          title="Custom products"
          hint="Pick exactly which products to show."
          // Custom products have no category, so there is no “See All” link either.
          onSelect={() => write({ mode: "custom", category: "" })}
        />

        {mode === "category" ? (
          <AgainFormRow label="Category">
            <CategoryCombobox
              radio
              categories={activeCategories}
              value={categoryId}
              onChange={(id) => write({ category: activeCategories.find((x) => x.id === id)?.slug ?? "" })}
              placeholder="Select category"
            />
          </AgainFormRow>
        ) : (
          <AgainFormRow label="Products">
            <ProductMultiPicker
              selectedIds={picks.map((p) => text(p.id)).filter(Boolean)}
              onChange={(ids) => write({ products: ids.map((id) => picks.find((p) => text(p.id) === id) ?? { key: id, id, hidden: false }) })}
            />
          </AgainFormRow>
        )}
      </div>

      <div className="space-y-3 rounded-md border border-border bg-card p-2.5">
        <AgainFormRow label="Products to show" help={mode === "category" ? "Empty = 5." : "Empty = all the products you picked (up to 10)."}>
          <Input
            type="number"
            min={1}
            max={20}
            value={c.limit ? String(c.limit) : ""}
            onChange={(e) => write({ limit: e.target.value ? Math.min(20, Math.max(1, Math.floor(Number(e.target.value)))) : 0 })}
            className="h-8 w-24 text-[13px]"
            placeholder={mode === "category" ? "5" : "All"}
          />
        </AgainFormRow>
        <AgainFormRow label="“See All” link" help={mode === "category" ? "Empty = the category's own page." : "Empty = no “See All” link."}>
          <Input value={text(c.see_all_href)} onChange={(e) => write({ see_all_href: e.target.value })} className="h-8 text-[13px]" placeholder={mode === "category" ? "/monitor" : "/offers"} />
        </AgainFormRow>
      </div>
      <p className="text-[11px] text-muted-foreground">Product changes show on the page after Save.</p>
    </div>
  );
}
