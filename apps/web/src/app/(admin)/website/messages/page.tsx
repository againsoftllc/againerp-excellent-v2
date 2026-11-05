"use client";

import { Suspense } from "react";
import { ContentDataSkeleton } from "@/components/layout/content-data-skeleton";
import { WebsiteMessagesPanel } from "@/components/website/messages/website-messages-panel";

function MessagesContent() {
  return (
    <div className="flex min-h-0 w-full min-w-0 flex-1 flex-col overflow-hidden">
      <WebsiteMessagesPanel />
    </div>
  );
}

/** Website -> Site -> Messages: what visitors sent from the storefront's contact form. */
export default function WebsiteMessagesPage() {
  return (
    <Suspense fallback={<ContentDataSkeleton label="Loading messages…" />}>
      <MessagesContent />
    </Suspense>
  );
}
