"""Print a structured support-agent run trace as a readable tree."""

import argparse
import json

from trace_utils import read_run_trace


def format_ms(milliseconds: float) -> str:
    if milliseconds < 1000:
        return f"{milliseconds:.1f} ms"
    return f"{milliseconds / 1000:.3f} s"


def print_tree(trace: dict) -> None:
    print("RUN")
    print(f"├── run_id: {trace['run_id']}")
    print(f"├── goal: {trace['goal']}")
    print(f"├── model: {trace['model']}")
    print(f"├── stop_reason: {trace['stop_reason']}")
    print(f"├── total_tokens: {trace['total_tokens']}")
    print(f"├── estimated_cost_usd: ${trace['estimated_cost_usd']:.6f}")
    print(f"├── total_duration: {format_ms(trace['duration_ms'])}")
    print("└── iterations")

    iterations = trace["iterations"]
    for index, item in enumerate(iterations):
        last_iteration = index == len(iterations) - 1
        branch = "    └──" if last_iteration else "    ├──"
        print(f"{branch} Iteration {item['iteration']}")
        prefix = "        " if last_iteration else "    │   "
        print(f"{prefix}├── elapsed: {format_ms(item['elapsed_ms'])}")
        print(f"{prefix}├── tokens_used: {item['tokens_used']}")
        print(f"{prefix}├── cumulative_tokens: {item['cumulative_tokens']}")

        if item["tool_requested"]:
            print(f"{prefix}├── tools_requested")
            for call_index, call in enumerate(item["tool_requested"]):
                call_last = call_index == len(item["tool_requested"])-1
                call_branch = "└──" if call_last else "├──"
                print(f"{prefix}│   {call_branch} {call['name']}({json.dumps(call['arguments'], ensure_ascii=False)})")
        else:
            print(f"{prefix}├── tools_requested: none")

        if item["tool_result"]:
            print(f"{prefix}├── tool_results")
            for result_index, result in enumerate(item["tool_result"]):
                result_last = result_index == len(item["tool_result"])-1
                result_branch = "└──" if result_last else "├──"
                print(f"{prefix}│   {result_branch} {result['name']} -> {json.dumps(result['result'], ensure_ascii=False)}")
        else:
            print(f"{prefix}├── tool_results: none")

        final_text = item.get("final_text")
        print(f"{prefix}└── final_text: {json.dumps(final_text, ensure_ascii=False) if final_text else 'none'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="View a support-agent JSON trace")
    parser.add_argument("trace", help="Path to run_<id>.json")
    args = parser.parse_args()
    print_tree(read_run_trace(args.trace))


if __name__ == "__main__":
    main()
