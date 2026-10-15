import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

import { 
  prefersReducedMotion, 
  animateEntrance, 
  animateTableRows, 
  animateNumber, 
  animateButtonFeedback 
} from '../lib/anime';

test('Anime.js Motion & Interaction Design Acceptance Tests', async (t) => {
  // Test 1: Library integration and package version verification
  await t.test('Criterion 1: animejs is installed at modern v4.x and exports valid API', () => {
    const pkgPath = path.resolve(__dirname, '../../package.json');
    const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
    assert.ok(pkg.dependencies.animejs, 'animejs must be present in package.json dependencies');
    assert.ok(
      pkg.dependencies.animejs.includes('4.') || pkg.dependencies.animejs.startsWith('^4') || pkg.dependencies.animejs.startsWith('~4'),
      `animejs version must be 4.x, got: ${pkg.dependencies.animejs}`
    );
  });

  // Test 2: prefers-reduced-motion handling
  await t.test('Criterion 2: prefersReducedMotion correctly detects user motion preference', () => {
    // In node/SSR environment without window, prefersReducedMotion returns false safely
    assert.strictEqual(typeof prefersReducedMotion(), 'boolean');

    // When window is mocked with reduce: true
    const originalWindow = global.window;
    try {
      global.window = {
        matchMedia: (query: string) => ({
          matches: query.includes('prefers-reduced-motion: reduce'),
          media: query,
          onchange: null,
          addListener: () => {},
          removeListener: () => {},
          addEventListener: () => {},
          removeEventListener: () => {},
          dispatchEvent: () => false,
        })
      } as unknown as Window & typeof globalThis;

      assert.strictEqual(prefersReducedMotion(), true, 'Should detect reduced motion when query matches');

      // Functions must safely return null when reduced motion is requested
      const mockElem = { textContent: '0' } as unknown as HTMLElement;
      const res = animateNumber(mockElem, 0, 10);
      assert.strictEqual(res, null, 'animateNumber should return null and not schedule animation under reduced motion');
      assert.strictEqual(mockElem.textContent, '10', 'animateNumber must immediately apply target value when reduced motion is active');

      const btnRes = animateButtonFeedback(mockElem, 'press');
      assert.strictEqual(btnRes, null, 'animateButtonFeedback must return null under reduced motion');

      const entRes = animateEntrance([]);
      assert.strictEqual(entRes, null, 'animateEntrance must return null under reduced motion');
    } finally {
      global.window = originalWindow;
    }
  });

  // Test 3: Dashboard source code adheres to anti-delay and unmount cleanup principles
  await t.test('Criterion 3: Dashboard component implements unmount cleanup and non-delayed controls', () => {
    const dashPath = path.resolve(__dirname, '../app/dashboard/page.tsx');
    assert.ok(fs.existsSync(dashPath), 'Dashboard page file must exist');
    const content = fs.readFileSync(dashPath, 'utf8');

    // Verifies cleanup of active animations
    assert.ok(
      content.includes('activeAnimationsRef.current.forEach') || content.includes('revert?.()'),
      'Dashboard must revert/clean up active animations on component unmount'
    );

    // Verifies entrance animation guards against repeating in React Strict Mode
    assert.ok(
      content.includes('hasEnteredRef.current'),
      'Dashboard must guard entrance animation to avoid repeating on re-renders'
    );

    // Verifies polling anti-replay guard on table rows
    assert.ok(
      content.includes('prevRunIdsRef.current'),
      'Dashboard must track row IDs to prevent replaying row entrance animations on identical polling refreshes'
    );

    // Verifies immediate interactivity: controls are not disabled waiting for animations
    assert.ok(
      !content.includes('animationDelay: "9999ms"'),
      'Dashboard must not block user controls behind animation delays'
    );
  });

  // Test 4: Task submission success animation is gated on authoritative response
  await t.test('Criterion 4: Success feedback is strictly triggered after authoritative API response', () => {
    const dashPath = path.resolve(__dirname, '../app/dashboard/page.tsx');
    const content = fs.readFileSync(dashPath, 'utf8');

    // Ensure createRun is called and awaited before success feedback
    const createRunIndex = content.indexOf('apiClient.createRun(contract)');
    const successAnimIndex = content.indexOf("animateButtonFeedback(submitBtnRef.current, 'success')");

    assert.ok(createRunIndex > 0, 'apiClient.createRun must be called in task submit handler');
    assert.ok(successAnimIndex > 0, 'Success feedback animation must be called');
    assert.ok(
      successAnimIndex > createRunIndex,
      'Success feedback animation must be executed strictly AFTER awaiting apiClient.createRun'
    );
  });

  // Test 5: Number animations only operate on genuine metrics
  await t.test('Criterion 5: KPI number animations operate strictly on genuine counts, not fabricated hardware metrics', () => {
    const dashPath = path.resolve(__dirname, '../app/dashboard/page.tsx');
    const content = fs.readFileSync(dashPath, 'utf8');

    // Ensures genuine metrics are animated
    assert.ok(content.includes('animateNumber(totalRef.current, prev.total, total)'), 'Total runs must be animated from genuine count');
    assert.ok(content.includes('animateNumber(verifiedRef.current, prev.verified, verified)'), 'Verified count must be animated from genuine count');

    // Ensures NO fake CPU/GPU/memory meters are animated
    assert.ok(!content.includes('animateNumber(cpuRef'), 'Must not animate fake CPU metrics');
    assert.ok(!content.includes('animateNumber(gpuRef'), 'Must not animate fake GPU metrics');
    assert.ok(!content.includes('animateNumber(ramRef'), 'Must not animate fake RAM metrics');
  });

  // Test 6: Safe fallback if DOM or animation initialization fails
  await t.test('Criterion 6: Helper functions gracefully handle null targets and exceptions', () => {
    // Calling with null elements does not throw
    assert.doesNotThrow(() => {
      const res = animateNumber(null, 0, 5);
      assert.strictEqual(res, null);
    });

    assert.doesNotThrow(() => {
      const res = animateButtonFeedback(null, 'press');
      assert.strictEqual(res, null);
    });

    assert.doesNotThrow(() => {
      let completed = false;
      animateEntrance([], () => {
        completed = true;
      });
      // In node, immediately calls onComplete
      assert.strictEqual(completed, true);
    });
  });
});
