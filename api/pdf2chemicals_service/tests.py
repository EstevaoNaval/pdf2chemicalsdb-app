"""HTTP client for the Torque gateway. Responses are mocked; no server is required."""

import unittest
from unittest.mock import patch

from pdf2chemicals_service.cluster import (
    get_pbs_job_status,
    is_pbs_job_completed,
    submit_pbs_script,
)


class GetPbsJobStatusTests(unittest.TestCase):
    def test_gateway_status_is_returned(self):
        with patch(
            "pdf2chemicals_service.cluster._gateway_call",
            return_value=(200, {"status": "RUNNING"}),
        ):
            self.assertEqual(get_pbs_job_status("57259.feynman"), "RUNNING")

    def test_not_found_is_completed(self):
        with patch(
            "pdf2chemicals_service.cluster._gateway_call",
            return_value=(404, {"job_id": "57259.feynman", "status": "NOT_FOUND"}),
        ):
            self.assertEqual(get_pbs_job_status("57259.feynman"), "COMPLETED")

    def test_gateway_error_is_unknown(self):
        with patch(
            "pdf2chemicals_service.cluster._gateway_call",
            return_value=(502, {"error": "qstat failed"}),
        ):
            self.assertEqual(get_pbs_job_status("57259.feynman"), "UNKNOWN")

    def test_unreachable_gateway_is_unknown(self):
        with patch(
            "pdf2chemicals_service.cluster._gateway_call",
            return_value=(None, {}),
        ):
            self.assertEqual(get_pbs_job_status("57259.feynman"), "UNKNOWN")

    def test_unexpected_status_is_unknown(self):
        with patch(
            "pdf2chemicals_service.cluster._gateway_call",
            return_value=(200, {"status": "WEIRD"}),
        ):
            self.assertEqual(get_pbs_job_status("57259.feynman"), "UNKNOWN")

    def test_blank_or_flag_like_job_id_is_unknown(self):
        self.assertEqual(get_pbs_job_status(""), "UNKNOWN")
        self.assertEqual(get_pbs_job_status("-f"), "UNKNOWN")


class SubmitPbsScriptTests(unittest.TestCase):
    def test_returns_job_id(self):
        with patch(
            "pdf2chemicals_service.cluster._gateway_call",
            return_value=(201, {"job_id": "57259.feynman"}),
        ) as call:
            self.assertEqual(submit_pbs_script("#PBS -N pdf2chemicals_x\n"), "57259.feynman")
        self.assertEqual(call.call_args.args[0], "POST")
        self.assertEqual(call.call_args.args[1], "/jobs")
        self.assertEqual(call.call_args.args[2], {"script": "#PBS -N pdf2chemicals_x\n"})

    def test_empty_script_raises(self):
        with self.assertRaises(ValueError):
            submit_pbs_script("  ")

    def test_failed_submit_raises(self):
        with patch(
            "pdf2chemicals_service.cluster._gateway_call",
            return_value=(502, {"error": "qsub failed"}),
        ):
            with self.assertRaises(RuntimeError):
                submit_pbs_script("#!/bin/bash\n")


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
