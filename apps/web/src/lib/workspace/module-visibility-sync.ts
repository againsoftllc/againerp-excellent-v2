import { isCenterManagedModule } from "@/lib/center/entitlements";
import { fetchDisabledModules, saveDisabledModules } from "@/lib/api/platform-settings";
import { TOGGLEABLE_MODULE_IDS, useModuleSettingsStore } from "@/lib/store/module-settings-store";

/**
 * Which workspace modules are turned off is one setting for the whole workspace (Workspace > Apps): the server
 * keeps it, and every browser reads it, so disabling a module hides it for every user. The browser store is
 * only a cache of that.
 */
export async function loadModuleVisibility(): Promise<void> {
  const disabled = await fetchDisabledModules();
  if (disabled) useModuleSettingsStore.getState().hydrateDisabledFromServer(disabled);
}

/** Save the modules this browser currently shows as off. Modules AgainERP Center switches are not stored. */
export async function saveModuleVisibility(): Promise<void> {
  const { enabled, centerBound } = useModuleSettingsStore.getState();
  const disabled = TOGGLEABLE_MODULE_IDS.filter(
    (id) => enabled[id] === false && !(centerBound && isCenterManagedModule(id)),
  );
  await saveDisabledModules(disabled);
}

/** Turn a module on or off for everyone; rolls the local switch back when the server refuses. */
export async function setModuleEnabledEverywhere(
  id: (typeof TOGGLEABLE_MODULE_IDS)[number],
  enabled: boolean,
): Promise<void> {
  const store = useModuleSettingsStore.getState();
  store.setModuleEnabled(id, enabled);
  try {
    await saveModuleVisibility();
  } catch (err) {
    useModuleSettingsStore.getState().setModuleEnabled(id, !enabled);
    throw err;
  }
}
