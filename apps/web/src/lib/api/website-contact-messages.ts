import { apiFetch } from "@/lib/api/client";

export type ContactMessageStatus = "new" | "read" | "done";

/** One message sent from the storefront's contact form (Branches page -> "Send Us a Message"). */
export type ApiContactMessage = {
  id: string;
  name: string;
  email: string;
  phone: string;
  subject: string;
  message: string;
  status: ContactMessageStatus;
  created_at: string;
};

export async function fetchContactMessages(): Promise<{ rows: ApiContactMessage[]; newCount: number }> {
  const res = await apiFetch<{ data: ApiContactMessage[]; meta?: { new?: number } }>("/api/v1/website/contact-messages");
  return { rows: res.data ?? [], newCount: res.meta?.new ?? 0 };
}

export async function setContactMessageStatus(id: string, status: ContactMessageStatus): Promise<ApiContactMessage> {
  const res = await apiFetch<{ data: ApiContactMessage }>(`/api/v1/website/contact-messages/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  return res.data;
}

export async function deleteContactMessage(id: string): Promise<void> {
  await apiFetch(`/api/v1/website/contact-messages/${id}`, { method: "DELETE" });
}
