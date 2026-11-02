"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Download, Trash2, UserCheck, UserX } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
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

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Input className="h-8 w-[240px] rounded-none" placeholder="Search email or phone…" value={search} onChange={(e) => setSearch(e.target.value)} />
        <Select className="h-8 w-[170px] rounded-none" value={status} onChange={(e) => setStatus(e.target.value as typeof status)}>
          <option value="all">All</option>
          <option value="active">Active</option>
          <option value="unsubscribed">Unsubscribed</option>
        </Select>
        <span className="text-xs text-muted-foreground">
          {rows.length} in total · {activeCount} active{filtered.length !== rows.length ? ` · ${filtered.length} shown` : ""}
        </span>
        <Button type="button" size="sm" variant="outline" className="ml-auto h-8 rounded-none" disabled={filtered.length === 0} onClick={downloadCsv}>
          <Download className="mr-1 h-3.5 w-3.5" />
          Download CSV
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto border border-border">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-muted/60 text-left text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="px-3 py-2">Email</th>
              <th className="px-3 py-2">Mobile</th>
              <th className="px-3 py-2">Source</th>
              <th className="px-3 py-2">Subscribed</th>
              <th className="px-3 py-2">Status</th>
              <th className="w-24 px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {loading && rows.length === 0 ? (
              <tr><td colSpan={6} className="px-3 py-6 text-muted-foreground">Loading subscribers…</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={6} className="px-3 py-6 text-muted-foreground">{rows.length === 0 ? "Nobody has subscribed yet." : "No subscriber matches."}</td></tr>
            ) : (
              filtered.map((r) => (
                <tr key={r.id} className="border-t border-border hover:bg-muted/30">
                  <td className="px-3 py-2">{r.email || "—"}</td>
                  <td className="px-3 py-2">{r.phone || "—"}</td>
                  <td className="px-3 py-2 text-muted-foreground">{r.source}</td>
                  <td className="px-3 py-2 text-muted-foreground">{formatWhen(r.created_at)}</td>
                  <td className="px-3 py-2">
                    <Badge variant={r.is_active ? "default" : "secondary"} className="rounded-none">{r.is_active ? "Active" : "Unsubscribed"}</Badge>
                  </td>
                  <td className="px-3 py-2">
                    {canWrite ? (
                      <div className="flex gap-0.5">
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          title={r.is_active ? "Unsubscribe" : "Subscribe again"}
                          onClick={() => void act(() => setNewsletterSubscriberActive(r.id, !r.is_active), r.is_active ? "Unsubscribed" : "Subscribed again")}
                        >
                          {r.is_active ? <UserX className="h-3.5 w-3.5" /> : <UserCheck className="h-3.5 w-3.5" />}
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-destructive"
                          title="Delete"
                          onClick={() => {
                            if (!window.confirm(`Delete ${r.email || r.phone}? They can subscribe again from the site.`)) return;
                            void act(() => deleteNewsletterSubscriber(r.id), "Deleted");
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
    </div>
  );
}
