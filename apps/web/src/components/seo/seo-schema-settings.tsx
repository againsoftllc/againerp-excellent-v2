"use client";

import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { fetchSeoSchemaConfig, saveSeoSchemaConfig, type SeoSchemaConfig } from "@/lib/api/seo-schema-config";
import { useAdminCanWrite } from "@/lib/hooks/use-admin-can-write";

function Card({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="overflow-hidden rounded-none border border-border bg-card">
      <div className="border-b border-border bg-muted px-4 py-2">
        <h2 className="text-[13px] font-semibold text-foreground">{title}</h2>
        {hint ? <p className="text-[11px] text-muted-foreground">{hint}</p> : null}
      </div>
      <div className="space-y-4 px-4 py-4">{children}</div>
    </section>
  );
}

function Field({ label, help, children }: { label: string; help?: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-muted-foreground">{label}</label>
      {children}
      {help ? <p className="text-[11px] text-muted-foreground">{help}</p> : null}
    </div>
  );
}

function Check({ checked, onChange, label, help, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; help?: string; disabled?: boolean }) {
  return (
    <label className="flex items-start gap-2 text-sm">
      <input type="checkbox" className="mt-0.5 h-4 w-4" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span>
        {label}
        {help ? <span className="block text-[11px] text-muted-foreground">{help}</span> : null}
      </span>
    </label>
  );
}

const TOKENS = "{name} {brand} {category} {site} {sku} {price}";
const PAGE_LABELS: [keyof SeoSchemaConfig["pages"], string, string][] = [
  ["home", "Home page", "Organization, store and WebSite (search box)"],
  ["category", "Category pages", "Breadcrumb, product list, collection page"],
  ["brand", "Brand pages", "Breadcrumb, product list, collection page"],
  ["product", "Product pages", "Product, offer, rating, breadcrumb"],
  ["branches", "Branches page", "A local business for every listed branch"],
  ["offers", "Offers and Happy Hour", "Product list with the offer period"],
  ["info", "Information pages", "A plain web page (terms, policy, about)"],
];

/**
 * Admin -> SEO -> Config -> Schema & meta templates. Saved on the server; the storefront reads it for every page and builds its
 * JSON-LD from these fields plus the real data of each page (prices, reviews, branches), so nothing here has to be typed as code.
 */
export function SeoSchemaSettings() {
  const canWrite = useAdminCanWrite();
  const [cfg, setCfg] = useState<SeoSchemaConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [phonesText, setPhonesText] = useState("");

  useEffect(() => {
    let live = true;
    fetchSeoSchemaConfig()
      .then((c) => {
        if (!live) return;
        setCfg(c);
        setPhonesText(c.business.phones.join("\n"));
      })
      .catch((err) => toast.error(err instanceof Error ? err.message : "Failed to load the schema settings"));
    return () => {
      live = false;
    };
  }, []);

  if (!cfg) return <p className="p-6 text-sm text-muted-foreground">Loading…</p>;

  const set = (fn: (c: SeoSchemaConfig) => SeoSchemaConfig) => setCfg((c) => (c ? fn(structuredClone(c)) : c));
  const b = cfg.business;

  const save = async () => {
    setSaving(true);
    try {
      const phones = phonesText.split("\n").map((p) => p.trim()).filter(Boolean);
      const saved = await saveSeoSchemaConfig({ ...cfg, business: { ...cfg.business, phones } });
      setCfg(saved);
      setPhonesText(saved.business.phones.join("\n"));
      toast.success("Schema settings saved");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 p-4">
      <div className="flex items-start gap-3">
        <div>
          <h1 className="text-base font-semibold text-foreground">Schema &amp; meta templates</h1>
          <p className="text-sm text-muted-foreground">
            The structured data (JSON-LD) search engines read on every storefront page, and the title patterns. Blank business fields use the
            shop&apos;s own settings. The storefront adds each page&apos;s real data (prices, ratings, branches) itself.
          </p>
        </div>
        {canWrite ? (
          <Button className="ml-auto rounded-none" disabled={saving} onClick={() => void save()}>
            {saving ? "Saving…" : "Save"}
          </Button>
        ) : null}
      </div>

      <Card title="Structured data">
        <Check checked={cfg.enabled} disabled={!canWrite} onChange={(v) => set((c) => ({ ...c, enabled: v }))} label="Output JSON-LD" help="Turn everything below off at once." />
        <div className="grid gap-3 sm:grid-cols-2">
          {PAGE_LABELS.map(([key, label, help]) => (
            <Check key={key} checked={cfg.pages[key]} disabled={!canWrite || !cfg.enabled} onChange={(v) => set((c) => ({ ...c, pages: { ...c.pages, [key]: v } }))} label={label} help={help} />
          ))}
        </div>
      </Card>

      <Card title="Business" hint="For the Organization / store schema on the home page. Leave a field blank to use the shop's settings.">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Name">
            <Input className="rounded-none" value={b.name} disabled={!canWrite} onChange={(e) => set((c) => ({ ...c, business: { ...c.business, name: e.target.value } }))} />
          </Field>
          <Field label="Legal name">
            <Input className="rounded-none" value={b.legal_name} disabled={!canWrite} onChange={(e) => set((c) => ({ ...c, business: { ...c.business, legal_name: e.target.value } }))} />
          </Field>
          <Field label="Logo link" help="Full https:// address of the logo image.">
            <Input className="rounded-none" value={b.logo_url} disabled={!canWrite} onChange={(e) => set((c) => ({ ...c, business: { ...c.business, logo_url: e.target.value } }))} />
          </Field>
          <Field label="Email">
            <Input className="rounded-none" value={b.email} disabled={!canWrite} onChange={(e) => set((c) => ({ ...c, business: { ...c.business, email: e.target.value } }))} />
          </Field>
          <Field label="Type">
            <Select className="h-9 w-full rounded-none" value={b.store_type} disabled={!canWrite} onChange={(e) => set((c) => ({ ...c, business: { ...c.business, store_type: e.target.value as typeof b.store_type } }))}>
              <option value="OnlineStore">Online store</option>
              <option value="ElectronicsStore">Electronics store</option>
              <option value="Store">Store</option>
              <option value="LocalBusiness">Local business</option>
            </Select>
          </Field>
          <Field label="Price range" help="e.g. ৳৳ (optional).">
            <Input className="rounded-none" value={b.price_range} disabled={!canWrite} onChange={(e) => set((c) => ({ ...c, business: { ...c.business, price_range: e.target.value } }))} />
          </Field>
        </div>
        <Field label="Phone numbers (one per line)">
          <Textarea className="min-h-[64px] rounded-none" value={phonesText} disabled={!canWrite} onChange={(e) => setPhonesText(e.target.value)} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Head office street">
            <Input className="rounded-none" value={b.address.street} disabled={!canWrite} onChange={(e) => set((c) => ({ ...c, business: { ...c.business, address: { ...c.business.address, street: e.target.value } } }))} />
          </Field>
          <Field label="City">
            <Input className="rounded-none" value={b.address.locality} disabled={!canWrite} onChange={(e) => set((c) => ({ ...c, business: { ...c.business, address: { ...c.business.address, locality: e.target.value } } }))} />
          </Field>
          <Field label="Postal code">
            <Input className="rounded-none" value={b.address.postal_code} disabled={!canWrite} onChange={(e) => set((c) => ({ ...c, business: { ...c.business, address: { ...c.business.address, postal_code: e.target.value } } }))} />
          </Field>
          <Field label="Country code" help="Two letters, e.g. BD.">
            <Input className="rounded-none" maxLength={2} value={b.address.country} disabled={!canWrite} onChange={(e) => set((c) => ({ ...c, business: { ...c.business, address: { ...c.business.address, country: e.target.value.toUpperCase() } } }))} />
          </Field>
        </div>
      </Card>

      <Card title="Social profiles" hint="Full https:// links of your profiles (the shop's own links are used when these are blank).">
        <div className="grid gap-3 sm:grid-cols-2">
          {(["facebook", "instagram", "youtube", "tiktok", "x", "linkedin"] as const).map((key) => (
            <Field key={key} label={key === "x" ? "X (Twitter)" : key.charAt(0).toUpperCase() + key.slice(1)}>
              <Input className="rounded-none" value={b.social[key]} disabled={!canWrite} onChange={(e) => set((c) => ({ ...c, business: { ...c.business, social: { ...c.business.social, [key]: e.target.value } } }))} />
            </Field>
          ))}
        </div>
      </Card>

      <Card title="Products" hint="Added to every product's offer.">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Item condition">
            <Select className="h-9 w-full rounded-none" value={cfg.product.item_condition} disabled={!canWrite} onChange={(e) => set((c) => ({ ...c, product: { ...c.product, item_condition: e.target.value as typeof cfg.product.item_condition } }))}>
              <option value="NewCondition">New</option>
              <option value="RefurbishedCondition">Refurbished</option>
              <option value="UsedCondition">Used</option>
            </Select>
          </Field>
          <Field label="Price valid for (days)" help="0 = leave it out.">
            <Input type="number" min={0} max={365} className="rounded-none" value={cfg.product.price_valid_days} disabled={!canWrite} onChange={(e) => set((c) => ({ ...c, product: { ...c.product, price_valid_days: Math.max(0, Number(e.target.value) || 0) } }))} />
          </Field>
          <Field label="Return window (days)" help="0 = no return policy in the schema.">
            <Input type="number" min={0} max={365} className="rounded-none" value={cfg.product.return_days} disabled={!canWrite} onChange={(e) => set((c) => ({ ...c, product: { ...c.product, return_days: Math.max(0, Number(e.target.value) || 0) } }))} />
          </Field>
          <Field label="Return policy page" help="Link of the page that explains returns.">
            <Input className="rounded-none" value={cfg.product.return_policy_url} disabled={!canWrite} onChange={(e) => set((c) => ({ ...c, product: { ...c.product, return_policy_url: e.target.value } }))} />
          </Field>
        </div>
      </Card>

      <Card title="Title & description patterns" hint={`Tokens: ${TOKENS}. Blank = the page's own wording.`}>
        {(
          [
            ["home", "Home page"],
            ["category", "Category pages"],
            ["brand", "Brand pages"],
            ["product", "Product pages"],
          ] as const
        ).map(([key, label]) => (
          <div key={key} className="grid gap-3 sm:grid-cols-2">
            <Field label={`${label} - title`}>
              <Input className="rounded-none" value={cfg.meta[`${key}_title`]} disabled={!canWrite} onChange={(e) => set((c) => ({ ...c, meta: { ...c.meta, [`${key}_title`]: e.target.value } }))} placeholder="{name} Price in Bangladesh | {site}" />
            </Field>
            <Field label={`${label} - description`}>
              <Input className="rounded-none" value={cfg.meta[`${key}_description`]} disabled={!canWrite} onChange={(e) => set((c) => ({ ...c, meta: { ...c.meta, [`${key}_description`]: e.target.value } }))} placeholder="Buy {name} at the best price in Bangladesh." />
            </Field>
          </div>
        ))}
      </Card>
    </div>
  );
}
