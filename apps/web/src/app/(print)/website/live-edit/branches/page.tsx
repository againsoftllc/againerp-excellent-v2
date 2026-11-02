import { ExcellentLiveEditEmbedPanel } from "@/components/website/live-edit/excellent-live-edit-embed-panel";

/** Full-screen Live Edit for the Branches page - same editor as Home, with the storefront's /branches below. */
export default function WebsiteBranchesLiveEditPage() {
  return <ExcellentLiveEditEmbedPanel shell page="branches" />;
}
