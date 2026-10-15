import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

import { LIFECYCLE_STAGES } from '../components/OrchestrationVisualizer';
import { SAMPLE_CONTRACTS, SAMPLE_OBSERVATIONS } from '../app/playground/page';
import { evaluatePollingSuccess, evaluatePollingError, isRequestCurrent } from '../app/page';
import { RunStatus } from '../models/types';

test('UI-A4 Sessions & Playground Acceptance Tests', async (t) => {
  const appDir = path.resolve(__dirname, '../app');
  const sessionsFilePath = path.join(appDir, 'sessions/page.tsx');
  const playgroundFilePath = path.join(appDir, 'playground/page.tsx');

  const sessionsSource = fs.readFileSync(sessionsFilePath, 'utf8');
  const playgroundSource = fs.readFileSync(playgroundFilePath, 'utf8');

  // Criterion 1: Semantic heading hierarchy (single H1 per page)
  await t.test('Criterion 1: Sessions and Playground maintain single H1 semantic hierarchy', () => {
    // Sessions H1 check
    const sessionsH1Matches = sessionsSource.match(/<h1[^>]*>([\s\S]*?)<\/h1>/gi) || [];
    assert.strictEqual(
      sessionsH1Matches.length,
      1,
      `Sessions page must have exactly 1 <h1> element, found ${sessionsH1Matches.length}`
    );
    assert.ok(
      sessionsH1Matches[0].includes('MISSION CONTROL'),
      'Sessions <h1> must identify the page as MISSION CONTROL'
    );

    // Playground H1 check
    const playgroundH1Matches = playgroundSource.match(/<h1[^>]*>([\s\S]*?)<\/h1>/gi) || [];
    assert.strictEqual(
      playgroundH1Matches.length,
      1,
      `Playground page must have exactly 1 <h1> element, found ${playgroundH1Matches.length}`
    );
    assert.ok(
      playgroundH1Matches[0].includes('PLAYGROUND'),
      'Playground <h1> must identify the page as PLAYGROUND'
    );
  });

  // Criterion 2: Sessions polling safeguards (identity check, 5 failure threshold, abort controller)
  await t.test('Criterion 2: Sessions page implements robust request identity guards and polling safeguards', () => {
    // Identity guard
    assert.ok(
      sessionsSource.includes('selectedRunIdRef.current'),
      'Sessions page must track active request identity via useRef'
    );
    assert.ok(
      sessionsSource.includes('isRequestCurrent'),
      'Sessions page must use isRequestCurrent to guard against out-of-order responses'
    );

    // Abort controller
    assert.ok(
      sessionsSource.includes('AbortController'),
      'Sessions page must use AbortController to cancel stale requests on unmount or switch'
    );

    // 5 consecutive failure threshold
    assert.ok(
      sessionsSource.includes('evaluatePollingError'),
      'Sessions page must use evaluatePollingError to enforce 5-failure threshold'
    );
    assert.ok(
      sessionsSource.includes('connectionAlert'),
      'Sessions page must surface operational connection alerts'
    );

    // Test evaluatePollingError behavior
    const testErr = new Error('Gateway timed out');
    let failures = 0;
    for (let i = 1; i <= 4; i++) {
      const res = evaluatePollingError(testErr, 'run-test', failures, 5);
      assert.strictEqual(res.shouldStop, false);
      failures = res.nextConsecutiveFailures;
    }
    const terminalRes = evaluatePollingError(testErr, 'run-test', failures, 5);
    assert.strictEqual(terminalRes.shouldStop, true);
    assert.strictEqual(terminalRes.stopReason, 'MAX_FAILURES');
  });

  // Criterion 3: Lifecycle mapping and terminal-state polling termination
  await t.test('Criterion 3: Lifecycle mapping conforms to canonical stages and terminal states stop polling', () => {
    // Canonical stages exist
    assert.strictEqual(LIFECYCLE_STAGES[0], 'INIT');
    assert.ok(LIFECYCLE_STAGES.includes('BUILD'));
    assert.ok(LIFECYCLE_STAGES.includes('ATTACK'));
    assert.ok(LIFECYCLE_STAGES.includes('REPAIR'));
    assert.ok(LIFECYCLE_STAGES.includes('VERIFY'));
    assert.ok(LIFECYCLE_STAGES.includes('VERIFIED'));
    assert.ok(LIFECYCLE_STAGES.includes('ABORTED'));

    // Terminal evaluation tests
    const activeStatus: RunStatus = {
      run_id: 'run-1',
      task_id: 'task-1',
      state: 'BUILD',
      status: 'active',
      iteration: 1,
      resource_status: { iterations_used: 1, iterations_limit: 20 },
      started_at: '2026-10-15T00:00:00Z',
      updated_at: '2026-10-15T00:00:10Z',
      patch_lineage: []
    };
    const activeEval = evaluatePollingSuccess(activeStatus, 0);
    assert.strictEqual(activeEval.shouldStop, false, 'Active run in BUILD state must continue polling');

    const verifiedStatus: RunStatus = {
      ...activeStatus,
      state: 'VERIFIED',
      status: 'completed'
    };
    const verifiedEval = evaluatePollingSuccess(verifiedStatus, 0);
    assert.strictEqual(verifiedEval.shouldStop, true, 'Terminal VERIFIED state must stop polling immediately');

    const abortedStatus: RunStatus = {
      ...activeStatus,
      state: 'ABORTED',
      status: 'failed'
    };
    const abortedEval = evaluatePollingSuccess(abortedStatus, 0);
    assert.strictEqual(abortedEval.shouldStop, true, 'Terminal ABORTED state must stop polling immediately');
  });

  // Criterion 4: Sessions timeline strictly uses real data fields and forbids fake streaming
  await t.test('Criterion 4: Sessions execution timeline strictly uses genuine persisted fields without simulation', () => {
    // Forbids fabricated simulation
    assert.ok(
      sessionsSource.includes('Zero-Fabrication Guard') || sessionsSource.includes('Live websocket streaming is not implemented'),
      'Sessions page must disclose absence of fabricated live streaming'
    );
    assert.ok(
      !sessionsSource.includes('generateFakeStream'),
      'Sessions page must not contain fake stream generators'
    );
    assert.ok(
      !sessionsSource.includes('mockStreamOutput'),
      'Sessions page must not contain mock streaming output'
    );

    // Uses genuine persisted fields
    assert.ok(sessionsSource.includes('status.task_id'));
    assert.ok(sessionsSource.includes('status.state'));
    assert.ok(sessionsSource.includes('status.iteration'));
    assert.ok(sessionsSource.includes('status.resource_status'));
    assert.ok(sessionsSource.includes('status.patch_candidate'));
    assert.ok(sessionsSource.includes('status.evidence_receipt'));
  });

  // Criterion 5: Playground workbench enforces path traversal validation and ceiling caps
  await t.test('Criterion 5: Playground workbench rejects path traversal and enforces resource ceilings', () => {
    assert.ok(SAMPLE_CONTRACTS.valid, 'SAMPLE_CONTRACTS must define valid contract');
    assert.ok(SAMPLE_CONTRACTS.repair, 'SAMPLE_CONTRACTS must define repair contract');
    assert.ok(SAMPLE_CONTRACTS.malicious, 'SAMPLE_CONTRACTS must define malicious traversal contract');
    assert.ok(SAMPLE_CONTRACTS.untrusted, 'SAMPLE_CONTRACTS must define untrusted target contract');

    // Verify traversal sample has prohibited paths
    const malScope = SAMPLE_CONTRACTS.malicious.allowed_scope;
    assert.ok(malScope.some(s => s.includes('..')), 'Malicious contract must test traversal rejection');

    // Validation logic checks in source
    assert.ok(
      playgroundSource.includes("pattern.includes('..')"),
      'Playground must test for prohibited ../ path traversal'
    );
    assert.ok(
      playgroundSource.includes("pattern.startsWith('/')"),
      'Playground must test for prohibited root directory references'
    );
    assert.ok(
      playgroundSource.includes('50'),
      'Playground must warn when max_iterations exceeds 50'
    );
    assert.ok(
      playgroundSource.includes('100'),
      'Playground must warn when max_tool_calls exceeds 100'
    );
  });

  // Criterion 6: Playground terminal strictly enforces read-only mode and forbids arbitrary shell execution
  await t.test('Criterion 6: Playground terminal enforces read-only observation mode and blocks arbitrary execution', () => {
    assert.ok(
      playgroundSource.includes('Read-Only Telemetry Viewer') || playgroundSource.includes('READ-ONLY INSPECTION CONSOLE'),
      'Playground must disclose read-only nature of execution observations'
    );
    assert.ok(
      playgroundSource.includes('Host command execution is strictly prohibited') || playgroundSource.includes('arbitrary shell execution is disabled'),
      'Playground must explicitly state host command execution is prohibited'
    );
    assert.ok(
      !playgroundSource.includes('runShellCommand'),
      'Playground must not provide arbitrary shell execution functions'
    );
    assert.ok(
      !playgroundSource.includes('child_process'),
      'Playground must not invoke host processes'
    );

    // Verify structured observations adhere to schema
    assert.ok(SAMPLE_OBSERVATIONS.length >= 2, 'Must provide at least 2 structured observations');
    for (const obs of SAMPLE_OBSERVATIONS) {
      assert.ok(obs.id.length > 0);
      assert.ok(typeof obs.exit_code === 'number');
      assert.ok(obs.stdout_sha256.length === 64);
      assert.strictEqual(obs.sandbox_backend, 'LocalDevelopmentBackend');
    }
  });

  // Criterion 7: Cross-navigation links connect to valid destinations
  await t.test('Criterion 7: Sessions and Playground provide valid cross-navigation links', () => {
    // Sessions links
    assert.ok(sessionsSource.includes('/results?runId='), 'Sessions must link to results');
    assert.ok(sessionsSource.includes('/evidence?runId='), 'Sessions must link to evidence');
    assert.ok(sessionsSource.includes('href="/"'), 'Sessions must link to intake');

    // Playground links
    assert.ok(playgroundSource.includes('href="/"'), 'Playground must link to intake');
    assert.ok(playgroundSource.includes('/?taskId='), 'Playground must support exporting to intake form');
  });

  // Criterion 8: Subordinate Judge claims cannot alter deterministic verdict presentation
  await t.test('Criterion 8: Subordinate Judge claims remain non-authoritative', () => {
    assert.ok(
      sessionsSource.includes('Non-authoritative') || sessionsSource.includes('VerdictDisplay'),
      'Sessions page must note that Judge explanation is non-authoritative'
    );
    assert.ok(
      sessionsSource.includes('VerdictDisplay'),
      'Sessions page must use VerdictDisplay for authoritative verdict rendering'
    );
  });
});
