import { AdminThemeShell } from "@/components/providers/admin-theme-shell";

/**
 * Chrome-less shell for pages meant to be embedded cross-origin (the storefront
 * hosting the Live Edit panel directly). No AdminAuthGate here — these routes
 * receive their session via postMessage from the embedding page instead of the
 * normal ERP admin login/cookie flow.
 */
export default function EmbedLayout({ children }: { children: React.ReactNode }) {
  return (
    <AdminThemeShell>
      <div className="min-h-screen bg-background text-foreground">{children}</div>
    </AdminThemeShell>
  );
}
