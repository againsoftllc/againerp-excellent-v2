"use client";

import { SeoRobotsSettings } from "@/components/seo/seo-robots-settings";

/** Saved on the server (not in the browser): the storefront serves it at /robots.txt. */
export default function SeoRobotsConfigPage() {
  return (
    <div className="flex min-h-0 w-full min-w-0 flex-1 flex-col overflow-y-auto">
      <SeoRobotsSettings />
    </div>
  );
}
