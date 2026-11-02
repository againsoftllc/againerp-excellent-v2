"use client";

import { Suspense } from "react";
import { ContentDataSkeleton } from "@/components/layout/content-data-skeleton";
import { MarketingPopupsPanel } from "@/components/website/marketing/marketing-popups-panel";

function PopupsContent() {
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden">
      <div className="shrink-0">
        <h1 className="text-base font-semibold text-foreground">Popups</h1>
        <p className="text-sm text-muted-foreground">
          A Happy Hour, an offer, a notice or a picture shown over the storefront.
        </p>
      </div>
      <MarketingPopupsPanel />
    </div>
  );
}

export default function WebsiteMarketingPopupsPage() {
  return (
    <Suspense fallback={<ContentDataSkeleton label="Loading Popups…" />}>
      <PopupsContent />
    </Suspense>
  );
}
