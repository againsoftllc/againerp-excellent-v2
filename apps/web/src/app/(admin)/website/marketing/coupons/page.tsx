"use client";

import { Suspense } from "react";
import { ContentDataSkeleton } from "@/components/layout/content-data-skeleton";
import { MarketingCouponsPanel } from "@/components/website/marketing/marketing-coupons-panel";

function CouponsContent() {
  return (
    <div className="flex min-h-0 w-full min-w-0 flex-1 flex-col overflow-hidden">
      <MarketingCouponsPanel />
    </div>
  );
}

export default function WebsiteMarketingCouponsPage() {
  return (
    <Suspense fallback={<ContentDataSkeleton label="Loading coupons…" />}>
      <CouponsContent />
    </Suspense>
  );
}
