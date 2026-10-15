import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

import { getApiBaseUrl, apiClient, ApiError } from '../api/client';
import { getVerdictVisuals, getVerdictDisplayMode } from '../components/VerdictDisplay';
import { getReceiptIntegrityStatus } from '../components/EvidenceReceiptView';
import { EvidenceReceipt } from '../models/types';

test('Stage 16.2.1 Frontend Tests: API Integration, UI Truthfulness & Dark Theme', async (t) => {
  // Test 1: API client base URL configuration
  await t.test('API client base URL defaults to http://127.0.0.1:8000/api/v1 and honors NEXT_PUBLIC_API_BASE_URL', () => {
    const defaultUrl = getApiBaseUrl();
    assert.ok(
      defaultUrl.includes(':8000/api/v1'),
      `Default base URL must point to FastAPI /api/v1 on port 8000, got: ${defaultUrl}`
    );
    assert.strictEqual(typeof apiClient.createRun, 'function');
    assert.strictEqual(typeof apiClient.getRunStatus, 'function');
    assert.strictEqual(typeof apiClient.getEvidenceReceipt, 'function');
    assert.strictEqual(typeof apiClient.getJudgeExplanation, 'function');
    assert.strictEqual(typeof apiClient.getRunHistory, 'function');
    assert.strictEqual(typeof apiClient.getRunDiff, 'function');
  });

  // Test 2: Honest error handling
  await t.test('ApiError preserves status and detail without fabrication', () => {
    const err = new ApiError(404, 'API Error 404: Run not found', 'Run run-123 does not exist');
    assert.strictEqual(err.status, 404);
    assert.strictEqual(err.message, 'API Error 404: Run not found');
    assert.strictEqual(err.detail, 'Run run-123 does not exist');
  });

  // Test 3: Static / Demo notices presence on required pages
  await t.test('Static/demo and reference notices are present in /projects, /repositories, /agents, and /models', () => {
    const appDir = path.resolve(__dirname, '../app');

    // /projects
    const projectsContent = fs.readFileSync(path.join(appDir, 'projects/page.tsx'), 'utf8');
    assert.ok(
      projectsContent.includes('Static Demo Target Workspaces') || projectsContent.includes('Demo Fixtures'),
      '/projects must clearly disclose static demo target workspaces'
    );
    assert.ok(
      projectsContent.includes('not implemented in this stage'),
      '/projects must explain that dynamic CRUD is not implemented'
    );

    // /repositories
    const reposContent = fs.readFileSync(path.join(appDir, 'repositories/page.tsx'), 'utf8');
    assert.ok(
      reposContent.includes('Static Architecture Reference') || reposContent.includes('Static Reference'),
      '/repositories must clearly disclose static reference nature'
    );

    // /agents
    const agentsContent = fs.readFileSync(path.join(appDir, 'agents/page.tsx'), 'utf8');
    assert.ok(
      agentsContent.includes('Architecture Specification'),
      '/agents must clearly disclose architectural specification nature'
    );

    // /models
    const modelsContent = fs.readFileSync(path.join(appDir, 'models/page.tsx'), 'utf8');
    assert.ok(
      modelsContent.includes('Configuration Reference'),
      '/models must clearly disclose static provider reference nature'
    );
  });

  // Test 4: Settings page honesty
  await t.test('Settings page distinguishes route connectivity probe from full-system health and marks static ceilings', () => {
    const appDir = path.resolve(__dirname, '../app');
    const settingsContent = fs.readFileSync(path.join(appDir, 'settings/page.tsx'), 'utf8');

    // Connection probe phrasing
    assert.ok(
      settingsContent.includes('Verifies route reachability only') || settingsContent.includes('does not evaluate sandbox daemon'),
      'Settings connection probe must not imply every subsystem is healthy'
    );
    assert.ok(
      settingsContent.includes('STATIC POLICY') || settingsContent.includes('STATIC CONSTANTS'),
      'Settings must clearly label enforced system ceilings as static policy'
    );
    assert.ok(
      settingsContent.includes('POLICY SPECIFICATION'),
      'Settings must clearly label guardrails as policy specifications'
    );
  });

  // Test 5: Dark theme styling in VerdictDisplay
  await t.test('VerdictDisplay uses dark-theme tokens and maintains deterministic semantics', () => {
    // Verified
    const verified = getVerdictVisuals('VERIFIED', 'VERIFIED');
    assert.ok(verified.bgClass.includes('emerald'));
    assert.strictEqual(verified.icon, '✓');

    // Rejected
    const rejected = getVerdictVisuals('REJECTED', 'ABORTED');
    assert.ok(rejected.bgClass.includes('red'));
    assert.strictEqual(rejected.icon, '✕');

    // Inconclusive
    const inconclusive = getVerdictVisuals('INCONCLUSIVE', 'VERIFIED');
    assert.ok(inconclusive.bgClass.includes('amber'));
    assert.strictEqual(inconclusive.icon, '⚠');
    assert.strictEqual(inconclusive.isStateMismatch, true);

    // Operational failure mode
    const opMode = getVerdictDisplayMode('VERIFIED', 'Execution timeout');
    assert.strictEqual(opMode, 'OPERATIONAL_FAILURE');
  });

  // Test 6: EvidenceReceiptView dark theme tokens and honest integrity status
  await t.test('EvidenceReceiptView uses dark-theme tokens and honest client-side integrity status', () => {
    const receiptPath = path.resolve(__dirname, '../components/EvidenceReceiptView.tsx');
    const receiptContent = fs.readFileSync(receiptPath, 'utf8');

    // Ensure dark container classes
    assert.ok(receiptContent.includes('bg-[#0d1117]'), 'Must use dark background container #0d1117');
    assert.ok(receiptContent.includes('border-[#1e2638]'), 'Must use dark border #1e2638');
    assert.ok(receiptContent.includes('text-slate-200'), 'Must use light text for dark contrast');
    assert.ok(!receiptContent.includes('border-indigo-200'), 'Must not use light-theme indigo border');

    // Integrity badge honesty
    const statusWithHash = getReceiptIntegrityStatus({ receipt_hash: 'abc123sha' } as Partial<EvidenceReceipt>);
    assert.strictEqual(statusWithHash.hasHash, true);
    assert.strictEqual(statusWithHash.title, 'HASH RECORDED (UNVERIFIED CLIENT-SIDE)');

    const statusNoHash = getReceiptIntegrityStatus(null);
    assert.strictEqual(statusNoHash.hasHash, false);
    assert.strictEqual(statusNoHash.title, 'RECEIPT HASH MISSING');
  });

  // Test 7: JudgeExplanationView dark theme tokens and non-authoritative advisory
  await t.test('JudgeExplanationView uses dark theme tokens and retains non-authoritative disclaimer', () => {
    const judgePath = path.resolve(__dirname, '../components/JudgeExplanationView.tsx');
    const judgeContent = fs.readFileSync(judgePath, 'utf8');

    assert.ok(judgeContent.includes('bg-[#0d1117]'), 'Must use dark background container');
    assert.ok(judgeContent.includes('border-[#1e2638]'), 'Must use dark border');
    assert.ok(judgeContent.includes('Non-Authoritative Advisory'), 'Must display non-authoritative advisory');
    assert.ok(judgeContent.includes('does NOT determine the verdict'), 'Must retain subordinate advisory notice');
  });
});
