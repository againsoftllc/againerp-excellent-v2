"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { PermissionMap } from "@/lib/auth/permissions";

export type AdminRoleSummary = {
  id: string;
  name: string;
  slug: string;
};

export type AdminUser = {
  id: string;
  email: string;
  username: string;
  name: string;
  role: string;
  is_active: boolean;
  role_ids?: string[];
  roles?: AdminRoleSummary[];
  /** Warehouses an admin limited this user to; empty/absent = every warehouse. */
  warehouse_ids?: string[];
  default_warehouse_id?: string | null;
  company_id?: string | null;
  company_name?: string | null;
  company_slug?: string | null;
};

type AdminAuthState = {
  _hasHydrated: boolean;
  setHasHydrated: (v: boolean) => void;
  user: AdminUser | null;
  token: string | null;
  expiresAt: string | null;
  permissions: PermissionMap;
  /** null = no restriction (all modules enabled) */
  enabledModules: string[] | null;
  setSession: (payload: {
    user: AdminUser;
    token: string;
    expiresAt: string;
    permissions?: PermissionMap;
    enabledModules?: string[] | null;
  }) => void;
  setPermissions: (permissions: PermissionMap) => void;
  clearSession: () => void;
};

/**
 * A plain cookie that only says "an admin is signed in in this browser": the storefront shows its Live Edit / Edit product
 * buttons when it sees it. It holds no token and grants nothing (editing needs this admin's own sign-in).
 * It is set on the parent domain (erp.excellent.com.bd -> .excellent.com.bd) so the storefront (www.) can read it; on
 * localhost / an IP it stays host-only, which every port of that host shares. NEXT_PUBLIC_EDITOR_COOKIE_DOMAIN overrides.
 */
const EDITOR_MARKER_COOKIE = "excellent_editor";
function syncEditorMarker(signedIn: boolean, expiresAt?: string | null) {
  if (typeof document === "undefined") return;
  try {
    const host = window.location.hostname;
    const labels = host.split(".");
    const configured = process.env.NEXT_PUBLIC_EDITOR_COOKIE_DOMAIN?.trim();
    const domain = configured || (host === "localhost" || /^[\d.]+$/.test(host) || labels.length < 3 ? "" : `.${labels.slice(1).join(".")}`);
    const left = expiresAt ? (Date.parse(expiresAt) - Date.now()) / 1000 : 8 * 3600;
    const maxAge = signedIn && Number.isFinite(left) && left > 60 ? Math.floor(Math.min(left, 7 * 24 * 3600)) : 0;
    document.cookie = `${EDITOR_MARKER_COOKIE}=${maxAge > 0 ? "1" : ""}; Path=/; Max-Age=${maxAge}; SameSite=Lax${domain ? `; Domain=${domain}` : ""}${window.location.protocol === "https:" ? "; Secure" : ""}`;
  } catch {
    /* the buttons simply do not show */
  }
}

export const useAdminAuth = create<AdminAuthState>()(
  persist(
    (set) => ({
      _hasHydrated: false,
      setHasHydrated: (v) => set({ _hasHydrated: v }),
      user: null,
      token: null,
      expiresAt: null,
      permissions: {},
      enabledModules: null,
      setSession: ({ user, token, expiresAt, permissions, enabledModules }) => {
        syncEditorMarker(Boolean(token), expiresAt);
        set({
          user,
          token,
          expiresAt,
          permissions: permissions ?? {},
          enabledModules: enabledModules ?? null,
        });
      },
      setPermissions: (permissions) => set({ permissions }),
      clearSession: () => {
        syncEditorMarker(false);
        set({ user: null, token: null, expiresAt: null, permissions: {}, enabledModules: null });
      },
    }),
    {
      name: "againerp-admin-auth",
      partialize: (s) => ({
        user: s.user,
        token: s.token,
        expiresAt: s.expiresAt,
        permissions: s.permissions,
        enabledModules: s.enabledModules,
      }),
      onRehydrateStorage: () => (state) => {
        // already signed in when the admin opens (sessions from before this existed too): keep the marker in step
        syncEditorMarker(Boolean(state?.token), state?.expiresAt);
        state?.setHasHydrated(true);
      },
    },
  ),
);

export function getStoredAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const fromStore = useAdminAuth.getState().token;
    if (fromStore) return fromStore;
    const raw = localStorage.getItem("againerp-admin-auth");
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { state?: { token?: string | null } };
    return parsed.state?.token ?? null;
  } catch {
    return null;
  }
}
