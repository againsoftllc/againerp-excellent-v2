"use client";

import { useEffect, useState } from "react";

import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/native-select";
import { fetchProductChargeOptions, type ProductChargeAttribute } from "@/lib/api/platform-settings";

type Rule = { attribute: string; charges: Record<string, number> };

type Props = {
  chargesJson: string;
  exemptText: string;
  onChangeCharges: (json: string) => void;
};

function parseRules(json: string): Rule[] {
  try {
    const data = JSON.parse((json || "").trim() || "[]");
    if (!Array.isArray(data)) return [];
    const rules: Rule[] = [];
    for (const item of data as Record<string, unknown>[]) {
      const attribute = String(item?.attribute ?? "").trim();
      const raw = item?.charges;
      if (!attribute || !raw || typeof raw !== "object") continue;
      const charges: Record<string, number> = {};
      for (const [value, amount] of Object.entries(raw as Record<string, unknown>)) {
        const n = Number(amount);
        if (value.trim() && Number.isFinite(n) && n >= 0) charges[value.trim()] = n;
      }
      rules.push({ attribute, charges });
    }
    return rules;
  } catch {
    return [];
  }
}

/** Per-unit extra delivery charge by product attribute value, e.g. Screen Size "26-30 inch" → ৳300. */
export function ShippingProductChargesPanel({ chargesJson, exemptText, onChangeCharges }: Props) {
  const [options, setOptions] = useState<ProductChargeAttribute[] | null>(null);
  const [failed, setFailed] = useState(false);
  const rules = parseRules(chargesJson);

  useEffect(() => {
    fetchProductChargeOptions()
      .then(setOptions)
      .catch(() => setFailed(true));
  }, []);

  // A value with no (or zero) charge is dropped when saving: the storefront treats it as "no extra".
  // An attribute with no charges yet stays in the list so it can be filled in.
  const emit = (next: Rule[]) => {
    onChangeCharges(
      JSON.stringify(
        next.map((r) => ({
          attribute: r.attribute,
          charges: Object.fromEntries(Object.entries(r.charges).filter(([, amount]) => amount > 0)),
        })),
      ),
    );
  };

  const setCharge = (attribute: string, value: string, amount: number) => {
    emit(
      rules.map((r) =>
        r.attribute === attribute ? { ...r, charges: { ...r.charges, [value]: Math.max(0, amount || 0) } } : r,
      ),
    );
  };

  const addAttribute = (code: string) => {
    if (!code || rules.some((r) => r.attribute === code)) return;
    emit([...rules, { attribute: code, charges: {} }]);
  };

  const exempt = exemptText
    .split(/[,\n]/)
    .map((d) => d.trim())
    .filter(Boolean);
  const available = (options ?? []).filter((o) => !rules.some((r) => r.attribute === o.code));

  return (
    <div className="overflow-hidden rounded-none border border-border bg-card shadow-sm">
      <div className="border-b border-border bg-muted/30 px-4 py-2.5">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Product Delivery Charges (BDT, once per order)
        </p>
        <p className="mt-0.5 text-[11px] text-muted-foreground">
          Extra charge added to Home Delivery when the cart holds a product whose attribute matches (e.g. monitors by Screen Size). It is added once: the largest matching charge in the cart applies, however many units or products.
          {exempt.length > 0
            ? ` Not added in: ${exempt.join(", ")} — there only the district price applies.`
            : " Added in every district."}{" "}
          Store Pickup never gets it.
        </p>
      </div>

      {failed && <p className="px-4 py-3 text-xs text-destructive">Could not load the attribute list.</p>}

      {rules.map((rule) => {
        const attr = options?.find((o) => o.code === rule.attribute);
        const known = new Set((attr?.values ?? []).map((v) => v.value.toLowerCase()));
        // Saved ranges no product carries any more (e.g. the filter option was renamed) charge nothing.
        const orphans = Object.keys(rule.charges).filter((v) => attr && !known.has(v.toLowerCase()));
        return (
          <div key={rule.attribute} className="border-b border-border last:border-b-0">
            <div className="flex items-center justify-between bg-muted/10 px-4 py-2">
              <p className="text-sm font-semibold">{attr?.name ?? rule.attribute}</p>
              <button
                type="button"
                onClick={() => emit(rules.filter((r) => r.attribute !== rule.attribute))}
                className="text-xs text-muted-foreground underline hover:text-destructive"
              >
                Remove
              </button>
            </div>
            <div className="divide-y divide-border">
              {(attr?.values ?? []).map((v) => (
                <div key={v.value} className="flex items-center justify-between gap-3 px-4 py-2.5">
                  <p className="text-sm">
                    {v.value} <span className="text-[11px] text-muted-foreground">· {v.count} products</span>
                  </p>
                  <Input
                    type="number"
                    min={0}
                    step={1}
                    placeholder="0"
                    value={rule.charges[v.value] ?? ""}
                    onChange={(e) => setCharge(rule.attribute, v.value, parseFloat(e.target.value))}
                    className="h-9 w-36 rounded-none text-xs"
                  />
                </div>
              ))}
              {orphans.map((v) => (
                <div key={v} className="flex items-center justify-between gap-3 bg-amber-500/10 px-4 py-2.5">
                  <p className="text-sm">
                    {v}{" "}
                    <span className="text-[11px] text-amber-600">
                      · no product has this value now, so ৳{rule.charges[v]} is not charged
                    </span>
                  </p>
                  <button
                    type="button"
                    onClick={() => {
                      const rest = { ...rule.charges };
                      delete rest[v];
                      emit(rules.map((r) => (r.attribute === rule.attribute ? { ...r, charges: rest } : r)));
                    }}
                    className="text-xs text-muted-foreground underline hover:text-destructive"
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
          </div>
        );
      })}

      <div className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center">
        <Select
          value=""
          onChange={(e) => addAttribute(e.target.value)}
          className="h-9 w-full sm:w-64"
          disabled={!options}
        >
          <option value="">{options ? "Add an attribute (e.g. Screen Size)…" : "Loading attributes…"}</option>
          {available.map((o) => (
            <option key={o.code} value={o.code}>
              {o.name}
            </option>
          ))}
        </Select>
        {rules.length === 0 && (
          <p className="text-[11px] text-muted-foreground">
            No product delivery charges yet — every order pays the district price only.
          </p>
        )}
      </div>
    </div>
  );
}
