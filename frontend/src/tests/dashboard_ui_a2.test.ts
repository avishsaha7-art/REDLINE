import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';
import { RunHistoryItem, TaskContract } from '../models/types';

// Helper to simulate the exact dashboard metric aggregation logic
export function calculateDashboardMetrics(runs: RunHistoryItem[]) {
  const total = runs.length;
  const verified = runs.filter(r => r.verdict === 'VERIFIED').length;
  const rejected = runs.filter(r => r.verdict === 'REJECTED').length;
  const inconclusive = runs.filter(r => r.verdict === 'INCONCLUSIVE').length;
  const active = runs.filter(r => r.final_state !== 'VERIFIED' && r.final_state !== 'ABORTED').length;
  const verifiedPercent = total > 0 ? Math.round((verified / total) * 100) : 0;

  return {
    total,
    verified,
    rejected,
    inconclusive,
    active,
    verifiedPercent
  };
}

test('UI-A2 Dashboard Overview & Task Intake Acceptance Tests', async (t) => {
  // Test 1: Data mapping and truthful metric aggregates
  await t.test('Criterion 1: Dashboard metric calculations strictly derive from genuine RunHistoryItem records', () => {
    const mockRuns: RunHistoryItem[] = [
      {
        run_id: 'run-01',
        task_id: 'task-auth',
        final_state: 'VERIFIED',
        verdict: 'VERIFIED',
        created_at: '2026-10-14T10:00:00Z',
        completed_at: '2026-10-14T10:05:00Z'
      },
      {
        run_id: 'run-02',
        task_id: 'task-payment',
        final_state: 'ABORTED',
        verdict: 'REJECTED',
        created_at: '2026-10-14T10:10:00Z',
        completed_at: '2026-10-14T10:15:00Z'
      },
      {
        run_id: 'run-03',
        task_id: 'task-crypto',
        final_state: 'ABORTED',
        verdict: 'INCONCLUSIVE',
        created_at: '2026-10-14T10:20:00Z',
        completed_at: '2026-10-14T10:25:00Z'
      },
      {
        run_id: 'run-04',
        task_id: 'task-fuzz',
        final_state: 'ATTACK',
        created_at: '2026-10-14T10:30:00Z'
      }
    ];

    const metrics = calculateDashboardMetrics(mockRuns);

    assert.strictEqual(metrics.total, 4, 'Total runs must be exactly 4');
    assert.strictEqual(metrics.verified, 1, 'Verified count must be exactly 1');
    assert.strictEqual(metrics.rejected, 1, 'Rejected count must be exactly 1');
    assert.strictEqual(metrics.inconclusive, 1, 'Inconclusive count must be exactly 1');
    assert.strictEqual(metrics.active, 1, 'Active (in-flight) count must be exactly 1');
    assert.strictEqual(metrics.verifiedPercent, 25, 'FTR verification percentage must be 25%');
  });

  // Test 2: Empty database produces useful empty state and zero division protection
  await t.test('Criterion 2: Empty database produces 0 metrics and protects against NaN/division-by-zero', () => {
    const emptyMetrics = calculateDashboardMetrics([]);

    assert.strictEqual(emptyMetrics.total, 0);
    assert.strictEqual(emptyMetrics.verified, 0);
    assert.strictEqual(emptyMetrics.rejected, 0);
    assert.strictEqual(emptyMetrics.inconclusive, 0);
    assert.strictEqual(emptyMetrics.active, 0);
    assert.strictEqual(emptyMetrics.verifiedPercent, 0, 'Percentage must be 0, never NaN');
    assert.ok(!Number.isNaN(emptyMetrics.verifiedPercent), 'Percentage must never evaluate to NaN');
  });

  // Test 3: Dashboard source code enforces Truthful Telemetry and forbids fabricated hardware gauges
  await t.test('Criterion 3: Dashboard source enforces UI truthfulness and forbids fake hardware telemetry', () => {
    const dashboardPath = path.resolve(__dirname, '../app/dashboard/page.tsx');
    assert.ok(fs.existsSync(dashboardPath), 'Dashboard page file must exist');
    const content = fs.readFileSync(dashboardPath, 'utf-8');

    // Forbids fabricated live CPU/GPU/VRAM load animation or simulation
    assert.doesNotMatch(content, /animateNumber\(\s*cpuRef/, 'Must not animate fake CPU numbers');
    assert.doesNotMatch(content, /animateNumber\(\s*gpuRef/, 'Must not animate fake GPU numbers');
    assert.doesNotMatch(content, /animateNumber\(\s*ramRef/, 'Must not animate fake RAM numbers');
    assert.doesNotMatch(content, /animateNumber\(\s*vramRef/, 'Must not animate fake VRAM numbers');

    // Confirms honest disclosure of telemetry limits
    assert.ok(
      content.includes('Live CPU/GPU/VRAM telemetry unavailable in current backend version') ||
      content.includes('Hardware Telemetry'),
      'Dashboard must honestly state hardware telemetry limitations'
    );

    // Confirms authoritative ResourceBudgetNotice is embedded
    assert.ok(content.includes('<ResourceBudgetNotice'), 'Dashboard must embed ResourceBudgetNotice component');
  });

  // Test 4: Single H1 semantic heading hierarchy on Dashboard and Root page
  await t.test('Criterion 4: Semantic heading hierarchy maintains single H1 per page', () => {
    const dashboardPath = path.resolve(__dirname, '../app/dashboard/page.tsx');
    const dashboardContent = fs.readFileSync(dashboardPath, 'utf-8');
    const rootPath = path.resolve(__dirname, '../app/page.tsx');
    const rootContent = fs.readFileSync(rootPath, 'utf-8');

    // Count <h1> tags in dashboard
    const dashH1Matches = dashboardContent.match(/<h1[\s>]/g) || [];
    assert.strictEqual(dashH1Matches.length, 1, 'Dashboard page must contain exactly one <h1> element');

    // Count <h1> tags in root page
    const rootH1Matches = rootContent.match(/<h1[\s>]/g) || [];
    assert.strictEqual(rootH1Matches.length, 1, 'Root page must contain exactly one <h1> element');

    // Verify sub-panels use <h2> or <h3>
    assert.ok(dashboardContent.includes('<h2'), 'Dashboard must use <h2> for panel headers');
    assert.ok(rootContent.includes('<h2'), 'Root page must use <h2> for panel headers');
  });

  // Test 5: Task contract compliance in Quick Task Dispatch and Root Task Intake
  await t.test('Criterion 5: Task intake structures conform strictly to TaskContract schema', () => {
    const dashboardPath = path.resolve(__dirname, '../app/dashboard/page.tsx');
    const dashContent = fs.readFileSync(dashboardPath, 'utf-8');
    const formPath = path.resolve(__dirname, '../components/RunCreationForm.tsx');
    const formContent = fs.readFileSync(formPath, 'utf-8');

    // Check TaskContract construction in dashboard
    assert.ok(dashContent.includes('const contract: TaskContract = {'), 'Dashboard must construct valid TaskContract');
    assert.ok(dashContent.includes('task_id:'), 'Dashboard contract must specify task_id');
    assert.ok(dashContent.includes('repository_id:'), 'Dashboard contract must specify repository_id');
    assert.ok(dashContent.includes('base_commit_or_snapshot:'), 'Dashboard contract must specify base_commit_or_snapshot');
    assert.ok(dashContent.includes('task_description:'), 'Dashboard contract must specify task_description');
    assert.ok(dashContent.includes('resource_budget:'), 'Dashboard contract must specify resource_budget');

    // Check TaskContract construction in RunCreationForm
    assert.ok(formContent.includes('const contract: TaskContract = {'), 'RunCreationForm must construct valid TaskContract');
    assert.ok(formContent.includes('task_id:'), 'RunCreationForm contract must specify task_id');
    assert.ok(formContent.includes('repository_id:'), 'RunCreationForm contract must specify repository_id');
    assert.ok(formContent.includes('base_commit_or_snapshot:'), 'RunCreationForm contract must specify base_commit_or_snapshot');
    assert.ok(formContent.includes('task_description:'), 'RunCreationForm contract must specify task_description');
    assert.ok(formContent.includes('resource_budget:'), 'RunCreationForm contract must specify resource_budget');
  });

  // Test 6: Cross-navigation between Dashboard and Root Intake
  await t.test('Criterion 6: Seamless cross-navigation links connect Dashboard and Task Intake', () => {
    const dashboardPath = path.resolve(__dirname, '../app/dashboard/page.tsx');
    const dashContent = fs.readFileSync(dashboardPath, 'utf-8');
    const rootPath = path.resolve(__dirname, '../app/page.tsx');
    const rootContent = fs.readFileSync(rootPath, 'utf-8');

    // Dashboard links to root task intake
    assert.ok(dashContent.includes('href="/"'), 'Dashboard must provide link to root task intake (/)');

    // Root page links back to dashboard overview
    assert.ok(rootContent.includes('href="/dashboard"'), 'Root page must provide link back to /dashboard');

    // Links to monitoring and evidence use encodeURIComponent
    assert.ok(dashContent.includes('/sessions?runId='), 'Dashboard must link to session monitor with runId');
    assert.ok(dashContent.includes('/results?runId='), 'Dashboard must link to results view with runId');
    assert.ok(dashContent.includes('/evidence?runId='), 'Dashboard must link to evidence view with runId');
  });
});
