"use client";

import { Suspense } from "react";
import { ContentDataSkeleton } from "@/components/layout/content-data-skeleton";
import { MarketingSubscribersPanel } from "@/components/website/marketing/marketing-subscribers-panel";

function SubscribersContent() {
  return (
    <div className="flex min-h-0 w-full min-w-0 flex-1 flex-col overflow-hidden">
      <MarketingSubscribersPanel />
    </div>
  );
}

export default function WebsiteMarketingSubscribersPage() {
  return (
    <Suspense fallback={<ContentDataSkeleton label="Loading Subscribers…" />}>
      <SubscribersContent />
    </Suspense>
  );
}
