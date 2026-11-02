"use client";

import { useMemo, useState } from "react";
import { Filter, GripVertical, RotateCcw } from "lucide-react";
import type { BulkAttributeGroupRow } from "@/lib/mock-data/attribute-profiles";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

type Props = {
  groups: BulkAttributeGroupRow[];
  onChange: (groups: BulkAttributeGroupRow[]) => void;
};

type Entry = { key: string; name: string; group: string; order: number };

/**
 * The order of the filters on the storefront's category page - independent of the specification table above
 * (which keeps its own group / attribute order on the product page). Drag a filter to move it.
 */
export function FilterOrderPanel({ groups, onChange }: Props) {
  const [dragKey, setDragKey] = useState<string | null>(null);
  const [overKey, setOverKey] = useState<string | null>(null);

  const entries = useMemo<Entry[]>(() => {
    const list: Entry[] = [];
    groups.forEach((g, gi) =>
      g.attributes.forEach((a, ai) => {
        if (a.filterable && a.name.trim()) {
          list.push({ key: a.key, name: a.name, group: g.name, order: a.filterOrder ?? 1000 + gi * 100 + ai });
        }
      }),
    );
    return list.sort((x, y) => x.order - y.order);
  }, [groups]);

  if (entries.length < 2) return null;

  const hasCustom = groups.some((g) => g.attributes.some((a) => a.filterable && a.filterOrder !== undefined));

  const apply = (keys: string[]) => {
    const pos = new Map(keys.map((k, i) => [k, i]));
    onChange(
      groups.map((g) => ({
        ...g,
        attributes: g.attributes.map((a) => (pos.has(a.key) ? { ...a, filterOrder: pos.get(a.key) } : a)),
      })),
    );
  };

  const drop = (targetKey: string) => {
    if (!dragKey || dragKey === targetKey) return;
    const keys = entries.map((e) => e.key).filter((k) => k !== dragKey);
    keys.splice(keys.indexOf(targetKey), 0, dragKey);
    apply(keys);
    setDragKey(null);
    setOverKey(null);
  };

  const reset = () =>
    onChange(groups.map((g) => ({ ...g, attributes: g.attributes.map((a) => ({ ...a, filterOrder: undefined })) })));

  return (
    <div className="rounded-xl border border-input bg-card p-4">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Filter className="h-3.5 w-3.5 text-primary" />
          Filter order on the category page
        </div>
        {hasCustom && (
          <Button type="button" variant="ghost" size="sm" className="h-7 gap-1 px-2 text-xs" onClick={reset} title="Follow the specification order again">
            <RotateCcw className="h-3 w-3" /> Use specification order
          </Button>
        )}
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        Drag to arrange the storefront filters. The product page keeps the specification order above.
      </p>
      <ol className="space-y-1.5">
        {entries.map((e, i) => (
          <li
            key={e.key}
            draggable
            onDragStart={() => setDragKey(e.key)}
            onDragEnd={() => { setDragKey(null); setOverKey(null); }}
            onDragOver={(ev) => { ev.preventDefault(); setOverKey(e.key); }}
            onDragLeave={() => setOverKey((k) => (k === e.key ? null : k))}
            onDrop={() => drop(e.key)}
            className={cn(
              "flex cursor-grab items-center gap-2 rounded-md border border-input bg-background px-2.5 py-1.5 text-sm active:cursor-grabbing",
              dragKey === e.key && "opacity-50",
              overKey === e.key && dragKey !== e.key && "ring-2 ring-primary/30",
            )}
          >
            <GripVertical className="h-4 w-4 shrink-0 text-muted-foreground" />
            <span className="w-5 shrink-0 text-xs tabular-nums text-muted-foreground">{i + 1}</span>
            <span className="flex-1 truncate font-medium">{e.name}</span>
            <span className="truncate text-xs text-muted-foreground">{e.group}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
