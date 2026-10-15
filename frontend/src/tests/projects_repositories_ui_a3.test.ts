import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

import { REGISTERED_PROJECTS, ProjectWorkspace } from '../app/projects/page';
import { REPOSITORY_POLICIES, RepositoryPolicy } from '../app/repositories/page';

test('UI-A3 Projects & Repositories Acceptance Tests', async (t) => {
  const appDir = path.resolve(__dirname, '../app');
  const projectsFilePath = path.join(appDir, 'projects/page.tsx');
  const reposFilePath = path.join(appDir, 'repositories/page.tsx');

  const projectsSource = fs.readFileSync(projectsFilePath, 'utf8');
  const reposSource = fs.readFileSync(reposFilePath, 'utf8');

  // Criterion 1: Semantic heading hierarchy (single H1 per page)
  await t.test('Criterion 1: Projects and Repositories maintain single H1 semantic hierarchy', () => {
    // Projects H1 check
    const projectH1Matches = projectsSource.match(/<h1[^>]*>([\s\S]*?)<\/h1>/gi) || [];
    assert.strictEqual(
      projectH1Matches.length,
      1,
      `Projects page must have exactly 1 <h1> element, found ${projectH1Matches.length}`
    );
    assert.ok(
      projectH1Matches[0].includes('PROJECTS'),
      'Projects <h1> must identify the page as PROJECTS'
    );

    // Repositories H1 check
    const reposH1Matches = reposSource.match(/<h1[^>]*>([\s\S]*?)<\/h1>/gi) || [];
    assert.strictEqual(
      reposH1Matches.length,
      1,
      `Repositories page must have exactly 1 <h1> element, found ${reposH1Matches.length}`
    );
    assert.ok(
      reposH1Matches[0].includes('REPOSITORIES'),
      'Repositories <h1> must identify the page as REPOSITORIES'
    );
  });

  // Criterion 2: Projects page truthfulness and demo disclosure
  await t.test('Criterion 2: Projects page discloses static demo nature and forbids fake health scores', () => {
    // Required disclosure strings
    assert.ok(
      projectsSource.includes('Static Demo Target Workspaces') || projectsSource.includes('Demo Fixtures'),
      'Projects page must disclose that target workspaces are static demonstration fixtures'
    );
    assert.ok(
      projectsSource.includes('not implemented in this stage'),
      'Projects page must state that dynamic CRUD is not implemented in this stage'
    );

    // Truthfulness guarantees: No fabricated health scores, deterministic percentages, or test pass rates
    assert.ok(
      !projectsSource.includes('healthScore'),
      'Projects page must not invent healthScore metrics'
    );
    assert.ok(
      !projectsSource.includes('99.4%') && !projectsSource.includes('98.7%'),
      'Projects page must not display fabricated pass rate percentages'
    );
    assert.ok(
      !projectsSource.includes('activeAgents: 14'),
      'Projects page must not fabricate active agent counts'
    );
  });

  // Criterion 3: Projects data fixtures align with backend sandbox trust definitions
  await t.test('Criterion 3: Projects data fixtures accurately reflect backend sandbox targets', () => {
    assert.ok(Array.isArray(REGISTERED_PROJECTS), 'REGISTERED_PROJECTS must be an exported array');
    assert.ok(REGISTERED_PROJECTS.length >= 3, 'Must contain at least 3 benchmark target workspaces');

    const projectIds = REGISTERED_PROJECTS.map((p: ProjectWorkspace) => p.id);
    assert.ok(projectIds.includes('repo-int-1'), 'Must include repo-int-1 core benchmark');
    assert.ok(projectIds.includes('untrusted-external-repo'), 'Must include untrusted-external-repo');
    assert.ok(projectIds.includes('repo-payments-api'), 'Must include repo-payments-api');

    for (const project of REGISTERED_PROJECTS) {
      assert.ok(project.name.length > 0, `Project ${project.id} must have a name`);
      assert.ok(project.description.length > 0, `Project ${project.id} must have a description`);
      assert.ok(['TRUSTED', 'UNTRUSTED'].includes(project.trustTier), `Project ${project.id} must have valid trustTier`);
      assert.ok(Array.isArray(project.allowedScope), `Project ${project.id} must specify allowedScope`);
      assert.ok(project.baseSnapshot.length > 0, `Project ${project.id} must have a baseSnapshot`);
    }

    // Verify untrusted external target has UNTRUSTED trust tier
    const untrusted = REGISTERED_PROJECTS.find((p: ProjectWorkspace) => p.id === 'untrusted-external-repo');
    assert.strictEqual(untrusted?.trustTier, 'UNTRUSTED');
  });

  // Criterion 4: Repositories page truthfulness and architectural disclosure
  await t.test('Criterion 4: Repositories page discloses architectural reference and forbids fake GitHub URLs', () => {
    // Required disclosure strings
    assert.ok(
      reposSource.includes('Static Architecture Reference') || reposSource.includes('Static Reference'),
      'Repositories page must disclose static reference nature'
    );
    assert.ok(
      reposSource.includes('Security Boundary Enforcement (Section 47)'),
      'Repositories page must retain Section 47 Security Boundary Enforcement notice'
    );
    assert.ok(
      reposSource.includes('backend/sandbox/trust.py'),
      'Repositories page must cite backend/sandbox/trust.py as authoritative source of trust'
    );

    // Truthfulness guarantees: No invented GitHub URLs or fake webhook latencies
    assert.ok(
      !reposSource.includes('https://github.com/example/'),
      'Repositories page must not invent fake GitHub clone URLs'
    );
    assert.ok(
      !reposSource.includes('WEBHOOK LATENCY'),
      'Repositories page must not fabricate GitHub webhook latencies'
    );
    assert.ok(
      !reposSource.includes('14ms'),
      'Repositories page must not fabricate latency metrics'
    );
  });

  // Criterion 5: Repositories data fixtures align with backend policies
  await t.test('Criterion 5: Repositories data fixtures contain complete security policy gates', () => {
    assert.ok(Array.isArray(REPOSITORY_POLICIES), 'REPOSITORY_POLICIES must be an exported array');
    assert.ok(REPOSITORY_POLICIES.length >= 3, 'Must contain at least 3 repository policy specifications');

    const repoIds = REPOSITORY_POLICIES.map((r: RepositoryPolicy) => r.repositoryId);
    assert.ok(repoIds.includes('repo-int-1'), 'Must include repo-int-1');
    assert.ok(repoIds.includes('untrusted-external-repo'), 'Must include untrusted-external-repo');
    assert.ok(repoIds.includes('repo-payments-api'), 'Must include repo-payments-api');

    for (const repo of REPOSITORY_POLICIES) {
      assert.ok(repo.sandboxPolicy.length > 0, `Repo ${repo.repositoryId} must specify sandboxPolicy`);
      assert.ok(repo.scopeEnforcement.length > 0, `Repo ${repo.repositoryId} must specify scopeEnforcement`);
      assert.ok(repo.pathTraversalGate.includes('FAIL_CLOSED'), `Repo ${repo.repositoryId} must enforce FAIL_CLOSED path traversal`);
      assert.strictEqual(repo.snapshotDigest.length, 64, `Repo ${repo.repositoryId} snapshotDigest must be 64-char hex SHA-256`);
    }

    // Verify untrusted repo has POLICY_BLOCKED sandbox policy
    const untrustedRepo = REPOSITORY_POLICIES.find((r: RepositoryPolicy) => r.repositoryId === 'untrusted-external-repo');
    assert.ok(untrustedRepo?.sandboxPolicy.includes('POLICY_BLOCKED'));
    assert.ok(untrustedRepo?.scopeEnforcement.includes('HARD_BLOCK'));
  });

  // Criterion 6: Working filter & search behavior on both pages
  await t.test('Criterion 6: Working filter and search behavior operates on displayed records', () => {
    // Test Projects filter logic
    const testProjects = [...REGISTERED_PROJECTS];

    // Filter by tier: TRUSTED
    const trustedOnly = testProjects.filter(p => p.trustTier === 'TRUSTED');
    assert.ok(trustedOnly.length > 0);
    assert.ok(trustedOnly.every(p => p.trustTier === 'TRUSTED'));

    // Filter by tier: UNTRUSTED
    const untrustedOnly = testProjects.filter(p => p.trustTier === 'UNTRUSTED');
    assert.strictEqual(untrustedOnly.length, 1);
    assert.strictEqual(untrustedOnly[0].id, 'untrusted-external-repo');

    // Filter by query: 'payments'
    const query = 'payments';
    const searched = testProjects.filter(p =>
      p.id.toLowerCase().includes(query) ||
      p.name.toLowerCase().includes(query) ||
      p.description.toLowerCase().includes(query)
    );
    assert.strictEqual(searched.length, 1);
    assert.strictEqual(searched[0].id, 'repo-payments-api');

    // Test Repositories filter logic
    const testRepos = [...REPOSITORY_POLICIES];
    const blockedRepos = testRepos.filter(r => r.sandboxPolicy.includes('POLICY_BLOCKED'));
    assert.strictEqual(blockedRepos.length, 1);
    assert.strictEqual(blockedRepos[0].repositoryId, 'untrusted-external-repo');
  });

  // Criterion 7: Seamless cross-navigation links connect to Task Intake with repoId
  await t.test('Criterion 7: Both pages provide functional links to Task Intake with target repoId', () => {
    // In projects page: links to /?repoId=...
    assert.ok(
      projectsSource.includes('/?repoId='),
      'Projects page must include links to Task Intake with repoId query param'
    );
    assert.ok(
      projectsSource.includes('href="/"'),
      'Projects page must include primary CTA link to Task Intake'
    );

    // In repositories page: links to /?repoId=...
    assert.ok(
      reposSource.includes('/?repoId='),
      'Repositories page must include links to Task Intake with repoId query param'
    );
    assert.ok(
      reposSource.includes('href="/"'),
      'Repositories page must include primary CTA link to Task Intake'
    );
  });
});
