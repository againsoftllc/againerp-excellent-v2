"use client";

import { Suspense } from "react";
import { ContentDataSkeleton } from "@/components/layout/content-data-skeleton";
import { MarketingPopupsPanel } from "@/components/website/marketing/marketing-popups-panel";

function PopupsContent() {
  return (
    <div className="flex min-h-0 w-full min-w-0 flex-1 flex-col overflow-hidden">
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
