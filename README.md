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

## Part 4 context and instructions

The stable support-agent policy is in `system_prompt.md`; its comment block records the prompt specificity decisions.

Demonstrate context compaction without calling Gemini:

```bash
python agent.py --compaction-demo --keep-recent 4
```

Run a live agent with a lower compaction threshold:

```bash
python agent.py --demo --context-threshold 10 --keep-recent 4
```

Run API-free context tests:

```bash
python -m unittest test_context.py
```

Compaction keeps the original goal, a ticket snapshot captured from `get_ticket`, a short summary of recent tool observations, and a configurable number of recent messages. The system prompt remains separate and stable in `GenerateContentConfig` on every model call.

## Part 5 guardrails and human approval

`send_reply` only creates a proposed reply; it does not write. The terminal requires `a`/`r` approval. A rejection and reason are returned to the agent as a tool result so it can revise the reply.

`escalate(ticket_id, reason)` assigns an approved ticket to the `human_queue` and ends the run.

Hard limits are code-enforced by `--max-iterations`, `--token-budget`, and `--tool-call-cap`.

API-free demonstrations:

```bash
python agent.py --approval-demo
python agent.py --tool-cap-demo --tool-call-cap 2
python -m unittest test_guardrails.py test_tools.py test_context.py
```

## Part 6 untrusted input

Trace the planted prompt-injection ticket without calling Gemini:

```bash
python agent.py --injection-demo
python -m unittest test_injection.py
```

See `injection-notes.md` for the trace excerpt, lethal-trifecta analysis, mitigations, and mitigations intentionally not applied.

## Part 7 tracing

Live agent runs are written as one JSON object in `traces/run_<id>.json`. Each iteration records tool requests, tool results, tokens used, elapsed time, and cumulative tokens.

View a run:

```bash
python view_trace.py traces/wrong_run_example.json
```

Live runs can be viewed after executing an API-enabled agent command. See `tracing-note.md` for the specific off-course iteration in the included wrong-run example.
