"""Status mapping for `qstat -f`. subprocess is mocked; no Torque server is required."""

import subprocess
import unittest
from unittest.mock import patch

from pdf2chemicals_service.cluster import (
    _parse_qstat_full,
    get_pbs_job_status,
    is_pbs_job_completed,
)


def _qstat(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        args=["qstat", "-f", "1.feynman"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


QSTAT_COMPLETED = """\
Job Id: 57259.feynman
    Job_Name = pdf2chemicals_abc
    job_state = C
    euser = svc_pdf2chemicals_prod
    exit_status = 0
    resources_used.cput = 00:00:01
\tcontinuation that is not an attribute
"""


class QstatFullParserTests(unittest.TestCase):
    def test_reads_four_space_attributes_and_skips_tab_continuations(self):
        attrs = _parse_qstat_full(QSTAT_COMPLETED)
        self.assertEqual(attrs["job_state"], "C")
        self.assertEqual(attrs["exit_status"], "0")
        self.assertEqual(attrs["euser"], "svc_pdf2chemicals_prod")
        self.assertNotIn("continuation", attrs)


class GetPbsJobStatusTests(unittest.TestCase):
    def test_exit_status_zero_is_completed(self):
        with patch(
            "pdf2chemicals_service.cluster.subprocess.run",
            return_value=_qstat(stdout=QSTAT_COMPLETED),
        ):
            self.assertEqual(get_pbs_job_status("57259.feynman"), "COMPLETED")

    def test_nonzero_exit_status_is_failed(self):
        output = "    job_state = C\n    exit_status = 1\n"
        with patch(
            "pdf2chemicals_service.cluster.subprocess.run",
            return_value=_qstat(stdout=output),
        ):
            self.assertEqual(get_pbs_job_status("57259.feynman"), "FAILED")

    def test_negative_exit_status_is_failed(self):
        output = "    job_state = C\n    exit_status = -3\n"
        with patch(
            "pdf2chemicals_service.cluster.subprocess.run",
            return_value=_qstat(stdout=output),
        ):
            self.assertEqual(get_pbs_job_status("57259.feynman"), "FAILED")

    def test_queued_running_and_exiting_states(self):
        cases = [("Q", "QUEUED"), ("R", "RUNNING"), ("E", "RUNNING"), ("H", "RUNNING")]
        for state, expected in cases:
            with self.subTest(state=state):
                output = f"    job_state = {state}\n"
                with patch(
                    "pdf2chemicals_service.cluster.subprocess.run",
                    return_value=_qstat(stdout=output),
                ):
                    self.assertEqual(get_pbs_job_status("57259.feynman"), expected)

    def test_finished_without_exit_status_is_completed(self):
        with patch(
            "pdf2chemicals_service.cluster.subprocess.run",
            return_value=_qstat(stdout="    job_state = C\n"),
        ):
            self.assertEqual(get_pbs_job_status("57259.feynman"), "COMPLETED")

    def test_missing_job_state_is_unknown(self):
        with patch(
            "pdf2chemicals_service.cluster.subprocess.run",
            return_value=_qstat(stdout="    Job_Name = only\n"),
        ):
            self.assertEqual(get_pbs_job_status("57259.feynman"), "UNKNOWN")

    def test_unknown_job_id_is_completed(self):
        with patch(
            "pdf2chemicals_service.cluster.subprocess.run",
            return_value=_qstat(stderr="qstat: Unknown Job Id 57259.feynman", returncode=1),
        ):
            self.assertEqual(get_pbs_job_status("57259.feynman"), "COMPLETED")

    def test_qstat_error_is_unknown(self):
        with patch(
            "pdf2chemicals_service.cluster.subprocess.run",
            return_value=_qstat(stderr="Cannot connect to server", returncode=1),
        ):
            self.assertEqual(get_pbs_job_status("57259.feynman"), "UNKNOWN")

    def test_blank_or_flag_like_job_id_is_unknown(self):
        self.assertEqual(get_pbs_job_status(""), "UNKNOWN")
        self.assertEqual(get_pbs_job_status("-f"), "UNKNOWN")

    def test_timeout_and_missing_binary_are_unknown(self):
        with patch(
            "pdf2chemicals_service.cluster.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["qstat"], timeout=30),
        ):
            self.assertEqual(get_pbs_job_status("57259.feynman"), "UNKNOWN")
        with patch(
            "pdf2chemicals_service.cluster.subprocess.run",
            side_effect=FileNotFoundError(),
        ):
            self.assertEqual(get_pbs_job_status("57259.feynman"), "UNKNOWN")


class IsPbsJobCompletedTests(unittest.TestCase):
    def test_completed_and_failed_count_as_finished(self):
        with patch(
            "pdf2chemicals_service.cluster.get_pbs_job_status", return_value="FAILED"
        ):
            self.assertTrue(is_pbs_job_completed("57259.feynman"))
        with patch(
            "pdf2chemicals_service.cluster.get_pbs_job_status", return_value="RUNNING"
        ):
            self.assertFalse(is_pbs_job_completed("57259.feynman"))
