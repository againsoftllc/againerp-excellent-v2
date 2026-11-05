"use client";

import { useMemo, type ReactNode } from "react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { RefreshCw, Settings2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { AgainListGrid } from "@/components/shared/again-list-grid";
import { FilterSelect, type FilterSelectOption } from "@/components/shared/filter-select";
import { GridFullscreenHeader } from "@/components/shared/grid-fullscreen";
import { ListGridHeaderStart } from "@/components/shared/list-grid-header-start";
import { RowActionsTrigger } from "@/components/shared/row-actions-icon";
import { useApiHealth } from "@/lib/api/use-api-health";
import { cn } from "@/lib/utils";

/** Status words of the Promotions lists in the same colours the other admin tables use (Published = green, Draft = amber ...). */
export type StatusTone = "success" | "warning" | "muted" | "outline";

export function StatusBadge({ label, tone }: { label: string; tone: StatusTone }) {
  return (
    <div className="flex h-full items-center overflow-hidden">
      <Badge variant={tone} className="max-w-28 shrink-0 truncate leading-4 capitalize">
        {label}
      </Badge>
    </div>
  );
}

type Props<T extends { id: string }> = {
  /** Name shown at the left of the toolbar, like "Products" / "Brands". */
  title: string;
  rows: T[];
  loading: boolean;
  /** The data columns; the row menu column is added in front. */
  columns: ColDef<T>[];
  /** Items of the row's settings-cog menu (DropdownMenuItem ...); leave out for a list with no row menu. */
  rowMenu?: (row: T) => ReactNode;
  /** Shown only when the admin may write; pass undefined otherwise. */
  onNew?: () => void;
  onRefresh: () => void;
  /** Click on a row (anywhere but the cog) opens it. */
  onOpen?: (row: T) => void;
  search: { value: string; onChange: (value: string) => void; placeholder: string };
  statusFilter?: { value: string; onChange: (value: string) => void; options: FilterSelectOption[]; label: string };
  extraFilters?: ReactNode;
  filtersActive: boolean;
  onResetFilters: () => void;
  emptyTitle: string;
  emptyHint?: string;
  /** Where the admin's column layout is saved (one per list). */
  layoutKey: string;
  /** Sheets and dialogs of the page, rendered beside the grid. */
  children?: ReactNode;
  /** The phone-width view (the table is hidden under 768px). */
  mobile?: ReactNode;
  error?: string | null;
};

/**
 * One table for every list of the Promotions menu (Happy Hour, Offers, Coupons, Popups, Subscribers): the same shell as
 * Products and the other admin lists - `[Name] [New] [cog]` toolbar, search and status filter, status badges, the row's
 * settings cog at the left, 50-row pages, fullscreen, zoom and a saved column layout. A page only gives columns and rows.
 */
export function MarketingListGrid<T extends { id: string }>({
  title,
  rows,
  loading,
  columns,
  rowMenu,
  onNew,
  onRefresh,
  onOpen,
  search,
  statusFilter,
  extraFilters,
  filtersActive,
  onResetFilters,
  emptyTitle,
  emptyHint,
  layoutKey,
  children,
  mobile,
  error,
}: Props<T>) {
  const apiHealth = useApiHealth();
  const healthTitle =
    apiHealth.status === "connected"
      ? "API connected"
      : apiHealth.status === "partial"
        ? "API partly reachable"
        : apiHealth.status === "disconnected"
          ? "API unreachable"
          : "Checking connection…";

  const columnDefs = useMemo<ColDef<T>[]>(() => {
    const actions: ColDef<T>[] = rowMenu
      ? [
          {
            colId: "actions",
            headerName: "",
            width: 26,
            maxWidth: 26,
            minWidth: 26,
            pinned: "left",
            resizable: false,
            suppressMovable: true,
            suppressHeaderMenuButton: true,
            suppressSizeToFit: true,
            sortable: false,
            headerClass: "product-grid-actions-col",
            cellClass: "product-grid-actions-col",
            headerComponent: GridFullscreenHeader,
            cellRenderer: (p: ICellRendererParams<T>) =>
              p.data ? (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <RowActionsTrigger />
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start">{rowMenu(p.data)}</DropdownMenuContent>
                </DropdownMenu>
              ) : null,
          },
        ]
      : [];
    return [...actions, ...columns];
  }, [columns, rowMenu]);

  const headerLeftActions = (
    <ListGridHeaderStart title={title}>
      {onNew ? (
        <Button size="sm" className="rounded-none" onClick={onNew}>
          New
        </Button>
      ) : null}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size="icon"
            className={cn(
              "relative h-[26px] w-[26px] shrink-0 rounded-none",
              apiHealth.status === "connected" &&
                "border-emerald-500/50 text-emerald-600 hover:bg-emerald-500/10 hover:text-emerald-700 dark:text-emerald-400",
              apiHealth.status === "partial" &&
                "border-amber-500/50 text-amber-600 hover:bg-amber-500/10 hover:text-amber-700 dark:text-amber-400",
              apiHealth.status === "disconnected" &&
                "border-red-500/50 text-red-600 hover:bg-red-500/10 hover:text-red-700 dark:text-red-400",
              apiHealth.status === "checking" && "text-muted-foreground",
            )}
            aria-label={`Settings (${healthTitle})`}
            title={healthTitle}
          >
            <Settings2 className="h-3.5 w-3.5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="min-w-[11rem]">
          <DropdownMenuItem
            onClick={() => {
              onRefresh();
              apiHealth.recheck();
            }}
            disabled={loading}
          >
            <RefreshCw className={cn("mr-1.5 h-3 w-3", loading && "animate-spin")} />
            Refresh
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </ListGridHeaderStart>
  );

  return (
    <div className="flex min-h-0 w-full min-w-0 flex-1 flex-col overflow-hidden">
      {error && !loading ? (
        <p className="shrink-0 border-b border-destructive/30 bg-destructive/5 px-3 py-1.5 text-xs text-destructive">API: {error}</p>
      ) : null}
      <AgainListGrid<T>
        className="min-h-0 flex-1"
        rowData={rows}
        columnDefs={columnDefs}
        loading={loading && rows.length === 0}
        headerLeftActions={headerLeftActions}
        filterBar={
          <>
            <Input
              placeholder={search.placeholder}
              value={search.value}
              onChange={(e) => search.onChange(e.target.value)}
              className="w-[220px] shrink-0 rounded-none"
            />
            {statusFilter ? (
              <FilterSelect
                value={statusFilter.value}
                onChange={statusFilter.onChange}
                width="w-[138px]"
                className="shrink-0"
                ariaLabel={statusFilter.label}
                options={statusFilter.options}
              />
            ) : null}
            {extraFilters}
          </>
        }
        emptyTitle={filtersActive ? "Nothing matches your filters" : emptyTitle}
        emptyHint={filtersActive ? undefined : emptyHint}
        onResetFilters={filtersActive ? onResetFilters : undefined}
        onRowClicked={onOpen}
        layoutKey={layoutKey}
        mobile={mobile}
      />
      {children}
    </div>
  );
}
