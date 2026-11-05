import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { CenterEntitlements } from "@/lib/center/entitlements";
import {
  erpEnabledFromCenter,
  isCenterAiEnabled,
  isCenterManagedModule,
} from "@/lib/center/entitlements";

/** Toggleable workspace modules — Dashboard and Workspace stay always on. */
export const TOGGLEABLE_MODULE_IDS = [
  "catalog",
  "inventory",
  "purchase",
  "rma",
  "service",
  "vendors",
  "ai",
  "dropshipping",
  "hrm",
  "blog",
  "website",
  "sales",
  "pos",
  "finance",
  "accounting",
  "crm",
  "customers",
  "expenses",
] as const;

export type ToggleableModuleId = (typeof TOGGLEABLE_MODULE_IDS)[number];

type ModuleSettingsState = {
  /** Local preference (persisted). Center-managed modules may be overridden at read time. */
  enabled: Record<ToggleableModuleId, boolean>;
  centerBound: boolean;
  centerPlan: string | null;
  centerClientName: string | null;
  centerEnabledModules: string[];
  /** Center AI Access — when true, ERP AI Assistant uses Center-proxied OpenAI. */
  centerAiEnabled: boolean;
  centerAiAccessStatus: string | null;
  centerError: string | null;
  setModuleEnabled: (id: ToggleableModuleId, enabled: boolean) => void;
  /** The server decides which modules are off for everyone; this browser only caches it. */
  hydrateDisabledFromServer: (disabled: string[]) => void;
  applyCenterEntitlements: (payload: {
    bound: boolean;
    data?: CenterEntitlements;
    error?: string | null;
  }) => void;
  /** Effective visibility after Center overlay. */
  isModuleVisible: (id: ToggleableModuleId) => boolean;
};

const DEFAULT_ENABLED = Object.fromEntries(
  TOGGLEABLE_MODULE_IDS.map((id) => [id, true]),
) as Record<ToggleableModuleId, boolean>;

export const useModuleSettingsStore = create<ModuleSettingsState>()(
  persist(
    (set, get) => ({
      enabled: DEFAULT_ENABLED,
      centerBound: false,
      centerPlan: null,
      centerClientName: null,
      centerEnabledModules: [],
      centerAiEnabled: false,
      centerAiAccessStatus: null,
      centerError: null,
      setModuleEnabled: (id, enabled) => {
        if (get().centerBound && isCenterManagedModule(id)) return;
        set((state) => ({ enabled: { ...state.enabled, [id]: enabled } }));
      },
      hydrateDisabledFromServer: (disabled) => {
        const off = new Set(disabled);
        set((state) => ({
          enabled: Object.fromEntries(
            TOGGLEABLE_MODULE_IDS.map((id) => {
              // a module Center manages keeps the value Center gave it
              const managed = state.centerBound && isCenterManagedModule(id);
              return [id, managed ? state.enabled[id] !== false : !off.has(id)];
            }),
          ) as Record<ToggleableModuleId, boolean>,
        }));
      },
      applyCenterEntitlements: ({ bound, data, error }) => {
        if (!bound || !data) {
          set({
            centerBound: false,
            centerPlan: null,
            centerClientName: null,
            centerEnabledModules: [],
            centerAiEnabled: false,
            centerAiAccessStatus: null,
            centerError: error ?? null,
          });
          return;
        }
        const merged = erpEnabledFromCenter(data, get().enabled);
        set({
          enabled: merged,
          centerBound: true,
          centerPlan: data.plan,
          centerClientName: data.name,
          centerEnabledModules: data.enabled_modules,
          centerAiEnabled: isCenterAiEnabled(data),
          centerAiAccessStatus: data.ai_access_status ?? null,
          centerError: error ?? null,
        });
      },
      isModuleVisible: (id) => get().enabled[id] !== false,
    }),
    {
      name: "againerp-modules",
      partialize: (state) => ({ enabled: state.enabled }),
      merge: (persisted, current) => {
        const prev = persisted as Partial<ModuleSettingsState> | undefined;
        return {
          ...current,
          ...prev,
          enabled: { ...DEFAULT_ENABLED, ...prev?.enabled },
        };
      },
    },
  ),
);

export function isToggleableModuleId(id: string): id is ToggleableModuleId {
  return (TOGGLEABLE_MODULE_IDS as readonly string[]).includes(id);
}
