"use client";

import { Suspense } from "react";
import { ContentDataSkeleton } from "@/components/layout/content-data-skeleton";
import { MarketingSubscribersPanel } from "@/components/website/marketing/marketing-subscribers-panel";

function SubscribersContent() {
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden">
      <div className="shrink-0">
        <h1 className="text-base font-semibold text-foreground">Subscribers</h1>
        <p className="text-sm text-muted-foreground">Emails and mobile numbers collected by the Subscribe box in the storefront footer.</p>
      </div>
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
