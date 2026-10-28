from backend.models.schemas import TaskContract, RunState, OperationalResult, ArchitectPlan, PatchCandidate
from backend.orchestrator.state_machine import StateMachine
from backend.agents.architect import ArchitectAgent
from backend.agents.builder import BuilderAgent
from backend.verification.patch_validation import validate_patch
from backend.agents.red_team import RedTeamAgent
from backend.agents.repairer import RepairerAgent
from backend.agents.judge import JudgeAgent

class Orchestrator:
    def __init__(self, run_id: str, task_contract: TaskContract, model_provider=None):
        self.state_machine = StateMachine(run_id, task_contract)
        self.task_contract = task_contract
        from backend.models.registry import get_model_provider
        resolved_provider = model_provider if model_provider is not None else get_model_provider()
        self.model_provider = resolved_provider
        # Initialize agents
        self.architect = ArchitectAgent(tools=["read_file", "list_files", "search_code"], model_provider=resolved_provider, events=self.state_machine.events)
        self.builder = BuilderAgent(tools=["read_file", "write_file", "run_tests"], model_provider=resolved_provider, events=self.state_machine.events)
        self.red_team = RedTeamAgent(model_provider=resolved_provider, events=self.state_machine.events)
        self.repairer = RepairerAgent(tools=["read_file", "list_files", "search_code"], model_provider=resolved_provider, events=self.state_machine.events)
        self.judge = JudgeAgent(model_provider=resolved_provider)
        
        self.architect_plan = None
        self.patch_candidate = None
        self.selected_attacks = None
        self.counterexamples = []
        self.seen_repairs = set()
        self.repair_attempts = 0
        self.patch_lineage = []
        self.last_test_summary = None
        self.last_test_observation = None
        self.last_test_execution_result = None
        from backend.sandbox.capabilities import RepositoryTrust
        from backend.sandbox.trust import resolve_repository_trust
        if getattr(self.task_contract, "repository_url", None):
            self.repository_trust = RepositoryTrust.UNTRUSTED.value
        else:
            trust_val = getattr(self.task_contract, "repository_trust", None)
            self.repository_trust = resolve_repository_trust(self.task_contract.repository_id, trust_val).value

    def _resolve_repo_root(self) -> str:
        import os
        if hasattr(self, "repo_root") and self.repo_root and os.path.isdir(self.repo_root):
            return os.path.abspath(self.repo_root)
        if os.environ.get("REDLINE_REPO_ROOT") and os.path.isdir(os.environ["REDLINE_REPO_ROOT"]):
            return os.path.abspath(os.environ["REDLINE_REPO_ROOT"])

        from backend.sandbox.registry import get_repository_registry
        target = get_repository_registry().resolve_target(self.task_contract.repository_id)
        if target and os.path.isdir(target.repo_root):
            return os.path.abspath(target.repo_root)

        repo_id = self.task_contract.repository_id
        if repo_id and not any(c in repo_id for c in ("/", "\\", ":", "%", "..")):
            fixture_dir = os.path.join("data", "fixtures", repo_id)
            if os.path.isdir(fixture_dir):
                return os.path.abspath(fixture_dir)

        # Fail closed: reject unknown target rather than silently falling back to repo-int-1 or cwd
        raise ValueError(f"Unknown repository target '{repo_id}'. Target must be registered before verification.")


    def _resolve_test_command(self, repo_root: str) -> list[str]:
        import os
        if hasattr(self, "test_command") and self.test_command:
            return list(self.test_command)
        if hasattr(self.task_contract, "test_command") and getattr(self.task_contract, "test_command"):
            return list(self.task_contract.test_command)
        if os.path.exists(os.path.join(repo_root, "test_main.py")):
            return ["python", "test_main.py"]
        if os.path.exists(os.path.join(repo_root, "pytest.ini")) or os.path.isdir(os.path.join(repo_root, "tests")):
            return ["python", "-m", "pytest", "-o", "pythonpath=."]
        return ["python", "test_main.py"]

    def run(self) -> RunState:
        # Initial acceptance
        self.state_machine.advance("TASK_ACCEPTED")
        
        while self.state_machine.current_state not in (RunState.VERIFIED, RunState.ABORTED):
            self.state_machine.increment_iteration()
            if self.state_machine.governance.is_exhausted():
                self.state_machine.advance(OperationalResult.RESOURCE_LIMIT)
                break
                
            state = self.state_machine.current_state
            
            if state == RunState.RECON:
                # We skip deep recon for Stage 4 implementation to focus on Architect/Builder
                self.state_machine.advance("RECON_COMPLETE")
                
            elif state == RunState.PLAN:
                import time
                from backend.orchestrator.repository_ingestion import discover_repository
                import os
                
                try:
                    repo_root = self._resolve_repo_root()
                except ValueError as exc:
                    self.state_machine.events.record_event("REPOSITORY_RESOLUTION_FAILED", {
                        "repository_id": self.task_contract.repository_id,
                        "reason": str(exc)
                    })
                    self.state_machine.advance(OperationalResult.INVALID_REPOSITORY)
                    break

                ingestion_result = discover_repository(repo_root, self.task_contract, time.time())
                
                self.untrusted_context = ingestion_result.to_untrusted_context_string(self.task_contract.resource_budget)
                self.snapshot_hash = ingestion_result.snapshot.snapshot_hash
                self.workspace_id = getattr(self.task_contract, "repository_id", "unknown_workspace")
                
                self.state_machine.events.record_event("REPOSITORY_SNAPSHOT_CREATED", {
                    "repository_id": ingestion_result.snapshot.repository_id,
                    "snapshot_hash": ingestion_result.snapshot.snapshot_hash,
                    "file_manifest_hash": ingestion_result.snapshot.file_manifest_hash,
                    "file_count": ingestion_result.snapshot.file_count,
                    "total_accepted_bytes": ingestion_result.snapshot.total_accepted_bytes
                })
                self.state_machine.events.record_event("REPOSITORY_FILE_DISCOVERY_COMPLETED", {
                    "excluded_count": len(ingestion_result.excluded_files)
                })
                self.state_machine.events.record_event("REPOSITORY_CONTEXT_SELECTED", {
                    "context_hash": ingestion_result.context_hash
                })
                
                try:
                    self.architect_plan = self.architect.plan(self.task_contract, getattr(self, "untrusted_context", ""))
                    if isinstance(self.architect_plan, OperationalResult):
                        self.state_machine.advance(self.architect_plan)
                    else:
                        self.state_machine.advance(self.architect_plan)
                except Exception as e:
                    import traceback; traceback.print_exc()
                    self.state_machine.advance(OperationalResult.MODEL_FAILURE)
                    
            elif state == RunState.BASELINE:
                # Setup baseline / fetch initial repo state - stub for Stage 4
                self.state_machine.advance("BASELINE_READY")
                
            elif state == RunState.BUILD:
                try:
                    untrusted_context = getattr(self, "untrusted_context", "No file content loaded for Builder stub yet.")
                    build_res = self.builder.build(self.task_contract, self.architect_plan, untrusted_context)
                    
                    if isinstance(build_res, OperationalResult):
                        self.state_machine.events.record_event("PATCH_POLICY_REJECTED", {"reason": build_res.value})
                        self.state_machine.advance(OperationalResult.POLICY_BLOCKED)
                    else:
                        self.patch_candidate = build_res
                        try:
                            validate_patch(self.patch_candidate, self.task_contract)
                            self.state_machine.events.record_event("PATCH_CANDIDATE_VALIDATED", {"patch_id": self.patch_candidate.patch_id, "patch_hash": self.patch_candidate.diff_sha256})
                            self.patch_lineage.append(self.patch_candidate.patch_id)
                            self.state_machine.events.record_event("PATCH_POLICY_ACCEPTED", {"patch_id": self.patch_candidate.patch_id})
                            self.state_machine.events.record_event("PATCH_CREATED", {"patch_id": self.patch_candidate.patch_id})
                            self.state_machine.advance(self.patch_candidate)
                        except ValueError as e:
                            self.state_machine.events.record_event("PATCH_POLICY_REJECTED", {"reason": str(e)})
                            self.state_machine.advance(OperationalResult.POLICY_BLOCKED)
                except Exception as e:
                    import traceback; traceback.print_exc()
                    self.state_machine.advance(OperationalResult.MODEL_FAILURE)
                    
            elif state == RunState.TEST:
                from backend.sandbox.client import SandboxClient
                from backend.sandbox.factory import get_sandbox_backend
                from backend.sandbox.models import SandboxPolicy
                from backend.verification.observer import DeterministicVerificationObserver
                from backend.verification.models import ExecutionStatus, Counterexample, OracleType as VerificationOracleType
                import hashlib

                repo_root = self._resolve_repo_root()
                test_command = self._resolve_test_command(repo_root)

                policy = SandboxPolicy(
                    max_runtime_seconds=min(60, self.task_contract.resource_budget.max_runtime),
                    allowed_commands=["python", "pytest"]
                )
                trust = self.repository_trust
                backend = getattr(self, "sandbox_backend", None) or get_sandbox_backend(policy, repository_trust=trust)

                client = SandboxClient(
                    policy=policy,
                    repo_root=repo_root,
                    backend=backend,
                    repository_trust=trust
                )

                self.state_machine.events.record_event("TEST_EXECUTION_STARTED", {
                    "patch_id": self.patch_candidate.patch_id if self.patch_candidate else "none",
                    "repo_root": repo_root,
                    "test_command": test_command,
                    "trust": trust
                })

                exec_res = client.run_isolated(
                    patch=self.patch_candidate,
                    test_command=test_command,
                    run_id=self.state_machine.run_id
                )

                observer = DeterministicVerificationObserver()
                test_obs = observer.observe_execution(
                    exec_res,
                    getattr(self, "workspace_id", self.task_contract.repository_id),
                    getattr(self, "snapshot_hash", "unknown"),
                    self.patch_candidate.diff_sha256 if self.patch_candidate else "unknown"
                )
                test_summary = observer.observe_tests(exec_res)

                self.last_test_execution_result = exec_res
                self.last_test_observation = test_obs
                self.last_test_summary = test_summary

                self.state_machine.events.record_event("TEST_EXECUTION_COMPLETED", {
                    "exit_code": exec_res.exit_code,
                    "status": test_obs.status.value,
                    "stdout_bytes": test_obs.stdout_bytes,
                    "stderr_bytes": test_obs.stderr_bytes,
                    "duration_ms": test_obs.duration_ms,
                    "passed": test_summary.passed,
                    "failed": test_summary.failed,
                    "errored": test_summary.errored,
                    "inconclusive": test_summary.inconclusive,
                    "patch_id": self.patch_candidate.patch_id if self.patch_candidate else "none",
                    "backend": test_obs.sandbox_backend,
                    "security_level": test_obs.security_level
                })

                # Determine lifecycle transition
                prov = getattr(exec_res, "backend_provenance", {}) or {}
                prov_status = prov.get("status")

                if getattr(exec_res, "policy_blocked", False) or test_obs.status == ExecutionStatus.POLICY_BLOCKED:
                    self.state_machine.advance(OperationalResult.POLICY_BLOCKED)
                elif exec_res.timed_out or test_obs.status == ExecutionStatus.TIMEOUT:
                    self.state_machine.advance(OperationalResult.TIMEOUT)
                elif prov_status == "OPERATIONAL_FAILURE" or test_obs.status == ExecutionStatus.SANDBOX_FAILURE:
                    self.state_machine.advance(OperationalResult.SANDBOX_FAILURE)
                elif test_obs.status == ExecutionStatus.RESOURCE_LIMIT or getattr(exec_res, "resource_limited", False):
                    self.state_machine.advance(OperationalResult.RESOURCE_LIMIT)
                elif prov_status == "PATCH_APPLY_FAILED":
                    ce = Counterexample(
                        counterexample_id=f"ce_patch_{self.state_machine.run_id}_{len(self.counterexamples)+1}",
                        invariant_id="PATCH_APPLICATION",
                        test_id=None,
                        input_data=self.patch_candidate.diff if self.patch_candidate else "",
                        observed_output=exec_res.stderr or "Patch failed to apply cleanly to repository snapshot",
                        expected_output="Clean git apply with exit code 0",
                        failure_reason="Git patch rejected or conflicted with workspace base",
                        oracle_type=VerificationOracleType.DETERMINISTIC_CONTRACT,
                        execution_id=exec_res.run_id,
                        evidence_hash=exec_res.stderr_sha256 or hashlib.sha256(b"PATCH_APPLY_FAILED").hexdigest(),
                        patch_id=self.patch_candidate.patch_id if self.patch_candidate else None,
                        target_file=self.patch_candidate.changed_files[0] if (self.patch_candidate and self.patch_candidate.changed_files) else None,
                        workspace_id=getattr(self, "workspace_id", None),
                        snapshot_hash=getattr(self, "snapshot_hash", None)
                    )
                    self.counterexamples.append(ce)
                    self.state_machine.events.record_event("COUNTEREXAMPLE_FOUND", {
                        "counterexample_id": ce.counterexample_id,
                        "reason": "PATCH_APPLY_FAILED"
                    })
                    self.state_machine.advance("TEST_FAILED")
                elif exec_res.exit_code != 0 or test_summary.failed > 0 or test_summary.errored > 0:
                    ce = Counterexample(
                        counterexample_id=f"ce_test_{self.state_machine.run_id}_{len(self.counterexamples)+1}",
                        invariant_id="DETERMINISTIC_TEST_SUITE",
                        test_id="test_suite",
                        input_data=" ".join(test_command),
                        observed_output=exec_res.stderr or exec_res.stdout or "Non-zero exit code",
                        expected_output="All tests passing with exit code 0",
                        failure_reason=f"Tests failed with exit code {exec_res.exit_code} (failed={test_summary.failed}, errored={test_summary.errored})",
                        oracle_type=VerificationOracleType.DETERMINISTIC_CONTRACT,
                        execution_id=exec_res.run_id,
                        evidence_hash=hashlib.sha256((exec_res.stdout + exec_res.stderr).encode()).hexdigest(),
                        patch_id=self.patch_candidate.patch_id if self.patch_candidate else None,
                        target_file=self.patch_candidate.changed_files[0] if (self.patch_candidate and self.patch_candidate.changed_files) else None,
                        workspace_id=getattr(self, "workspace_id", None),
                        snapshot_hash=getattr(self, "snapshot_hash", None)
                    )
                    self.counterexamples.append(ce)
                    self.state_machine.events.record_event("COUNTEREXAMPLE_FOUND", {
                        "counterexample_id": ce.counterexample_id,
                        "reason": "TESTS_FAILED"
                    })
                    self.state_machine.advance("TEST_FAILED")
                elif test_summary.passed == 0 or test_summary.executed == 0 or test_summary.inconclusive > 0:
                    ce = Counterexample(
                        counterexample_id=f"ce_inconclusive_{self.state_machine.run_id}_{len(self.counterexamples)+1}",
                        invariant_id="DETERMINISTIC_TEST_EVIDENCE",
                        test_id="test_suite",
                        input_data=" ".join(test_command),
                        observed_output=exec_res.stdout or "No tests passed",
                        expected_output="At least one passed test in execution summary",
                        failure_reason="Test execution produced no passing test evidence (inconclusive)",
                        oracle_type=VerificationOracleType.DETERMINISTIC_CONTRACT,
                        execution_id=exec_res.run_id,
                        evidence_hash=hashlib.sha256((exec_res.stdout + exec_res.stderr).encode()).hexdigest(),
                        patch_id=self.patch_candidate.patch_id if self.patch_candidate else None,
                        target_file=self.patch_candidate.changed_files[0] if (self.patch_candidate and self.patch_candidate.changed_files) else None,
                        workspace_id=getattr(self, "workspace_id", None),
                        snapshot_hash=getattr(self, "snapshot_hash", None)
                    )
                    self.counterexamples.append(ce)
                    self.state_machine.events.record_event("COUNTEREXAMPLE_FOUND", {
                        "counterexample_id": ce.counterexample_id,
                        "reason": "TESTS_INCONCLUSIVE"
                    })
                    self.state_machine.advance("TEST_FAILED")
                else:
                    self.state_machine.events.record_event("TESTS_PASSED", {
                        "passed": test_summary.passed,
                        "executed": test_summary.executed
                    })
                    self.state_machine.advance("TEST_SUCCESS")
                
            elif state == RunState.ATTACK:
                try:
                    untrusted_context = getattr(self, "untrusted_context", "")
                    self.selected_attacks = self.red_team.generate_attacks(
                        self.task_contract,
                        self.patch_candidate,
                        untrusted_context
                    )
                    
                    if not self.selected_attacks:
                        self.state_machine.advance("ATTACK_FAILED")
                    else:
                        self.state_machine.advance("ATTACK_SUCCESS")
                except Exception as e:
                    import traceback; traceback.print_exc()
                    self.state_machine.advance(OperationalResult.TOOL_FAILURE)
                
            elif state == RunState.ANALYZE:
                if not self.counterexamples:
                    # No counterexamples means it failed for some operational reason or it's unrepairable
                    self.state_machine.advance("UNREPAIRABLE")
                elif self.repair_attempts >= self.task_contract.resource_budget.max_failed_attempts:
                    self.state_machine.advance("UNREPAIRABLE")
                else:
                    self.state_machine.advance("NEEDS_REPAIR")
                
            elif state == RunState.REPAIR:
                try:
                    self.repair_attempts += 1
                    ce_text = "\n".join([f"Target: {ce.invariant_id}\nInput: {ce.input_data}\nObserved: {ce.observed_output}\nExpected: {ce.expected_output}\nReason: {ce.failure_reason}" for ce in self.counterexamples])
                    
                    repair_candidate = self.repairer.repair(
                        self.task_contract,
                        self.patch_candidate,
                        ce_text,
                        getattr(self, "untrusted_context", "")
                    )
                    
                    if isinstance(repair_candidate, OperationalResult):
                        self.state_machine.events.record_event("REPAIR_POLICY_REJECTED", {"reason": repair_candidate.value})
                        self.state_machine.advance(OperationalResult.POLICY_BLOCKED)
                        continue
                        
                    from backend.sandbox.client import SandboxClient
                    norm_diff = SandboxClient._normalize_patch_diff(repair_candidate.diff)

                    # Convert to PatchCandidate for deterministic loop
                    new_patch = PatchCandidate(
                        patch_id=repair_candidate.repair_id,
                        task_id=self.task_contract.task_id,
                        base_commit_or_snapshot=self.task_contract.base_commit_or_snapshot,
                        diff=norm_diff,
                        changed_files=repair_candidate.changed_files,
                        patch_metadata={
                            "agent": "Repairer", 
                            "status": "generated", 
                            "parent_hash": repair_candidate.base_patch_hash,
                            "repair_hash": repair_candidate.repair_hash,
                            "target_failure": repair_candidate.target_failure
                        },
                        generation_provenance={"repair_id": repair_candidate.repair_id}
                    )
                    
                    try:
                        validate_patch(new_patch, self.task_contract)
                        
                        # Duplicate detection
                        if repair_candidate.repair_hash in self.seen_repairs:
                            self.state_machine.advance(OperationalResult.TOOL_FAILURE)
                            continue
                        self.seen_repairs.add(repair_candidate.repair_hash)

                        self.state_machine.events.record_event("REPAIR_CANDIDATE_VALIDATED", {"repair_id": repair_candidate.repair_id})
                        self.patch_candidate = new_patch
                        self.patch_lineage.append(self.patch_candidate.patch_id)
                        self.state_machine.advance(self.patch_candidate)
                    except ValueError as e:
                        self.state_machine.events.record_event("REPAIR_POLICY_REJECTED", {"reason": str(e)})
                        self.state_machine.advance(OperationalResult.POLICY_BLOCKED)
                except Exception as e:
                    import traceback; traceback.print_exc()
                    self.state_machine.advance(OperationalResult.MODEL_FAILURE)
                
            elif state == RunState.VERIFY:
                from backend.verification.attack_validator import validate_attack_for_execution
                from backend.verification.attack_executor import AttackVerificationEngine
                from backend.sandbox.factory import get_sandbox_backend
                from backend.sandbox.models import SandboxPolicy
                from backend.verification.policy import DeterministicVerificationPolicy
                from backend.verification.models import TestResultSummary, RegressionSummary
                from backend.evidence.builder import EvidenceAggregator
                
                if not self.selected_attacks:
                    self.selected_attacks = []
                    
                policy = SandboxPolicy()
                trust = self.repository_trust
                backend = getattr(self, "sandbox_backend", None) or get_sandbox_backend(policy, repository_trust=trust)
                repo_root = self._resolve_repo_root()
                try:
                    executor = AttackVerificationEngine(backend, repository_trust=trust, repo_root=repo_root, patch_candidate=self.patch_candidate)
                except TypeError:
                    try:
                        executor = AttackVerificationEngine(backend, repository_trust=trust)
                    except TypeError:
                        executor = AttackVerificationEngine(backend)
                if hasattr(executor, "repository_trust"):
                    executor.repository_trust = trust
                if hasattr(executor, "repo_root"):
                    executor.repo_root = repo_root
                if hasattr(executor, "patch_candidate"):
                    executor.patch_candidate = self.patch_candidate
                
                any_fails = False
                if not hasattr(self, "counterexamples") or self.counterexamples is None:
                    self.counterexamples = []
                
                all_obs = []
                all_oracles = []
                
                for attack_candidate in self.selected_attacks:
                    try:
                        req = validate_attack_for_execution(
                            self.state_machine.run_id,
                            self.task_contract.task_id,
                            getattr(self, "snapshot_hash", "unknown"),
                            self.patch_candidate.diff_sha256 if self.patch_candidate else "unknown",
                            attack_candidate
                        )
                    except ValueError as e:
                        self.state_machine.events.record_event("ATTACK_VALIDATION_FAILED", {"attack_id": attack_candidate.attack_id, "reason": str(e)})
                        continue
                        
                    obs, oracle_res, ce = executor.execute_and_verify(req, getattr(self, "workspace_id", "unknown"))
                    all_obs.append(obs)
                    all_oracles.append(oracle_res)
                    
                    self.state_machine.events.record_event("ATTACK_OBSERVATION", {"execution_id": req.execution_id, "status": obs.status.value})
                    
                    # If oracle says the attack succeeded, the security invariant failed
                    if oracle_res.result == "FAIL":
                        any_fails = True
                        if ce:
                            if getattr(ce, "patch_id", None) is None and getattr(self, "patch_candidate", None):
                                ce.patch_id = self.patch_candidate.patch_id
                            if getattr(ce, "target_file", None) is None and getattr(req, "target", None):
                                ce.target_file = req.target
                            if getattr(ce, "workspace_id", None) is None:
                                ce.workspace_id = getattr(self, "workspace_id", "unknown")
                            if getattr(ce, "snapshot_hash", None) is None:
                                ce.snapshot_hash = getattr(self, "snapshot_hash", "unknown")
                            self.state_machine.events.record_event("COUNTEREXAMPLE_FOUND", {"counterexample_id": ce.counterexample_id})
                            self.counterexamples.append(ce)
                            
                from backend.verification.models import ExecutionStatus, VerificationStatus
                
                # Pick primary observation: prioritize operational errors and non-zero exit codes
                main_obs = None
                for obs in all_obs:
                    if obs.status in (
                        ExecutionStatus.POLICY_BLOCKED,
                        ExecutionStatus.SANDBOX_FAILURE,
                        ExecutionStatus.RESOURCE_LIMIT,
                        ExecutionStatus.TIMEOUT,
                        ExecutionStatus.EXECUTION_FAILURE,
                    ):
                        main_obs = obs
                        break
                    elif obs.status == ExecutionStatus.NONZERO and main_obs is None:
                        main_obs = obs
                if main_obs is None and all_obs:
                    main_obs = all_obs[0]
                if main_obs is None and hasattr(self, "last_test_observation"):
                    main_obs = self.last_test_observation
                    
                # Preserve the genuine test summary from test execution
                test_summary = getattr(self, "last_test_summary", None)
                if test_summary is None:
                    test_summary = TestResultSummary()

                # REV-017: Aggregate security oracles into deterministic security verification
                from backend.verification.security_models import SecurityResultAggregation, SecurityResultClassification
                security_agg = None
                if all_oracles or all_obs:
                    if any(o.result == "FAIL" for o in all_oracles):
                        sec_status = SecurityResultClassification.FAIL
                    elif any(o.result == "INCONCLUSIVE" for o in all_oracles):
                        sec_status = SecurityResultClassification.INCONCLUSIVE
                    elif any(obs.status == ExecutionStatus.POLICY_BLOCKED for obs in all_obs):
                        sec_status = SecurityResultClassification.BLOCKED
                    elif any(obs.status in (ExecutionStatus.TIMEOUT, ExecutionStatus.RESOURCE_LIMIT, ExecutionStatus.SANDBOX_FAILURE, ExecutionStatus.EXECUTION_FAILURE) for obs in all_obs):
                        sec_status = SecurityResultClassification.INCONCLUSIVE
                    elif all(o.result == "PASS" for o in all_oracles) and len(all_oracles) > 0:
                        sec_status = SecurityResultClassification.PASS
                    else:
                        sec_status = SecurityResultClassification.NOT_EVALUATED

                    security_agg = SecurityResultAggregation(
                        overall_status=sec_status
                    )

                # Compile deterministic verification result
                ver_policy = DeterministicVerificationPolicy()
                self.verification_result = ver_policy.evaluate(
                    repository_snapshot_hash=getattr(self, "snapshot_hash", "unknown"),
                    patch_hash=self.patch_candidate.diff_sha256 if getattr(self, "patch_candidate", None) else "unknown",
                    structured_observation=main_obs,
                    test_summary=test_summary,
                    regression_summary=RegressionSummary(),
                    invariants=[],
                    security_aggregation=security_agg,
                    oracle_results=all_oracles,
                    counterexamples=self.counterexamples,
                    task_contract=self.task_contract
                )
                
                # Build receipt with canonical snapshot hash (REV-007)
                aggregator = EvidenceAggregator(self.task_contract, patch_lineage=self.patch_lineage)
                provider_name = getattr(self.model_provider, "provider_name", getattr(self.model_provider, "provider", "test"))
                model_name = getattr(self.model_provider, "default_model", getattr(self.model_provider, "model", "unknown"))
                prov_backend = (getattr(main_obs, "sandbox_backend", None) if main_obs and getattr(main_obs, "sandbox_backend", None) != "UNKNOWN" else None) or type(backend).__name__
                self.evidence_receipt = aggregator.build_receipt(
                    self.state_machine.run_id,
                    self.patch_candidate if self.patch_candidate else PatchCandidate(patch_id="none", task_id=self.task_contract.task_id, base_commit_or_snapshot="", diff=""),
                    self.verification_result,
                    self.selected_attacks,
                    {"provider": provider_name, "model": model_name},
                    {"backend": prov_backend},
                    snapshot_hash=getattr(self, "snapshot_hash", None)
                )
                            
                # Route strictly according to deterministic verification status
                if self.verification_result.status in (
                    VerificationStatus.POLICY_BLOCKED,
                    VerificationStatus.SANDBOX_FAILURE,
                    VerificationStatus.RESOURCE_LIMIT,
                    VerificationStatus.TIMEOUT,
                    VerificationStatus.EXECUTION_FAILURE,
                ):
                    op_map = {
                        VerificationStatus.POLICY_BLOCKED: OperationalResult.POLICY_BLOCKED,
                        VerificationStatus.SANDBOX_FAILURE: OperationalResult.SANDBOX_FAILURE,
                        VerificationStatus.RESOURCE_LIMIT: OperationalResult.RESOURCE_LIMIT,
                        VerificationStatus.TIMEOUT: OperationalResult.TIMEOUT,
                        VerificationStatus.EXECUTION_FAILURE: OperationalResult.TOOL_FAILURE,
                    }
                    op_res = op_map.get(self.verification_result.status, OperationalResult.TOOL_FAILURE)
                    self.state_machine.advance(op_res)
                elif self.verification_result.status == VerificationStatus.REJECTED:
                    # Repairable or unrepairable: route to ANALYZE
                    self.state_machine.advance("VERIFY_FAILED")
                elif self.verification_result.status == VerificationStatus.INCONCLUSIVE:
                    # Non-success: advance to JUDGE so the advisory Judge agent explains the receipt,
                    # but JUDGE strictly fails closed to ABORTED.
                    self.state_machine.advance("VERIFY_INCONCLUSIVE")
                elif self.verification_result.status == VerificationStatus.VERIFIED:
                    self.state_machine.advance("VERIFY_SUCCESS")
                else:
                    self.state_machine.advance(OperationalResult.POLICY_BLOCKED)
                
            elif state == RunState.JUDGE:
                from backend.models.evidence import verify_receipt_integrity
                from backend.verification.models import VerificationStatus
                
                receipt = getattr(self, "evidence_receipt", None)
                if not receipt:
                    self.state_machine.events.record_event("EVIDENCE_MISSING", {})
                    self.state_machine.advance("JUDGE_FAIL")
                    continue
                
                if not verify_receipt_integrity(receipt):
                    self.state_machine.events.record_event("EVIDENCE_INTEGRITY_FAILURE", {})
                    self.state_machine.advance("JUDGE_FAIL")
                    continue
                    
                try:
                    self.judge_explanation = self.judge.generate_explanation(
                        receipt,
                        self.task_contract,
                        self.patch_candidate
                    )
                    self.state_machine.events.record_event("JUDGE_EXPLANATION_GENERATED", {})
                except Exception as e:
                    import traceback; traceback.print_exc()
                    # Judge failure does NOT change the deterministic verification result
                    self.state_machine.events.record_event("JUDGE_FAILURE", {"reason": str(e)})
                
                # Authoritative deterministic gate:
                # VERIFIED lifecycle state requires the deterministic receipt verdict to be VERIFIED.
                # INCONCLUSIVE and REJECTED must NEVER reach VERIFIED.
                if receipt.verdict == VerificationStatus.VERIFIED:
                    self.state_machine.advance("JUDGE_PASS")
                else:
                    self.state_machine.advance("JUDGE_FAIL")
                
        # If run aborted before VERIFY, build a fail-closed operational receipt
        if self.state_machine.current_state == RunState.ABORTED and not getattr(self, "evidence_receipt", None):
            from backend.evidence.builder import EvidenceAggregator
            from backend.verification.policy import DeterministicVerificationPolicy
            from backend.verification.models import TestResultSummary, RegressionSummary
            
            obs = getattr(self, "last_test_observation", None)
            ver_policy = DeterministicVerificationPolicy()
            ver_res = ver_policy.evaluate(
                repository_snapshot_hash=getattr(self, "snapshot_hash", getattr(self.task_contract, "base_commit_or_snapshot", "unknown")),
                patch_hash=self.patch_candidate.diff_sha256 if getattr(self, "patch_candidate", None) else "unknown",
                structured_observation=obs,
                test_summary=getattr(self, "last_test_summary", None) or TestResultSummary(),
                regression_summary=RegressionSummary(),
                invariants=[],
                security_aggregation=None,
                oracle_results=[],
                counterexamples=self.counterexamples
            )
            aggregator = EvidenceAggregator(self.task_contract, patch_lineage=self.patch_lineage)
            provider_name = getattr(self.model_provider, "provider_name", getattr(self.model_provider, "provider", "test"))
            model_name = getattr(self.model_provider, "default_model", getattr(self.model_provider, "model", "unknown"))
            self.evidence_receipt = aggregator.build_receipt(
                self.state_machine.run_id,
                self.patch_candidate if self.patch_candidate else PatchCandidate(patch_id="none", task_id=self.task_contract.task_id, base_commit_or_snapshot="", diff=""),
                ver_res,
                self.selected_attacks or [],
                {"provider": provider_name, "model": model_name},
                {"backend": "SandboxClient"},
                snapshot_hash=getattr(self, "snapshot_hash", None)
            )

        return self.state_machine.current_state
