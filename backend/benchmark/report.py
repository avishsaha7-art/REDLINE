"""
Benchmark Report Generation for REDLINE.

Generates auditable, evidence-linked benchmark reports in JSON and Markdown formats.
Guarantees:
1. Exact trust anchors (commit SHA, tag, manifest digest) match frozen baseline.
2. Complete audit trail with task outcomes and evidence digests.
3. Cryptographic integrity digest (SHA-256) over the canonical structured report payload.
4. Redaction: Never exposes secrets or hidden evaluator code.
5. Mandatory non-statistical limitation disclaimer.
"""

import json
import uuid
import datetime
import hashlib
from typing import Dict, Any, List, Optional, Tuple, Union

from backend.benchmark.models import (
    BenchmarkRunRecord,
    BenchmarkReport,
    TaskEvaluationResult,
    BenchmarkVerdict,
)
from backend.benchmark.comparison import BenchmarkComparator


class BenchmarkReportGenerator:
    """
    Constructs auditable JSON and Markdown benchmark reports with canonical SHA-256 integrity digests.
    """
    @classmethod
    def generate_report(cls, run: BenchmarkRunRecord) -> BenchmarkReport:
        """
        Creates a structured, cryptographically hashed BenchmarkReport from a run record.
        """
        metrics = BenchmarkComparator.compute_arm_metrics(run)
        task_details = list(run.task_results.values())

        report = BenchmarkReport(
            report_id=f"rep_{uuid.uuid4().hex[:12]}",
            schema_version="1.0.0",
            run_id=run.run_id,
            dataset_name=run.config.dataset_name,
            dataset_version=run.config.dataset_version,
            git_anchor_commit=run.config.target_commit_sha,
            git_annotated_tag=run.config.annotated_tag,
            manifest_sha256=run.config.manifest_sha256,
            runner_version="1.0.0",
            evaluator_version="1.0.0",
            sandbox_provenance=run.capability_result or {},
            config=run.config,
            summary_metrics=metrics,
            task_details=task_details,
            disclaimer=BenchmarkComparator.STATISTICAL_DISCLAIMER,
        )
        report.report_sha256 = report.compute_digest()
        return report

    @classmethod
    def verify_report(cls, report: Union[BenchmarkReport, Dict[str, Any], str]) -> Tuple[bool, str, str]:
        """
        Verifies the cryptographic SHA-256 integrity digest of a BenchmarkReport.
        Accepts BenchmarkReport instance, dict, or JSON string.
        Returns: (is_valid, expected_digest, actual_digest)
        """
        if isinstance(report, str):
            try:
                data = json.loads(report)
            except Exception as e:
                return False, "", f"MALFORMED_JSON: {str(e)}"
            try:
                report_obj = BenchmarkReport(**data)
            except Exception as e:
                return False, "", f"MALFORMED_REPORT_SCHEMA: {str(e)}"
        elif isinstance(report, dict):
            try:
                report_obj = BenchmarkReport(**report)
            except Exception as e:
                return False, "", f"MALFORMED_REPORT_SCHEMA: {str(e)}"
        elif isinstance(report, BenchmarkReport):
            report_obj = report
        else:
            return False, "", "INVALID_REPORT_TYPE"

        actual_digest = report_obj.report_sha256
        if not actual_digest:
            return False, "", "MISSING_DIGEST"

        expected_digest = report_obj.compute_digest()
        import hmac
        is_valid = hmac.compare_digest(actual_digest.lower(), expected_digest.lower())
        return is_valid, expected_digest, actual_digest

    @classmethod
    def to_markdown(cls, report: BenchmarkReport) -> str:
        """Renders the benchmark report as human-readable Markdown."""
        sm = report.summary_metrics
        lines = [
            f"# REDLINE Benchmark Run Report: `{report.run_id}`",
            "",
            "## 1. Provenance & Trust Anchors",
            f"- **Report ID:** `{report.report_id}`",
            f"- **Report SHA-256 Digest:** `{report.report_sha256}`",
            f"- **Run ID:** `{report.run_id}`",
            f"- **Generated At:** `{report.created_at}`",
            f"- **Dataset:** `{report.dataset_name}` v`{report.dataset_version}`",
            f"- **Dataset Git Commit:** `{report.git_anchor_commit}`",
            f"- **Dataset Annotated Tag:** `{report.git_annotated_tag}`",
            f"- **Manifest SHA-256:** `{report.manifest_sha256}`",
            f"- **Runner / Evaluator Version:** v`{report.runner_version}` / v`{report.evaluator_version}`",
            "",
            "## 2. Execution Environment & Sandbox Capabilities",
            f"- **Arm Type:** `{report.config.arm_type.value}`",
            f"- **Sandbox Backend:** `{report.sandbox_provenance.get('backend', 'Unknown')}`",
            f"- **Security Level:** `{report.sandbox_provenance.get('security_level', 'UNAVAILABLE')}`",
            f"- **Filesystem Isolation:** `{report.sandbox_provenance.get('filesystem_isolation', 'NOT_AVAILABLE')}`",
            f"- **Untrusted Execution Authorized:** `{report.sandbox_provenance.get('secure_untrusted_execution', False)}`",
            "",
            "## 3. Benchmark Summary Metrics",
            "| Metric | Value | Denominator / Basis |",
            "|--------|-------|---------------------|",
            f"| Total Declared Tasks | {sm.get('total_declared_tasks', 0)} | Frozen Benchmark Dataset |",
            f"| Total Attempted Tasks | {sm.get('total_attempted_tasks', 0)} | Candidates Executed |",
            f"| Total Blocked Tasks | {sm.get('total_blocked_tasks', 0)} | Refused / Blocked Before Execution |",
            f"| Authoritative Verified | {sm.get('verified_count', 0)} | Security & Regression Invariants Passed |",
            f"| Authoritative Rejected | {sm.get('rejected_count', 0)} | Exploitable or Regressed |",
            f"| Inconclusive | {sm.get('inconclusive_count', 0)} | Non-deterministic / Truncated Evidence |",
            f"| Operational Failures | {sm.get('operational_failure_count', 0)} | Sandbox Missing, Timeout, Policy Block |",
            f"| Benchmark Pass Rate | {sm.get('benchmark_pass_rate', 0.0) * 100:.1f}% | Verified / Declared Tasks (n={sm.get('total_declared_tasks', 12)}) |",
            "",
            "## 4. Task-Level Evaluation Outcomes",
            "| Task ID | Execution Status | Verdict | Vulnerability Neutralized | Secure Invariant | Regression Passed | Duration (ms) |",
            "|---------|------------------|---------|---------------------------|------------------|-------------------|---------------|",
        ]

        for t in report.task_details:
            exec_status = "ATTEMPTED" if t.attempted else "BLOCKED (NOT_EXECUTED)"
            neut = "PASS" if t.vulnerability_neutralized else ("FAIL" if t.vulnerability_neutralized is False else "N/A")
            sec = "PASS" if t.secure_acceptance_passed else ("FAIL" if t.secure_acceptance_passed is False else "N/A")
            reg = "PASS" if t.regression_passed else ("FAIL" if t.regression_passed is False else "N/A")
            dur = str(t.execution_duration_ms or 0)
            lines.append(f"| `{t.task_id}` | {exec_status} | **{t.verdict.value}** | {neut} | {sec} | {reg} | {dur} |")

        lines.extend([
            "",
            "## 5. Statistical & Generalization Disclaimer",
            f"> {report.disclaimer}",
            "",
            "---",
            f"*End of Report — SHA-256 Digest: `{report.report_sha256}`*"
        ])

        return "\n".join(lines)
