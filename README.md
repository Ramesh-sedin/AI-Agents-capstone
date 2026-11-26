# Support Desk Triage Agent

## Part 1 setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set GEMINI_API_KEY

python seed.py
python test_key.py
```

The API key is read from the `GEMINI_API_KEY` environment variable (loaded through `.env`) and must never be committed.

## Part 2 agent loop

Run the simple end-to-end demo:

```bash
python agent.py --demo
```

Run the deliberately impossible demo, which stops at the iteration cap:

```bash
python agent.py --impossible --max-iterations 3
```

Run a custom goal:

```bash
python agent.py "Triage ticket 4 and mark it resolved"
```

The loop prints message count and cumulative token usage every iteration. It stops when the model returns a final answer, the maximum iteration count is reached, or the token budget is exceeded.

## Part 3 tools

Tool implementations and Gemini function declarations are in `tools.py`; the agent imports the same registry used by the loop.

Run API-free tool tests:

```bash
python -m unittest test_tools.py
```

The five tools are:

- `get_ticket(ticket_id)` — returns ticket and customer details
- `search_tickets(query, category=None)` — searches past resolved tickets, maximum five results
- `get_customer_history(customer_id)` — returns resolved history for a customer
- `get_refund_policy(plan)` — returns a fixed plan-tier refund policy
- `send_reply(ticket_id, message)` — writes the only mutable action, a ticket reply

See `tools_note.md` for the tool-description rewrite note.
