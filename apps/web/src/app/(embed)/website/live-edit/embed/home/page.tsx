import { ExcellentLiveEditEmbedPanel } from "@/components/website/live-edit/excellent-live-edit-embed-panel";

/**
 * Chrome-less Live Edit panel, embedded by the storefront itself
 * (`/?liveEdit=1`) so editors work directly on the real site.
 */
export default function WebsiteHomeLiveEditEmbedPage() {
  return <ExcellentLiveEditEmbedPanel />;
}
