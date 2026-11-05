"use client";

import { Suspense } from "react";
import { ContentDataSkeleton } from "@/components/layout/content-data-skeleton";
import { MarketingHappyHourPanel } from "@/components/website/marketing/marketing-happy-hour-panel";

function HappyHourContent() {
  return (
    <div className="flex min-h-0 w-full min-w-0 flex-1 flex-col overflow-hidden">
      <MarketingHappyHourPanel />
    </div>
  );
}

export default function WebsiteMarketingHappyHourPage() {
  return (
    <Suspense fallback={<ContentDataSkeleton label="Loading Happy Hour…" />}>
      <HappyHourContent />
    </Suspense>
  );
}
