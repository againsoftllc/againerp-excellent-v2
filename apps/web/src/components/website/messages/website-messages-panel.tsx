"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { Check, Mail, MailOpen, Phone, RotateCcw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { MarketingListGrid, StatusBadge, type StatusTone } from "@/components/website/marketing/marketing-list-grid";
import {
  deleteContactMessage,
  fetchContactMessages,
  setContactMessageStatus,
  type ApiContactMessage,
  type ContactMessageStatus,
} from "@/lib/api/website-contact-messages";
import { useAdminCanWrite } from "@/lib/hooks/use-admin-can-write";

const STATUS_TONE: Record<string, StatusTone> = { new: "warning", read: "muted", done: "success" };
const STATUS_LABEL: Record<ContactMessageStatus, string> = { new: "New", read: "Read", done: "Done" };

function formatWhen(iso: string): string {
  const d = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/** What visitors wrote in the storefront's contact form (Branches page), so the shop can answer them. */
export function WebsiteMessagesPanel() {
  const canWrite = useAdminCanWrite();
  const [rows, setRows] = useState<ApiContactMessage[]>([]);
  const [newCount, setNewCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [openId, setOpenId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchContactMessages();
      setRows(res.rows);
      setNewCount(res.newCount);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load messages");
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
      if (status !== "all" && r.status !== status) return false;
      if (!q) return true;
      return [r.name, r.phone, r.email, r.subject, r.message].some((v) => v.toLowerCase().includes(q));
    });
  }, [rows, search, status]);

  const open = useMemo(() => rows.find((r) => r.id === openId) ?? null, [rows, openId]);

  const mark = useCallback(
    async (row: ApiContactMessage, next: ContactMessageStatus, quiet = false) => {
      try {
        const updated = await setContactMessageStatus(row.id, next);
        setRows((prev) => prev.map((r) => (r.id === row.id ? updated : r)));
        setNewCount((n) => Math.max(0, n + (next === "new" ? 1 : 0) - (row.status === "new" ? 1 : 0)));
        if (!quiet) toast.success(`Marked as ${STATUS_LABEL[next].toLowerCase()}`);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Could not update");
      }
    },
    [],
  );

  const remove = useCallback(async (row: ApiContactMessage) => {
    if (!window.confirm(`Delete the message from ${row.name || row.phone || row.email}?`)) return;
    try {
      await deleteContactMessage(row.id);
      setRows((prev) => prev.filter((r) => r.id !== row.id));
      setNewCount((n) => Math.max(0, n - (row.status === "new" ? 1 : 0)));
      setOpenId((id) => (id === row.id ? null : id));
      toast.success("Deleted");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Delete failed");
    }
  }, []);

  const openRow = useCallback(
    (row: ApiContactMessage) => {
      setOpenId(row.id);
      // opening a new message reads it, like an inbox
      if (row.status === "new" && canWrite) void mark(row, "read", true);
    },
    [canWrite, mark],
  );
  const openRef = useRef(openRow);
  openRef.current = openRow;
  const markRef = useRef(mark);
  markRef.current = mark;
  const removeRef = useRef(remove);
  removeRef.current = remove;

  const columns = useMemo<ColDef<ApiContactMessage>[]>(
    () => [
      {
        field: "status",
        headerName: "Status",
        width: 90,
        cellRenderer: (p: ICellRendererParams<ApiContactMessage>) =>
          p.data ? <StatusBadge label={STATUS_LABEL[p.data.status]} tone={STATUS_TONE[p.data.status] ?? "muted"} /> : null,
      },
      { field: "name", headerName: "Name", width: 150, cellClass: "font-medium" },
      { field: "phone", headerName: "Phone", width: 130 },
      { field: "email", headerName: "Email", width: 190 },
      { field: "subject", headerName: "Subject", width: 150 },
      { field: "message", headerName: "Message", flex: 1.6, minWidth: 220 },
      { field: "created_at", headerName: "Received", width: 160 },
    ],
    [],
  );

  const rowMenu = useCallback(
    (row: ApiContactMessage) => (
      <>
        <DropdownMenuItem onClick={() => openRef.current(row)}>
          <MailOpen className="mr-1.5 h-3 w-3" /> Open
        </DropdownMenuItem>
        {canWrite ? (
          <>
            {row.status !== "done" ? (
              <DropdownMenuItem onClick={() => void markRef.current(row, "done")}>
                <Check className="mr-1.5 h-3 w-3" /> Mark as done
              </DropdownMenuItem>
            ) : null}
            {row.status !== "new" ? (
              <DropdownMenuItem onClick={() => void markRef.current(row, "new")}>
                <RotateCcw className="mr-1.5 h-3 w-3" /> Mark as new
              </DropdownMenuItem>
            ) : null}
            <DropdownMenuItem className="text-destructive" onClick={() => void removeRef.current(row)}>
              <Trash2 className="mr-1.5 h-3 w-3" /> Delete
            </DropdownMenuItem>
          </>
        ) : null}
      </>
    ),
    [canWrite],
  );

  const filtersActive = search.trim() !== "" || status !== "all";

  return (
    <MarketingListGrid<ApiContactMessage>
      title="Messages"
      rows={filtered}
      loading={loading}
      columns={columns}
      rowMenu={rowMenu}
      onRefresh={() => void load()}
      onOpen={openRow}
      search={{ value: search, onChange: setSearch, placeholder: "Search name, phone, message…" }}
      statusFilter={{
        value: status,
        onChange: setStatus,
        label: "Status filter",
        options: [{ value: "all", label: "All" }, { value: "new", label: "New" }, { value: "read", label: "Read" }, { value: "done", label: "Done" }],
      }}
      extraFilters={
        <span className="shrink-0 text-xs text-muted-foreground">
          {rows.length} in total · {newCount} new
        </span>
      }
      filtersActive={filtersActive}
      onResetFilters={() => {
        setSearch("");
        setStatus("all");
      }}
      emptyTitle="No messages yet"
      emptyHint="What visitors send from the Branches page (Send Us a Message) appears here."
      layoutKey="grid-layout:website-messages"
      error={error}
      mobile={
        <div className="divide-y divide-border">
          {filtered.map((row) => (
            <button key={row.id} type="button" className="flex w-full items-start justify-between gap-3 px-3 py-3 text-left" onClick={() => openRow(row)}>
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium">{row.name}</span>
                <span className="block truncate text-xs text-muted-foreground">{row.subject || row.phone}</span>
                <span className="line-clamp-2 text-xs text-muted-foreground">{row.message}</span>
              </span>
              <StatusBadge label={STATUS_LABEL[row.status]} tone={STATUS_TONE[row.status] ?? "muted"} />
            </button>
          ))}
        </div>
      }
    >
      <Sheet open={!!open} onOpenChange={(o) => !o && setOpenId(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-lg">
          {open ? (
            <>
              <SheetHeader>
                <SheetTitle>{open.subject || "Message"}</SheetTitle>
              </SheetHeader>
              <div className="mt-4 space-y-4 px-4 pb-6 text-sm">
                <div className="flex items-center gap-2">
                  <StatusBadge label={STATUS_LABEL[open.status]} tone={STATUS_TONE[open.status] ?? "muted"} />
                  <span className="text-xs text-muted-foreground">{formatWhen(open.created_at)}</span>
                </div>
                <dl className="grid grid-cols-[88px_1fr] gap-x-3 gap-y-2">
                  <dt className="text-muted-foreground">Name</dt>
                  <dd className="font-medium">{open.name || "—"}</dd>
                  <dt className="text-muted-foreground">Phone</dt>
                  <dd>
                    {open.phone ? (
                      <a className="inline-flex items-center gap-1 text-primary hover:underline" href={`tel:${open.phone}`}>
                        <Phone className="h-3 w-3" /> {open.phone}
                      </a>
                    ) : (
                      "—"
                    )}
                  </dd>
                  <dt className="text-muted-foreground">Email</dt>
                  <dd>
                    {open.email ? (
                      <a className="inline-flex items-center gap-1 text-primary hover:underline" href={`mailto:${open.email}`}>
                        <Mail className="h-3 w-3" /> {open.email}
                      </a>
                    ) : (
                      "—"
                    )}
                  </dd>
                </dl>
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">Message</p>
                  <p className="whitespace-pre-wrap break-words border border-border bg-muted/30 p-3">{open.message || "—"}</p>
                </div>
                {canWrite ? (
                  <div className="flex flex-wrap gap-2">
                    {open.status !== "done" ? (
                      <Button size="sm" className="rounded-none" onClick={() => void mark(open, "done")}>
                        <Check className="mr-1 h-3.5 w-3.5" /> Mark as done
                      </Button>
                    ) : (
                      <Button size="sm" variant="outline" className="rounded-none" onClick={() => void mark(open, "read")}>
                        <RotateCcw className="mr-1 h-3.5 w-3.5" /> Reopen
                      </Button>
                    )}
                    <Button size="sm" variant="outline" className="rounded-none text-destructive" onClick={() => void remove(open)}>
                      <Trash2 className="mr-1 h-3.5 w-3.5" /> Delete
                    </Button>
                  </div>
                ) : null}
              </div>
            </>
          ) : null}
        </SheetContent>
      </Sheet>
    </MarketingListGrid>
  );
}
