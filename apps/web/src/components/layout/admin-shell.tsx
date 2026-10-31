"use client";

import { usePathname } from "next/navigation";
import { WorkspaceShell } from "@/components/workspace/workspace-shell";
import { NavigationLoadingOverlay } from "@/components/layout/navigation-loading-overlay";
import { AiDrawer } from "@/components/ai/ai-drawer";
import { AiFloatingChat } from "@/components/ai/ai-floating-chat";

/** @deprecated Use WorkspaceShell — kept for layout import stability.
 * The floating Aladin button (draggable, bottom-right) is shown on every page except /ai, where the chat is already on screen. */
export function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <>
      <WorkspaceShell>{children}</WorkspaceShell>
      <NavigationLoadingOverlay />
      <AiDrawer />
      {pathname.startsWith("/ai") ? null : <AiFloatingChat />}
    </>
  );
}
