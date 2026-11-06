"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { fetchPlatformSettings, upsertPlatformSetting } from "@/lib/api/platform-settings";
import { useAdminCanWrite } from "@/lib/hooks/use-admin-can-write";

const GOOGLE_KEY = "seo.google_site_verification";
const BING_KEY = "seo.bing_site_verification";

/** The code inside a pasted <meta ... content="CODE"> tag, or the text as typed. */
function codeOf(value: string): string {
  const match = /content\s*=\s*["']([^"']+)["']/i.exec(value);
  return (match ? match[1] : value).trim();
}

/**
 * Search engine ownership codes. Unlike the rest of this page they are saved on the server (platform settings),
 * because the storefront prints them as meta tags in the head of every page.
 */
export function SeoVerificationCard() {
  const canWrite = useAdminCanWrite();
  const [google, setGoogle] = useState("");
  const [bing, setBing] = useState("");
  const [saved, setSaved] = useState({ google: "", bing: "" });
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let live = true;
    fetchPlatformSettings()
      .then((rows) => {
        if (!live) return;
        const value = (key: string) => rows.find((r) => r.key === key)?.value ?? "";
        const next = { google: value(GOOGLE_KEY), bing: value(BING_KEY) };
        setGoogle(next.google);
        setBing(next.bing);
        setSaved(next);
        setLoaded(true);
      })
      .catch(() => live && toast.error("Could not load the verification codes"));
    return () => {
      live = false;
    };
  }, []);

  const dirty = google !== saved.google || bing !== saved.bing;

  const save = async () => {
    const next = { google: codeOf(google), bing: codeOf(bing) };
    setSaving(true);
    try {
      await Promise.all([
        upsertPlatformSetting(GOOGLE_KEY, next.google),
        upsertPlatformSetting(BING_KEY, next.bing),
      ]);
      setGoogle(next.google);
      setBing(next.bing);
      setSaved(next);
      toast.success("Verification codes saved. They appear on the website within a minute.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not save the verification codes");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="overflow-hidden rounded-none border border-border bg-card">
      <div className="border-b border-border bg-muted px-4 py-2">
        <h2 className="text-[13px] font-semibold text-foreground">Search engine verification</h2>
      </div>
      <div className="space-y-5 px-4 py-4">
        <p className="text-[12px] text-muted-foreground">
          Prove to Google / Bing that you own the website: paste the code (or the whole meta tag) they give you,
          save, then press Verify there. The website prints it as a meta tag on every page. These are saved on the
          server, for all users.
        </p>
        <div>
          <label className="text-[13px] font-medium text-foreground" htmlFor="seo-google-verification">
            Google Search Console
          </label>
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            Search Console → Add property → URL prefix → HTML tag. Copy the content value, or the whole tag.
          </p>
          <Input
            id="seo-google-verification"
            value={google}
            onChange={(e) => setGoogle(e.target.value)}
            className="mt-2 h-8 w-full max-w-xl rounded-none text-[13px]"
            placeholder='e.g. abc123… or <meta name="google-site-verification" content="abc123…" />'
            disabled={!canWrite || !loaded}
          />
        </div>
        <div>
          <label className="text-[13px] font-medium text-foreground" htmlFor="seo-bing-verification">
            Bing Webmaster Tools
          </label>
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            Optional. Bing → Add site → HTML meta tag (msvalidate.01). Copy the content value, or the whole tag.
          </p>
          <Input
            id="seo-bing-verification"
            value={bing}
            onChange={(e) => setBing(e.target.value)}
            className="mt-2 h-8 w-full max-w-xl rounded-none text-[13px]"
            placeholder="e.g. 0123456789ABCDEF…"
            disabled={!canWrite || !loaded}
          />
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            size="sm"
            className="rounded-none"
            disabled={!canWrite || !dirty || saving}
            onClick={() => void save()}
          >
            {saving ? "Saving…" : "Save verification codes"}
          </Button>
        </div>
      </div>
    </section>
  );
}
