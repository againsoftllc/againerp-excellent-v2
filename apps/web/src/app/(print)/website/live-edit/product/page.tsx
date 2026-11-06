import { ExcellentLiveEditEmbedPanel } from "@/components/website/live-edit/excellent-live-edit-embed-panel";

/**
 * Full-screen Live Edit for one product: toolbar on top (device switcher), the product's storefront page below in
 * `?liveEdit=1` mode and the product's full editor open. Opened by the storefront's "Edit product" button with
 * `?slug=<address>&id=<product id>`.
 */
export default async function WebsiteProductLiveEditPage({ searchParams }: { searchParams: Promise<{ slug?: string; id?: string }> }) {
  const { slug = "", id = "" } = await searchParams;
  return <ExcellentLiveEditEmbedPanel shell page="product" productId={id} productSlug={slug} />;
}
