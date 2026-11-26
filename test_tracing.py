"""API-free tests for Part 7 structured traces and viewer utilities."""

import tempfile
import unittest
from pathlib import Path

from trace_utils import add_iteration, finish_run_trace, new_run_trace, read_run_trace, write_run_trace


class TracingTests(unittest.TestCase):
    def test_round_trip_one_run(self):
        trace = new_run_trace("Triage ticket 18")
        add_iteration(
            trace,
            1,
            123.4,
            500,
            500,
            [{"name": "get_ticket", "arguments": {"ticket_id": 18}}],
            [{"name": "get_ticket", "result": {"id": 18}}],
        )
        trace = finish_run_trace(trace, "final_answer", "Stop for escalation")

        with tempfile.TemporaryDirectory() as directory:
            path = write_run_trace(trace, Path(directory))
            loaded = read_run_trace(path)

        self.assertEqual(loaded["goal"], "Triage ticket 18")
        self.assertEqual(loaded["total_tokens"], 500)
        self.assertEqual(loaded["iterations"][0]["tool_requested"][0]["name"], "get_ticket")

    def test_wrong_run_fixture_is_viewable(self):
        fixture = Path(__file__).with_name("traces") / "wrong_run_example.json"
        trace = read_run_trace(fixture)
        self.assertEqual(len(trace["iterations"]), 3)
        self.assertEqual(trace["iterations"][1]["tool_requested"][0]["name"], "send_reply")


if __name__ == "__main__":
    unittest.main()
