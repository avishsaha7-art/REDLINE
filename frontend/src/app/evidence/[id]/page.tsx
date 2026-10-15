import React, { Suspense } from 'react';
import { redirect } from 'next/navigation';

interface Props {
  params: Promise<{ id: string }>;
}

async function RedirectToEvidence({ params }: Props) {
  const resolved = await params;
  redirect(`/evidence?runId=${encodeURIComponent(resolved.id)}`);
  return null;
}

export default function EvidenceDetailPage({ params }: Props) {
  return (
    <Suspense fallback={<div className="p-12 text-center text-xs font-mono text-slate-500">Redirecting to Evidence Audit...</div>}>
      <RedirectToEvidence params={params} />
    </Suspense>
  );
}
