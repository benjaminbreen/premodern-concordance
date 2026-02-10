import { redirect } from "next/navigation";

export default async function BookDefaultPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  redirect(`/books/${id}/about`);
}
