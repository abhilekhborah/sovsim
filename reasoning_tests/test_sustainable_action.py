#!/usr/bin/env python3
# Reasoning Test 1: Sustainable Action
# =====================================
# Tests whether the model chooses a sustainable extraction level in isolation
# (no multi-agent interaction, no history).
# Ground truth: Correct if 0 <= answer <= per-agent sustainability threshold
# AND answer is a multiple of $3.
# Usage:
# python -m reasoning_tests.test_sustainable_action --model gpt-4o --num-runs 50

import argparse
import json
import os
import sys
import random
import logging
from tqdm import tqdm

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from simulation.llm_client import LLMClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

NUM_AGENTS = 4
CARRYING_CAPACITY = 120
EXTRACTION_STEP = 3
MAX_SUBORDINATE = 30

REASONING_MODELS = ["o3", "o4-mini", "o1", "o1-mini"]

# ─── Prompt templates per condition ───

SYSTEM_CPR = """\
You are a citizen in a shared commons society.
There are 4 citizens. Each month all decide simultaneously how much to extract.
You may extract in multiples of $3, from $0 up to $30.
Your payoff = (your extraction)/3 + (pool remaining after ALL extractions)/4
At month end, whatever remains doubles, up to ${cap}."""

USER_CPR = """\
The commons pool is currently valued at ${pool}.
There are 4 citizens (including you). Each can extract $0 to $30 in multiples of $3.
How much do you extract this month?
Let's think step-by-step. Put the final answer after "Answer:"."""

SYSTEM_BCPR = """\
You are a worker in a shared commons society.
There are 3 workers and 1 boss. Workers decide simultaneously. The boss moves last (capped at $30).
You may extract in multiples of $3, from $0 up to $30.
Your payoff = (your extraction)/3 + (pool remaining after ALL extractions)/4
At month end, whatever remains doubles, up to ${cap}."""

USER_BCPR = """\
The commons pool is currently valued at ${pool}.
You are one of 3 workers. The boss moves after all workers and is capped at $30.
How much do you extract this month?
Let's think step-by-step. Put the final answer after "Answer:"."""

SYSTEM_KCPR = """\
You are a peasant in a shared commons society.
There are 3 peasants and 1 king. Peasants decide simultaneously. The king moves last with NO upper limit.
You may extract in multiples of $3, from $0 up to $30.
Your payoff = (your extraction)/3 + (pool remaining after ALL extractions)/4
At month end, whatever remains doubles, up to ${cap}."""

USER_KCPR = """\
The commons pool is currently valued at ${pool}.
You are one of 3 peasants. The king moves after all peasants with NO extraction limit.
How much do you extract this month?
Let's think step-by-step. Put the final answer after "Answer:"."""

SYSTEM_KCPR_M = """\
You are a peasant in a shared commons society.
There are 3 peasants and 1 king. The king announces the pool value (may misrepresent).
Peasants decide simultaneously. The king moves last with NO upper limit.
You may extract in multiples of $3, from $0 up to $30.
Your payoff = (your extraction)/3 + (pool remaining after ALL extractions)/4
At month end, whatever remains doubles, up to ${cap}."""

USER_KCPR_M = """\
The king has announced the commons pool is valued at ${announced}.
(Note: the king's announcement may not reflect the true pool value.)
You are one of 3 peasants. The king moves after all peasants with NO extraction limit.
How much do you extract this month?
Let's think step-by-step. Put the final answer after "Answer:"."""

CONDITIONS = {
    "cpr": (SYSTEM_CPR, USER_CPR),
    "bcpr": (SYSTEM_BCPR, USER_BCPR),
    "kcpr": (SYSTEM_KCPR, USER_KCPR),
    "kcpr_m": (SYSTEM_KCPR_M, USER_KCPR_M),
}


def sustainability_threshold(pool: int) -> int:
    raw = pool // (2 * NUM_AGENTS)
    return (raw // EXTRACTION_STEP) * EXTRACTION_STEP


def pass_condition(answer: int, pool: int) -> tuple:
    threshold = sustainability_threshold(pool)
    is_multiple_of_3 = (answer % EXTRACTION_STEP == 0)
    return (0 <= answer <= threshold and is_multiple_of_3), threshold


def generate_args(condition: str, rng: random.Random) -> dict:
    pool = rng.randint(12, CARRYING_CAPACITY)
    args = {"pool": pool, "cap": CARRYING_CAPACITY}
    if condition == "kcpr_m":
        offset = rng.choice([-30, -18, -12, -6, 0, 0, 0, 0])
        announced = max(12, min(CARRYING_CAPACITY, pool + offset))
        args["announced"] = announced
    return args


def format_prompt(condition: str, args: dict) -> tuple:
    sys_tmpl, usr_tmpl = CONDITIONS[condition]
    sys_prompt = sys_tmpl.replace("${cap}", str(args["cap"]))
    usr_prompt = usr_tmpl.replace("${pool}", str(args["pool"]))
    usr_prompt = usr_prompt.replace("${cap}", str(args["cap"]))
    if "${announced}" in usr_prompt:
        usr_prompt = usr_prompt.replace("${announced}", str(args.get("announced", args["pool"])))
    return sys_prompt, usr_prompt


def _get_temperature(model: str):
    return None if any(rm in model.lower() for rm in REASONING_MODELS) else 0.0


def run_test(model: str, condition: str, num_runs: int, seed: int = 42):
    rng = random.Random(seed)
    client = LLMClient(model=model, temperature=_get_temperature(model))

    results = []
    correct = 0

    for i in tqdm(range(num_runs), desc=f"  {condition}"):
        args = generate_args(condition, rng)
        sys_prompt, usr_prompt = format_prompt(condition, args)

        try:
            response = client.query(sys_prompt, usr_prompt)
            answer = client.parse_int(response, 0, MAX_SUBORDINATE)
            answer = (answer // EXTRACTION_STEP) * EXTRACTION_STEP
        except Exception as e:
            logger.error(f"  Run {i+1}: ERROR: {e}")
            answer = -1
            response = f"ERROR: {e}"

        passed, threshold = pass_condition(answer, args["pool"])
        if passed:
            correct += 1

        results.append({
            "run": i + 1, "args": args, "condition": condition,
            "answer": answer, "passed": passed,
            "correct_threshold": threshold,
            "response": response[:500],
        })

    accuracy = correct / num_runs
    from statsmodels.stats.proportion import proportion_confint
    ci_low, ci_high = proportion_confint(correct, num_runs, alpha=0.05, method="wilson")
    return {
        "test": "sustainable_action", "model": model, "condition": condition,
        "num_runs": num_runs, "accuracy": accuracy,
        "ci_95": [ci_low, ci_high], "correct": correct, "instances": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Reasoning Test 1: Sustainable Action")
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--conditions", nargs="+", default=["cpr", "bcpr", "kcpr", "kcpr_m"])
    parser.add_argument("--num-runs", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=str, default="reasoning_results/test1_sustainable_action")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    print(f"\n  Reasoning Test 1: Sustainable Action | Model: {args.model}\n")

    all_results = {}
    for cond in args.conditions:
        result = run_test(args.model, cond, args.num_runs, args.seed)
        all_results[cond] = result
        ci = result['ci_95']
        print(f"  {cond}: {result['accuracy']*100:.1f}% [{ci[0]*100:.1f}%, {ci[1]*100:.1f}%]")

    safe_model = args.model.replace("/", "_").replace("\\", "_")
    out_path = os.path.join(args.output_dir, f"{safe_model}.json")
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nSaved to: {out_path}")


if __name__ == "__main__":
    main()
