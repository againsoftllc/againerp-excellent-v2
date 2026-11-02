import { apiFetch } from "@/lib/api/client";

/** A branch = one store-pickup counter: the same list checkout offers for Store Pickup. */
export type ApiBranch = {
  key: string;
  label: string;
  address: string;
  phone: string;
  map_url: string;
  image: string;
  hours: string;
  whatsapp: string;
  email: string;
  visible: boolean;
};

export async function fetchBranches(): Promise<ApiBranch[]> {
  const res = await apiFetch<{ data: ApiBranch[] }>("/api/v1/website/branches");
  return res.data ?? [];
}

export async function saveBranches(branches: ApiBranch[]): Promise<ApiBranch[]> {
  const res = await apiFetch<{ data: ApiBranch[] }>("/api/v1/website/branches", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ branches }),
  });
  return res.data ?? [];
}
