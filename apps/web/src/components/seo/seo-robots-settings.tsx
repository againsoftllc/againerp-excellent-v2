"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { fetchSeoRobots, saveSeoRobots, type SeoRobotsConfig } from "@/lib/api/seo-schema-config";
import { useAdminCanWrite } from "@/lib/hooks/use-admin-can-write";

const CLOSED = "User-agent: *\nDisallow: /";

/**
 * Admin -> SEO -> Config -> Robots.txt. Saved on the server; the storefront serves it at /robots.txt.
 * While "keep the site closed" is on the whole site is closed to crawlers and the rules below are not used.
 */
export function SeoRobotsSettings() {
  const canWrite = useAdminCanWrite();
  const [cfg, setCfg] = useState<SeoRobotsConfig | null>(null);
  const [wasClosed, setWasClosed] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let live = true;
    fetchSeoRobots()
      .then((c) => {
        if (!live) return;
        setCfg(c);
        setWasClosed(c.block_all);
      })
      .catch((err) => toast.error(err instanceof Error ? err.message : "Failed to load robots.txt"));
    return () => {
      live = false;
    };
  }, []);

  if (!cfg) return <p className="p-6 text-sm text-muted-foreground">Loading…</p>;

  const save = async () => {
    if (wasClosed && !cfg.block_all && !window.confirm("This opens the whole site to Google and other search engines. Continue?")) return;
    setSaving(true);
    try {
      const saved = await saveSeoRobots(cfg);
      setCfg(saved);
      setWasClosed(saved.block_all);
      toast.success("robots.txt saved - the storefront picks it up within a minute");
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
          <h1 className="text-base font-semibold text-foreground">Robots.txt</h1>
          <p className="text-sm text-muted-foreground">Crawl rules search engines read at /robots.txt of the storefront.</p>
        </div>
        <Button className="ml-auto" onClick={save} disabled={!canWrite || saving}>
          {saving ? "Saving…" : "Save"}
        </Button>
      </div>

      <section className="overflow-hidden rounded-none border border-border bg-card">
        <div className="border-b border-border bg-muted px-4 py-2">
          <h2 className="text-[13px] font-semibold text-foreground">Crawl rules</h2>
        </div>
        <div className="space-y-4 px-4 py-4">
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4"
              checked={cfg.block_all}
              disabled={!canWrite}
              onChange={(e) => setCfg({ ...cfg, block_all: e.target.checked })}
            />
            <span>
              Keep the whole site closed to search engines
              <span className="block text-[11px] text-muted-foreground">
                On: /robots.txt is just <code>Disallow: /</code>, Google cannot read any page. Turn it off when the SEO work is done.
              </span>
            </span>
          </label>

          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Rules used when the site is open</label>
            <Textarea value={cfg.text} onChange={(e) => setCfg({ ...cfg, text: e.target.value })} rows={12} className="font-mono text-[13px]" disabled={!canWrite} />
            <p className="text-[11px] text-muted-foreground">
              One directive per line. A Sitemap line with the shop&apos;s own address is added automatically when there is none.
            </p>
          </div>

          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">What the storefront serves now</p>
            <pre className="whitespace-pre-wrap rounded-none border border-border bg-muted px-3 py-2 font-mono text-[12px]">{cfg.block_all ? CLOSED : cfg.text}</pre>
          </div>
        </div>
      </section>
    </div>
  );
}
