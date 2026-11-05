"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { Download, Trash2, UserCheck, UserX } from "lucide-react";
import { toast } from "sonner";
import { DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { MarketingListGrid, StatusBadge } from "@/components/website/marketing/marketing-list-grid";
import { Button } from "@/components/ui/button";
import {
  deleteNewsletterSubscriber,
  fetchNewsletterSubscribers,
  setNewsletterSubscriberActive,
  type ApiNewsletterSubscriber,
} from "@/lib/api/marketing-newsletter";
import { useAdminCanWrite } from "@/lib/hooks/use-admin-can-write";

function formatWhen(iso: string): string {
  const d = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

const csvCell = (v: string) => `"${v.replace(/"/g, '""')}"`;

/** Who signed up through the storefront footer's Subscribe box (an email or a mobile number). */
export function MarketingSubscribersPanel() {
  const canWrite = useAdminCanWrite();
  const [rows, setRows] = useState<ApiNewsletterSubscriber[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<"all" | "active" | "unsubscribed">("all");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows((await fetchNewsletterSubscribers()).rows);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load subscribers");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) => {
      if (status === "active" && !r.is_active) return false;
      if (status === "unsubscribed" && r.is_active) return false;
      return !q || r.email.toLowerCase().includes(q) || r.phone.toLowerCase().includes(q);
    });
  }, [rows, search, status]);

  const activeCount = rows.filter((r) => r.is_active).length;

  const downloadCsv = () => {
    const lines = [
      ["email", "phone", "status", "source", "subscribed_at"].join(","),
      ...filtered.map((r) => [r.email, r.phone, r.is_active ? "active" : "unsubscribed", r.source, r.created_at].map(csvCell).join(",")),
    ];
    const blob = new Blob([`﻿${lines.join("\n")}`], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `newsletter-subscribers-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const act = async (fn: () => Promise<void>, done: string) => {
    try {
      await fn();
      toast.success(done);
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed");
    }
  };

  const activeRef = useRef(act);
  activeRef.current = act;

  const columns = useMemo<ColDef<ApiNewsletterSubscriber>[]>(
    () => [
      { field: "email", headerName: "Email", flex: 1.4, minWidth: 180, valueFormatter: (p) => p.value || "—" },
      { field: "phone", headerName: "Mobile", width: 140, valueFormatter: (p) => p.value || "—" },
      { field: "source", headerName: "Source", width: 130 },
      { field: "created_at", headerName: "Subscribed", width: 160 },
      {
        colId: "status",
        headerName: "Status",
        width: 130,
        valueGetter: (p) => (p.data ? (p.data.is_active ? "active" : "unsubscribed") : ""),
        cellRenderer: (p: ICellRendererParams<ApiNewsletterSubscriber>) =>
          p.data ? <StatusBadge label={p.data.is_active ? "active" : "unsubscribed"} tone={p.data.is_active ? "success" : "muted"} /> : null,
      },
    ],
    [],
  );

  const rowMenu = useCallback(
    (r: ApiNewsletterSubscriber) =>
      canWrite ? (
        <>
          <DropdownMenuItem
            onClick={() =>
              void activeRef.current(() => setNewsletterSubscriberActive(r.id, !r.is_active), r.is_active ? "Unsubscribed" : "Subscribed again")
            }
          >
            {r.is_active ? <UserX className="mr-1.5 h-3 w-3" /> : <UserCheck className="mr-1.5 h-3 w-3" />}
            {r.is_active ? "Unsubscribe" : "Subscribe again"}
          </DropdownMenuItem>
          <DropdownMenuItem
            className="text-destructive"
            onClick={() => {
              if (!window.confirm(`Delete ${r.email || r.phone}? They can subscribe again from the site.`)) return;
              void activeRef.current(() => deleteNewsletterSubscriber(r.id), "Deleted");
            }}
          >
            <Trash2 className="mr-1.5 h-3 w-3" /> Delete
          </DropdownMenuItem>
        </>
      ) : (
        <DropdownMenuItem disabled>View only</DropdownMenuItem>
      ),
    [canWrite],
  );

  const filtersActive = search.trim() !== "" || status !== "all";

  return (
    <MarketingListGrid<ApiNewsletterSubscriber>
      title="Subscribers"
      rows={filtered}
      loading={loading}
      columns={columns}
      rowMenu={rowMenu}
      onRefresh={() => void load()}
      search={{ value: search, onChange: setSearch, placeholder: "Search email or phone…" }}
      statusFilter={{
        value: status,
        onChange: (v) => setStatus(v as typeof status),
        label: "Status filter",
        options: [{ value: "all", label: "All" }, { value: "active", label: "Active" }, { value: "unsubscribed", label: "Unsubscribed" }],
      }}
      extraFilters={
        <>
          <span className="shrink-0 text-xs text-muted-foreground">
            {rows.length} in total · {activeCount} active{filtered.length !== rows.length ? ` · ${filtered.length} shown` : ""}
          </span>
          <Button type="button" size="sm" variant="outline" className="ml-auto h-[26px] shrink-0 rounded-none" disabled={filtered.length === 0} onClick={downloadCsv}>
            <Download className="mr-1 h-3.5 w-3.5" />
            Download CSV
          </Button>
        </>
      }
      filtersActive={filtersActive}
      onResetFilters={() => {
        setSearch("");
        setStatus("all");
      }}
      emptyTitle="Nobody has subscribed yet"
      emptyHint="People who use the Subscribe box on the site appear here."
      layoutKey="grid-layout:marketing-subscribers"
      mobile={
        <div className="divide-y divide-border">
          {filtered.map((r) => (
            <div key={r.id} className="flex items-center justify-between gap-3 px-3 py-3">
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium">{r.email || r.phone || "—"}</span>
                <span className="block truncate text-xs text-muted-foreground">{formatWhen(r.created_at)}</span>
              </span>
              <StatusBadge label={r.is_active ? "active" : "unsubscribed"} tone={r.is_active ? "success" : "muted"} />
            </div>
          ))}
        </div>
      }
    />
  );
}
