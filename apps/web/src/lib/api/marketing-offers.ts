import { apiFetch } from "@/lib/api/client";

export type OfferStatus = "draft" | "scheduled" | "running" | "ended" | "disabled";

export type ApiOfferDeal = {
  id?: string;
  product_slug: string;
  offer_price: number;
  note?: string | null;
  priority: number;
  /** Deal quota — null/undefined means unlimited. */
  quantity?: number | null;
  /** Server-managed, incremented at checkout. Read-only in the UI. */
  quantity_sold?: number;
  /** Auto-flips off once quantity sells out; the admin can also toggle it. */
  enabled?: boolean;
  sort_order: number;
};

export type ApiOfferSection = {
  id?: string;
  key: string;
  label: string;
  sort_order: number;
  deals: ApiOfferDeal[];
};

export type ApiMarketingOffer = {
  id: string;
  slug: string;
  title: string;
  subtitle?: string | null;
  description: string;
  image_url?: string | null;
  /** When set, the offer's "View Details" and its own detail page both
   * redirect here instead of showing its product grid. */
  custom_link?: string | null;
  outlet_label: string;
  starts_at: string;
  ends_at: string;
  /** Optional nightly window — both null means "active all day". */
  daily_start_hour: number | null;
  daily_end_hour: number | null;
  status: OfferStatus;
  terms: string[];
  sort_order: number;
  sections: ApiOfferSection[];
  created_at: string;
  updated_at: string;
};

export type OfferWriteInput = {
  slug: string;
  title: string;
  subtitle?: string | null;
  description?: string;
  image_url?: string | null;
  custom_link?: string | null;
  outlet_label?: string;
  starts_at: string;
  ends_at: string;
  daily_start_hour?: number | null;
  daily_end_hour?: number | null;
  status: OfferStatus;
  terms?: string[];
  sort_order?: number;
  sections: {
    key?: string;
    label: string;
    sort_order?: number;
    deals: {
      product_slug: string;
      offer_price: number;
      note?: string | null;
      priority?: number;
      quantity?: number | null;
      enabled?: boolean;
      sort_order?: number;
    }[];
  }[];
};

type ListResponse = { data: ApiMarketingOffer[]; meta: { count: number } };
type ItemResponse = { data: ApiMarketingOffer };

export async function fetchMarketingOffers(params?: {
  search?: string;
  status?: string;
}): Promise<ApiMarketingOffer[]> {
  const q = new URLSearchParams();
  if (params?.search) q.set("search", params.search);
  if (params?.status) q.set("status", params.status);
  const qs = q.toString();
  const res = await apiFetch<ListResponse>(`/api/v1/marketing/offers${qs ? `?${qs}` : ""}`);
  return res.data ?? [];
}

export async function createMarketingOffer(input: OfferWriteInput): Promise<ApiMarketingOffer> {
  const res = await apiFetch<ItemResponse>("/api/v1/marketing/offers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return res.data;
}

export async function updateMarketingOffer(
  id: string,
  input: Partial<OfferWriteInput>,
): Promise<ApiMarketingOffer> {
  const res = await apiFetch<ItemResponse>(`/api/v1/marketing/offers/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return res.data;
}

export async function deleteMarketingOffer(id: string): Promise<void> {
  await apiFetch<void>(`/api/v1/marketing/offers/${id}`, { method: "DELETE" });
}
