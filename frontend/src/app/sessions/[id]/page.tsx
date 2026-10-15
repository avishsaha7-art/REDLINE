import React, { Suspense } from 'react';
import { redirect } from 'next/navigation';

interface Props {
  params: Promise<{ id: string }>;
}

async function RedirectToSession({ params }: Props) {
  const resolved = await params;
  redirect(`/sessions?runId=${encodeURIComponent(resolved.id)}`);
  return null;
}

export default function SessionDetailPage({ params }: Props) {
  return (
    <Suspense fallback={<div className="p-12 text-center text-xs font-mono text-slate-500">Redirecting to Mission Control...</div>}>
      <RedirectToSession params={params} />
    </Suspense>
  );
}
