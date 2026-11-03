"use client";

import "@/components/providers/ag-grid-provider";
import { useGridLayout } from "@/components/shared/use-grid-layout";
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AgGridReact } from "ag-grid-react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import {
  DndContext,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  GripVertical,
  ImageUp,
  MoreHorizontal,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import {
  createMarketingOffer,
  deleteMarketingOffer,
  updateMarketingOffer,
  type ApiMarketingOffer,
  type OfferStatus,
  type OfferWriteInput,
} from "@/lib/api/marketing-offers";
import { useMarketingOffers } from "@/lib/api/use-marketing-offers";
import { useCatalogCategories } from "@/lib/api/use-catalog-categories";
import { useCatalogProducts } from "@/lib/api/use-catalog-products";
import { fetchReferencePrices } from "@/lib/api/catalog-products";
import { useCatalogMedia, uploadCatalogMediaFiles } from "@/lib/api/use-catalog-media";
import { CategoryCombobox } from "@/components/categories/category-combobox";
import { ProductCombobox } from "@/components/products/product-combobox";
import { AgaincartClassicEditor } from "@/components/products/againcart-classic-editor";
import { MediaLibraryModal } from "@/components/media/media-library-modal";
import type { MediaLibraryItem } from "@/lib/mock-data/media-library";
import { useIsDark } from "@/lib/use-is-dark";
import { useAdminCanWrite } from "@/lib/hooks/use-admin-can-write";
import { useViewerWriteUrlGuard } from "@/lib/hooks/use-viewer-write-url-guard";
import { useApiHealth } from "@/lib/api/use-api-health";
import { ApiRefreshButton } from "@/components/products/api-refresh-button";
import { getApiBaseUrl } from "@/lib/api/client";
import { getStorefrontBaseUrl } from "@/lib/website/live-edit";
import type { Product } from "@/lib/mock-data/products";
import type { Category } from "@/lib/mock-data/categories";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
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

const PAGE_SIZE = 50;
const CATEGORY_ADD_LIMIT = 24;
const STATUS_OPTIONS: OfferStatus[] = ["draft", "scheduled", "running", "ended", "disabled"];

type DiscountMode = "percent" | "amount";

type DealDraft = {
  product_slug: string;
  product_name: string;
  regular_price: string;
  offer_price: string;
  note: string;
  priority: string;
  /** Deal quota — empty string means unlimited. */
  quantity: string;
  /** Server-managed, incremented at checkout. Read-only in the UI. */
  quantity_sold: number;
  /** Auto-flips off once quantity sells out; the admin can also toggle it. */
  enabled: boolean;
};

type SectionDraft = {
  id: string;
  key: string;
  label: string;
  category_id: string;
  discount_mode: DiscountMode;
  discount_value: string;
  deals: DealDraft[];
};

function buildUrl(params: URLSearchParams) {
  const q = params.toString();
  return q ? `/website/marketing/offers?${q}` : "/website/marketing/offers";
}

function toLocalInput(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function toIso(local: string) {
  const d = new Date(local);
  return Number.isNaN(d.getTime()) ? new Date().toISOString() : d.toISOString();
}

function newSectionId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `section-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function emptySection(): SectionDraft {
  return {
    id: newSectionId(),
    key: "",
    label: "",
    category_id: "",
    discount_mode: "percent",
    discount_value: "10",
    deals: [],
  };
}

/** The regular price of a product is its own selling price (Price BDT) - not the struck-through compare-at price. */
function productRegularPrice(product: Product): number {
  return Number(product.price) || 0;
}

function calcOfferPrice(
  regular: number,
  mode: DiscountMode,
  rawValue: string,
): number | null {
  const value = Number(rawValue);
  if (!Number.isFinite(regular) || regular <= 0) return null;
  if (!Number.isFinite(value) || value <= 0) return null;
  if (mode === "percent") {
    if (value >= 100) return null;
    return Math.max(1, Math.round(regular * (1 - value / 100)));
  }
  if (value >= regular) return null;
  return Math.max(1, Math.round(regular - value));
}

/** Builds a deal defaulting to a price the admin already configured on the
 * product (its currently active Special Price), falling back to the
 * product's own regular price when it has none — never a computed discount.
 * The admin edits the Offer column per-product from there. */
function dealFromProduct(
  product: Product,
  referencePrice: number | null | undefined,
  note = "",
): DealDraft | null {
  const regular = productRegularPrice(product);
  if (!Number.isFinite(regular) || regular <= 0) return null;
  const offer =
    referencePrice != null && referencePrice > 0 && referencePrice < regular
      ? referencePrice
      : regular;
  return {
    product_slug: product.slug,
    product_name: product.name,
    regular_price: String(regular),
    offer_price: String(Math.round(offer)),
    note,
    priority: "0",
    quantity: "",
    quantity_sold: 0,
    enabled: true,
  };
}

/** The products of a category AND of every category below it (Laptop covers Laptop > Gaming Laptop > Acer), however deep a product is filed. */
function productsForCategory(products: Product[], categoryId: string, categories: Category[]): Product[] {
  if (!categoryId) return [];
  const wanted = new Set<string>([categoryId]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const c of categories) {
      if (c.parentId && wanted.has(c.parentId) && !wanted.has(c.id)) {
        wanted.add(c.id);
        grew = true;
      }
    }
  }
  return products.filter((p) => (p.categoryIds || []).some((id) => wanted.has(id)));
}

function money(n: number | string) {
  const v = Number(n);
  if (!Number.isFinite(v)) return "—";
  return `৳${v.toLocaleString("en-US")}`;
}

function imagePreviewUrl(url: string): string {
  if (!url) return "";
  if (/^https?:\/\//i.test(url)) return url;
  if (url.startsWith("/uploads/")) return `${getApiBaseUrl()}${url}`;
  return `${getStorefrontBaseUrl()}${url.startsWith("/") ? "" : "/"}${url}`;
}

/** `terms` stays one entry per line — the editor just gives each line its own
 * block, so a term can carry inline formatting (bold, links, color) instead
 * of being plain text. */
function termsToEditorHtml(terms: string[]): string {
  return terms.map((t) => `<p>${t}</p>`).join("");
}

function editorHtmlToTerms(html: string): string[] {
  if (typeof document === "undefined") return [];
  const container = document.createElement("div");
  container.innerHTML = html;
  const blocks = Array.from(container.children).filter((el) =>
    ["P", "LI", "DIV", "H1", "H2", "H3", "H4"].includes(el.tagName),
  );
  const source = blocks.length ? blocks : [container];
  return source
    .map((el) => el.innerHTML.trim())
    .filter((t) => t && t !== "<br>");
}

export function OffersAdminPanel() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const isDark = useIsDark();
  const canWrite = useAdminCanWrite();
  const apiHealth = useApiHealth();
  const { offers: campaigns, loading, error, refetch } = useMarketingOffers();

  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");

  const createOpen = searchParams.get("create") === "1";
  const editId = searchParams.get("edit");
  const editCampaign = useMemo(
    () => (editId ? campaigns.find((c) => c.id === editId) ?? null : null),
    [editId, campaigns],
  );
  const formOpen = createOpen || !!editCampaign;

  useEffect(() => {
    if (error) toast.error(`API: ${error}`, { id: "marketing-offer-api" });
  }, [error]);

  const pushParams = (mutate: (p: URLSearchParams) => void) => {
    const p = new URLSearchParams(searchParams.toString());
    mutate(p);
    router.push(buildUrl(p), { scroll: false });
  };

  const openCreate = () =>
    pushParams((p) => {
      p.delete("edit");
      p.set("create", "1");
    });

  const openEdit = (row: ApiMarketingOffer) =>
    pushParams((p) => {
      p.delete("create");
      p.set("edit", row.id);
    });

  const closeForm = () =>
    pushParams((p) => {
      p.delete("create");
      p.delete("edit");
    });

  useViewerWriteUrlGuard(formOpen, closeForm);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return campaigns.filter((row) => {
      if (status !== "all" && row.status !== status) return false;
      if (!q) return true;
      return (
        row.title.toLowerCase().includes(q) ||
        row.slug.toLowerCase().includes(q) ||
        row.description.toLowerCase().includes(q)
      );
    });
  }, [campaigns, search, status]);

  const columnDefs = useMemo<ColDef<ApiMarketingOffer>[]>(
    () => [
      {
        field: "title",
        headerName: "Offer",
        flex: 1.6,
        minWidth: 180,
        cellRenderer: (p: ICellRendererParams<ApiMarketingOffer>) =>
          p.data ? (
            <button
              type="button"
              className="truncate text-left font-medium text-foreground hover:underline"
              onClick={(e) => {
                e.stopPropagation();
                openEdit(p.data!);
              }}
            >
              {p.data.title}
            </button>
          ) : null,
      },
      { field: "slug", headerName: "Slug", width: 140 },
      {
        field: "status",
        headerName: "Status",
        width: 110,
        cellRenderer: (p: ICellRendererParams<ApiMarketingOffer>) =>
          p.data ? (
            <Badge
              variant={p.data.status === "running" ? "default" : "secondary"}
              className="rounded-none capitalize"
            >
              {p.data.status}
            </Badge>
          ) : null,
      },
      {
        colId: "deals",
        headerName: "Deals",
        width: 90,
        valueGetter: (p) =>
          (p.data?.sections || []).reduce((sum, s) => sum + (s.deals?.length ?? 0), 0),
      },
      {
        colId: "actions",
        headerName: "",
        width: 56,
        pinned: "right",
        sortable: false,
        cellRenderer: (p: ICellRendererParams<ApiMarketingOffer>) =>
          p.data ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-7 w-7 rounded-none p-0">
                  <MoreHorizontal className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="rounded-none">
                <DropdownMenuItem onClick={() => openEdit(p.data!)}>
                  <Pencil className="mr-2 h-3.5 w-3.5" />
                  Edit
                </DropdownMenuItem>
                {canWrite ? (
                  <DropdownMenuItem
                    className="text-destructive"
                    onClick={() => {
                      void (async () => {
                        if (!confirm(`Delete “${p.data!.title}”?`)) return;
                        try {
                          await deleteMarketingOffer(p.data!.id);
                          toast.success("Deleted");
                          await refetch();
                        } catch (err) {
                          toast.error(err instanceof Error ? err.message : "Delete failed");
                        }
                      })();
                    }}
                  >
                    <Trash2 className="mr-2 h-3.5 w-3.5" />
                    Delete
                  </DropdownMenuItem>
                ) : null}
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null,
      },
    ],
    [canWrite, refetch],
  );

  // Column order + widths saved per admin (same as the other data tables).
  const layout = useGridLayout("marketing-offers", columnDefs);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          className="h-8 w-[220px] rounded-none"
          placeholder="Search…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <Select
          className="h-8 w-[140px] rounded-none"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="all">All status</option>
          {STATUS_OPTIONS.map((key) => (
            <option key={key} value={key}>
              {key}
            </option>
          ))}
        </Select>
        <ApiRefreshButton
          status={apiHealth.status}
          loading={loading}
          onRefresh={() => {
            void refetch();
            apiHealth.recheck();
          }}
        />
        {canWrite ? (
          <Button size="sm" className="ml-auto h-8 rounded-none" onClick={openCreate}>
            <Plus className="mr-1 h-3.5 w-3.5" />
            New
          </Button>
        ) : null}
      </div>

      <div style={layout.containerStyle} className={`ag-theme-quartz${isDark ? "-dark" : ""} min-h-0 flex-1`}>
        {loading && campaigns.length === 0 ? (
          <p className="p-4 text-sm text-muted-foreground">Loading Offers…</p>
        ) : filtered.length === 0 ? (
          <p className="p-4 text-sm text-muted-foreground">No offers match your filters.</p>
        ) : (
          <AgGridReact<ApiMarketingOffer>
            rowData={filtered}
            columnDefs={layout.columnDefs}
            {...layout.gridProps}
            getRowId={(p) => p.data.id}
            pagination
            paginationPageSize={PAGE_SIZE}
            paginationPageSizeSelector={[50, 100, 500, 1000]}
            suppressCellFocus
            rowHeight={40}
            headerHeight={36}
            onRowDoubleClicked={(e) => e.data && openEdit(e.data)}
          />
        )}
      </div>

      <OfferFormSheet
        open={formOpen}
        mode={createOpen ? "create" : "edit"}
        campaign={editCampaign}
        onOpenChange={(open) => {
          if (!open) closeForm();
        }}
        onSaved={async () => {
          await refetch();
          closeForm();
        }}
      />
    </div>
  );
}

function OfferFormSheet({
  open,
  mode,
  campaign,
  onOpenChange,
  onSaved,
}: {
  open: boolean;
  mode: "create" | "edit";
  campaign: ApiMarketingOffer | null;
  onOpenChange: (open: boolean) => void;
  onSaved: () => Promise<void>;
}) {
  const { categories, loading: categoriesLoading } = useCatalogCategories({ channel: "catalog" });
  const { products: allProducts, loading: productsLoading } = useCatalogProducts({ channel: "catalog" });
  const { items: mediaItems, refetch: refetchMedia } = useCatalogMedia();
  // A draft (or archived) product is never shown on the shop, so it cannot be picked for an offer. The full list is kept to look up
  // the products already in a deal (name, picture, price) and to flag the ones that are not published.
  const products = useMemo(() => allProducts.filter((p) => p.status === "published"), [allProducts]);
  const productsBySlug = useMemo(() => {
    const map = new Map<string, Product>();
    for (const p of allProducts) map.set(p.slug, p);
    return map;
  }, [allProducts]);

  const [title, setTitle] = useState("");
  const [slug, setSlug] = useState("");
  const [subtitle, setSubtitle] = useState("");
  const [description, setDescription] = useState("");
  const [imageUrl, setImageUrl] = useState("");
  const [imagePickerOpen, setImagePickerOpen] = useState(false);
  const [customLink, setCustomLink] = useState("");
  const [outlet, setOutlet] = useState("All Outlet");
  const [status, setStatus] = useState<OfferStatus>("running");
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [termsText, setTermsText] = useState("");
  const [sections, setSections] = useState<SectionDraft[]>([]);
  const [pickProductId, setPickProductId] = useState<Record<number, string>>({});
  const [saving, setSaving] = useState(false);
  const [editingSectionIndex, setEditingSectionIndex] = useState<number | null>(null);
  const [allProductsOpen, setAllProductsOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    setEditingSectionIndex(null);
    setAllProductsOpen(false);
    if (mode === "edit" && campaign) {
      setTitle(campaign.title);
      setSlug(campaign.slug);
      setSubtitle(campaign.subtitle || "");
      setDescription(campaign.description || "");
      setImageUrl(campaign.image_url || "");
      setCustomLink(campaign.custom_link || "");
      setOutlet(campaign.outlet_label || "All Outlet");
      setStatus(campaign.status);
      setStartsAt(toLocalInput(campaign.starts_at));
      setEndsAt(toLocalInput(campaign.ends_at));
      setTermsText(termsToEditorHtml(campaign.terms || []));
      setSections(
        (campaign.sections || []).map((s) => ({
          id: s.id || newSectionId(),
          key: s.key,
          label: s.label,
          category_id: "",
          discount_mode: "percent" as DiscountMode,
          discount_value: "10",
          deals: (s.deals || []).map((d) => ({
            product_slug: d.product_slug,
            product_name: d.product_slug,
            regular_price: "",
            offer_price: String(d.offer_price),
            note: d.note || "",
            priority: String(d.priority ?? 0),
            quantity: d.quantity != null ? String(d.quantity) : "",
            quantity_sold: d.quantity_sold ?? 0,
            enabled: d.enabled ?? true,
          })),
        })),
      );
      setPickProductId({});
      return;
    }
    const now = new Date();
    const end = new Date(now.getTime() + 90 * 24 * 60 * 60 * 1000);
    setTitle("");
    setSlug("");
    setSubtitle("");
    setDescription("");
    setImageUrl("");
    setCustomLink("");
    setOutlet("All Outlet");
    setStatus("running");
    setStartsAt(toLocalInput(now.toISOString()));
    setEndsAt(toLocalInput(end.toISOString()));
    setTermsText("");
    setSections([]);
    setPickProductId({});
  }, [open, mode, campaign]);

  // Enrich section category ids + deal names/prices once catalog loads (no form reset).
  useEffect(() => {
    if (!open || !categories.length) return;
    setSections((rows) =>
      rows.map((section) => {
        if (section.category_id) return section;
        const matched =
          categories.find((c) => c.slug === section.key) ||
          categories.find(
            (c) => c.name.trim().toLowerCase() === section.label.trim().toLowerCase(),
          );
        return matched ? { ...section, category_id: matched.id } : section;
      }),
    );
  }, [open, categories]);

  useEffect(() => {
    if (!open || !productsBySlug.size) return;
    setSections((rows) =>
      rows.map((section) => ({
        ...section,
        deals: section.deals.map((deal) => {
          const product = productsBySlug.get(deal.product_slug);
          if (!product) return deal;
          return {
            ...deal,
            product_name: product.name,
            regular_price: String(productRegularPrice(product)),
          };
        }),
      })),
    );
  }, [open, productsBySlug]);

  const updateSection = (index: number, patch: Partial<SectionDraft>) =>
    setSections((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  const updateDeal = (sectionIndex: number, dealIndex: number, patch: Partial<DealDraft>) =>
    setSections((rows) =>
      rows.map((row, i) =>
        i === sectionIndex
          ? {
              ...row,
              deals: row.deals.map((deal, j) => (j === dealIndex ? { ...deal, ...patch } : deal)),
            }
          : row,
      ),
    );

  const removeDeal = (sectionIndex: number, dealIndex: number) =>
    setSections((rows) =>
      rows.map((row, i) =>
        i === sectionIndex ? { ...row, deals: row.deals.filter((_, j) => j !== dealIndex) } : row,
      ),
    );

  const mergeDeals = (sectionIndex: number, incoming: DealDraft[], replace = false) => {
    setSections((rows) =>
      rows.map((row, i) => {
        if (i !== sectionIndex) return row;
        if (replace) return { ...row, deals: incoming };
        const seen = new Set(row.deals.map((d) => d.product_slug));
        const next = [...row.deals];
        for (const deal of incoming) {
          if (seen.has(deal.product_slug)) continue;
          seen.add(deal.product_slug);
          next.push(deal);
        }
        return { ...row, deals: next };
      }),
    );
  };

  const addCategoryProducts = async (sectionIndex: number, categoryIdOverride?: string) => {
    const section = sections[sectionIndex];
    const categoryId = categoryIdOverride ?? section?.category_id;
    if (!section || !categoryId) {
      toast.error("Select a category first");
      return;
    }
    const pool = productsForCategory(products, categoryId, categories);
    if (pool.length === 0) {
      toast.error("No catalog products in this category");
      return;
    }
    const picked = pool.slice(0, CATEGORY_ADD_LIMIT);
    let referencePrices: Record<string, number> = {};
    try {
      referencePrices = await fetchReferencePrices(picked.map((p) => p.slug));
    } catch {
      // Reference lookup is a convenience default — fall back to full price.
    }
    const deals: DealDraft[] = [];
    let skipped = 0;
    for (const product of picked) {
      const deal = dealFromProduct(product, referencePrices[product.slug] ?? null);
      if (!deal) {
        skipped += 1;
        continue;
      }
      deals.push(deal);
    }
    if (deals.length === 0) {
      toast.error("No valid products to add");
      return;
    }
    mergeDeals(sectionIndex, deals);
    const extra = pool.length > CATEGORY_ADD_LIMIT ? ` (first ${CATEGORY_ADD_LIMIT})` : "";
    toast.success(`Added ${deals.length} product${deals.length === 1 ? "" : "s"}${extra}`);
    if (skipped) toast.message(`${skipped} skipped (invalid regular price)`);
  };

  const applyDiscountToSection = (sectionIndex: number) => {
    const section = sections[sectionIndex];
    if (!section) return;
    const next = section.deals.map((deal) => {
      const regular = Number(deal.regular_price);
      const offer = calcOfferPrice(regular, section.discount_mode, section.discount_value);
      if (offer == null) return deal;
      return { ...deal, offer_price: String(offer) };
    });
    mergeDeals(sectionIndex, next, true);
    toast.success("Discount re-applied to section deals");
  };

  const addPickedProduct = async (sectionIndex: number, productId: string) => {
    if (!productId) return;
    const section = sections[sectionIndex];
    const product = products.find((p) => p.id === productId);
    if (!section || !product) return;
    if (section.deals.some((d) => d.product_slug === product.slug)) {
      toast.message("Product already in this section");
      setPickProductId((prev) => ({ ...prev, [sectionIndex]: "" }));
      return;
    }
    let referencePrice: number | null = null;
    try {
      const prices = await fetchReferencePrices([product.slug]);
      referencePrice = prices[product.slug] ?? null;
    } catch {
      // Reference lookup is a convenience default — fall back to full price.
    }
    const deal = dealFromProduct(product, referencePrice);
    if (!deal) {
      toast.error("This product has no valid regular price");
      return;
    }
    mergeDeals(sectionIndex, [deal]);
    setPickProductId((prev) => ({ ...prev, [sectionIndex]: "" }));
  };

  const categoriesForPicker = useMemo(() => {
    const byId = new Map(categories.map((c) => [c.id, c]));
    const extras: Category[] = [];
    for (const section of sections) {
      if (!section.category_id || byId.has(section.category_id)) continue;
      extras.push({
        id: section.category_id,
        name: section.label || section.key || "Category",
        caption: section.key,
        slug: section.key || section.category_id,
        parentId: null,
        sortOrder: 9999,
        productCount: 0,
        active: true,
        showInTopMenu: false,
        updatedAt: "",
      });
    }
    return extras.length ? [...categories, ...extras] : categories;
  }, [categories, sections]);

  const sectionDragSensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
  );
  const sectionIds = useMemo(() => sections.map((s) => s.id), [sections]);
  const handleSectionDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = sections.findIndex((s) => s.id === active.id);
    const newIndex = sections.findIndex((s) => s.id === over.id);
    if (oldIndex < 0 || newIndex < 0) return;
    setSections((rows) => arrayMove(rows, oldIndex, newIndex));
  };

  const handleImageSelect = (items: MediaLibraryItem[]) => {
    if (items.length === 0) {
      setImagePickerOpen(false);
      return;
    }
    setImageUrl(items[0].url);
    setImagePickerOpen(false);
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        resizable
        closeButton="chevron"
        className="flex w-[560px] min-w-[160px] max-w-[800px] flex-col rounded-none p-0"
      >
        <SheetHeader className="border-b border-border px-4 py-3">
          <SheetTitle className="text-sm font-semibold">
            {mode === "create" ? "New Offer" : "Edit Offer"}
          </SheetTitle>
        </SheetHeader>
        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-4">
          <Field label="Title">
            <Input className="rounded-none" value={title} onChange={(e) => setTitle(e.target.value)} />
          </Field>
          <Field label="Slug">
            <Input className="rounded-none" value={slug} onChange={(e) => setSlug(e.target.value)} />
          </Field>
          <Field label="Subtitle (optional)">
            <Input className="rounded-none" value={subtitle} onChange={(e) => setSubtitle(e.target.value)} />
          </Field>
          <Field label="Description">
            <AgaincartClassicEditor
              value={description}
              onChange={setDescription}
              placeholder="Offer description…"
              minRows={3}
              fieldLabel="Description"
            />
          </Field>

          <Field label="Card image">
            <div className="flex items-center gap-2">
              <div className="relative h-16 w-16 shrink-0 overflow-hidden rounded-none border border-border bg-muted/40">
                {imageUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={imagePreviewUrl(imageUrl)}
                    alt=""
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <div className="flex h-full items-center justify-center text-[9px] text-muted-foreground">
                    No image
                  </div>
                )}
              </div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-8 gap-1.5 rounded-none"
                onClick={() => {
                  void refetchMedia();
                  setImagePickerOpen(true);
                }}
              >
                <ImageUp className="h-3.5 w-3.5" />
                {imageUrl ? "Change" : "Add image"}
              </Button>
              {imageUrl ? (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="h-8 rounded-none text-destructive"
                  onClick={() => setImageUrl("")}
                >
                  Remove
                </Button>
              ) : null}
            </div>
          </Field>

          <Field label="Custom link (optional)">
            <Input
              className="rounded-none"
              value={customLink}
              onChange={(e) => setCustomLink(e.target.value)}
              placeholder="https://… or /some-page"
            />
            <p className="mt-1 text-[10px] text-muted-foreground">
              When set, this offer skips its own product page — "View Details" on the Offers list
              and this offer's own URL both send shoppers straight here instead. Sections become
              optional.
            </p>
          </Field>

          <Field label="Outlet label">
            <Input className="rounded-none" value={outlet} onChange={(e) => setOutlet(e.target.value)} />
          </Field>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Status">
              <Select
                className="rounded-none"
                value={status}
                onChange={(e) => setStatus(e.target.value as OfferStatus)}
              >
                {STATUS_OPTIONS.map((key) => (
                  <option key={key} value={key}>
                    {key}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Offer starts">
              <Input
                type="datetime-local"
                className="rounded-none"
                value={startsAt}
                onChange={(e) => setStartsAt(e.target.value)}
              />
            </Field>
            <Field label="Offer ends">
              <Input
                type="datetime-local"
                className="rounded-none"
                value={endsAt}
                onChange={(e) => setEndsAt(e.target.value)}
              />
            </Field>
          </div>

          <div className="space-y-2 border border-border p-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs font-semibold text-foreground">Sections</p>
              <div className="flex gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="h-7 rounded-none"
                  disabled={sections.every((s) => s.deals.length === 0)}
                  onClick={() => setAllProductsOpen(true)}
                >
                  View Offer Products
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="h-7 rounded-none"
                  onClick={() => {
                    const newIndex = sections.length;
                    setSections((rows) => [...rows, emptySection()]);
                    setEditingSectionIndex(newIndex);
                  }}
                >
                  <Plus className="mr-1 h-3.5 w-3.5" />
                  Add section
                </Button>
              </div>
            </div>
            {(categoriesLoading || productsLoading) && (
              <p className="text-xs text-muted-foreground">Loading catalog…</p>
            )}

            {sections.length === 0 ? (
              <p className="text-[11px] text-muted-foreground">
                No sections yet. Add one, then pick a category or product inside it.
              </p>
            ) : (
              <DndContext
                sensors={sectionDragSensors}
                collisionDetection={closestCenter}
                onDragEnd={handleSectionDragEnd}
              >
                <SortableContext items={sectionIds} strategy={verticalListSortingStrategy}>
                  <div className="space-y-1.5">
                    {sections.map((section, sIndex) => {
                      const category = categoriesForPicker.find((c) => c.id === section.category_id);
                      return (
                        <SortableSectionRow key={section.id} id={section.id}>
                          <button
                            type="button"
                            className="min-w-0 flex-1 text-left"
                            onClick={() => setEditingSectionIndex(sIndex)}
                          >
                            <p className="truncate text-xs font-medium text-foreground">
                              {section.label || "Untitled section"}
                            </p>
                            <p className="truncate text-[10px] text-muted-foreground">
                              {section.deals.length} product{section.deals.length === 1 ? "" : "s"}
                              {category ? ` · ${category.name}` : ""}
                            </p>
                          </button>
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            className="h-7 rounded-none"
                            onClick={() => setEditingSectionIndex(sIndex)}
                          >
                            <Pencil className="mr-1 h-3.5 w-3.5" />
                            Edit
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 rounded-none"
                            onClick={() => setSections((rows) => rows.filter((_, i) => i !== sIndex))}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </SortableSectionRow>
                      );
                    })}
                  </div>
                </SortableContext>
              </DndContext>
            )}
          </div>

          <SectionEditorSheet
            open={editingSectionIndex !== null}
            section={editingSectionIndex !== null ? sections[editingSectionIndex] ?? null : null}
            categoriesForPicker={categoriesForPicker}
            products={products}
            productsBySlug={productsBySlug}
            pickProductId={editingSectionIndex !== null ? pickProductId[editingSectionIndex] || "" : ""}
            onPickProductId={(id) => {
              if (editingSectionIndex === null) return;
              setPickProductId((prev) => ({ ...prev, [editingSectionIndex]: id }));
            }}
            onUpdateSection={(patch) => {
              if (editingSectionIndex !== null) updateSection(editingSectionIndex, patch);
            }}
            onUpdateDeal={(dealIndex, patch) => {
              if (editingSectionIndex !== null) updateDeal(editingSectionIndex, dealIndex, patch);
            }}
            onRemoveDeal={(dealIndex) => {
              if (editingSectionIndex !== null) removeDeal(editingSectionIndex, dealIndex);
            }}
            onAddCategoryProducts={() => {
              if (editingSectionIndex !== null) addCategoryProducts(editingSectionIndex);
            }}
            onCategorySelected={(categoryId) => {
              if (editingSectionIndex !== null) addCategoryProducts(editingSectionIndex, categoryId);
            }}
            onApplyDiscount={() => {
              if (editingSectionIndex !== null) applyDiscountToSection(editingSectionIndex);
            }}
            onAddPickedProduct={(id) => {
              if (editingSectionIndex !== null) addPickedProduct(editingSectionIndex, id);
            }}
            onClose={() => {
              if (editingSectionIndex !== null) {
                const s = sections[editingSectionIndex];
                if (s && !s.label.trim() && s.deals.length === 0) {
                  setSections((rows) => rows.filter((_, i) => i !== editingSectionIndex));
                }
              }
              setEditingSectionIndex(null);
            }}
          />

          <AllProductsSheet
            open={allProductsOpen}
            sections={sections}
            productsBySlug={productsBySlug}
            onUpdateDeal={updateDeal}
            onRemoveDeal={removeDeal}
            onClose={() => setAllProductsOpen(false)}
          />

          <Field label="Terms (each paragraph is one term)">
            <AgaincartClassicEditor
              value={termsText}
              onChange={setTermsText}
              placeholder="One term per paragraph…"
              minRows={4}
              fieldLabel="Terms"
            />
          </Field>
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
                if (!title.trim() || !slug.trim()) {
                  toast.error("Title and slug are required");
                  return;
                }
                const cleanSections = sections
                  .filter((s) => s.label.trim())
                  .map((s, i) => ({
                    key:
                      s.key ||
                      s.label
                        .trim()
                        .toLowerCase()
                        .replace(/[^a-z0-9]+/g, "-")
                        .replace(/(^-|-$)/g, ""),
                    label: s.label.trim(),
                    sort_order: i,
                    deals: s.deals
                      .filter((d) => d.product_slug.trim() && Number(d.offer_price) > 0)
                      .map((d, j) => ({
                        product_slug: d.product_slug.trim(),
                        offer_price: Number(d.offer_price),
                        note: d.note.trim() || null,
                        priority: Number(d.priority) || 0,
                        quantity:
                          d.quantity.trim() === "" ? null : Number(d.quantity) || 0,
                        enabled: d.enabled,
                        sort_order: j,
                      })),
                  }))
                  .filter((s) => s.deals.length > 0);
                if (cleanSections.length === 0 && !customLink.trim()) {
                  toast.error("Add at least one section with a valid deal, or set a custom link");
                  return;
                }
                const payload: OfferWriteInput = {
                  title: title.trim(),
                  slug: slug.trim(),
                  subtitle: subtitle.trim() || null,
                  description: description.trim(),
                  image_url: imageUrl.trim() || null,
                  custom_link: customLink.trim() || null,
                  outlet_label: outlet.trim() || "All Outlet",
                  status,
                  starts_at: toIso(startsAt),
                  ends_at: toIso(endsAt),
                  terms: editorHtmlToTerms(termsText),
                  sections: cleanSections,
                };
                setSaving(true);
                try {
                  if (mode === "create") {
                    await createMarketingOffer(payload);
                    toast.success("Offer created");
                  } else if (campaign) {
                    await updateMarketingOffer(campaign.id, payload);
                    toast.success("Offer updated");
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

      <MediaLibraryModal
        open={imagePickerOpen}
        onOpenChange={(next) => {
          if (!next) setImagePickerOpen(false);
          else void refetchMedia();
        }}
        items={mediaItems}
        mode="single"
        title="Choose offer card image"
        accept={["image"]}
        initialSelectedIds={[]}
        onSelect={handleImageSelect}
        onUploadFiles={async (files) => {
          const uploaded = await uploadCatalogMediaFiles(files);
          await refetchMedia();
          return uploaded;
        }}
      />
    </Sheet>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground">
        {label}
        {hint ? <span className="ml-1 font-normal text-muted-foreground/70">({hint})</span> : null}
      </Label>
      {children}
    </div>
  );
}

/** One drag-and-drop-able row in the section list. */
function SortableSectionRow({ id, children }: { id: string; children: React.ReactNode }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id,
  });
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(
        "flex items-center justify-between gap-2 border border-border bg-muted/20 px-2.5 py-2",
        isDragging && "z-10 opacity-90 shadow-md ring-1 ring-primary/40",
      )}
    >
      <button
        type="button"
        className="shrink-0 touch-none px-0.5 text-muted-foreground hover:text-foreground"
        aria-label="Drag to reorder"
        {...attributes}
        {...listeners}
      >
        <GripVertical className="h-4 w-4 cursor-grab active:cursor-grabbing" />
      </button>
      {children}
    </div>
  );
}

type DealRow = {
  key: string;
  deal: DealDraft;
  sectionLabel?: string;
  onUpdate: (patch: Partial<DealDraft>) => void;
  onRemove: () => void;
};

/** Shared product-deal table — used inside a single section's editor and in
    the cross-section "View Offer Products" drawer (which adds the Section
    column). Identical to Happy Hour's DealsTable. */
function DealsTable({
  rows,
  productsBySlug,
  showSection = false,
}: {
  rows: DealRow[];
  productsBySlug: Map<string, Product>;
  showSection?: boolean;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const updateScrollFades = () => {
    const el = scrollRef.current;
    if (!el) return;
    setCanScrollLeft(el.scrollLeft > 2);
    setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 2);
  };

  useEffect(() => {
    updateScrollFades();
    const el = scrollRef.current;
    if (!el) return;
    el.addEventListener("scroll", updateScrollFades);
    window.addEventListener("resize", updateScrollFades);
    return () => {
      el.removeEventListener("scroll", updateScrollFades);
      window.removeEventListener("resize", updateScrollFades);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-measure whenever the row count changes
  }, [rows.length]);

  if (rows.length === 0) {
    return <p className="text-[11px] text-muted-foreground">No deals yet.</p>;
  }
  return (
    <div className="relative">
      <div
        ref={scrollRef}
        className="overflow-x-auto border border-border/60 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
      <table className="w-full min-w-[560px] table-fixed border-collapse text-[11px]">
        <thead>
          <tr className="bg-muted/40 text-left">
            <th className="w-9 px-1.5 py-1 font-medium" />
            <th className="px-1.5 py-1 font-medium">Product</th>
            {showSection ? <th className="w-24 px-1.5 py-1 font-medium">Section</th> : null}
            <th className="w-16 px-1.5 py-1 font-medium">Regular</th>
            <th className="w-10 px-1.5 py-1 font-medium">Qty</th>
            <th className="w-24 px-1.5 py-1 font-medium">Stock</th>
            <th className="w-28 px-1.5 py-1 font-medium">Offer ৳</th>
            <th className="w-14 px-1.5 py-1 font-medium">Priority</th>
            <th className="w-28 px-1.5 py-1 font-medium">Quantity</th>
            <th className="w-14 px-1.5 py-1 font-medium">Enabled</th>
            <th className="w-8 px-1.5 py-1" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const { deal } = row;
            const product = productsBySlug.get(deal.product_slug);
            return (
              <tr
                key={row.key}
                className={cn(
                  "border-t border-border/60 align-top",
                  !deal.enabled && "bg-muted/30 opacity-60",
                )}
              >
                <td className="px-1.5 py-1.5">
                  {product?.thumbnail ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={product.thumbnail}
                      alt=""
                      className="h-7 w-7 rounded-none border border-border object-cover"
                    />
                  ) : (
                    <div className="h-7 w-7 rounded-none border border-dashed border-border bg-muted/30" />
                  )}
                </td>
                <td className="min-w-0 px-1.5 py-1.5">
                  <p className="truncate font-medium text-foreground">
                    {deal.product_name || deal.product_slug}
                  </p>
                  {product && product.status !== "published" ? (
                    <p className="text-[10px] font-medium text-destructive">
                      {product.status === "draft" ? "Draft" : `Not published (${product.status})`} - not shown on the site until it is published
                    </p>
                  ) : null}
                  <Input
                    className="mt-1 h-6 rounded-none text-[10px]"
                    placeholder="Note (optional)"
                    value={deal.note}
                    onChange={(e) => row.onUpdate({ note: e.target.value })}
                  />
                </td>
                {showSection ? (
                  <td className="truncate px-1.5 py-1.5 text-muted-foreground">{row.sectionLabel}</td>
                ) : null}
                <td className="px-1.5 py-1.5 text-muted-foreground">
                  {deal.regular_price ? money(deal.regular_price) : "—"}
                  {product && Number(product.compareAtPrice) > (Number(deal.regular_price) || 0) ? (
                    <span className="block text-[10px] line-through" title="Compare at price (struck through on the shop)">
                      {money(product.compareAtPrice as number)}
                    </span>
                  ) : null}
                </td>
                <td className="px-1.5 py-1.5 text-muted-foreground">{product ? product.stock : "—"}</td>
                <td className="px-1.5 py-1.5">
                  {product ? (
                    <Badge
                      variant={product.stockStatus === "In Stock" ? "default" : "secondary"}
                      className="rounded-none whitespace-nowrap"
                    >
                      {product.stockStatus}
                    </Badge>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="px-1.5 py-1.5">
                  <Input
                    className="h-7 rounded-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                    type="number"
                    value={deal.offer_price}
                    onChange={(e) => row.onUpdate({ offer_price: e.target.value })}
                  />
                </td>
                <td className="px-1.5 py-1.5">
                  <Input
                    className="h-7 rounded-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                    type="number"
                    value={deal.priority}
                    onChange={(e) => row.onUpdate({ priority: e.target.value })}
                  />
                </td>
                <td className="px-1.5 py-1.5">
                  <Input
                    className="h-7 rounded-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                    type="number"
                    min={0}
                    value={deal.quantity}
                    onChange={(e) => row.onUpdate({ quantity: e.target.value })}
                    placeholder="Unlimited"
                    title="Deal quota, separate from stock. Leave blank for unlimited. Once sold out this deal auto-disables."
                  />
                  {deal.quantity.trim() !== "" ? (
                    <p className="mt-0.5 whitespace-nowrap text-[10px] text-muted-foreground">
                      Sold {deal.quantity_sold}/{deal.quantity}
                    </p>
                  ) : null}
                </td>
                <td className="px-1.5 py-1.5 text-center">
                  <input
                    type="checkbox"
                    checked={deal.enabled}
                    onChange={(e) => row.onUpdate({ enabled: e.target.checked })}
                    title={
                      deal.enabled
                        ? "Enabled — applies its price"
                        : "Disabled — price does not apply, but the row stays here"
                    }
                    className="h-4 w-4 accent-primary"
                  />
                </td>
                <td className="px-1.5 py-1.5">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 rounded-none"
                    onClick={row.onRemove}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="border-t border-border/60 bg-muted/20 px-2 py-1 text-[10px] text-muted-foreground">
        Lower priority number shows first when a product appears more than once.
      </p>
      </div>
      {canScrollLeft ? (
        <div className="pointer-events-none absolute inset-y-0 left-0 w-6 bg-gradient-to-r from-background to-transparent" />
      ) : null}
      {canScrollRight ? (
        <div className="pointer-events-none absolute inset-y-0 right-0 w-6 bg-gradient-to-l from-background to-transparent" />
      ) : null}
    </div>
  );
}

/** Popup drawer for one section: name it, pick a category or products, set the
    discount, and edit each product's offer price / priority. */
function SectionEditorSheet({
  open,
  section,
  categoriesForPicker,
  products,
  productsBySlug,
  pickProductId,
  onPickProductId,
  onUpdateSection,
  onUpdateDeal,
  onRemoveDeal,
  onAddCategoryProducts,
  onCategorySelected,
  onApplyDiscount,
  onAddPickedProduct,
  onClose,
}: {
  open: boolean;
  section: SectionDraft | null;
  categoriesForPicker: Category[];
  products: Product[];
  productsBySlug: Map<string, Product>;
  pickProductId: string;
  onPickProductId: (id: string) => void;
  onUpdateSection: (patch: Partial<SectionDraft>) => void;
  onUpdateDeal: (dealIndex: number, patch: Partial<DealDraft>) => void;
  onRemoveDeal: (dealIndex: number) => void;
  onAddCategoryProducts: () => void;
  onCategorySelected: (categoryId: string) => void;
  onApplyDiscount: () => void;
  onAddPickedProduct: (productId: string) => void;
  onClose: () => void;
}) {
  const categoryProducts = section ? productsForCategory(products, section.category_id, categoriesForPicker) : [];
  const pickerProducts = section?.category_id
    ? categoryProducts.length
      ? categoryProducts
      : products
    : products;

  const rows: DealRow[] =
    section?.deals.map((deal, dIndex) => ({
      key: `${deal.product_slug}-${dIndex}`,
      deal,
      onUpdate: (patch: Partial<DealDraft>) => onUpdateDeal(dIndex, patch),
      onRemove: () => onRemoveDeal(dIndex),
    })) ?? [];

  return (
    <Sheet
      open={open}
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
    >
      <SheetContent
        side="right"
        resizable
        closeButton="chevron"
        className="flex w-[640px] min-w-[320px] max-w-[900px] flex-col rounded-none p-0"
      >
        <SheetHeader className="border-b border-border px-4 py-3">
          <SheetTitle className="text-sm font-semibold">
            {section?.label ? section.label : "New section"}
          </SheetTitle>
        </SheetHeader>
        {section ? (
          <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-4">
            <Field label="Section label">
              <Input
                className="rounded-none"
                placeholder="e.g. Monitor"
                value={section.label}
                onChange={(e) =>
                  onUpdateSection({
                    label: e.target.value,
                    key:
                      section.key ||
                      e.target.value
                        .toLowerCase()
                        .replace(/[^a-z0-9]+/g, "-")
                        .replace(/(^-|-$)/g, ""),
                  })
                }
              />
            </Field>

            <Field label="Category">
              <CategoryCombobox
                categories={categoriesForPicker}
                value={section.category_id}
                placeholder="Search category…"
                className="w-full"
                onChange={(id, name) => {
                  const cat = categoriesForPicker.find((c) => c.id === id);
                  const prev = categoriesForPicker.find((c) => c.id === section.category_id);
                  const shouldFillLabel =
                    !section.label.trim() || (prev && section.label.trim() === prev.name.trim());
                  onUpdateSection({
                    category_id: id,
                    key: cat?.slug || section.key,
                    label: shouldFillLabel && name ? name : section.label,
                  });
                  if (id) onCategorySelected(id);
                }}
              />
            </Field>

            <div className="grid grid-cols-[120px_1fr] gap-2">
              <Field label="Discount type">
                <Select
                  className="rounded-none"
                  value={section.discount_mode}
                  onChange={(e) =>
                    onUpdateSection({ discount_mode: e.target.value as DiscountMode })
                  }
                >
                  <option value="percent">Percent %</option>
                  <option value="amount">Fixed ৳ off</option>
                </Select>
              </Field>
              <Field label={section.discount_mode === "percent" ? "Percent off" : "৳ amount off"}>
                <Input
                  type="number"
                  min={1}
                  className="rounded-none"
                  value={section.discount_value}
                  onChange={(e) => onUpdateSection({ discount_value: e.target.value })}
                  placeholder={section.discount_mode === "percent" ? "10" : "500"}
                />
              </Field>
            </div>

            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-7 rounded-none"
                onClick={onAddCategoryProducts}
              >
                Add category products
                {section.category_id ? ` (${categoryProducts.length})` : ""}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-7 rounded-none"
                disabled={section.deals.length === 0}
                onClick={onApplyDiscount}
              >
                Re-apply discount
              </Button>
            </div>

            <Field label="Add single product">
              <ProductCombobox
                products={pickerProducts}
                value={pickProductId}
                placeholder="Search product…"
                onChange={(id) => {
                  onPickProductId(id);
                  if (id) onAddPickedProduct(id);
                }}
              />
            </Field>

            <DealsTable rows={rows} productsBySlug={productsBySlug} />
          </div>
        ) : null}
        <div className="flex justify-end gap-2 border-t border-border px-4 py-3">
          <Button className="rounded-none" onClick={onClose}>
            Done
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}

/** "View Offer Products" drawer: every product across every section in one
    flat, editable table so the admin doesn't have to open each section to
    tweak an offer price. */
function AllProductsSheet({
  open,
  sections,
  productsBySlug,
  onUpdateDeal,
  onRemoveDeal,
  onClose,
}: {
  open: boolean;
  sections: SectionDraft[];
  productsBySlug: Map<string, Product>;
  onUpdateDeal: (sectionIndex: number, dealIndex: number, patch: Partial<DealDraft>) => void;
  onRemoveDeal: (sectionIndex: number, dealIndex: number) => void;
  onClose: () => void;
}) {
  const [search, setSearch] = useState("");
  const [sectionFilter, setSectionFilter] = useState("all");
  const [discountMode, setDiscountMode] = useState<DiscountMode>("percent");
  const [discountValue, setDiscountValue] = useState("10");

  useEffect(() => {
    if (!open) {
      setSearch("");
      setSectionFilter("all");
      setDiscountMode("percent");
      setDiscountValue("10");
    }
  }, [open]);

  const allRows: DealRow[] = sections.flatMap((section, sIndex) =>
    section.deals.map((deal, dIndex) => ({
      key: `${sIndex}-${deal.product_slug}-${dIndex}`,
      deal,
      sectionLabel: section.label || "Untitled section",
      onUpdate: (patch: Partial<DealDraft>) => onUpdateDeal(sIndex, dIndex, patch),
      onRemove: () => onRemoveDeal(sIndex, dIndex),
    })),
  );

  const sectionOptions = useMemo(
    () => Array.from(new Set(sections.map((s) => s.label || "Untitled section"))),
    [sections],
  );

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return allRows.filter((row) => {
      if (sectionFilter !== "all" && row.sectionLabel !== sectionFilter) return false;
      if (!q) return true;
      return (
        row.deal.product_name.toLowerCase().includes(q) ||
        row.deal.product_slug.toLowerCase().includes(q)
      );
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allRows, search, sectionFilter]);

  const applyDiscountToShown = () => {
    let applied = 0;
    let skipped = 0;
    for (const row of rows) {
      const regular = Number(row.deal.regular_price);
      const offer = calcOfferPrice(regular, discountMode, discountValue);
      if (offer == null) {
        skipped += 1;
        continue;
      }
      row.onUpdate({ offer_price: String(offer) });
      applied += 1;
    }
    if (applied === 0) {
      toast.error("Discount too high — no valid offer prices");
      return;
    }
    toast.success(`Discount applied to ${applied} product${applied === 1 ? "" : "s"}`);
    if (skipped) toast.message(`${skipped} skipped (discount ≥ regular price)`);
  };

  return (
    <Sheet
      open={open}
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
    >
      <SheetContent
        side="right"
        resizable
        closeButton="chevron"
        className="flex w-[760px] min-w-[400px] max-w-[1000px] flex-col rounded-none p-0"
      >
        <SheetHeader className="border-b border-border px-4 py-3">
          <SheetTitle className="text-sm font-semibold">
            All offer products ({rows.length}
            {rows.length !== allRows.length ? ` of ${allRows.length}` : ""})
          </SheetTitle>
        </SheetHeader>
        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-4">
          <div className="flex flex-wrap items-end gap-2 border border-border/60 bg-muted/20 p-2">
            <Field label="Discount type">
              <Select
                className="h-8 w-[110px] rounded-none"
                value={discountMode}
                onChange={(e) => setDiscountMode(e.target.value as DiscountMode)}
              >
                <option value="percent">Percent %</option>
                <option value="amount">৳ amount</option>
              </Select>
            </Field>
            <Field label={discountMode === "percent" ? "Percent off" : "৳ amount off"}>
              <Input
                className="h-8 w-[100px] rounded-none"
                type="number"
                value={discountValue}
                onChange={(e) => setDiscountValue(e.target.value)}
                placeholder={discountMode === "percent" ? "10" : "500"}
              />
            </Field>
            <Button
              type="button"
              variant="outline"
              className="h-8 rounded-none"
              disabled={rows.length === 0}
              onClick={applyDiscountToShown}
            >
              Apply to shown ({rows.length})
            </Button>
          </div>
          <div className="flex flex-wrap gap-2">
            <Input
              className="h-8 w-[220px] rounded-none"
              placeholder="Search product…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <Select
              className="h-8 w-[180px] rounded-none"
              value={sectionFilter}
              onChange={(e) => setSectionFilter(e.target.value)}
            >
              <option value="all">All sections</option>
              {sectionOptions.map((label) => (
                <option key={label} value={label}>
                  {label}
                </option>
              ))}
            </Select>
          </div>
          <DealsTable rows={rows} productsBySlug={productsBySlug} showSection />
        </div>
        <div className="flex justify-end gap-2 border-t border-border px-4 py-3">
          <Button className="rounded-none" onClick={onClose}>
            Close
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
