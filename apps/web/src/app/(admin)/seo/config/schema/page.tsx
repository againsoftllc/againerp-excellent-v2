"use client";

import { SeoSchemaSettings } from "@/components/seo/seo-schema-settings";

/** Saved on the server (not in the browser): the storefront builds its JSON-LD and meta titles from it. */
export default function SeoSchemaConfigPage() {
  return (
    <div className="flex min-h-0 w-full min-w-0 flex-1 flex-col overflow-y-auto">
      <SeoSchemaSettings />
    </div>
  );
}
