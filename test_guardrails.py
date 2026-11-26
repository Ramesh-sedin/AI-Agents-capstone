"""API-free tests for Part 5 approval and hard-limit guardrails."""

import unittest

import agent


class GuardrailTests(unittest.TestCase):
    def test_reply_rejection_is_returned_for_revision(self):
        answers = iter(["r", "Make it shorter and mention the next step"])
        approved, reason = agent.request_reply_approval(
            7,
            "We will review this issue and respond later.",
            input_fn=lambda prompt: next(answers),
        )
        self.assertFalse(approved)
        self.assertIn("next step", reason)

    def test_reply_approval_can_be_granted(self):
        approved, reason = agent.request_reply_approval(
            7,
            "Please try the reset link again.",
            input_fn=lambda prompt: "a",
        )
        self.assertTrue(approved)
        self.assertIn("Approved", reason)

    def test_per_tool_cap_stops_on_next_call(self):
        counts = {}
        for _ in range(3):
            self.assertIsNone(agent.enforce_tool_cap("get_ticket", counts, 3))
        stopped = agent.enforce_tool_cap("get_ticket", counts, 3)
        self.assertIn("per-tool call cap", stopped)
        self.assertIn("get_ticket", stopped)

    def test_each_tool_has_an_independent_limit(self):
        counts = {}
        for _ in range(3):
            agent.enforce_tool_cap("get_ticket", counts, 3)
        self.assertIsNone(agent.enforce_tool_cap("search_tickets", counts, 3))


if __name__ == "__main__":
    unittest.main()
