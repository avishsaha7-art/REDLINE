import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

import { NAV_SECTIONS, NavItem } from '../components/NavigationSidebar';
import { apiClient, ApiError } from '../api/client';
import { RunDiff } from '../models/types';

test('Stage 16.2 Navigation and Route Structure Acceptance Tests', async (t) => {
  const allNavItems: NavItem[] = NAV_SECTIONS.flatMap(s => s.items);

  await t.test('Criterion 1: Exactly 12 primary navigation destinations are registered across 3 sections', () => {
    assert.strictEqual(NAV_SECTIONS.length, 3, 'Must have exactly 3 logical sections: CORE WORKFLOW, OVERVIEW & AUDIT, PLATFORM & ENGINE');
    assert.strictEqual(allNavItems.length, 12, 'Must have exactly 12 navigation destinations');

    const expectedSectionTitles = [
      'CORE WORKFLOW',
      'OVERVIEW & AUDIT',
      'PLATFORM & ENGINE'
    ];
    assert.deepStrictEqual(NAV_SECTIONS.map(s => s.title), expectedSectionTitles);
  });

  await t.test('Criterion 2: All 12 required destination paths and labels match specification', () => {
    const expectedDestinations: { name: string; href: string }[] = [
      // Core Workflow
      { name: 'New Task', href: '/' },
      { name: 'Mission Control', href: '/sessions' },
      { name: 'Run Results', href: '/results' },
      { name: 'Evidence & Diffs', href: '/evidence' },
      // Overview & Audit
      { name: 'Dashboard', href: '/dashboard' },
      { name: 'Session History', href: '/history' },
      { name: 'Projects', href: '/projects' },
      { name: 'Repositories', href: '/repositories' },
      // Platform & Engine
      { name: 'Agents', href: '/agents' },
      { name: 'Playground', href: '/playground' },
      { name: 'Models', href: '/models' },
      { name: 'Settings', href: '/settings' },
    ];

    for (const expected of expectedDestinations) {
      const match = allNavItems.find(item => item.href === expected.href);
      assert.ok(match, `Destination route ${expected.href} must exist in navigation items`);
      assert.strictEqual(match?.name, expected.name, `Route ${expected.href} must be named ${expected.name}`);
    }
  });

  await t.test('Criterion 3: Physical Next.js App Router files exist for all 12 destinations and dynamic subroutes', () => {
    const appDir = path.resolve(__dirname, '../app');
    
    const requiredPagePaths = [
      'page.tsx', // 1. Home / New Task
      'sessions/page.tsx', // 2. Mission Control
      'sessions/[id]/page.tsx', // Dynamic session detail
      'results/page.tsx', // 3. Run Results
      'runs/[id]/page.tsx', // Dynamic run detail
      'evidence/page.tsx', // 4. Evidence & Diffs
      'evidence/[id]/page.tsx', // Dynamic evidence detail
      'dashboard/page.tsx', // 5. Dashboard
      'history/page.tsx', // 6. Session History
      'projects/page.tsx', // 7. Projects
      'repositories/page.tsx', // 8. Repositories
      'agents/page.tsx', // 9. Agents
      'playground/page.tsx', // 10. Playground
      'models/page.tsx', // 11. Models
      'settings/page.tsx', // 12. Settings
    ];

    for (const relPath of requiredPagePaths) {
      const fullPath = path.join(appDir, relPath);
      assert.ok(fs.existsSync(fullPath), `Target route page file must exist: ${relPath}`);
      const content = fs.readFileSync(fullPath, 'utf8');
      assert.ok(content.length > 50, `Route page file ${relPath} must contain substantive implementation`);
    }
  });

  await t.test('Criterion 4: AppShell provides accessible #main-content skip link and security indicators', () => {
    const appShellPath = path.resolve(__dirname, '../components/AppShell.tsx');
    assert.ok(fs.existsSync(appShellPath), 'AppShell component file must exist');
    const content = fs.readFileSync(appShellPath, 'utf8');
    
    // Accessibility skip link
    assert.ok(content.includes('href="#main-content"'), 'AppShell must contain skip to main content anchor');
    assert.ok(content.includes('id="main-content"'), 'AppShell main container must possess id="main-content"');
    
    // Security & Architecture indicators
    assert.ok(content.includes('SANDBOX POLICY: HARDENED'), 'AppShell must display hardened sandbox policy status');
    assert.ok(content.includes('BACKEND IS SOURCE OF TRUTH'), 'AppShell must display backend authority indicator');
  });

  await t.test('Criterion 5: DiffViewer enforces Code Audit Advisory and does not execute displayed code', () => {
    const diffViewerPath = path.resolve(__dirname, '../components/DiffViewer.tsx');
    assert.ok(fs.existsSync(diffViewerPath), 'DiffViewer component must exist');
    const content = fs.readFileSync(diffViewerPath, 'utf8');

    // Advisory notice verification
    assert.ok(content.includes('CODE AUDIT ADVISORY'), 'DiffViewer must contain CODE AUDIT ADVISORY notice');
    assert.ok(content.includes('does NOT prove code safety'), 'Advisory must state inspecting a diff does NOT prove code safety');
    assert.ok(content.includes('Deterministic adversarial verification remains authoritative'), 'Advisory must reaffirm deterministic verification authority');

    // Safe rendering: pre/code tags only, no eval or dangerouslySetInnerHTML
    assert.ok(!content.includes('dangerouslySetInnerHTML'), 'DiffViewer must NOT use dangerouslySetInnerHTML');
    assert.ok(!content.includes('eval('), 'DiffViewer must NOT use eval');
  });

  await t.test('Criterion 6: ResourceBudgetNotice enforces bounded limits and never fabricates live hardware metrics', () => {
    const budgetPath = path.resolve(__dirname, '../components/ResourceBudgetNotice.tsx');
    assert.ok(fs.existsSync(budgetPath), 'ResourceBudgetNotice component must exist');
    const content = fs.readFileSync(budgetPath, 'utf8');

    // Bounded ceilings
    assert.ok(content.includes('Effective Budget & System Ceilings'), 'Must specify budget ceilings');
    assert.ok(content.includes('BACKEND ENFORCED'), 'Must specify backend enforcement');
    assert.ok(content.includes('Iterations'), 'Must track iteration limits');
    assert.ok(content.includes('Tool Calls'), 'Must track tool call limits');
    assert.ok(content.includes('Wall Timeout'), 'Must track wall clock timeout');

    // Anti-fabrication guarantees
    assert.ok(!content.includes('GPU Usage:'), 'Must NOT fabricate GPU usage');
    assert.ok(!content.includes('CPU Load:'), 'Must NOT fabricate live CPU load');
    assert.ok(!content.includes('Free Memory:'), 'Must NOT fabricate live RAM memory');
  });

  await t.test('Criterion 7: ApiClient exposes getRunDiff and handles 404/500 without crashing', async () => {
    assert.strictEqual(typeof apiClient.getRunDiff, 'function', 'apiClient must have getRunDiff method');

    // Mock global fetch to verify URL and method
    const originalFetch = global.fetch;
    let requestedUrl = '';
    
    global.fetch = async (url: RequestInfo | URL) => {
      requestedUrl = String(url);
      return {
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async (): Promise<RunDiff> => ({
          run_id: 'test-run-123',
          patch_id: 'patch-456',
          diff: '--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new',
          changed_files: ['file.py']
        })
      } as unknown as Response;
    };

    try {
      const diff = await apiClient.getRunDiff('test-run-123');
      assert.strictEqual(diff.run_id, 'test-run-123');
      assert.ok(requestedUrl.endsWith('/api/v1/runs/test-run-123/diff'), `URL must target /diff endpoint, got: ${requestedUrl}`);
      assert.strictEqual(diff.changed_files.length, 1);
      assert.strictEqual(diff.changed_files[0], 'file.py');
    } finally {
      global.fetch = originalFetch;
    }
  });

  await t.test('Criterion 8: ApiClient getRunDiff properly propagates ApiError on 404 Not Found', async () => {
    const originalFetch = global.fetch;
    
    global.fetch = async () => {
      return {
        ok: false,
        status: 404,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Patch not found' })
      } as unknown as Response;
    };

    try {
      await assert.rejects(
        async () => {
          await apiClient.getRunDiff('missing-run');
        },
        (err: unknown) => {
          assert.ok(err instanceof ApiError, 'Error must be an instance of ApiError');
          assert.strictEqual((err as ApiError).status, 404, 'Status must be 404');
          return true;
        }
      );
    } finally {
      global.fetch = originalFetch;
    }
  });
});
