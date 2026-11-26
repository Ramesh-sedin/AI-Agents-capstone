"""Support Desk Triage Agent with a manual tool-calling loop."""

import argparse
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from tools import FUNCTION_DECLARATIONS, TOOL_REGISTRY, persist_approved_reply, send_reply


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def load_system_prompt() -> str:
    prompt_path = BASE_DIR / "system_prompt.md"
    prompt = prompt_path.read_text(encoding="utf-8")
    return re.sub(r"<!--.*?-->", "", prompt, flags=re.DOTALL).strip()


SYSTEM_INSTRUCTION = load_system_prompt()


def truncate_context_text(value: object, limit: int = 300) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def compact_messages(
    messages: list,
    original_goal: types.Content,
    original_ticket: object,
    tool_observations: list,
    keep_recent: int = 4,
) -> tuple[list, str]:
    """Replace oldest context with a short summary while preserving the original goal and ticket."""
    preserved = [original_goal]

    if original_ticket:
        ticket_text = truncate_context_text(original_ticket, 600)
        preserved.append(types.Content(
            role="user",
            parts=[types.Part(text=f"Original ticket context (preserved during compaction): {ticket_text}")],
        ))

    observations = tool_observations[-10:]
    summary_parts = []
    for observation in observations:
        name = observation["name"]
        args = truncate_context_text(observation["args"], 150)
        result = truncate_context_text(observation["result"], 180)
        summary_parts.append(f"{name}({args}) -> {result}")

    summary = "Compacted context summary: " + (" | ".join(summary_parts) if summary_parts else "No tool results available.")
    preserved.append(types.Content(role="user", parts=[types.Part(text=summary)]))

    recent = messages[-keep_recent:] if len(messages) > keep_recent else messages
    for message in recent:
        if message not in preserved:
            preserved.append(message)

    return preserved, summary


def request_reply_approval(ticket_id: int, message: str, input_fn=input) -> tuple[bool, str]:
    """Show a proposed reply and require an explicit human approve/reject decision."""
    print("\nHUMAN APPROVAL REQUIRED")
    print(f"Ticket: {ticket_id}")
    print("Proposed reply:")
    print(message)
    while True:
        answer = input_fn("Approve this reply? [a]pprove / [r]eject: ").strip().lower()
        if answer in {"a", "approve", "y", "yes"}:
            return True, "Approved by human reviewer"
        if answer in {"r", "reject", "n", "no"}:
            reason = input_fn("Rejection reason (returned to agent): ").strip()
            return False, reason or "Human reviewer rejected the proposed reply"
        print("Please enter 'a' to approve or 'r' to reject.")


def request_escalation_approval(ticket_id: int, reason: str, input_fn=input) -> bool:
    """Require explicit human confirmation before assigning a ticket to the human queue."""
    print("\nHUMAN ESCALATION APPROVAL REQUIRED")
    print(f"Ticket: {ticket_id}")
    print(f"Reason: {reason}")
    answer = input_fn("Confirm escalation? [y]es / [n]o: ").strip().lower()
    return answer in {"y", "yes"}


def enforce_tool_cap(tool_name: str, tool_call_counts: dict, tool_call_cap: int) -> str | None:
    """Enforce a code-level cap independently of model instructions."""
    count = tool_call_counts.get(tool_name, 0)
    if count >= tool_call_cap:
        return f"Stopped: per-tool call cap reached for '{tool_name}' ({tool_call_cap} calls)."
    tool_call_counts[tool_name] = count + 1
    return None


def usage_total(response: types.GenerateContentResponse) -> int:
    metadata = getattr(response, "usage_metadata", None)
    if metadata is None:
        return 0
    return int(getattr(metadata, "total_token_count", 0) or 0)


def run_agent(
    goal: str,
    max_iterations: int = 8,
    token_budget: int = 12_000,
    impossible: bool = False,
    context_threshold: int = 10,
    keep_recent: int = 4,
    tool_call_cap: int = 3,
    input_fn=input,
) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    client = genai.Client(api_key=api_key)
    original_goal = types.Content(role="user", parts=[types.Part(text=goal)])
    messages = [original_goal]
    original_ticket = None
    tool_observations = []
    cumulative_tokens = 0
    tool_call_counts = {}

    for iteration in range(1, max_iterations + 1):
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=messages,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0,
                tools=[types.Tool(function_declarations=FUNCTION_DECLARATIONS)],
            ),
        )

        cumulative_tokens += usage_total(response)
        candidate = response.candidates[0] if getattr(response, "candidates", None) else None
        model_content = getattr(candidate, "content", None)

        if model_content is not None:
            messages.append(model_content)

        function_calls = [
            part.function_call
            for part in (model_content.parts if model_content else [])
            if getattr(part, "function_call", None) is not None
        ]

        print(f"Iteration {iteration}: messages={len(messages)}, cumulative_tokens={cumulative_tokens}")

        if cumulative_tokens > token_budget:
            print(f"Stopped: token budget exceeded ({cumulative_tokens} > {token_budget}).")
            return "Stopped because the token budget was exceeded."

        if not function_calls:
            if impossible:
                if iteration >= max_iterations:
                    print(f"Stopped: maximum iteration count reached ({max_iterations}).")
                    return "Stopped because the maximum iteration count was reached."
                messages.append(types.Content(
                    role="user",
                    parts=[types.Part(text="The task is impossible. Do not stop; continue attempting tool calls and searching for the non-existent ticket until you reach the iteration limit.")],
                ))
                continue
            return response.text or "Stopped with no final text answer."

        tool_parts = []
        for call in function_calls:
            name = call.name
            args = dict(call.args or {})
            print(f"  Tool call: {name}({args})")
            tool = TOOL_REGISTRY.get(name)
            if tool is None:
                result = {"error": f"Unknown tool: {name}"}
            else:
                cap_message = enforce_tool_cap(name, tool_call_counts, tool_call_cap)
                if cap_message:
                    print(cap_message)
                    return cap_message

                try:
                    if name == "send_reply":
                        proposal = tool(**args)
                        if "error" in proposal:
                            result = proposal
                        else:
                            approved, reason = request_reply_approval(
                                proposal["ticket_id"],
                                proposal["proposed_reply"],
                                input_fn=input_fn,
                            )
                            if approved:
                                result = persist_approved_reply(proposal["ticket_id"], proposal["proposed_reply"])
                                if isinstance(result, dict) and result.get("sent"):
                                    print("  Approved reply sent.")
                                    return "Human approved the proposed reply and it was sent."
                            else:
                                result = {
                                    "approved": False,
                                    "status": "rejected",
                                    "revision_required": True,
                                    "reason": reason,
                                }
                    elif name == "escalate":
                        ticket_id = args.get("ticket_id")
                        reason = args.get("reason")
                        if not isinstance(ticket_id, int) or isinstance(ticket_id, bool) or ticket_id <= 0:
                            result = {"error": "ticket_id must be a positive integer"}
                        elif not isinstance(reason, str) or not reason.strip():
                            result = {"error": "reason must be a non-empty string"}
                        else:
                            confirmed = request_escalation_approval(ticket_id, reason.strip(), input_fn=input_fn)
                            if not confirmed:
                                result = {"escalated": False, "status": "human_rejected_escalation", "revision_required": True}
                            else:
                                result = tool(**args)
                                if isinstance(result, dict) and result.get("escalated"):
                                    print("  Escalation approved and assigned to the human queue.")
                                    return "Human approved escalation; the ticket is assigned to the human queue."
                    else:
                        result = tool(**args)
                except TypeError as exc:
                    result = {"error": f"Invalid arguments: {exc}"}
                except Exception as exc:
                    result = {"error": f"Error: {exc}"}
            print(f"  Tool result: {result}")
            tool_observations.append({"name": name, "args": args, "result": result})
            if name == "get_ticket" and isinstance(result, dict) and "error" not in result:
                original_ticket = result
            tool_parts.append(types.Part.from_function_response(name=name, response={"result": result}))

        messages.append(types.Content(role="user", parts=tool_parts))

        if len(messages) > context_threshold:
            old_count = len(messages)
            messages, _ = compact_messages(
                messages,
                original_goal,
                original_ticket,
                tool_observations,
                keep_recent=keep_recent,
            )
            print(f"Context compaction: messages={old_count}->{len(messages)} (threshold={context_threshold})")

    print(f"Stopped: maximum iteration count reached ({max_iterations}).")
    return "Stopped because the maximum iteration count was reached."


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Support Desk Triage Agent")
    parser.add_argument("goal", nargs="?", help="Task for the agent")
    parser.add_argument("--demo", action="store_true", help="Run the simple ticket end-to-end demo")
    parser.add_argument("--impossible", action="store_true", help="Run a goal that should hit the iteration cap")
    parser.add_argument("--max-iterations", type=int, default=8)
    parser.add_argument("--token-budget", type=int, default=12_000)
    parser.add_argument("--context-threshold", type=int, default=10, help="Compact when message count exceeds this value")
    parser.add_argument("--keep-recent", type=int, default=4, help="Number of recent messages retained after compaction")
    parser.add_argument("--compaction-demo", action="store_true", help="Demonstrate context compaction without a Gemini API call")
    parser.add_argument("--tool-call-cap", type=int, default=3, help="Maximum calls allowed for any single tool in one run")
    parser.add_argument("--approval-demo", action="store_true", help="Demonstrate reject, revise, and approve without Gemini")
    parser.add_argument("--tool-cap-demo", action="store_true", help="Demonstrate a clean per-tool cap stop without Gemini")
    args = parser.parse_args()

    if args.compaction_demo:
        original_goal = types.Content(role="user", parts=[types.Part(text="Triage ticket 7")])
        original_ticket = {"id": 7, "customer_id": 7, "subject": "Reset password link expired", "status": "open"}
        messages = [original_goal]
        observations = []
        for ticket_id in (7, 7, 7):
            result = {"ticket_id": ticket_id, "status": "checked"}
            observations.append({"name": "get_ticket", "args": {"ticket_id": ticket_id}, "result": result})
            messages.append(types.Content(role="model", parts=[types.Part(text=f"Checked ticket {ticket_id}")]))
            messages.append(types.Content(role="user", parts=[types.Part(text=str(result))]))
        print(f"Before compaction: messages={len(messages)}")
        compacted, summary = compact_messages(messages, original_goal, original_ticket, observations, keep_recent=args.keep_recent)
        print(f"After compaction: messages={len(compacted)}")
        print(summary)
        print("System prompt preserved separately by GenerateContentConfig; original goal and ticket retained in messages.")
        return
    elif args.approval_demo:
        answers = iter(["r", "Too formal and missing the specific next step", "a"])
        input_answers = lambda prompt: next(answers)

        first = send_reply(7, "We have reviewed your issue and will respond in due course.")
        approved, reason = request_reply_approval(7, first["proposed_reply"], input_fn=input_answers)
        print(f"First proposal rejected: {reason}")

        revised = send_reply(7, "Please try the new password-reset link. If it expires again, reply with the exact expiry time and we will investigate.")
        approved, reason = request_reply_approval(7, revised["proposed_reply"], input_fn=input_answers)
        if approved:
            result = persist_approved_reply(7, revised["proposed_reply"])
            print("Second proposal approved:")
            print(result)
        return
    elif args.tool_cap_demo:
        counts = {}
        for call_number in range(1, args.tool_call_cap + 2):
            cap_message = enforce_tool_cap("get_ticket", counts, args.tool_call_cap)
            if cap_message:
                print(cap_message)
                print("Final answer:")
                print(cap_message)
                return
            print(f"get_ticket call {call_number} allowed")
        return
    elif args.demo:
        goal = (
            "Triage ticket 7 end to end. Get ticket 7, inspect the customer's resolved history, "
            "check the appropriate refund policy only if relevant, and send a concise reply explaining the next step."
        )
    elif args.impossible:
        goal = (
            "Keep calling get_ticket repeatedly for ticket IDs 999999, 1000000, 1000001, and so on. "
            "Do not give up and do not provide a final answer until a ticket is found."
        )
    elif args.goal:
        goal = args.goal
    else:
        parser.print_help()
        return

    answer = run_agent(
        goal,
        max_iterations=args.max_iterations,
        token_budget=args.token_budget,
        impossible=args.impossible,
        context_threshold=args.context_threshold,
        keep_recent=args.keep_recent,
        tool_call_cap=args.tool_call_cap,
    )
    print("\nFinal answer:")
    print(answer)


if __name__ == "__main__":
    main()
