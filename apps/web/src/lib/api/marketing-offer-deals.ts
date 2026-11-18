import { apiFetch } from "@/lib/api/client";

export type DealKind = "offer" | "happy_hour";

/** One deal (a product inside an Offer or a Happy Hour campaign), flattened for the Offer Products grid. */
export type ApiOfferDeal = {
  id: string; // = key, so the grid shell can use it
  key: string;
  kind: DealKind;
  deal_id: string;
  campaign_id: string;
  campaign_title: string;
  campaign_slug: string;
  campaign_status: string;
  starts_at: string | null;
  ends_at: string | null;
  daily_start_hour: number | null;
  daily_end_hour: number | null;
  section: string;
  /** the section (of its offer) the deal is in */
  section_id: string;
  product_slug: string;
  product_id: string | null;
  product_name: string;
  sku: string | null;
  /** the manufacturer's model number (the product's Model field) */
  model: string | null;
  thumbnail: string | null;
  brand: string | null;
  category: string | null;
  product_status: string;
  regular_price: number | null;
  offer_price: number;
  priority: number;
  quantity: number | null;
  quantity_sold: number;
  enabled: boolean;
  note: string | null;
  /** its price applies right now */
  live: boolean;
  /** and it is the one the shopper pays (lowest priority number among the product's live offers) */
  winner: boolean;
};

export type DealPatch = {
  offer_price?: number;
  priority?: number;
  quantity?: number | null;
  enabled?: boolean;
  note?: string | null;
  move_to_kind?: DealKind;
  move_to_campaign_id?: string;
  /** which section of the target offer (left out = its first section) */
  move_to_section_id?: string;
};

export async function fetchOfferDeals(): Promise<ApiOfferDeal[]> {
  const res = await apiFetch<{ data: Omit<ApiOfferDeal, "id">[] }>("/api/v1/marketing/offer-deals");
  return (res.data ?? []).map((r) => ({ ...r, id: r.key }));
}

export async function patchOfferDeal(kind: DealKind, dealId: string, body: DealPatch): Promise<void> {
  await apiFetch(`/api/v1/marketing/offer-deals/${kind}/${dealId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function deleteOfferDeal(kind: DealKind, dealId: string): Promise<void> {
  await apiFetch<void>(`/api/v1/marketing/offer-deals/${kind}/${dealId}`, { method: "DELETE" });
}
