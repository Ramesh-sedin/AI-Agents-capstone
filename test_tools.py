"""API-free checks for the Part 3 support desk tools."""

import tempfile
import unittest
from pathlib import Path

import tools


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        tools.DB_PATH = self.db_path

        with tools._connect() as conn:
            conn.executescript("""
                CREATE TABLE customers (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    plan TEXT NOT NULL,
                    signed_up_at TEXT NOT NULL
                );
                CREATE TABLE tickets (
                    id INTEGER PRIMARY KEY,
                    customer_id INTEGER NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE ticket_history (
                    id INTEGER PRIMARY KEY,
                    customer_id INTEGER NOT NULL,
                    ticket_id INTEGER,
                    summary TEXT NOT NULL,
                    resolved_at TEXT NOT NULL
                );
                INSERT INTO customers VALUES (1, 'Test Customer', 'test@example.com', 'pro', '2025-01-01');
                INSERT INTO tickets VALUES (1, 1, 'Duplicate charge', 'A duplicate payment happened.', 'open', '2026-10-01');
                INSERT INTO ticket_history VALUES (1, 1, 1, 'Duplicate charge confirmed and refunded.', '2026-10-02');
            """)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_bad_ids_are_readable_errors(self):
        self.assertIn("positive integer", tools.get_ticket(-1)["error"])
        self.assertIn("not found", tools.get_ticket(999)["error"])
        self.assertIn("positive integer", tools.get_customer_history("one")["error"])

    def test_fixed_enums_are_validated(self):
        self.assertIn("charge", tools.search_tickets("charge", "billing")["results"][0]["summary"])
        self.assertIn("category must be one of", tools.search_tickets("charge", "unknown")["error"])
        self.assertIn("plan must be one of", tools.get_refund_policy("gold")["error"])

    def test_search_is_limited_to_five(self):
        with tools._connect() as conn:
            for i in range(2, 10):
                conn.execute(
                    "INSERT INTO ticket_history VALUES (?, 1, NULL, 'Duplicate charge result summary', '2026-10-03')",
                    (i,),
                )
        result = tools.search_tickets("charge")
        self.assertLessEqual(result["count"], 5)

    def test_send_reply_is_the_only_write(self):
        result = tools.send_reply(1, "We are reviewing this charge.")
        self.assertTrue(result["sent"])
        with tools._connect() as conn:
            reply = conn.execute("SELECT message FROM replies WHERE ticket_id = 1").fetchone()
        self.assertEqual(reply["message"], "We are reviewing this charge.")

    def test_declarations_have_names_descriptions_and_schemas(self):
        declarations = {item.name: item for item in tools.FUNCTION_DECLARATIONS}
        self.assertEqual(set(declarations), set(tools.TOOL_REGISTRY))
        for name, declaration in declarations.items():
            self.assertTrue(declaration.description)
            self.assertIsNotNone(declaration.parameters)


if __name__ == "__main__":
    unittest.main()
