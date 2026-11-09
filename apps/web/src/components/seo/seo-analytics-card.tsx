"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { fetchPlatformSettings, upsertPlatformSetting } from "@/lib/api/platform-settings";
import { useAdminCanWrite } from "@/lib/hooks/use-admin-can-write";

const KEY = "seo.google_analytics_id";
const ENABLED_KEY = "seo.google_analytics_enabled";
const ID_RE = /\bG-[A-Z0-9]{4,20}\b/;

/** The G-XXXXXXXXXX ID inside whatever was pasted (the ID, or the whole gtag snippet), upper-cased; "" when there is none. */
function idOf(value: string): string {
  return ID_RE.exec(value.trim().toUpperCase())?.[0] ?? "";
}

/**
 * Google Analytics (GA4). Saved on the server (platform settings): the storefront loads Google Analytics with this
 * ID on every page and sends page views plus the shop events (product views, add to cart, checkout, purchases, searches).
 * Empty = the storefront loads nothing from Google at all.
 */
export function SeoAnalyticsCard() {
  const canWrite = useAdminCanWrite();
  const [value, setValue] = useState("");
  const [saved, setSaved] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  /** The On / Off switch: off keeps the saved ID but the website loads no analytics. A missing setting means on. */
  const [enabled, setEnabled] = useState(true);
  const [toggling, setToggling] = useState(false);

  useEffect(() => {
    let live = true;
    fetchPlatformSettings()
      .then((rows) => {
        if (!live) return;
        const current = rows.find((r) => r.key === KEY)?.value ?? "";
        setValue(current);
        setSaved(current);
        setEnabled((rows.find((r) => r.key === ENABLED_KEY)?.value ?? "").trim().toLowerCase() !== "false");
        setLoaded(true);
      })
      .catch(() => live && toast.error("Could not load the Google Analytics ID"));
    return () => {
      live = false;
    };
  }, []);

  const dirty = value !== saved;
  const typed = value.trim();
  const invalid = typed !== "" && idOf(typed) === "";

  const toggle = async (next: boolean) => {
    setToggling(true);
    try {
      await upsertPlatformSetting(ENABLED_KEY, next ? "true" : "false");
      setEnabled(next);
      toast.success(next ? "Google Analytics is ON. It is on the website within a minute." : "Google Analytics is OFF. The website stops loading it within a minute (the ID stays saved).");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not change the Google Analytics switch");
    } finally {
      setToggling(false);
    }
  };

  const save = async () => {
    const next = idOf(value);
    if (value.trim() && !next) return toast.error("That is not a Google Analytics measurement ID. It looks like G-XXXXXXXXXX.");
    setSaving(true);
    try {
      await upsertPlatformSetting(KEY, next);
      setValue(next);
      setSaved(next);
      toast.success(next ? "Google Analytics ID saved. It is on the website within a minute." : "Google Analytics removed from the website.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not save the Google Analytics ID");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="overflow-hidden rounded-none border border-border bg-card">
      <div className="border-b border-border bg-muted px-4 py-2">
        <h2 className="text-[13px] font-semibold text-foreground">Google Analytics</h2>
      </div>
      <div className="space-y-4 px-4 py-4">
        <div className="max-w-xl">
          <Switch
            id="seo-ga-enabled"
            label={enabled ? "Google Analytics is ON" : "Google Analytics is OFF"}
            description={
              enabled
                ? saved
                  ? "The website counts visits and shop events. Turn off to stop it; the ID below stays saved."
                  : "On, but no measurement ID is saved yet: nothing is loaded until you save one below."
                : "Nothing is loaded from Google on the website. Turn on to start counting again with the saved ID."
            }
            checked={enabled}
            onCheckedChange={(next: boolean) => void toggle(next)}
            disabled={!canWrite || !loaded || toggling}
          />
        </div>
        <p className="text-[12px] text-muted-foreground">
          Paste the Google Analytics 4 measurement ID and save: the website then counts visits, and sends product views,
          add to cart, checkout starts, orders (with their value) and searches. Leave it empty to turn Google Analytics off.
          It is saved on the server, for all users. Visits made while you are signed in to the admin or inside Live Edit are not counted.
        </p>
        <div>
          <label className="text-[13px] font-medium text-foreground" htmlFor="seo-ga-id">
            Measurement ID
          </label>
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            analytics.google.com → Admin → Data streams → your web stream → Measurement ID (looks like G-XXXXXXXXXX).
          </p>
          <Input
            id="seo-ga-id"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className="mt-2 h-8 w-full max-w-xl rounded-none text-[13px]"
            placeholder="G-XXXXXXXXXX"
            disabled={!canWrite || !loaded}
          />
          {invalid ? <p className="mt-1 text-[12px] text-destructive">This does not look like a measurement ID (G- and letters or digits).</p> : null}
        </div>
        <div className="flex gap-2">
          <Button type="button" size="sm" className="rounded-none" disabled={!canWrite || !dirty || saving || invalid} onClick={() => void save()}>
            {saving ? "Saving…" : "Save Google Analytics"}
          </Button>
        </div>
      </div>
    </section>
  );
}
