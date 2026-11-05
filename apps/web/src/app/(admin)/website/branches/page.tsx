"use client";

import { Suspense } from "react";
import { ContentDataSkeleton } from "@/components/layout/content-data-skeleton";
import { WebsiteBranchesPanel } from "@/components/website/branches/website-branches-panel";

function BranchesContent() {
  return (
    <div className="flex min-h-0 w-full min-w-0 flex-1 flex-col overflow-hidden">
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
