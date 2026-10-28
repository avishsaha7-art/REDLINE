import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

import { apiClient, ApiError } from '../api/client';
import { TaskContract, ImportRepositoryRequest, RepositoryResponse } from '../models/types';
import { getVerdictVisuals } from '../components/VerdictDisplay';
import { REPOSITORY_POLICIES, RepositoryPolicy } from '../app/repositories/page';

test('REDLINE Stage 2 — Frontend Repository Import and End-to-End Tests', async (t) => {
  const componentsDir = path.resolve(__dirname, '../components');
  const appDir = path.resolve(__dirname, '../app');

  const runCreationFormPath = path.join(componentsDir, 'RunCreationForm.tsx');
  const reposPagePath = path.join(appDir, 'repositories/page.tsx');
  const rootPagePath = path.join(appDir, 'page.tsx');

  const runCreationFormSource = fs.readFileSync(runCreationFormPath, 'utf8');
  const reposPageSource = fs.readFileSync(reposPagePath, 'utf8');
  const rootPageSource = fs.readFileSync(rootPagePath, 'utf8');

  // Test 1: RunCreationForm contains Remote Git Intake inputs and controls
  await t.test('Criterion 1: RunCreationForm provides Remote Git intake fields and actions', () => {
    assert.ok(runCreationFormSource.includes('id="repo-url-input"'), 'Form must have repo-url-input');
    assert.ok(runCreationFormSource.includes('id="commit-sha-input"'), 'Form must have commit-sha-input');
    assert.ok(runCreationFormSource.includes('id="import-repo-button"'), 'Form must have import-repo-button');
    assert.ok(runCreationFormSource.includes('id="remote-intake-tab"'), 'Form must have remote-intake-tab');
    assert.ok(runCreationFormSource.includes('id="presets-tab"'), 'Form must have presets-tab');
    assert.ok(runCreationFormSource.includes('id="launch-run-button"'), 'Form must have launch-run-button');
    assert.ok(runCreationFormSource.includes('importRepository'), 'Form must call importRepository');
  });

  // Test 2: RunCreationForm preserves demo presets A, B, C, D
  await t.test('Criterion 2: RunCreationForm preserves demo presets A, B, C, D', () => {
    assert.ok(runCreationFormSource.includes("loadScenario('A')"), 'Preset A must be callable');
    assert.ok(runCreationFormSource.includes("loadScenario('B')"), 'Preset B must be callable');
    assert.ok(runCreationFormSource.includes("loadScenario('C')"), 'Preset C must be callable');
    assert.ok(runCreationFormSource.includes("loadScenario('D')"), 'Preset D must be callable');
    assert.ok(runCreationFormSource.includes('task-demo-verified-01'), 'Scenario A task ID preserved');
    assert.ok(runCreationFormSource.includes('task-demo-untrusted-04'), 'Scenario D untrusted task ID preserved');
  });

  // Test 3: RunCreationForm constructs valid TaskContract and enforces UNTRUSTED for remote
  await t.test('Criterion 3: TaskContract construction and UNTRUSTED trust enforcement', () => {
    assert.ok(runCreationFormSource.includes('const contract: TaskContract = {'), 'Must declare TaskContract');
    assert.ok(runCreationFormSource.includes('task_id:'), 'Must specify task_id');
    assert.ok(runCreationFormSource.includes('repository_id:'), 'Must specify repository_id');
    assert.ok(runCreationFormSource.includes('base_commit_or_snapshot:'), 'Must specify base_commit_or_snapshot');
    assert.ok(runCreationFormSource.includes('task_description:'), 'Must specify task_description');
    assert.ok(runCreationFormSource.includes('resource_budget:'), 'Must specify resource_budget');
    assert.ok(runCreationFormSource.includes("contract.repository_trust = 'UNTRUSTED'"), 'Remote repository must be forced to UNTRUSTED');
  });

  // Test 4: Repositories page provides dynamic intake drawer and preserves static reference
  await t.test('Criterion 4: Repositories page provides dynamic intake drawer and preserves Section 47', () => {
    assert.ok(reposPageSource.includes('id="toggle-import-button"'), 'Page must have toggle-import-button');
    assert.ok(reposPageSource.includes('id="repo-page-url-input"'), 'Page must have repo-page-url-input');
    assert.ok(reposPageSource.includes('id="repo-page-commit-input"'), 'Page must have repo-page-commit-input');
    assert.ok(reposPageSource.includes('Security Boundary Enforcement (Section 47)'), 'Must retain Section 47 notice');
    assert.ok(reposPageSource.includes('backend/sandbox/trust.py'), 'Must cite backend/sandbox/trust.py');
    assert.ok(Array.isArray(REPOSITORY_POLICIES), 'Must export REPOSITORY_POLICIES');
    assert.ok(REPOSITORY_POLICIES.length >= 4, 'Must have at least 4 baseline policies');
  });

  // Test 5: Root page passes initialRepoId from URL query parameter
  await t.test('Criterion 5: Root page detects query parameter and passes initialRepoId', () => {
    assert.ok(rootPageSource.includes('initialRepoId='), 'page.tsx must pass initialRepoId to RunCreationForm');
    assert.ok(rootPageSource.includes('URLSearchParams'), 'page.tsx must read URLSearchParams');
    assert.ok(rootPageSource.includes('repoId'), 'page.tsx must read repoId param');
  });

  // Test 6: VerdictDisplay provides distinct styling for POLICY_BLOCKED
  await t.test('Criterion 6: VerdictDisplay correctly renders POLICY_BLOCKED verdict', () => {
    const blockedVisuals = getVerdictVisuals('POLICY_BLOCKED', 'ABORTED');
    assert.ok(blockedVisuals.bgClass.includes('rose'), 'POLICY_BLOCKED should use rose/red border styling');
    assert.strictEqual(blockedVisuals.icon, '🛡️', 'POLICY_BLOCKED should use shield icon');

    const verifiedVisuals = getVerdictVisuals('VERIFIED', 'VERIFIED');
    assert.strictEqual(verifiedVisuals.icon, '✓');

    const inconclusiveVisuals = getVerdictVisuals('INCONCLUSIVE', 'VERIFIED');
    assert.strictEqual(inconclusiveVisuals.icon, '⚠');
  });

  // Test 7: ApiClient exposes repository intake endpoints
  await t.test('Criterion 7: ApiClient exposes importRepository, listRepositories, getRepository', () => {
    assert.strictEqual(typeof apiClient.importRepository, 'function');
    assert.strictEqual(typeof apiClient.listRepositories, 'function');
    assert.strictEqual(typeof apiClient.getRepository, 'function');
    assert.strictEqual(typeof apiClient.createRun, 'function');
    assert.strictEqual(typeof apiClient.getRunStatus, 'function');
    assert.strictEqual(typeof apiClient.getRunHistory, 'function');
    assert.strictEqual(typeof apiClient.getRunDiff, 'function');
  });

  // Test 8: Mocked ApiClient integration for import and run creation
  await t.test('Criterion 8: Mocked import and run creation contracts', async () => {
    const originalFetch = globalThis.fetch;

    try {
      // Mock /api/v1/repositories/import
      globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
        const urlStr = typeof input === 'string' ? input : input.toString();

        if (urlStr.endsWith('/repositories/import')) {
          const body = JSON.parse(init?.body as string);
          if (!body.repository_url.startsWith('https://')) {
            return new Response(JSON.stringify({ detail: 'Only https allowed' }), { status: 400 });
          }
          return new Response(JSON.stringify({
            repository_id: 'repo-remote-test-12345',
            trust: 'UNTRUSTED',
            repository_url: body.repository_url,
            commit_sha: body.commit_sha,
            snapshot_hash: 'a'.repeat(64),
            file_manifest_hash: 'b'.repeat(64),
            file_count: 5,
            total_bytes: 4096,
            is_quarantined: true,
            registered_at: '2026-10-27T00:00:00Z'
          }), { status: 201 });
        }

        if (urlStr.endsWith('/runs') && init?.method === 'POST') {
          return new Response(JSON.stringify({ run_id: 'run-remote-verify-99' }), { status: 200 });
        }

        return new Response('Not Found', { status: 404 });
      };

      // 1. Import repository
      const importRes = await apiClient.importRepository({
        repository_url: 'https://github.com/octocat/Hello-World.git',
        commit_sha: '7fd1a60b01f91b314f59955a4e4d4e80d8edf11d'
      });

      assert.strictEqual(importRes.repository_id, 'repo-remote-test-12345');
      assert.strictEqual(importRes.trust, 'UNTRUSTED');
      assert.strictEqual(importRes.is_quarantined, true);

      // 2. Create Run with imported repository
      const runRes = await apiClient.createRun({
        task_id: 'task-e2e-remote-01',
        repository_id: importRes.repository_id,
        base_commit_or_snapshot: importRes.commit_sha || '7fd1a60b01f91b314f59955a4e4d4e80d8edf11d',
        task_description: 'Verify imported remote repo against security invariants',
        allowed_scope: [],
        repository_trust: 'UNTRUSTED',
        repository_url: importRes.repository_url || undefined,
        commit_sha: importRes.commit_sha || undefined
      });

      assert.strictEqual(runRes.run_id, 'run-remote-verify-99');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
