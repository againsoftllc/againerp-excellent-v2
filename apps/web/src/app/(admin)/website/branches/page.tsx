"use client";

import { Suspense } from "react";
import { ContentDataSkeleton } from "@/components/layout/content-data-skeleton";
import { WebsiteBranchesPanel } from "@/components/website/branches/website-branches-panel";

function BranchesContent() {
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden">
      <div className="shrink-0">
        <h1 className="text-base font-semibold text-foreground">Branches</h1>
        <p className="text-sm text-muted-foreground">Address, phone, hours, map and photo of each shop. The page&apos;s own layout is edited in Live Edit.</p>
      </div>
      <WebsiteBranchesPanel />
    </div>
  );
}

export default function WebsiteBranchesPage() {
  return (
    <Suspense fallback={<ContentDataSkeleton label="Loading Branches…" />}>
      <BranchesContent />
    </Suspense>
  );
}
