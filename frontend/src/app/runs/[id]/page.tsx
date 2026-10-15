import React, { Suspense } from 'react';
import { redirect } from 'next/navigation';

interface Props {
  params: Promise<{ id: string }>;
}

async function RedirectToRunResult({ params }: Props) {
  const resolved = await params;
  redirect(`/results?runId=${encodeURIComponent(resolved.id)}`);
  return null;
}

export default function RunResultDetailPage({ params }: Props) {
  return (
    <Suspense fallback={<div className="p-12 text-center text-xs font-mono text-slate-500">Redirecting to Run Results...</div>}>
      <RedirectToRunResult params={params} />
    </Suspense>
  );
}
