"""API-free tests for Part 4 system prompt and context compaction."""

import unittest

from google.genai import types

import agent


class ContextTests(unittest.TestCase):
    def test_system_prompt_load_is_stable_and_comments_are_removed(self):
        prompt = agent.load_system_prompt()
        self.assertIn("Support Desk Triage Agent", prompt)
        self.assertIn("Escalate or stop instead", prompt)
        self.assertNotIn("PROMPT DECISION NOTES", prompt)

    def test_compaction_preserves_goal_ticket_and_shortens_history(self):
        original_goal = types.Content(role="user", parts=[types.Part(text="Triage ticket 7")])
        original_ticket = {"id": 7, "subject": "Reset password link expired", "status": "open"}
        messages = [original_goal]
        observations = []

        for i in range(8):
            result = {"call": i, "summary": "x" * 500}
            observations.append({"name": "get_ticket", "args": {"ticket_id": 7}, "result": result})
            messages.append(types.Content(role="model", parts=[types.Part(text=f"step {i}")]))
            messages.append(types.Content(role="user", parts=[types.Part(text="tool result " + "x" * 500)]))

        compacted, summary = agent.compact_messages(
            messages,
            original_goal,
            original_ticket,
            observations,
            keep_recent=4,
        )

        self.assertLess(len(compacted), len(messages))
        self.assertIn("Triage ticket 7", compacted[0].parts[0].text)
        compacted_text = " ".join(
            part.text
            for content in compacted
            for part in content.parts
            if getattr(part, "text", None)
        )
        self.assertIn("Original ticket context", compacted_text)
        self.assertIn("Compacted context summary", summary)
        self.assertLess(len(summary), 3000)


if __name__ == "__main__":
    unittest.main()
