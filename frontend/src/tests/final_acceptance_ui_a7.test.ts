import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

test('UI-A7 Final UI Acceptance, Integration, Responsiveness & Polish Tests', async (t) => {
  const appDir = path.resolve(__dirname, '../app');
  const componentsDir = path.resolve(__dirname, '../components');

  const routes = [
    { file: 'page.tsx', title: 'Task Intake' },
    { file: 'dashboard/page.tsx', title: 'Dashboard' },
    { file: 'projects/page.tsx', title: 'Projects' },
    { file: 'sessions/page.tsx', title: 'Sessions' },
    { file: 'repositories/page.tsx', title: 'Repositories' },
    { file: 'agents/page.tsx', title: 'Agents' },
    { file: 'playground/page.tsx', title: 'Playground' },
    { file: 'evidence/page.tsx', title: 'Evidence' },
    { file: 'models/page.tsx', title: 'Models' },
    { file: 'settings/page.tsx', title: 'Settings' },
    { file: 'history/page.tsx', title: 'History' },
    { file: 'results/page.tsx', title: 'Results' },
  ];

  await t.test('Criterion 1: Strict single semantic <h1> exists across all 12 primary routes', () => {
    for (const route of routes) {
      const fullPath = path.join(appDir, route.file);
      assert.ok(fs.existsSync(fullPath), `Physical file must exist: ${route.file}`);
      const content = fs.readFileSync(fullPath, 'utf-8');
      const countH1 = (content.match(/<h1[\s>]/g) || []).length;
      assert.strictEqual(countH1, 1, `Route ${route.file} must have exactly one <h1>, found ${countH1}`);
    }
  });

  await t.test('Criterion 2: Dynamic deep-link routes exist and redirect cleanly with query preservation', () => {
    const dynamicRoutes = [
      { file: 'sessions/[id]/page.tsx', redirectTarget: '/sessions?runId=' },
      { file: 'runs/[id]/page.tsx', redirectTarget: '/results?runId=' },
      { file: 'evidence/[id]/page.tsx', redirectTarget: '/evidence?runId=' },
    ];

    for (const r of dynamicRoutes) {
      const fullPath = path.join(appDir, r.file);
      assert.ok(fs.existsSync(fullPath), `Dynamic route file must exist: ${r.file}`);
      const content = fs.readFileSync(fullPath, 'utf-8');
      assert.ok(content.includes(r.redirectTarget), `${r.file} must redirect to ${r.redirectTarget}`);
      assert.ok(content.includes('encodeURIComponent'), `${r.file} must encode URI parameters safely`);
    }
  });

  await t.test('Criterion 3: Responsive navigation drawer provides accessible dialog semantics', () => {
    const navPath = path.join(componentsDir, 'NavigationSidebar.tsx');
    const navContent = fs.readFileSync(navPath, 'utf-8');

    // Mobile drawer accessibility & behavior
    assert.ok(navContent.includes('role="dialog"'), 'NavigationSidebar implements dialog role on mobile');
    assert.ok(navContent.includes('aria-modal="true"'), 'Mobile drawer declares aria-modal');
    assert.ok(navContent.includes('aria-label="Mobile Navigation Menu"'), 'Mobile drawer has aria-label');
    assert.ok(navContent.includes('handleKeyDown'), 'Mobile drawer listens for keyboard events');
    assert.ok(navContent.includes('e.key === \'Escape\''), 'Escape key closes mobile drawer');
  });

  await t.test('Criterion 4: Tabular and ledger views implement responsive horizontal containment', () => {
    const tablePages = [
      'history/page.tsx',
      'dashboard/page.tsx',
      'evidence/page.tsx',
      'sessions/page.tsx',
    ];

    for (const page of tablePages) {
      const content = fs.readFileSync(path.join(appDir, page), 'utf-8');
      assert.ok(
        content.includes('overflow-x-auto'),
        `Page ${page} must wrap data tables or logs in overflow-x-auto container`
      );
    }
  });

  await t.test('Criterion 5: Zero client-side credential inputs or persistent key storage', () => {
    for (const route of routes) {
      const content = fs.readFileSync(path.join(appDir, route.file), 'utf-8');
      assert.ok(!content.includes('type="password"'), `Route ${route.file} must not render password inputs`);
      assert.ok(
        !content.includes('localStorage.setItem("api_key"'),
        `Route ${route.file} must not store credentials in localStorage`
      );
      assert.ok(
        !content.includes('sessionStorage.setItem("api_key"'),
        `Route ${route.file} must not store credentials in sessionStorage`
      );
    }
  });

  await t.test('Criterion 6: Truthful telemetry and subordinate Judge explanations preserved', () => {
    const resultsContent = fs.readFileSync(path.join(appDir, 'results/page.tsx'), 'utf-8');
    const evidenceContent = fs.readFileSync(path.join(appDir, 'evidence/page.tsx'), 'utf-8');
    const agentsContent = fs.readFileSync(path.join(appDir, 'agents/page.tsx'), 'utf-8');

    assert.ok(resultsContent.includes('JudgeExplanationView'), 'Results embeds Judge view');
    assert.ok(evidenceContent.includes('JudgeExplanationView'), 'Evidence embeds Judge view');
    assert.ok(
      agentsContent.includes('Strictly subordinate to deterministic verifier'),
      'Agents page discloses Judge subordination'
    );
  });

  await t.test('Criterion 7: Platform ceilings remain immutable read-only constants', () => {
    const settingsContent = fs.readFileSync(path.join(appDir, 'settings/page.tsx'), 'utf-8');
    assert.ok(settingsContent.includes('STATIC POLICY'), 'Settings marks ceilings as static policy');
    assert.ok(settingsContent.includes('backend/orchestrator/limits.py'), 'Settings cites backend source');
    assert.ok(
      settingsContent.includes('Dynamic modification from the web client is intentionally not supported'),
      'Settings denies client-side mutations'
    );
  });

  await t.test('Criterion 8: Gateway probe distinguishes route reachability from full daemon health', () => {
    const settingsContent = fs.readFileSync(path.join(appDir, 'settings/page.tsx'), 'utf-8');
    assert.ok(
      settingsContent.includes('Verifies HTTP route reachability only'),
      'Settings probe clarifies reachability-only nature'
    );
    assert.ok(
      settingsContent.includes('does not evaluate sandbox daemon'),
      'Settings probe denies full daemon evaluation'
    );
  });
});
