import { ProjectClient } from "./ProjectClient";

// Static export pre-renders only the placeholder; the real id is read from the
// route in ProjectClient at runtime via window.location.pathname.
export function generateStaticParams() {
  return [{ id: "shell" }];
}

export default async function ProjectDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <ProjectClient projectId={id} />;
}
