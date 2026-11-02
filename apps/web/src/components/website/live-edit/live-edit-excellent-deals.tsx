"use client";

import { AgainFormRow } from "@/components/again/again-form-sheet";
import { ProductMultiPicker } from "@/components/website/live-edit/live-edit-featured-drawer";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { useMarketingHappyHours } from "@/lib/api/use-marketing-happy-hours";
import { useMarketingOffers } from "@/lib/api/use-marketing-offers";
import { cn } from "@/lib/utils";
import { obj, type Json } from "@/lib/website/excellent-home";

type Row = Record<string, unknown>;
const text = (v: unknown) => (typeof v === "string" ? v : "");
const MAX_PICKS = 4;

type Source = "default" | "happy_hour" | "offer" | "products";

function Option({ active, title, hint, onSelect }: { active: boolean; title: string; hint: string; onSelect: () => void }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn("flex w-full items-start gap-2.5 rounded-md border px-2.5 py-2 text-left transition-colors", active ? "border-[#00a09d] bg-[#00a09d]/5" : "border-border hover:bg-muted/40")}
      aria-pressed={active}
    >
      <span className={cn("mt-0.5 flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border", active ? "border-[#00a09d]" : "border-border")} aria-hidden>
        {active ? <span className="h-1.5 w-1.5 rounded-full bg-[#00a09d]" /> : null}
      </span>
      <span className="min-w-0">
        <span className="block text-[13px] font-medium">{title}</span>
        <span className="block text-[11px] text-muted-foreground">{hint}</span>
      </span>
    </button>
  );
}

/**
 * "Deals of the day": a heading, then the products from ONE source, saved in `blocks.excellent.deals`:
 * `{ title, subtitle, source: "default" | "happy_hour" | "offer" | "products", campaign (slug), offer (slug),
 *    products: [{ key, id, hidden }], endsAt }`.
 * Nothing to show from the chosen source => the storefront lists the products of the latest orders.
 */
export function LiveEditExcellentDeals({ ex, setEx }: { ex: Json; setEx: (patch: Json) => void }) {
  const { campaigns } = useMarketingHappyHours();
  const { offers } = useMarketingOffers();

  const d = obj(ex.deals);
  const source: Source = d.source === "happy_hour" || d.source === "offer" || d.source === "products" ? d.source : "default";
  const picks: Row[] = Array.isArray(d.products) ? (d.products as Row[]).filter((p) => p && typeof p === "object") : [];
  const write = (patch: Json) => setEx({ deals: { ...d, ...patch } });

  const usableCampaigns = campaigns.filter((c) => c.status !== "disabled" && c.status !== "draft");
  const usableOffers = offers.filter((o) => o.status !== "disabled" && o.status !== "draft");

  return (
    <div className="space-y-3">
      <div className="space-y-3 rounded-md border border-border bg-card p-2.5">
        <AgainFormRow label="Heading">
          <Input value={text(d.title)} onChange={(e) => write({ title: e.target.value })} className="h-8 text-[13px]" placeholder="Empty = the campaign's name" />
        </AgainFormRow>
        <AgainFormRow label="Sub heading">
          <Input value={text(d.subtitle)} onChange={(e) => write({ subtitle: e.target.value })} className="h-8 text-[13px]" />
        </AgainFormRow>
      </div>

      <div className="space-y-2.5 rounded-md border border-border bg-card p-2.5">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Products</p>
        <Option active={source === "default"} title="Default" hint="The running Happy Hour. None running: the latest sold products." onSelect={() => write({ source: "default" })} />
        <Option
          active={source === "happy_hour"}
          title="Happy Hour"
          hint="Before the daily hour opens: counts down to the opening, regular prices. When it is open: Happy Hour prices."
          onSelect={() => write({ source: "happy_hour" })}
        />
        <Option active={source === "offer"} title="Offer" hint="The products of one offer; counts down to its end." onSelect={() => write({ source: "offer" })} />
        <Option active={source === "products"} title="Custom products" hint={`Pick exactly which products to show (up to ${MAX_PICKS}).`} onSelect={() => write({ source: "products" })} />

        {source === "happy_hour" ? (
          <AgainFormRow label="Happy Hour">
            <Select className="h-8 w-full text-[13px]" value={text(d.campaign)} onChange={(e) => write({ campaign: e.target.value })}>
              <option value="">Select a Happy Hour</option>
              {usableCampaigns.map((c) => (
                <option key={c.id} value={c.slug}>
                  {c.title} · {c.status}
                </option>
              ))}
            </Select>
          </AgainFormRow>
        ) : null}

        {source === "offer" ? (
          <AgainFormRow label="Offer">
            <Select className="h-8 w-full text-[13px]" value={text(d.offer)} onChange={(e) => write({ offer: e.target.value })}>
              <option value="">Select an offer</option>
              {usableOffers.map((o) => (
                <option key={o.id} value={o.slug}>
                  {o.title} · {o.status}
                </option>
              ))}
            </Select>
          </AgainFormRow>
        ) : null}

        {source === "products" ? (
          <>
            <AgainFormRow label="Products">
              <ProductMultiPicker
                selectedIds={picks.map((p) => text(p.id)).filter(Boolean)}
                onChange={(ids) =>
                  write({ products: ids.slice(0, MAX_PICKS).map((id) => picks.find((p) => text(p.id) === id) ?? { key: id, id, hidden: false }) })
                }
              />
            </AgainFormRow>
            <AgainFormRow label="Countdown ends" help="Empty = counts down to midnight.">
              <Input type="datetime-local" value={text(d.endsAt)} onChange={(e) => write({ endsAt: e.target.value })} className="h-8 text-[13px]" />
            </AgainFormRow>
          </>
        ) : null}
      </div>
      <p className="text-[11px] text-muted-foreground">With nothing to show from the chosen source, the 4 most recently sold products appear (no countdown). Changes show on the page after Save.</p>
    </div>
  );
}
