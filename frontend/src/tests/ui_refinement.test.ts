import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

import { LIFECYCLE_STAGES, computeStageVisuals } from '../components/OrchestrationVisualizer';
import { 
  getVerdictVisuals, 
  getVerdictDisplayMode 
} from '../components/VerdictDisplay';
import { 
  getReceiptIntegrityStatus, 
  validateSandboxCapabilities 
} from '../components/EvidenceReceiptView';
import { 
  evaluatePollingSuccess, 
  evaluatePollingError, 
  isRequestCurrent 
} from '../app/page';
import { ApiError } from '../api/client';
import { EvidenceReceipt, RunStatus } from '../models/types';

test('Stage 14.1 UI/UX Refinement & Production Acceptance Criteria', async (t) => {
  // Criterion 1: INIT is represented correctly in the lifecycle stage sequence
  await t.test('Criterion 1: INIT is the first stage in production LIFECYCLE_STAGES', () => {
    assert.strictEqual(LIFECYCLE_STAGES[0], 'INIT', 'INIT must be the first stage in lifecycle sequence');
    assert.ok(LIFECYCLE_STAGES.includes('INIT'), 'LIFECYCLE_STAGES must include INIT');
    assert.ok(LIFECYCLE_STAGES.includes('VERIFIED'), 'LIFECYCLE_STAGES must include VERIFIED');
    assert.ok(LIFECYCLE_STAGES.includes('ABORTED'), 'LIFECYCLE_STAGES must include ABORTED');
    
    const expected = [
      'INIT', 'RECON', 'PLAN', 'BASELINE', 'BUILD', 'TEST', 
      'ATTACK', 'ANALYZE', 'REPAIR', 'VERIFY', 'JUDGE', 'VERIFIED', 'ABORTED'
    ];
    assert.deepStrictEqual(LIFECYCLE_STAGES, expected);
  });

  // Criterion 2: VERIFIED + INCONCLUSIVE never produces a green success banner (exercises production getVerdictVisuals)
  await t.test('Criterion 2: Production getVerdictVisuals: VERIFIED state + INCONCLUSIVE verdict strictly yields AMBER, never green', () => {
    const visuals = getVerdictVisuals('INCONCLUSIVE', 'VERIFIED');

    assert.strictEqual(visuals.isStateMismatch, true, 'State vs verdict mismatch must be detected');
    assert.ok(visuals.bgClass.includes('amber'), 'Banner background must use amber styling');
    assert.ok(visuals.textClass.includes('amber'), 'Banner text must use amber styling');
    assert.ok(!visuals.bgClass.includes('emerald'), 'Banner must never use emerald styling for inconclusive');
    assert.ok(!visuals.bgClass.includes('green'), 'Banner must never use green styling for inconclusive');
    assert.strictEqual(visuals.icon, '⚠', 'Icon for inconclusive must be warning');

    // Also verify normal VERIFIED verdict produces emerald
    const verifiedVisuals = getVerdictVisuals('VERIFIED', 'VERIFIED');
    assert.strictEqual(verifiedVisuals.isStateMismatch, false);
    assert.ok(verifiedVisuals.bgClass.includes('emerald'));
    assert.strictEqual(verifiedVisuals.icon, '✓');

    // And verify REJECTED verdict produces red
    const rejectedVisuals = getVerdictVisuals('REJECTED', 'ABORTED');
    assert.ok(rejectedVisuals.bgClass.includes('red'));
    assert.strictEqual(rejectedVisuals.icon, '✕');
  });

  // Criterion 3: Receipt integrity badge presents truthful unverified status (exercises production getReceiptIntegrityStatus)
  await t.test('Criterion 3: Production getReceiptIntegrityStatus presents truthful unverified status', () => {
    const receiptWithHash: Partial<EvidenceReceipt> = {
      receipt_hash: '3a7bd3e2360a3d29eea436fcfb7e44c735d117c42d1c1835420b6b9942dd4f1b',
    };
    const receiptWithoutHash: Partial<EvidenceReceipt> = {
      receipt_hash: null,
    };

    const badgeWithHash = getReceiptIntegrityStatus(receiptWithHash);
    assert.strictEqual(badgeWithHash.hasHash, true);
    assert.strictEqual(badgeWithHash.title, 'HASH RECORDED (UNVERIFIED CLIENT-SIDE)');
    assert.notStrictEqual(badgeWithHash.title, 'INTEGRITY: SECURE', 'Static SECURE badge must not be used');
    assert.notStrictEqual(badgeWithHash.title, 'HASH VERIFIED', 'Must not falsely claim hash was verified client-side');
    assert.ok(badgeWithHash.subtitle.includes('not independently verified'));

    const badgeWithoutHash = getReceiptIntegrityStatus(receiptWithoutHash);
    assert.strictEqual(badgeWithoutHash.hasHash, false);
    assert.strictEqual(badgeWithoutHash.title, 'RECEIPT HASH MISSING');
    assert.ok(badgeWithoutHash.subtitle.includes('No cryptographic signature recorded'));

    const nullBadge = getReceiptIntegrityStatus(null);
    assert.strictEqual(nullBadge.hasHash, false);
    assert.strictEqual(nullBadge.title, 'RECEIPT HASH MISSING');
  });

  // Criterion 4: Missing sandbox capability data is not displayed as confirmed isolation (exercises production validateSandboxCapabilities)
  await t.test('Criterion 4: Production validateSandboxCapabilities: missing or untrusted data safely handled without unsafe casts', () => {
    // Null, undefined, primitive, or array data
    assert.strictEqual(validateSandboxCapabilities(null), null);
    assert.strictEqual(validateSandboxCapabilities(undefined), null);
    assert.strictEqual(validateSandboxCapabilities('string'), null);
    assert.strictEqual(validateSandboxCapabilities([1, 2, 3]), null);

    // Empty object
    assert.strictEqual(validateSandboxCapabilities({}), null);

    // Object with unrecognized keys only
    assert.strictEqual(validateSandboxCapabilities({ unknown_field: 123 }), null);

    // Development sandbox capability payload matching backend LocalDevelopmentBackend
    const devPayload = {
      security_level: 'DEVELOPMENT_ONLY',
      process_isolation: 'NOT_AVAILABLE',
      network_isolation: 'NOT_AVAILABLE',
      filesystem_isolation: 'NOT_AVAILABLE',
      credential_isolation: 'ENFORCED',
      secure_untrusted_execution: false,
    };

    const parsed = validateSandboxCapabilities(devPayload);
    assert.ok(parsed !== null, 'Valid payload should parse');
    assert.strictEqual(parsed.security_level, 'DEVELOPMENT_ONLY');
    assert.strictEqual(parsed.process_isolation, 'NOT_AVAILABLE');
    assert.strictEqual(parsed.network_isolation, 'NOT_AVAILABLE');
    assert.strictEqual(parsed.filesystem_isolation, 'NOT_AVAILABLE');
    assert.strictEqual(parsed.credential_isolation, 'ENFORCED');
    assert.strictEqual(parsed.secure_untrusted_execution, false, 'Must never report true for development backend');
  });

  // Criterion 5: The Judge cannot override the deterministic verdict
  await t.test('Criterion 5: Subordinate Judge claims cannot alter deterministic verdict presentation', () => {
    const deterministicVerdict = 'REJECTED';
    const optimisticJudge = {
      summary: 'All checks passed successfully and the patch is completely correct.',
      verified_claims: ['Claim A passed', 'Claim B passed'],
      failed_claims: [],
      confidence: 'HIGH'
    };

    // Production visual verdict is computed exclusively from deterministicVerdict
    const visuals = getVerdictVisuals(deterministicVerdict, 'ABORTED');
    assert.ok(visuals.bgClass.includes('red'), 'Deterministic REJECTED must stay red despite optimistic judge');
    assert.ok(!visuals.bgClass.includes('emerald'), 'Optimistic judge must not convert REJECTED to emerald');
    assert.ok(optimisticJudge.summary.includes('passed'), 'Judge claim was optimistic');
    assert.strictEqual(visuals.icon, '✕');
  });

  // Criterion 6: Operational failures are segregated from verification verdicts (exercises production getVerdictDisplayMode)
  await t.test('Criterion 6: Production getVerdictDisplayMode: operational failures take precedence over code verdict', () => {
    // When operational error is present, display mode is OPERATIONAL_FAILURE even if verdict is present
    const opMode = getVerdictDisplayMode('VERIFIED', 'Docker daemon unavailable on /var/run/docker.sock');
    assert.strictEqual(opMode, 'OPERATIONAL_FAILURE', 'Operational error must take priority');

    // Normal deterministic verdict without error
    const verdictMode = getVerdictDisplayMode('REJECTED', null);
    assert.strictEqual(verdictMode, 'DETERMINISTIC_VERDICT');

    // Pending verdict
    const pendingMode = getVerdictDisplayMode(null, null);
    assert.strictEqual(pendingMode, 'VERDICT_PENDING');
  });

  // Criterion 7: Reduced-motion support and non-color status markers (exercises production computeStageVisuals)
  await t.test('Criterion 7: Production computeStageVisuals includes motion-safe animation and non-color text markers', () => {
    // Active stage (e.g., BUILD in progress)
    const activeVisuals = computeStageVisuals('BUILD', 'BUILD', 4, 4, false);
    assert.ok(
      activeVisuals.containerClass.includes('motion-safe:animate-pulse'),
      'Active stage must use motion-safe:animate-pulse to respect prefers-reduced-motion'
    );
    assert.strictEqual(activeVisuals.badgeText, '[Active]');
    assert.strictEqual(activeVisuals.icon, '●');

    // Completed past stage
    const completedVisuals = computeStageVisuals('RECON', 'BUILD', 4, 1, false);
    assert.strictEqual(completedVisuals.badgeText, '[Done]');
    assert.strictEqual(completedVisuals.icon, '✓');

    // Aborted terminal stage
    const abortedVisuals = computeStageVisuals('ABORTED', 'ABORTED', 12, 12, true);
    assert.strictEqual(abortedVisuals.badgeText, '[Aborted]');
    assert.strictEqual(abortedVisuals.icon, '✕');

    // Verified terminal stage
    const verifiedVisuals = computeStageVisuals('VERIFIED', 'VERIFIED', 11, 11, false);
    assert.strictEqual(verifiedVisuals.badgeText, '[Completed]');
    assert.strictEqual(verifiedVisuals.icon, '✓');

    // Pending upcoming stage
    const pendingVisuals = computeStageVisuals('JUDGE', 'BUILD', 4, 10, false);
    assert.strictEqual(pendingVisuals.badgeText, '[Pending]');
    assert.strictEqual(pendingVisuals.icon, '○');
  });

  // Criterion 8: Empty, pending, and error states remain usable and robust
  await t.test('Criterion 8: Robust empty, pending, and error state production fallbacks', () => {
    // Mode with null verdict and null error
    const emptyMode = getVerdictDisplayMode(null, null);
    assert.strictEqual(emptyMode, 'VERDICT_PENDING');

    // Missing capabilities
    const missingCaps = validateSandboxCapabilities(null);
    assert.strictEqual(missingCaps, null);

    // Missing receipt
    const missingReceipt = getReceiptIntegrityStatus(null);
    assert.strictEqual(missingReceipt.hasHash, false);
    assert.strictEqual(missingReceipt.title, 'RECEIPT HASH MISSING');
  });
});

test('Finding 1 Regression: In-flight run-selection race condition', async (t) => {
  await t.test('Out-of-order responses for two different runs: stale Run A never overwrites active Run B', async () => {
    let activeSelectedRunId = 'run-A';
    let currentUiState: { runId: string; status: string } | null = null;

    // Simulate async requests with deferred resolution
    type DeferredResolver = (val: { runId: string; status: string }) => void;
    let resolveRunA: DeferredResolver = () => {};
    let resolveRunB: DeferredResolver = () => {};

    const requestA = new Promise<{ runId: string; status: string }>((resolve) => {
      resolveRunA = resolve;
    });

    const requestB = new Promise<{ runId: string; status: string }>((resolve) => {
      resolveRunB = resolve;
    });

    // Step 1: User requests Run A
    const reqARunId = 'run-A';
    requestA.then((data) => {
      // Production guard: verify response belongs to currently selected run
      if (isRequestCurrent(reqARunId, activeSelectedRunId)) {
        currentUiState = data;
      }
    });

    // Step 2: User switches selection to Run B
    const reqBRunId = 'run-B';
    activeSelectedRunId = reqBRunId;
    requestB.then((data) => {
      if (isRequestCurrent(reqBRunId, activeSelectedRunId)) {
        currentUiState = data;
      }
    });

    // Step 3: Run B responds first
    resolveRunB({ runId: 'run-B', status: 'active' });
    await Promise.resolve(); // flush microtask queue
    assert.deepStrictEqual(currentUiState, { runId: 'run-B', status: 'active' });

    // Step 4: Run A responds later (out of order)
    resolveRunA({ runId: 'run-A', status: 'failed' });
    await Promise.resolve(); // flush microtask queue

    // Run A must NOT have overwritten Run B in currentUiState
    assert.deepStrictEqual(
      currentUiState, 
      { runId: 'run-B', status: 'active' },
      'Stale Run A response must be discarded and must NOT overwrite Run B'
    );
  });

  await t.test('isRequestCurrent rejects empty or non-matching IDs', () => {
    assert.strictEqual(isRequestCurrent('run-1', 'run-1'), true);
    assert.strictEqual(isRequestCurrent('  run-1  ', 'run-1'), true);
    assert.strictEqual(isRequestCurrent('run-1', 'run-2'), false);
    assert.strictEqual(isRequestCurrent('', 'run-1'), false);
    assert.strictEqual(isRequestCurrent('run-1', ''), false);
  });
});

test('Finding 2 Regression: Polling error handling and alerts', async (t) => {
  await t.test('Five consecutive failures terminates polling and produces operational connection alert', () => {
    const error = new Error('Network timeout');
    let failures = 0;

    // Failures 1 to 4: polling should continue
    for (let i = 1; i <= 4; i++) {
      const evaluation = evaluatePollingError(error, 'run-100', failures, 5);
      assert.strictEqual(evaluation.shouldStop, false, `Failure ${i} should not stop polling`);
      assert.strictEqual(evaluation.nextConsecutiveFailures, i);
      assert.strictEqual(evaluation.alertMessage, undefined);
      failures = evaluation.nextConsecutiveFailures;
    }

    // 5th failure: polling terminates with alert
    const terminalEval = evaluatePollingError(error, 'run-100', failures, 5);
    assert.strictEqual(terminalEval.shouldStop, true, '5th consecutive failure must stop polling');
    assert.strictEqual(terminalEval.stopReason, 'MAX_FAILURES');
    assert.ok(
      terminalEval.alertMessage?.includes('5 consecutive failures'),
      'Alert must mention 5 consecutive failures'
    );
    assert.ok(
      terminalEval.alertMessage?.includes('Operational connection alert'),
      'Alert must identify as operational connection alert'
    );
  });

  await t.test('Recovery after successful request resets consecutive failure count to 0', () => {
    const mockActiveStatus: RunStatus = {
      run_id: 'run-100',
      task_id: 'task-1',
      state: 'BUILD',
      status: 'active',
      iteration: 1,
      resource_status: { iterations_used: 1, iterations_limit: 20 },
      started_at: '',
      updated_at: '',
      patch_lineage: [],
    };

    // After 4 failures, a successful response resets failure count
    const recoveryEval = evaluatePollingSuccess(mockActiveStatus, 4);
    assert.strictEqual(recoveryEval.shouldStop, false);
    assert.strictEqual(recoveryEval.nextConsecutiveFailures, 0, 'Success must reset failure count to 0');
  });

  await t.test('Terminal run states stop polling immediately', () => {
    // Terminal VERIFIED state
    const verifiedStatus: RunStatus = {
      run_id: 'run-100',
      task_id: 'task-1',
      state: 'VERIFIED',
      status: 'completed',
      iteration: 3,
      resource_status: { iterations_used: 3, iterations_limit: 20 },
      started_at: '',
      updated_at: '',
      patch_lineage: [],
    };
    const evalCompleted = evaluatePollingSuccess(verifiedStatus, 0);
    assert.strictEqual(evalCompleted.shouldStop, true);
    assert.strictEqual(evalCompleted.stopReason, 'TERMINAL_STATE');

    // Terminal ABORTED state
    const abortedStatus: RunStatus = {
      run_id: 'run-100',
      task_id: 'task-1',
      state: 'ABORTED',
      status: 'failed',
      iteration: 2,
      resource_status: { iterations_used: 2, iterations_limit: 20 },
      started_at: '',
      updated_at: '',
      patch_lineage: [],
    };
    const evalAborted = evaluatePollingSuccess(abortedStatus, 0);
    assert.strictEqual(evalAborted.shouldStop, true);
    assert.strictEqual(evalAborted.stopReason, 'TERMINAL_STATE');
  });

  await t.test('HTTP 404 distinguishes from transient error and stops polling immediately', () => {
    const notFoundError = new ApiError(404, 'API Error 404: Run not found');
    const eval404 = evaluatePollingError(notFoundError, 'run-ghost', 0, 5);

    assert.strictEqual(eval404.shouldStop, true, 'HTTP 404 must stop polling immediately on first failure');
    assert.strictEqual(eval404.stopReason, 'NOT_FOUND_404');
    assert.ok(eval404.alertMessage?.includes('HTTP 404'));
    assert.ok(eval404.alertMessage?.includes('run-ghost'));
  });
});

test('Finding 4 Validation: Heading hierarchy and metadata', async (t) => {
  await t.test('layout.tsx contains REDLINE product metadata, not Next.js starter', () => {
    const layoutPath = path.resolve(__dirname, '../app/layout.tsx');
    const layoutContent = fs.readFileSync(layoutPath, 'utf-8');

    assert.ok(layoutContent.includes('title: "REDLINE'), 'Layout must have REDLINE title');
    assert.ok(layoutContent.includes('guilty until proven safe'), 'Layout must have REDLINE philosophy description');
    assert.ok(!layoutContent.includes('Create Next App'), 'Layout must not contain starter title');
    assert.ok(!layoutContent.includes('Generated by create next app'), 'Layout must not contain starter description');
  });

  await t.test('VerdictDisplay component uses h2 and h3, with zero h1 elements to preserve single page h1', () => {
    const verdictCompPath = path.resolve(__dirname, '../components/VerdictDisplay.tsx');
    const compContent = fs.readFileSync(verdictCompPath, 'utf-8');

    // Verify VerdictDisplay does NOT contain <h1
    assert.strictEqual(
      compContent.includes('<h1'), 
      false, 
      'VerdictDisplay must not contain any <h1> tags; page.tsx owns the single page h1'
    );

    // Verify VerdictDisplay contains <h2> and <h3>
    assert.ok(compContent.includes('<h2'), 'VerdictDisplay must use <h2> for section heading');
    assert.ok(compContent.includes('<h3'), 'VerdictDisplay must use <h3> for verdict / status');
  });
});
