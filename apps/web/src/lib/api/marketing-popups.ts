import { apiFetch } from "@/lib/api/client";

export type PopupKind = "happy_hour" | "offer" | "notice" | "image";
export type PopupStatus = "draft" | "active" | "disabled";
export type PopupFrequency = "session" | "days" | "always";
export type PopupPages = "home" | "all" | "paths";
export type PopupDevices = "all" | "desktop" | "mobile";

export type PopupWriteInput = {
  name: string;
  kind: PopupKind;
  status: PopupStatus;
  title: string;
  body: string;
  image_url: string | null;
  button_label: string;
  link_url: string;
  campaign_slug: string;
  starts_at: string | null;
  ends_at: string | null;
  delay_seconds: number;
  frequency: PopupFrequency;
  frequency_days: number;
  pages: PopupPages;
  paths: string[];
  devices: PopupDevices;
  priority: number;
};

export type ApiMarketingPopup = PopupWriteInput & {
  id: string;
  created_at: string;
  updated_at: string;
};

export async function fetchMarketingPopups(): Promise<ApiMarketingPopup[]> {
  const res = await apiFetch<{ data: ApiMarketingPopup[] }>("/api/v1/marketing/popups");
  return res.data ?? [];
}

export async function createMarketingPopup(input: PopupWriteInput): Promise<ApiMarketingPopup> {
  const res = await apiFetch<{ data: ApiMarketingPopup }>("/api/v1/marketing/popups", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return res.data;
}

export async function updateMarketingPopup(id: string, input: Partial<PopupWriteInput>): Promise<ApiMarketingPopup> {
  const res = await apiFetch<{ data: ApiMarketingPopup }>(`/api/v1/marketing/popups/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return res.data;
}

export async function deleteMarketingPopup(id: string): Promise<void> {
  await apiFetch(`/api/v1/marketing/popups/${id}`, { method: "DELETE" });
}
