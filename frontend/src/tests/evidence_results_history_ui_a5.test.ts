import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { getReceiptIntegrityStatus, validateSandboxCapabilities } from '../components/EvidenceReceiptView';
import { getVerdictVisuals, getVerdictDisplayMode } from '../components/VerdictDisplay';
import { EvidenceReceipt } from '../models/types';

test('UI-A5 Evidence, Results & History Acceptance Tests', async (t) => {
  const evidencePath = path.resolve(__dirname, '../app/evidence/page.tsx');
  const resultsPath = path.resolve(__dirname, '../app/results/page.tsx');
  const historyPath = path.resolve(__dirname, '../app/history/page.tsx');

  const evidenceSource = fs.readFileSync(evidencePath, 'utf-8');
  const resultsSource = fs.readFileSync(resultsPath, 'utf-8');
  const historySource = fs.readFileSync(historyPath, 'utf-8');

  await t.test('Criterion 1: Evidence, Results, and History maintain single H1 semantic hierarchy', () => {
    const countH1 = (src: string) => (src.match(/<h1[\s>]/g) || []).length;
    assert.strictEqual(countH1(evidenceSource), 1, 'Evidence page must have exactly one <h1>');
    assert.strictEqual(countH1(resultsSource), 1, 'Results page must have exactly one <h1>');
    assert.strictEqual(countH1(historySource), 1, 'History page must have exactly one <h1>');

    assert.ok(evidenceSource.includes('08. Cryptographic Evidence &amp; Receipts'), 'Evidence page has proper title');
    assert.ok(resultsSource.includes('07. Run Verification Results'), 'Results page has proper title');
    assert.ok(historySource.includes('09. Verification History &amp; Audit Ledger'), 'History page has proper title');
  });

  await t.test('Criterion 2: Receipt integrity status truthfully distinguishes unverified client-side hashes', () => {
    // 1. Receipt with valid SHA-256 hash
    const receiptWithHash: Partial<EvidenceReceipt> = {
      receipt_hash: '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08'
    };
    const statusWithHash = getReceiptIntegrityStatus(receiptWithHash);
    assert.strictEqual(statusWithHash.hasHash, true);
    assert.ok(statusWithHash.title.includes('UNVERIFIED CLIENT-SIDE'), 'Must not claim cryptographic verification without client verifier');
    assert.ok(statusWithHash.subtitle.includes('Integrity not independently verified by frontend'));

    // 2. Receipt without hash
    const receiptNoHash: Partial<EvidenceReceipt> = {
      receipt_hash: ''
    };
    const statusNoHash = getReceiptIntegrityStatus(receiptNoHash);
    assert.strictEqual(statusNoHash.hasHash, false);
    assert.ok(statusNoHash.title.includes('MISSING'));

    // 3. Null receipt
    const nullStatus = getReceiptIntegrityStatus(null);
    assert.strictEqual(nullStatus.hasHash, false);
    assert.ok(nullStatus.title.includes('MISSING'));
  });

  await t.test('Criterion 3: Deterministic verdicts remain authoritative and semantically distinct', () => {
    // 1. VERIFIED strictly maps to emerald visuals
    const verifiedVisuals = getVerdictVisuals('VERIFIED', 'VERIFIED');
    assert.ok(verifiedVisuals.bgClass.includes('emerald'));
    assert.strictEqual(verifiedVisuals.icon, '✓');
    assert.strictEqual(verifiedVisuals.isStateMismatch, false);

    // 2. REJECTED strictly maps to red/rose visuals
    const rejectedVisuals = getVerdictVisuals('REJECTED', 'ABORTED');
    assert.ok(rejectedVisuals.bgClass.includes('red'));
    assert.strictEqual(rejectedVisuals.icon, '✕');

    // 3. INCONCLUSIVE strictly maps to amber visuals and never emerald
    const inconclusiveVisuals = getVerdictVisuals('INCONCLUSIVE', 'VERIFIED');
    assert.ok(inconclusiveVisuals.bgClass.includes('amber'));
    assert.strictEqual(inconclusiveVisuals.icon, '⚠');
    assert.strictEqual(inconclusiveVisuals.isStateMismatch, true, 'State VERIFIED with verdict INCONCLUSIVE must be flagged as mismatch');

    // 4. Operational failure takes precedence over verdict
    const opMode = getVerdictDisplayMode('VERIFIED', 'Docker sandbox timed out after 60s');
    assert.strictEqual(opMode, 'OPERATIONAL_FAILURE');
  });

  await t.test('Criterion 4: Judge natural-language explanations remain subordinate to deterministic verdicts', () => {
    // Evidence and Results must include Judge non-authoritative advisory disclaimers
    assert.ok(evidenceSource.includes('JudgeExplanationView'), 'Evidence page renders JudgeExplanationView');
    assert.ok(resultsSource.includes('JudgeExplanationView'), 'Results page renders JudgeExplanationView');

    // Ensure the Judge component source itself carries the strict non-authoritative disclaimer
    const judgePath = path.resolve(__dirname, '../components/JudgeExplanationView.tsx');
    const judgeSource = fs.readFileSync(judgePath, 'utf-8');
    assert.ok(judgeSource.includes('Non-Authoritative Advisory'), 'Judge view must feature Non-Authoritative Advisory header');
    assert.ok(judgeSource.includes('The Judge explains the evidence; it does NOT determine the verdict'), 'Judge view disclaimer must be explicit');
  });

  await t.test('Criterion 5: Evidence page provides genuine download controls and diff inspection', () => {
    // JSON download handling
    assert.ok(evidenceSource.includes('handleDownloadReceiptJson'), 'Evidence page implements JSON receipt download');
    assert.ok(evidenceSource.includes('application/json'), 'Download uses genuine application/json MIME blob');

    // DiffViewer integration
    assert.ok(evidenceSource.includes('DiffViewer'), 'Evidence page embeds DiffViewer');
    assert.ok(resultsSource.includes('DiffViewer'), 'Results page embeds DiffViewer');

    // DiffViewer must carry the security advisory
    const diffPath = path.resolve(__dirname, '../components/DiffViewer.tsx');
    const diffSource = fs.readFileSync(diffPath, 'utf-8');
    assert.ok(diffSource.includes('CODE AUDIT ADVISORY'), 'DiffViewer must enforce CODE AUDIT ADVISORY');
    assert.ok(diffSource.includes('does NOT prove code safety'), 'Advisory must state diff does not prove code safety');
  });

  await t.test('Criterion 6: History page implements search, filtering, and empty state separation', () => {
    assert.ok(historySource.includes('filteredHistory'), 'History page calculates filtered list');
    assert.ok(historySource.includes('verdictFilter'), 'History page provides verdict filtering');
    assert.ok(historySource.includes('searchTerm'), 'History page provides text search');
    assert.ok(historySource.includes('Reset Filters'), 'History page provides filter reset action');
    assert.ok(historySource.includes('No matching runs found'), 'History page has clear empty search state');
    assert.ok(historySource.includes('Submit a task contract to record your first run'), 'History page distinguishes empty database');
  });

  await t.test('Criterion 7: Cross-navigation destinations connect Evidence, Results, History, and Sessions', () => {
    assert.ok(evidenceSource.includes('/history'), 'Evidence links to /history');
    assert.ok(resultsSource.includes('/evidence?runId='), 'Results links to /evidence');
    assert.ok(resultsSource.includes('/sessions?runId='), 'Results links to /sessions');
    assert.ok(historySource.includes('/sessions?runId='), 'History links to /sessions');
    assert.ok(historySource.includes('/results?runId='), 'History links to /results');
    assert.ok(historySource.includes('/evidence?runId='), 'History links to /evidence');
  });

  await t.test('Criterion 8: Sandbox capabilities parser rejects malformed and untrusted data', () => {
    assert.strictEqual(validateSandboxCapabilities(null), null);
    assert.strictEqual(validateSandboxCapabilities(undefined), null);
    assert.strictEqual(validateSandboxCapabilities([]), null);
    assert.strictEqual(validateSandboxCapabilities('string'), null);
    assert.strictEqual(validateSandboxCapabilities({ random_unrelated_field: 123 }), null);

    const validCaps = validateSandboxCapabilities({
      process_isolation: 'ENFORCED',
      network_isolation: 'DROP_ALL',
      security_level: 'SECURE',
      secure_untrusted_execution: true
    });
    assert.ok(validCaps !== null);
    assert.strictEqual(validCaps?.process_isolation, 'ENFORCED');
    assert.strictEqual(validCaps?.network_isolation, 'DROP_ALL');
    assert.strictEqual(validCaps?.secure_untrusted_execution, true);
  });
});
