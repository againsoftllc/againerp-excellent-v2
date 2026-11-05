"use client";

import { Suspense } from "react";
import { ContentDataSkeleton } from "@/components/layout/content-data-skeleton";
import { MarketingOffersPanel } from "@/components/website/marketing/marketing-offers-panel";

function OffersContent() {
  return (
    <div className="flex min-h-0 w-full min-w-0 flex-1 flex-col overflow-hidden">
      <MarketingOffersPanel />
    </div>
  );
}

export default function WebsiteMarketingOffersPage() {
  return (
    <Suspense fallback={<ContentDataSkeleton label="Loading offers…" />}>
      <OffersContent />
    </Suspense>
  );
}
