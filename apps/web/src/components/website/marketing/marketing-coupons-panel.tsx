"use client";

import "@/components/providers/ag-grid-provider";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import type { CouponStatus, MarketingCoupon } from "@/lib/mock-data/marketing";
import {
  createMarketingCoupon,
  deleteMarketingCoupon,
  updateMarketingCoupon,
} from "@/lib/api/marketing-coupons";
import { useMarketingCoupons } from "@/lib/api/use-marketing-coupons";
import { useAdminCanWrite } from "@/lib/hooks/use-admin-can-write";
import { useViewerWriteUrlGuard } from "@/lib/hooks/use-viewer-write-url-guard";
import { Badge } from "@/components/ui/badge";
import { MarketingListGrid, StatusBadge, type StatusTone } from "@/components/website/marketing/marketing-list-grid";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Label } from "@/components/ui/label";

const PAGE_SIZE = 50;
const STATUS_OPTIONS: CouponStatus[] = ["active", "scheduled", "expired", "disabled"];
const STATUS_TONE: Record<string, StatusTone> = { active: "success", scheduled: "warning", expired: "outline", disabled: "muted" };

function buildUrl(params: URLSearchParams) {
  const q = params.toString();
  return q ? `/website/marketing/coupons?${q}` : "/website/marketing/coupons";
}

export function MarketingCouponsPanel() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const canWrite = useAdminCanWrite();
  const { coupons, loading, error, refetch } = useMarketingCoupons();

  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");

  const createOpen = searchParams.get("create") === "1";
  const editId = searchParams.get("edit");
  const editCoupon = useMemo(
    () => (editId ? coupons.find((c) => c.id === editId) ?? null : null),
    [editId, coupons],
  );
  const formOpen = createOpen || !!editCoupon;

  useEffect(() => {
    if (error) toast.error(`API: ${error}`, { id: "marketing-coupons-api" });
  }, [error]);

  const pushParams = (mutate: (p: URLSearchParams) => void) => {
    const p = new URLSearchParams(searchParams.toString());
    p.delete("tab");
    mutate(p);
    router.push(buildUrl(p), { scroll: false });
  };

  const openCreate = () =>
    pushParams((p) => {
      p.delete("edit");
      p.set("create", "1");
    });

  const openEdit = (coupon: MarketingCoupon) =>
    pushParams((p) => {
      p.delete("create");
      p.set("edit", coupon.id);
    });

  const closeForm = () =>
    pushParams((p) => {
      p.delete("create");
      p.delete("edit");
    });

  useViewerWriteUrlGuard(formOpen, closeForm);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return coupons.filter((coupon) => {
      if (status !== "all" && coupon.status !== status) return false;
      if (!q) return true;
      return (
        coupon.code.toLowerCase().includes(q) ||
        coupon.name.toLowerCase().includes(q) ||
        coupon.discount.toLowerCase().includes(q)
      );
    });
  }, [coupons, search, status]);

  const openEditRef = useRef(openEdit);
  openEditRef.current = openEdit;

  const columns = useMemo<ColDef<MarketingCoupon>[]>(
    () => [
      { field: "code", headerName: "Code", width: 130, cellClass: "font-mono font-medium" },
      { field: "name", headerName: "Name", flex: 1.4, minWidth: 160 },
      { field: "discount", headerName: "Discount", width: 120 },
      {
        field: "status",
        headerName: "Status",
        width: 110,
        cellRenderer: (p: ICellRendererParams<MarketingCoupon>) =>
          p.data ? <StatusBadge label={p.data.status} tone={STATUS_TONE[p.data.status] ?? "muted"} /> : null,
      },
      {
        colId: "redemptions",
        headerName: "Redeemed",
        width: 110,
        valueGetter: (p) =>
          p.data ? (p.data.limit != null ? `${p.data.redemptions}/${p.data.limit}` : String(p.data.redemptions)) : "",
      },
      {
        colId: "dates",
        headerName: "Valid",
        flex: 1,
        minWidth: 170,
        valueGetter: (p) => (p.data ? `${p.data.startsAt} → ${p.data.endsAt}` : ""),
      },
    ],
    [],
  );

  const rowMenu = useCallback(
    (row: MarketingCoupon) => (
      <>
        <DropdownMenuItem onClick={() => openEditRef.current(row)}>
          <Pencil className="mr-1.5 h-3 w-3" /> Edit
        </DropdownMenuItem>
        {canWrite ? (
          <DropdownMenuItem
            className="text-destructive"
            onClick={() => {
              void (async () => {
                try {
                  await deleteMarketingCoupon(row.id);
                  toast.success("Coupon deleted");
                  await refetch();
                } catch (err) {
                  toast.error(err instanceof Error ? err.message : "Delete failed");
                }
              })();
            }}
          >
            <Trash2 className="mr-1.5 h-3 w-3" /> Delete
          </DropdownMenuItem>
        ) : null}
      </>
    ),
    [canWrite, refetch],
  );

  const filtersActive = search.trim() !== "" || status !== "all";

  return (
    <MarketingListGrid<MarketingCoupon>
      title="Coupons"
      rows={filtered}
      loading={loading}
      columns={columns}
      rowMenu={rowMenu}
      onNew={canWrite ? openCreate : undefined}
      onRefresh={() => void refetch()}
      onOpen={openEdit}
      search={{ value: search, onChange: setSearch, placeholder: "Search code, name…" }}
      statusFilter={{
        value: status,
        onChange: setStatus,
        label: "Status filter",
        options: [{ value: "all", label: "All statuses" }, ...STATUS_OPTIONS.map((key) => ({ value: key, label: key[0].toUpperCase() + key.slice(1) }))],
      }}
      filtersActive={filtersActive}
      onResetFilters={() => {
        setSearch("");
        setStatus("all");
      }}
      emptyTitle="No coupons yet"
      emptyHint="Create one with New."
      layoutKey="grid-layout:marketing-coupons"
      mobile={
        <div className="divide-y divide-border">
          {filtered.map((row) => (
            <button key={row.id} type="button" className="flex w-full items-center justify-between gap-3 px-3 py-3 text-left" onClick={() => openEdit(row)}>
              <span className="min-w-0">
                <span className="block truncate font-mono text-sm font-medium">{row.code}</span>
                <span className="block truncate text-xs text-muted-foreground">
                  {row.name} · {row.discount}
                </span>
              </span>
              <StatusBadge label={row.status} tone={STATUS_TONE[row.status] ?? "muted"} />
            </button>
          ))}
        </div>
      }
      error={error}
    >
      <CouponFormSheet
        open={formOpen}
        mode={createOpen ? "create" : "edit"}
        coupon={editCoupon}
        onOpenChange={(open) => {
          if (!open) closeForm();
        }}
        onSaved={async () => {
          await refetch();
          closeForm();
        }}
      />
    </MarketingListGrid>
  );
}

function CouponFormSheet({
  open,
  mode,
  coupon,
  onOpenChange,
  onSaved,
}: {
  open: boolean;
  mode: "create" | "edit";
  coupon: MarketingCoupon | null;
  onOpenChange: (open: boolean) => void;
  onSaved: () => Promise<void>;
}) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [discountType, setDiscountType] = useState<"percent" | "fixed">("percent");
  const [discountValue, setDiscountValue] = useState("10");
  const [status, setStatus] = useState<CouponStatus>("active");
  const [limit, setLimit] = useState("");
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [minOrder, setMinOrder] = useState("");
  const [saving, setSaving] = useState(false);

  // Fill the form when the sheet opens or the record changes. Done while rendering (React's pattern for
  // resetting state on a prop change) so the sheet never shows the previous record first.
  const [loadedFor, setLoadedFor] = useState({ open: false, mode, coupon });
  if (loadedFor.open !== open || loadedFor.mode !== mode || loadedFor.coupon !== coupon) {
    setLoadedFor({ open, mode, coupon });
    if (open) fillForm();
  }

  function fillForm() {
    if (mode === "edit" && coupon) {
      setCode(coupon.code);
      setName(coupon.name);
      const isFixed = coupon.discount.toLowerCase().includes("fixed") || coupon.discount.includes("৳");
      setDiscountType(isFixed ? "fixed" : "percent");
      const num = coupon.discount.replace(/[^\d.]/g, "");
      setDiscountValue(num || "0");
      setStatus(coupon.status);
      setLimit(coupon.limit != null ? String(coupon.limit) : "");
      setStartsAt(coupon.startsAt.slice(0, 10));
      setEndsAt(coupon.endsAt.slice(0, 10));
      setMinOrder("");
      return;
    }
    const today = new Date();
    const end = new Date(today.getTime() + 30 * 24 * 60 * 60 * 1000);
    const iso = (d: Date) => d.toISOString().slice(0, 10);
    setCode("");
    setName("");
    setDiscountType("percent");
    setDiscountValue("10");
    setStatus("active");
    setLimit("");
    setStartsAt(iso(today));
    setEndsAt(iso(end));
    setMinOrder("");
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        resizable
        closeButton="chevron"
        className="flex w-[420px] min-w-[160px] max-w-[720px] flex-col rounded-none p-0"
      >
        <SheetHeader className="border-b border-border px-4 py-3">
          <SheetTitle className="text-sm font-semibold">
            {mode === "create" ? "New coupon" : "Edit coupon"}
          </SheetTitle>
        </SheetHeader>
        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-4">
          <Field label="Code">
            <Input
              className="rounded-none uppercase"
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase())}
            />
          </Field>
          <Field label="Name">
            <Input className="rounded-none" value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Discount type">
              <Select
                className="rounded-none"
                value={discountType}
                onChange={(e) => setDiscountType(e.target.value as "percent" | "fixed")}
              >
                <option value="percent">Percent</option>
                <option value="fixed">Fixed (৳)</option>
              </Select>
            </Field>
            <Field label="Value">
              <Input
                type="number"
                className="rounded-none"
                value={discountValue}
                onChange={(e) => setDiscountValue(e.target.value)}
              />
            </Field>
          </div>
          <Field label="Status">
            <Select
              className="rounded-none"
              value={status}
              onChange={(e) => setStatus(e.target.value as CouponStatus)}
            >
              {STATUS_OPTIONS.map((key) => (
                <option key={key} value={key}>
                  {key}
                </option>
              ))}
            </Select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Starts">
              <Input
                type="date"
                className="rounded-none"
                value={startsAt}
                onChange={(e) => setStartsAt(e.target.value)}
              />
            </Field>
            <Field label="Ends">
              <Input
                type="date"
                className="rounded-none"
                value={endsAt}
                onChange={(e) => setEndsAt(e.target.value)}
              />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Redemption limit">
              <Input
                type="number"
                className="rounded-none"
                placeholder="Unlimited"
                value={limit}
                onChange={(e) => setLimit(e.target.value)}
              />
            </Field>
            <Field label="Min order (৳)">
              <Input
                type="number"
                className="rounded-none"
                placeholder="None"
                value={minOrder}
                onChange={(e) => setMinOrder(e.target.value)}
              />
            </Field>
          </div>
        </div>
        <div className="flex justify-end gap-2 border-t border-border px-4 py-3">
          <Button variant="outline" className="rounded-none" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            className="rounded-none"
            disabled={saving}
            onClick={() => {
              void (async () => {
                if (!code.trim() || !name.trim()) {
                  toast.error("Code and name are required");
                  return;
                }
                setSaving(true);
                try {
                  const payload = {
                    code: code.trim().toUpperCase(),
                    name: name.trim(),
                    discount_type: discountType,
                    discount_value: Number(discountValue) || 0,
                    status,
                    redemption_limit: limit.trim() ? Number(limit) : null,
                    starts_at: startsAt,
                    ends_at: endsAt,
                    min_order_amount: minOrder.trim() ? Number(minOrder) : null,
                  };
                  if (mode === "create") {
                    await createMarketingCoupon(payload);
                    toast.success("Coupon created");
                  } else if (coupon) {
                    await updateMarketingCoupon(coupon.id, payload);
                    toast.success("Coupon updated");
                  }
                  await onSaved();
                } catch (err) {
                  toast.error(err instanceof Error ? err.message : "Save failed");
                } finally {
                  setSaving(false);
                }
              })();
            }}
          >
            {saving ? "Saving…" : "Save"}
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      {children}
    </div>
  );
}
