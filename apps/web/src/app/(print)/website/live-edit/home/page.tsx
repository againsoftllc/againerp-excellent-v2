import { ExcellentLiveEditEmbedPanel } from "@/components/website/live-edit/excellent-live-edit-embed-panel";

/**
 * Full-screen Live Edit for Home — toolbar on top (Save, lock, Section, device
 * switcher) with the real storefront below in `?liveEdit=1` mode. No admin
 * sidebar (print group).
 */
export default function WebsiteHomeLiveEditPage() {
  return <ExcellentLiveEditEmbedPanel shell />;
}
