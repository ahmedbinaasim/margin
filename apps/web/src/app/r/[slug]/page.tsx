import { ReportClient } from "./ReportClient";

// For static export we pre-render a placeholder shell. The real slug is read
// at runtime in the client (window.location.pathname).
export function generateStaticParams() {
  return [{ slug: "shell" }];
}

export default async function ReportPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return <ReportClient slug={slug} />;
}
