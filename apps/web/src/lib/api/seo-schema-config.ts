import { apiFetch } from "@/lib/api/client";

export type SeoSchemaConfig = {
  enabled: boolean;
  business: {
    name: string;
    legal_name: string;
    logo_url: string;
    phones: string[];
    email: string;
    store_type: "OnlineStore" | "Store" | "ElectronicsStore" | "LocalBusiness";
    price_range: string;
    address: { street: string; locality: string; region: string; postal_code: string; country: string };
    social: { facebook: string; instagram: string; youtube: string; tiktok: string; x: string; linkedin: string };
  };
  pages: { home: boolean; category: boolean; brand: boolean; product: boolean; branches: boolean; offers: boolean; info: boolean };
  product: {
    item_condition: "NewCondition" | "UsedCondition" | "RefurbishedCondition";
    price_valid_days: number;
    return_days: number;
    return_policy_url: string;
  };
  meta: {
    home_title: string;
    home_description: string;
    category_title: string;
    category_description: string;
    brand_title: string;
    brand_description: string;
    product_title: string;
    product_description: string;
  };
};

export async function fetchSeoSchemaConfig(): Promise<SeoSchemaConfig> {
  const res = await apiFetch<{ data: SeoSchemaConfig }>("/api/v1/seo/schema-config");
  return res.data;
}

export async function saveSeoSchemaConfig(config: SeoSchemaConfig): Promise<SeoSchemaConfig> {
  const res = await apiFetch<{ data: SeoSchemaConfig }>("/api/v1/seo/schema-config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  return res.data;
}
