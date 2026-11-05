import { apiFetch } from "./client";

export type PlatformSetting = {
  key: string;
  value: string | null;
  description: string | null;
  is_secret: boolean;
  group: string;
  label: string;
  configured: boolean;
};

export async function fetchPlatformSettings(): Promise<PlatformSetting[]> {
  return apiFetch<PlatformSetting[]>("/api/v1/platform-settings");
}

export async function upsertPlatformSetting(key: string, value: string): Promise<PlatformSetting> {
  return apiFetch<PlatformSetting>(`/api/v1/platform-settings/${key}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value }),
  });
}

export const DISABLED_MODULES_KEY = "workspace.disabled_modules";

/** Module ids turned off for every user, or null when the server could not be asked. */
export async function fetchDisabledModules(): Promise<string[] | null> {
  try {
    const row = await apiFetch<PlatformSetting>(`/api/v1/platform-settings/${DISABLED_MODULES_KEY}`);
    const parsed = JSON.parse((row.value ?? "").trim() || "[]");
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return null;
  }
}

export async function saveDisabledModules(ids: string[]): Promise<void> {
  await upsertPlatformSetting(DISABLED_MODULES_KEY, JSON.stringify(ids));
}

export type ProductChargeAttribute = {
  code: string;
  name: string;
  values: { value: string; count: number }[];
};

/** Filterable attributes and the values their published products carry (for the delivery-charge table). */
export async function fetchProductChargeOptions(): Promise<ProductChargeAttribute[]> {
  return apiFetch<ProductChargeAttribute[]>("/api/v1/platform-settings/shipping/product-charge-options");
}

export async function clearPlatformSetting(key: string): Promise<void> {
  await apiFetch(`/api/v1/platform-settings/${key}`, { method: "DELETE" });
}

export async function testPlatformSetting(key: string): Promise<{ ok: boolean; status: string }> {
  return apiFetch<{ ok: boolean; status: string }>(`/api/v1/platform-settings/${key}/test`, {
    method: "POST",
  });
}
