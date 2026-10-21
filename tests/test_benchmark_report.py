"""
Unit & Security Tests for Benchmark Report Generation.

Validates:
1. Exact trust anchors (commit SHA, tag, manifest digest) match frozen baseline.
2. Cryptographic report digest (SHA-256) is deterministically computed.
3. Markdown and JSON representations contain complete provenance and audit trails.
4. Redaction: No live secrets or hidden evaluator code exposed.
5. Mandatory statistical limitation disclaimer is present.
"""

from backend.benchmark.models import (
    BenchmarkArmType,
    BenchmarkReport,
    BenchmarkRunConfig,
    BenchmarkRunRecord,
    BenchmarkRunState,
    BenchmarkVerdict,
    TaskEvaluationResult,
)
from backend.benchmark.report import BenchmarkReportGenerator


def test_report_generation_preserves_trust_anchors():
    """Generated report must contain frozen trust anchor constants."""
    config = BenchmarkRunConfig(
        run_id="run_rep_test",
        arm_type=BenchmarkArmType.ARM_A_REDLINE,
    )
    record = BenchmarkRunRecord(
        run_id="run_rep_test",
        config=config,
        state=BenchmarkRunState.COMPLETED,
    )
    record.task_results["SEC-BENCH-001"] = TaskEvaluationResult(
        task_id="SEC-BENCH-001",
        arm="ARM_A_REDLINE",
        verdict=BenchmarkVerdict.VERIFIED,
        vulnerability_neutralized=True,
        secure_acceptance_passed=True,
        regression_passed=True,
        execution_duration_ms=150,
        evaluation_duration_ms=40,
        evidence_hashes={"log_sha256": "abcdef" * 10}
    )

    report = BenchmarkReportGenerator.generate_report(record)

    assert report.dataset_name == "REDLINE-Held-Out-Security-Benchmark"
    assert report.dataset_version == "1.0.0"
    assert report.git_anchor_commit == "6e476bccaba2187055254d1cd71b539d7903b34f"
    assert report.git_annotated_tag == "benchmark-v1.0.0"
    assert report.manifest_sha256 == "d2cd37b9a588151975c992426338b0341f39bc824e1627c32d51e02ed1ac20c2"
    assert len(report.report_sha256) == 64
    assert len(report.task_details) == 1
    assert "n=12" in report.disclaimer


def test_markdown_report_rendering():
    """Markdown rendering must produce structured, human-readable sections."""
    config = BenchmarkRunConfig(
        run_id="run_md_test",
        arm_type=BenchmarkArmType.ARM_A_REDLINE,
    )
    record = BenchmarkRunRecord(
        run_id="run_md_test",
        config=config,
        state=BenchmarkRunState.COMPLETED,
    )
    record.task_results["SEC-BENCH-001"] = TaskEvaluationResult(
        task_id="SEC-BENCH-001",
        arm="ARM_A_REDLINE",
        verdict=BenchmarkVerdict.VERIFIED,
        vulnerability_neutralized=True,
        secure_acceptance_passed=True,
        regression_passed=True,
        execution_duration_ms=100,
    )

    report = BenchmarkReportGenerator.generate_report(record)
    md = BenchmarkReportGenerator.to_markdown(report)

    assert "# REDLINE Benchmark Run Report: `run_md_test`" in md
    assert "## 1. Provenance & Trust Anchors" in md
    assert "## 2. Execution Environment & Sandbox Capabilities" in md
    assert "## 3. Benchmark Summary Metrics" in md
    assert "## 4. Task-Level Evaluation Outcomes" in md
    assert "## 5. Statistical & Generalization Disclaimer" in md
    assert report.report_sha256 in md
    assert "SEC-BENCH-001" in md
    assert "VERIFIED" in md


def test_report_contains_no_secrets_or_hidden_evaluator_content():
    """Reports must not leak raw python code or secrets."""
    config = BenchmarkRunConfig(run_id="run_leak_test", arm_type=BenchmarkArmType.SYNTHETIC)
    record = BenchmarkRunRecord(run_id="run_leak_test", config=config, state=BenchmarkRunState.COMPLETED)
    record.task_results["SEC-BENCH-001"] = TaskEvaluationResult(
        task_id="SEC-BENCH-001",
        arm="SYNTHETIC",
        verdict=BenchmarkVerdict.VERIFIED,
        vulnerability_neutralized=True,
        secure_acceptance_passed=True,
        regression_passed=True,
    )

    report = BenchmarkReportGenerator.generate_report(record)
    report_json = report.model_dump_json()

    # Must not contain secret patterns or raw source
    assert "sk-" not in report_json
    assert "SECRET" not in report_json or "SECRET_LEAKAGE" in report_json
    assert "def test_exploit" not in report_json
    assert "def test_secure" not in report_json


def test_valid_report_digest_verifies_after_serialization_and_parsing():
    """Requirement 7: A valid report digest verifies after serialization and parsing."""
    config = BenchmarkRunConfig(run_id="run_verify_test", arm_type=BenchmarkArmType.SYNTHETIC)
    record = BenchmarkRunRecord(run_id="run_verify_test", config=config, state=BenchmarkRunState.COMPLETED)
    record.task_results["SEC-BENCH-001"] = TaskEvaluationResult(
        task_id="SEC-BENCH-001",
        arm="SYNTHETIC",
        verdict=BenchmarkVerdict.VERIFIED,
        attempted=True,
        vulnerability_neutralized=True,
        secure_acceptance_passed=True,
        regression_passed=True,
    )
    report = BenchmarkReportGenerator.generate_report(record)

    # 1. Direct object verification
    is_valid, expected, actual = BenchmarkReportGenerator.verify_report(report)
    assert is_valid is True
    assert expected == actual == report.report_sha256
    assert report.verify_digest() is True

    # 2. JSON string round-trip verification
    report_json_str = report.model_dump_json()
    is_valid_json, expected_json, actual_json = BenchmarkReportGenerator.verify_report(report_json_str)
    assert is_valid_json is True
    assert expected_json == actual_json == report.report_sha256

    # 3. Parsed dict round-trip verification
    import json
    parsed_dict = json.loads(report_json_str)
    is_valid_dict, expected_dict, actual_dict = BenchmarkReportGenerator.verify_report(parsed_dict)
    assert is_valid_dict is True
    assert expected_dict == actual_dict == report.report_sha256


def test_altered_report_content_fails_digest_verification():
    """Requirement 8: Any change to hashed report content fails verification."""
    config = BenchmarkRunConfig(run_id="run_tamper_test", arm_type=BenchmarkArmType.SYNTHETIC)
    record = BenchmarkRunRecord(run_id="run_tamper_test", config=config, state=BenchmarkRunState.COMPLETED)
    record.task_results["SEC-BENCH-001"] = TaskEvaluationResult(
        task_id="SEC-BENCH-001",
        arm="SYNTHETIC",
        verdict=BenchmarkVerdict.VERIFIED,
        attempted=True,
    )
    report = BenchmarkReportGenerator.generate_report(record)

    import json
    report_dict = json.loads(report.model_dump_json())

    # Tampering scenario 1: Alter commit anchor
    tampered_1 = dict(report_dict)
    tampered_1["git_anchor_commit"] = "0000000000000000000000000000000000000000"
    is_valid, expected, actual = BenchmarkReportGenerator.verify_report(tampered_1)
    assert is_valid is False
    assert expected != actual

    # Tampering scenario 2: Alter task verdict in task_details
    tampered_2 = dict(report_dict)
    tampered_2["task_details"] = [dict(tampered_2["task_details"][0])]
    tampered_2["task_details"][0]["verdict"] = "REJECTED"
    is_valid, expected, actual = BenchmarkReportGenerator.verify_report(tampered_2)
    assert is_valid is False
    assert expected != actual

    # Tampering scenario 3: Alter summary metrics
    tampered_3 = dict(report_dict)
    tampered_3["summary_metrics"] = dict(tampered_3["summary_metrics"])
    tampered_3["summary_metrics"]["verified_count"] = 999
    is_valid, expected, actual = BenchmarkReportGenerator.verify_report(tampered_3)
    assert is_valid is False
    assert expected != actual


def test_altered_digest_fails_verification():
    """Requirement 9: A changed digest fails verification."""
    config = BenchmarkRunConfig(run_id="run_bad_digest_test", arm_type=BenchmarkArmType.SYNTHETIC)
    record = BenchmarkRunRecord(run_id="run_bad_digest_test", config=config, state=BenchmarkRunState.COMPLETED)
    record.task_results["SEC-BENCH-001"] = TaskEvaluationResult(
        task_id="SEC-BENCH-001",
        arm="SYNTHETIC",
        verdict=BenchmarkVerdict.VERIFIED,
    )
    report = BenchmarkReportGenerator.generate_report(record)

    import json
    report_dict = json.loads(report.model_dump_json())

    # Alter the digest itself
    report_dict["report_sha256"] = "a" * 64
    is_valid, expected, actual = BenchmarkReportGenerator.verify_report(report_dict)
    assert is_valid is False
    assert actual == "a" * 64
    assert expected != "a" * 64


def test_malformed_report_fails_verification():
    """Malformed JSON, missing fields, or invalid types fail verification cleanly."""
    # Invalid JSON string
    is_valid, _, err = BenchmarkReportGenerator.verify_report("{broken json:::")
    assert is_valid is False
    assert "MALFORMED_JSON" in err

    # Missing required schema fields
    is_valid, _, err = BenchmarkReportGenerator.verify_report({"invalid_key": 123})
    assert is_valid is False
    assert "MALFORMED_REPORT_SCHEMA" in err

    # Invalid input type
    is_valid, _, err = BenchmarkReportGenerator.verify_report(12345)
    assert is_valid is False
    assert "INVALID_REPORT_TYPE" in err

    # Missing digest field
    valid_record = BenchmarkRunRecord(
        run_id="run_missing_digest",
        config=BenchmarkRunConfig(run_id="run_missing_digest", arm_type=BenchmarkArmType.SYNTHETIC),
        state=BenchmarkRunState.COMPLETED
    )
    rep = BenchmarkReportGenerator.generate_report(valid_record)
    rep.report_sha256 = ""
    is_valid, _, err = BenchmarkReportGenerator.verify_report(rep)
    assert is_valid is False
    assert "MISSING_DIGEST" in err


def test_serialization_edge_cases_canonical_normalization():
    """
    Finding 3: Serialization edge cases:
    - Key order variations in dict must produce identical canonical digest.
    - Non-ASCII / Unicode characters must be handled deterministically.
    - Whitespace variations in external JSON payload normalize under deterministic canonical bytes.
    """
    import json
    config = BenchmarkRunConfig(run_id="run_canonical_edge", arm_type=BenchmarkArmType.SYNTHETIC)
    record = BenchmarkRunRecord(run_id="run_canonical_edge", config=config, state=BenchmarkRunState.COMPLETED)
    record.task_results["SEC-BENCH-001"] = TaskEvaluationResult(
        task_id="SEC-BENCH-001",
        arm="SYNTHETIC",
        verdict=BenchmarkVerdict.VERIFIED,
        attempted=True,
        failure_reason="Unicode: \u2705 \u00e9\u00e0\u00fc \u4e2d\u6587 \U0001F512"
    )
    report = BenchmarkReportGenerator.generate_report(record)

    # 1. Digest matches with Unicode content
    assert report.verify_digest() is True
    is_valid, expected, actual = BenchmarkReportGenerator.verify_report(report)
    assert is_valid is True
    assert expected == actual

    # 2. Key order variations in parsed dictionary
    raw_dict = json.loads(report.model_dump_json())
    # Reverse key order
    reversed_dict = {k: raw_dict[k] for k in reversed(list(raw_dict.keys()))}
    is_valid_rev, exp_rev, act_rev = BenchmarkReportGenerator.verify_report(reversed_dict)
    assert is_valid_rev is True
    assert exp_rev == act_rev == report.report_sha256

    # 3. Indented / formatted JSON string with extra spaces
    pretty_json = json.dumps(raw_dict, indent=4)
    is_valid_pretty, exp_pretty, act_pretty = BenchmarkReportGenerator.verify_report(pretty_json)
    assert is_valid_pretty is True
    assert exp_pretty == act_pretty == report.report_sha256


def test_unknown_top_level_fields_rejected_fail_closed():
    """
    Finding 1: An injected top-level field (such as attacker_note or __pwn__)
    must be rejected fail-closed and cannot be silently discarded while the digest verifies.
    """
    import json
    config = BenchmarkRunConfig(run_id="run_unknown_fields", arm_type=BenchmarkArmType.SYNTHETIC)
    record = BenchmarkRunRecord(run_id="run_unknown_fields", config=config, state=BenchmarkRunState.COMPLETED)
    record.task_results["SEC-BENCH-001"] = TaskEvaluationResult(
        task_id="SEC-BENCH-001",
        arm="SYNTHETIC",
        verdict=BenchmarkVerdict.VERIFIED,
        attempted=True,
    )
    report = BenchmarkReportGenerator.generate_report(record)
    base_dict = json.loads(report.model_dump_json())

    # 1. Injected 'attacker_note'
    tampered_1 = dict(base_dict)
    tampered_1["attacker_note"] = "Injected unauthorized commentary"
    is_valid, exp, act = BenchmarkReportGenerator.verify_report(tampered_1)
    assert is_valid is False
    assert "MALFORMED_REPORT_SCHEMA" in act
    assert "attacker_note" in act

    # 2. Injected '__pwn__'
    tampered_2 = dict(base_dict)
    tampered_2["__pwn__"] = True
    is_valid, exp, act = BenchmarkReportGenerator.verify_report(tampered_2)
    assert is_valid is False
    assert "MALFORMED_REPORT_SCHEMA" in act
    assert "__pwn__" in act

    # 3. Injected unknown field in raw JSON string representation
    tampered_json = json.dumps(tampered_1)
    is_valid, exp, act = BenchmarkReportGenerator.verify_report(tampered_json)
    assert is_valid is False
    assert "MALFORMED_REPORT_SCHEMA" in act


def test_unknown_nested_fields_rejected_fail_closed():
    """
    Finding 1: Nested unknown fields inside config or task_details must be
    strictly rejected and return a safe malformed-schema failure.
    """
    import json
    config = BenchmarkRunConfig(run_id="run_nested_unknown", arm_type=BenchmarkArmType.SYNTHETIC)
    record = BenchmarkRunRecord(run_id="run_nested_unknown", config=config, state=BenchmarkRunState.COMPLETED)
    record.task_results["SEC-BENCH-001"] = TaskEvaluationResult(
        task_id="SEC-BENCH-001",
        arm="SYNTHETIC",
        verdict=BenchmarkVerdict.VERIFIED,
        attempted=True,
    )
    report = BenchmarkReportGenerator.generate_report(record)
    base_dict = json.loads(report.model_dump_json())

    # 1. Unknown nested field in config
    tampered_cfg = dict(base_dict)
    tampered_cfg["config"] = dict(tampered_cfg["config"])
    tampered_cfg["config"]["unauthorized_config_opt"] = "malicious_mode"
    is_valid, exp, act = BenchmarkReportGenerator.verify_report(tampered_cfg)
    assert is_valid is False
    assert "MALFORMED_REPORT_SCHEMA" in act
    assert "unauthorized_config_opt" in act

    # 2. Unknown nested field in task_details item
    tampered_task = dict(base_dict)
    tampered_task["task_details"] = [dict(tampered_task["task_details"][0])]
    tampered_task["task_details"][0]["__pwn__"] = "injected_task_field"
    is_valid, exp, act = BenchmarkReportGenerator.verify_report(tampered_task)
    assert is_valid is False
    assert "MALFORMED_REPORT_SCHEMA" in act
    assert "__pwn__" in act


def test_unknown_field_direct_model_instantiation_raises_validation_error():
    """
    Finding 1: Direct instantiation with unknown fields raises pydantic.ValidationError.
    """
    import pydantic
    import pytest

    # Direct BenchmarkReport instantiation
    with pytest.raises(pydantic.ValidationError) as exc_info:
        BenchmarkReport(
            report_id="rep_test",
            schema_version="1.0.0",
            run_id="run_1",
            dataset_name="test",
            dataset_version="1.0.0",
            git_anchor_commit="abc",
            git_annotated_tag="v1",
            manifest_sha256="def",
            runner_version="1.0.0",
            evaluator_version="1.0.0",
            config=BenchmarkRunConfig(run_id="run_1"),
            disclaimer="disc",
            attacker_note="unauthorized"
        )
    assert "extra_forbidden" in str(exc_info.value)

    # Direct BenchmarkRunConfig instantiation
    with pytest.raises(pydantic.ValidationError) as exc_info:
        BenchmarkRunConfig(run_id="run_1", malicious_extra="flag")
    assert "extra_forbidden" in str(exc_info.value)

    # Direct TaskEvaluationResult instantiation
    with pytest.raises(pydantic.ValidationError) as exc_info:
        TaskEvaluationResult(
            task_id="SEC-BENCH-001",
            arm="SYNTHETIC",
            verdict=BenchmarkVerdict.VERIFIED,
            injected_field="value"
        )
    assert "extra_forbidden" in str(exc_info.value)


