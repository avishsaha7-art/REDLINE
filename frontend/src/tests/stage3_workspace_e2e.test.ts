import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

import { apiClient } from '../api/client';
import {
  ProjectRecord,
  LocalProjectImportRequest,
  ChatResponse,
  ProposalRecord
} from '../models/types';

test('REDLINE Stage 3 — Local Project Import, AI Workspace, Mentions & Controlled Repair', async (t) => {
  const appDir = path.resolve(__dirname, '../app');
  const componentsDir = path.resolve(__dirname, '../components');

  const workspacePath = path.join(appDir, 'workspace/page.tsx');
  const modalPath = path.join(componentsDir, 'LocalProjectImportModal.tsx');
  const projectsPath = path.join(appDir, 'projects/page.tsx');

  assert.ok(fs.existsSync(workspacePath), 'workspace/page.tsx must exist');
  assert.ok(fs.existsSync(modalPath), 'LocalProjectImportModal.tsx must exist');
  assert.ok(fs.existsSync(projectsPath), 'projects/page.tsx must exist');

  const workspaceSource = fs.readFileSync(workspacePath, 'utf8');
  const modalSource = fs.readFileSync(modalPath, 'utf8');
  const projectsSource = fs.readFileSync(projectsPath, 'utf8');

  // Criterion 1: Single H1 semantic hierarchy and workspace title
  await t.test('Criterion 1: Workspace maintains single H1 semantic hierarchy', () => {
    const h1Matches = workspaceSource.match(/<h1[^>]*>([\s\S]*?)<\/h1>/gi) || [];
    assert.strictEqual(
      h1Matches.length,
      1,
      `Workspace page must have exactly 1 <h1> element, found ${h1Matches.length}`
    );
    assert.ok(
      h1Matches[0].includes('AI PROJECT WORKSPACE'),
      'Workspace <h1> must identify page as AI PROJECT WORKSPACE'
    );
  });

  // Criterion 2: Local Project Import Modal capabilities
  await t.test('Criterion 2: LocalProjectImportModal provides directory upload and demo preset', () => {
    // Directory folder picker
    assert.ok(
      modalSource.includes('webkitdirectory'),
      'Modal must support webkitdirectory browser folder selection'
    );
    assert.ok(
      modalSource.includes('directory='),
      'Modal must support directory attribute'
    );
    // Quick Demo Preset
    assert.ok(
      modalSource.includes('loadDemoPreset') || modalSource.includes('Load Sample Project'),
      'Modal must provide quick demo preset'
    );
    // Exclusion rules
    assert.ok(
      modalSource.includes('.git') && modalSource.includes('node_modules') && modalSource.includes('.env'),
      'Modal must filter .git, node_modules, and .env files'
    );
    // UNTRUSTED notice
    assert.ok(
      modalSource.includes('UNTRUSTED'),
      'Modal must disclose that imported projects are strictly UNTRUSTED'
    );
  });

  // Criterion 3: File mentions and @ autocomplete
  await t.test('Criterion 3: Workspace implements @ file mention autocomplete and context indicators', () => {
    assert.ok(
      workspaceSource.includes('mentionMatches') || workspaceSource.includes('insertMention'),
      'Workspace must contain mention matching and insertion logic'
    );
    assert.ok(
      workspaceSource.includes('@'),
      'Workspace must support @ file mentions'
    );
    assert.ok(
      workspaceSource.includes('activeContextFiles'),
      'Workspace must track active context files'
    );
    assert.ok(
      workspaceSource.includes('Included Context') || workspaceSource.includes('Context:'),
      'Workspace must display context indicator bar'
    );
  });

  // Criterion 4: Controlled Diff Review & User Approval
  await t.test('Criterion 4: Workspace integrates DiffViewer with explicit user approval', () => {
    assert.ok(
      workspaceSource.includes('DiffViewer'),
      'Workspace must embed DiffViewer component'
    );
    assert.ok(
      workspaceSource.includes('handleApplyProposal') && workspaceSource.includes('handleRejectProposal'),
      'Workspace must provide explicit apply and reject handlers'
    );
    assert.ok(
      workspaceSource.includes('Approve & Apply') || workspaceSource.includes('Approve'),
      'Workspace must provide user approval action button'
    );
    assert.ok(
      workspaceSource.includes('Discard') || workspaceSource.includes('Reject'),
      'Workspace must provide proposal rejection button'
    );
  });

  // Criterion 5: Safe rendering (no eval or dangerouslySetInnerHTML)
  await t.test('Criterion 5: Safe rendering guarantees in Workspace and Modal', () => {
    assert.ok(!workspaceSource.includes('dangerouslySetInnerHTML'), 'Workspace must not use dangerouslySetInnerHTML');
    assert.ok(!workspaceSource.includes('eval('), 'Workspace must not use eval');
    assert.ok(!modalSource.includes('dangerouslySetInnerHTML'), 'Modal must not use dangerouslySetInnerHTML');
    assert.ok(!modalSource.includes('eval('), 'Modal must not use eval');
  });

  // Criterion 6: Navigation link from Projects page
  await t.test('Criterion 6: Projects page provides link to AI Project Workspace', () => {
    assert.ok(
      projectsSource.includes('href="/workspace"'),
      'Projects page must include a direct link to /workspace'
    );
  });

  // Criterion 7: ApiClient exposes all Stage 3 methods
  await t.test('Criterion 7: ApiClient exposes project workspace and chat methods', () => {
    assert.strictEqual(typeof apiClient.importLocalProject, 'function');
    assert.strictEqual(typeof apiClient.listProjects, 'function');
    assert.strictEqual(typeof apiClient.getProject, 'function');
    assert.strictEqual(typeof apiClient.listProjectFiles, 'function');
    assert.strictEqual(typeof apiClient.getProjectFileContent, 'function');
    assert.strictEqual(typeof apiClient.listConversations, 'function');
    assert.strictEqual(typeof apiClient.createConversation, 'function');
    assert.strictEqual(typeof apiClient.sendMessage, 'function');
    assert.strictEqual(typeof apiClient.applyProposal, 'function');
    assert.strictEqual(typeof apiClient.rejectProposal, 'function');
    assert.strictEqual(typeof apiClient.verifyProject, 'function');
  });

  // Criterion 8: Mocked API contract verification
  await t.test('Criterion 8: Mocked API contracts for project import and proposals', async () => {
    const originalFetch = globalThis.fetch;
    try {
      // Mock importLocalProject
      globalThis.fetch = async (url, init) => {
        const urlStr = String(url);
        if (urlStr.includes('/api/v1/projects/import') && init?.method === 'POST') {
          return new Response(JSON.stringify({
            project_id: 'project-test123456',
            name: 'mock-project',
            root_path: 'P:/REDLINE/data/projects/project-test123456',
            trust: 'UNTRUSTED',
            snapshot_hash: 'a1b2c3d4e5f6',
            file_manifest_hash: 'f6e5d4c3b2a1',
            file_count: 2,
            total_bytes: 512,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString()
          }), { status: 201, headers: { 'Content-Type': 'application/json' } });
        }

        if (urlStr.includes('/api/v1/projects/project-test123456/conversations/conv-1/messages')) {
          return new Response(JSON.stringify({
            conversation_id: 'conv-1',
            message_id: 'msg-1',
            role: 'assistant',
            content: 'Analysis complete.',
            mentioned_files: ['src/main.py'],
            proposal: {
              proposal_id: 'prop-1',
              project_id: 'project-test123456',
              status: 'PENDING',
              description: 'Fix input check',
              diff: '--- a/src/main.py\n+++ b/src/main.py',
              diff_sha256: 'sha-diff',
              changed_files: ['src/main.py'],
              proposed_content: { 'src/main.py': 'def main(): pass' },
              created_at: new Date().toISOString()
            }
          }), { status: 200, headers: { 'Content-Type': 'application/json' } });
        }

        return new Response('Not found', { status: 404 });
      };

      const importReq: LocalProjectImportRequest = {
        name: 'mock-project',
        files: [{ path: 'src/main.py', content: 'pass' }]
      };
      const proj = await apiClient.importLocalProject(importReq);
      assert.strictEqual(proj.project_id, 'project-test123456');
      assert.strictEqual(proj.trust, 'UNTRUSTED');

      const chat = await apiClient.sendMessage('project-test123456', 'conv-1', 'Fix bug');
      assert.strictEqual(chat.role, 'assistant');
      assert.ok(chat.proposal);
      assert.strictEqual(chat.proposal?.status, 'PENDING');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
