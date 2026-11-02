import { apiFetch } from "@/lib/api/client";

/** One footer "Subscribe" sign-up: an email or a mobile number. */
export type ApiNewsletterSubscriber = {
  id: string;
  email: string;
  phone: string;
  source: string;
  is_active: boolean;
  created_at: string;
};

export async function fetchNewsletterSubscribers(): Promise<{ rows: ApiNewsletterSubscriber[]; activeCount: number }> {
  const res = await apiFetch<{ data: ApiNewsletterSubscriber[]; meta: { count: number; active_count: number } }>(
    "/api/v1/marketing/newsletter-subscribers",
  );
  return { rows: res.data ?? [], activeCount: res.meta?.active_count ?? 0 };
}

export async function setNewsletterSubscriberActive(id: string, isActive: boolean): Promise<void> {
  await apiFetch(`/api/v1/marketing/newsletter-subscribers/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_active: isActive }),
  });
}

export async function deleteNewsletterSubscriber(id: string): Promise<void> {
  await apiFetch(`/api/v1/marketing/newsletter-subscribers/${id}`, { method: "DELETE" });
}
