"""qstat -f parsing for the Torque gateway. No Torque server is required."""

import os
import sys
import unittest

os.environ["GATEWAY_TOKEN"] = "test-token"
sys.path.insert(0, os.path.dirname(__file__))

import gateway


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
        attrs = gateway.parse_qstat_full(QSTAT_COMPLETED)
        self.assertEqual(attrs["job_state"], "C")
        self.assertEqual(attrs["exit_status"], "0")
        self.assertEqual(attrs["euser"], "svc_pdf2chemicals_prod")
        self.assertNotIn("continuation", attrs)


class SimplifyStatusTests(unittest.TestCase):
    def test_exit_status_zero_is_completed(self):
        self.assertEqual(
            gateway.simplify_status(gateway.parse_qstat_full(QSTAT_COMPLETED)),
            "COMPLETED",
        )

    def test_nonzero_exit_status_is_failed(self):
        attrs = gateway.parse_qstat_full("    job_state = C\n    exit_status = 1\n")
        self.assertEqual(gateway.simplify_status(attrs), "FAILED")

    def test_negative_exit_status_is_failed(self):
        attrs = gateway.parse_qstat_full("    job_state = C\n    exit_status = -3\n")
        self.assertEqual(gateway.simplify_status(attrs), "FAILED")

    def test_queued_running_and_exiting_states(self):
        cases = [("Q", "QUEUED"), ("R", "RUNNING"), ("E", "RUNNING"), ("H", "RUNNING")]
        for state, expected in cases:
            with self.subTest(state=state):
                attrs = gateway.parse_qstat_full("    job_state = %s\n" % state)
                self.assertEqual(gateway.simplify_status(attrs), expected)

    def test_finished_without_exit_status_is_completed(self):
        attrs = gateway.parse_qstat_full("    job_state = C\n")
        self.assertEqual(gateway.simplify_status(attrs), "COMPLETED")

    def test_missing_job_state_is_unknown(self):
        attrs = gateway.parse_qstat_full("    Job_Name = only\n")
        self.assertEqual(gateway.simplify_status(attrs), "UNKNOWN")
