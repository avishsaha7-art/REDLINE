import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

test('UI-A6 Agents, Models & Settings Acceptance Tests', async (t) => {
  const agentsPath = path.resolve(__dirname, '../app/agents/page.tsx');
  const modelsPath = path.resolve(__dirname, '../app/models/page.tsx');
  const settingsPath = path.resolve(__dirname, '../app/settings/page.tsx');

  const agentsSource = fs.readFileSync(agentsPath, 'utf-8');
  const modelsSource = fs.readFileSync(modelsPath, 'utf-8');
  const settingsSource = fs.readFileSync(settingsPath, 'utf-8');

  await t.test('Criterion 1: Agents, Models, and Settings maintain single H1 semantic hierarchy', () => {
    const countH1 = (src: string) => (src.match(/<h1[\s>]/g) || []).length;
    assert.strictEqual(countH1(agentsSource), 1, 'Agents page must have exactly one <h1>');
    assert.strictEqual(countH1(modelsSource), 1, 'Models page must have exactly one <h1>');
    assert.strictEqual(countH1(settingsSource), 1, 'Settings page must have exactly one <h1>');

    assert.ok(agentsSource.includes('04. Agent Fleet &amp; Architecture Specification'), 'Agents page has proper title');
    assert.ok(modelsSource.includes('09. Models &amp; Provider Infrastructure'), 'Models page has proper title');
    assert.ok(settingsSource.includes('10. Platform Governance &amp; Settings'), 'Settings page has proper title');
  });

  await t.test('Criterion 2: Truthful distinction between configured, unavailable, and measured statuses', () => {
    // Agents: Must state that it is an architectural specification, not active runtime daemons
    assert.ok(agentsSource.includes('Static Agent Architecture Specification'), 'Agents page discloses static architecture specification');
    assert.ok(agentsSource.includes('Prohibited from executing shell commands'), 'Agents page clarifies sandbox prohibitions');
    assert.ok(agentsSource.includes('Dynamic runtime agent creation or arbitrary process spawning is prohibited'), 'Agents page clarifies dynamic creation prohibition');
    assert.ok(!agentsSource.includes('Active Swarm (5 Online)'), 'Agents page must not claim a fake active swarm');

    // Models: Must clearly label static provider reference and offline mock
    assert.ok(modelsSource.includes('Configuration Reference'), 'Models page discloses static configuration reference');
    assert.ok(modelsSource.includes('Deterministic Test Mock Provider'), 'Models page accurately identifies offline mock provider');
    assert.ok(!modelsSource.includes('Connected (Ping: 12ms)'), 'Models page must not fabricate ping telemetry without measuring');

    // Settings: Gateway probe clearly states it only tests route reachability
    assert.ok(settingsSource.includes('Verifies HTTP route reachability only'), 'Settings probe must not claim full daemon health');
    assert.ok(settingsSource.includes('does not evaluate sandbox daemon'), 'Settings probe explicitly limits diagnostic scope');
  });

  await t.test('Criterion 3: Zero credential leakage & API keys never displayed or accepted in UI', () => {
    // Frontend never exposes or solicits API keys or credentials
    assert.ok(!agentsSource.includes('type="password"'), 'Agents page has no credential inputs');
    assert.ok(!modelsSource.includes('type="password"'), 'Models page has no credential inputs');
    assert.ok(!settingsSource.includes('type="password"'), 'Settings page has no credential inputs');

    // Models page emphasizes server-side credential isolation
    assert.ok(modelsSource.includes('NEBIUS_API_KEY (Zero Client Exposure)'), 'Models page emphasizes zero client exposure');
    assert.ok(modelsSource.includes('0 Keys in UI'), 'Models page asserts zero keys in UI');
    assert.ok(modelsSource.includes('No localStorage / sessionStorage storage'), 'Models page confirms no local storage');
    assert.ok(modelsSource.includes('Server-side NEBIUS_API_KEY environment variable. Zero credentials exposed to frontend'), 'Models page documents server-side credential management');

    // No localStorage/sessionStorage credential storage
    assert.ok(!modelsSource.includes('localStorage.setItem("api_key"'), 'No localStorage credential usage');
    assert.ok(!settingsSource.includes('localStorage.setItem("api_key"'), 'No localStorage credential usage');
  });

  await t.test('Criterion 4: Read-only security policy and system ceilings cannot be toggled client-side', () => {
    // Settings system ceilings must be displayed as read-only / immutable
    assert.ok(settingsSource.includes('STATIC POLICY'), 'Settings page labels system ceilings as static policy');
    assert.ok(settingsSource.includes('Read-Only Governance Invariant'), 'Settings page labels governance as read-only');
    assert.ok(settingsSource.includes('backend/orchestrator/limits.py'), 'Settings page cites authoritative limits source');
    assert.ok(settingsSource.includes('MAX_ITERATIONS'), 'Settings shows MAX_ITERATIONS limit');
    assert.ok(settingsSource.includes('MAX_TOOL_CALLS'), 'Settings shows MAX_TOOL_CALLS limit');
    assert.ok(settingsSource.includes('MAX_RUNTIME'), 'Settings shows MAX_RUNTIME limit');
    assert.ok(settingsSource.includes('MAX_PATCH_SIZE'), 'Settings shows MAX_PATCH_SIZE limit');

    // Sandbox isolation profile must be read-only and explicitly note non-editable
    assert.ok(settingsSource.includes('POLICY SPECIFICATION'), 'Sandbox settings labeled policy specification');
    assert.ok(settingsSource.includes('DROP_ALL'), 'Sandbox profile documents DROP_ALL');
    assert.ok(settingsSource.includes('DISABLED (--net none)'), 'Sandbox profile documents network isolation');
    assert.ok(settingsSource.includes('Dynamic modification from the web client is intentionally not supported'), 'Discloses modification is not supported');
  });

  await t.test('Criterion 5: Five logical REDLINE agents faithfully represented with Judge subordinate advisory', () => {
    // Verify presence of all 5 logical agents
    assert.ok(agentsSource.includes('Architect Agent'), 'Architect agent present');
    assert.ok(agentsSource.includes('Builder Agent'), 'Builder agent present');
    assert.ok(agentsSource.includes('Red Team Agent'), 'Red Team agent present');
    assert.ok(agentsSource.includes('Repairer Agent'), 'Repairer agent present');
    assert.ok(agentsSource.includes('Judge Agent'), 'Judge agent present');

    // Input contracts and output artifacts
    assert.ok(agentsSource.includes('TaskContract, RepositorySnapshot, BaselineResults'), 'Architect input contract present');
    assert.ok(agentsSource.includes('ArchitectPlan'), 'Architect output artifact present');
    assert.ok(agentsSource.includes('PatchCandidate'), 'Builder output artifact present');
    assert.ok(agentsSource.includes('AttackCandidate, MutationSpec'), 'Red Team output artifact present');
    assert.ok(agentsSource.includes('JudgeExplanation'), 'Judge output defined');

    // Judge subordinate role explicitly asserted
    assert.ok(agentsSource.includes('Strictly subordinate to deterministic verifier'), 'Judge subordinate role enforced');
    assert.ok(agentsSource.includes('Opinions cannot overturn counterexamples, alter verdicts, or manufacture test results'), 'Judge opinion limitations stated');
  });

  await t.test('Criterion 6: Models page truthfully presents providers and supported architectures', () => {
    assert.ok(modelsSource.includes('Nebius Token Factory Provider'), 'Nebius provider listed');
    assert.ok(modelsSource.includes('NVIDIA Nemotron / Cloud Gateway'), 'NVIDIA provider listed');
    assert.ok(modelsSource.includes('Deterministic Test Mock Provider'), 'Offline mock provider listed');
    assert.ok(modelsSource.includes('deepseek-ai/DeepSeek-R1'), 'DeepSeek-R1 supported architecture listed');
    assert.ok(modelsSource.includes('nvidia/nemotron-4-340b-instruct'), 'Nemotron supported architecture listed');
    assert.ok(modelsSource.includes('deterministic-mock-v1'), 'Mock architecture listed');
  });

  await t.test('Criterion 7: Settings page implements truthful Gateway Probe with route reachability', () => {
    assert.ok(settingsSource.includes('testConnection'), 'Settings implements probe function');
    assert.ok(settingsSource.includes('apiClient.getRunHistory'), 'Probe queries existing getRunHistory endpoint');
    assert.ok(settingsSource.includes('ONLINE: Gateway responded'), 'Probe indicates route reachability on success');
    assert.ok(settingsSource.includes('Roundtrip HTTP Latency'), 'Probe measures roundtrip latency');
    assert.ok(settingsSource.includes('Test Backend Connection'), 'Probe button available');
  });

  await t.test('Criterion 8: Seamless cross-navigation destinations are preserved across all pages', () => {
    // Navigation to Task Intake
    assert.ok(agentsSource.includes('href="/"'), 'Agents links to Task Intake');
    assert.ok(modelsSource.includes('href="/"'), 'Models links to Task Intake');
    assert.ok(settingsSource.includes('href="/"'), 'Settings links to Task Intake');

    // Inter-page links
    assert.ok(agentsSource.includes('href="/models"'), 'Agents links to Models');
    assert.ok(agentsSource.includes('href="/settings"'), 'Agents links to Settings');
    assert.ok(modelsSource.includes('href="/settings"'), 'Models links to Settings');
    assert.ok(modelsSource.includes('href="/agents"'), 'Models links to Agents');
    assert.ok(settingsSource.includes('href="/agents"'), 'Settings links to Agents');
    assert.ok(settingsSource.includes('href="/models"'), 'Settings links to Models');
    assert.ok(settingsSource.includes('href="/sessions"'), 'Settings links to Sessions');
  });
});
