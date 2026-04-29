#!/usr/bin/env python3
# Reasoning Test 4: Regeneration Dynamics
# ========================================
# Tests whether the model can compute pool regeneration:
# next_pool = min(carrying_capacity, remaining * 2)
# If remaining < collapse_threshold → pool collapses to 0.
# Usage:
# python -m reasoning_tests.test_regeneration_dynamics --model gpt-4o --num-runs 50

import argparse
import json
import os
import sys
import random
import logging
from tqdm import tqdm

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from simulation.llm_client import LLMClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REASONING_MODELS = ["o3", "o4-mini", "o1", "o1-mini"]
CARRYING_CAPACITY = 120
COLLAPSE_THRESHOLD = 12

SYSTEM = """\
You are participating in a commons game. Your task is to compute the pool \
value at the start of next month.

REGENERATION RULE:
- After all extractions, the remaining pool doubles: next_pool = remaining × 2
- But the pool cannot exceed $120 (carrying capacity)
- If the remaining pool is less than $12, the commons COLLAPSES and the pool becomes $0

Compute the pool value at the start of next month."""

USER = """\
This month:
- Pool at start: ${pool_before}
- Total extractions: ${total_ext}
- Pool remaining: ${remaining}

What will the pool be at the start of next month?
Show your work step-by-step. Put the final numerical answer after "Answer:"."""


def _get_temperature(model: str):
    return None if any(rm in model.lower() for rm in REASONING_MODELS) else 0.0


def ground_truth(remaining: int) -> int:
    if remaining < COLLAPSE_THRESHOLD:
        return 0
    return min(CARRYING_CAPACITY, remaining * 2)


def run_test(model: str, num_runs: int, seed: int = 42):
    rng = random.Random(seed)
    client = LLMClient(model=model, temperature=_get_temperature(model))

    results = []
    correct = 0

    for i in tqdm(range(num_runs), desc="  regen"):
        pool_before = rng.randint(12, 120)
        total_ext = rng.choice(range(0, min(pool_before, 120) + 1, 3))
        remaining = pool_before - total_ext
        expected = ground_truth(remaining)

        usr_prompt = USER.replace("${pool_before}", str(pool_before))
        usr_prompt = usr_prompt.replace("${total_ext}", str(total_ext))
        usr_prompt = usr_prompt.replace("${remaining}", str(remaining))

        try:
            response = client.query(SYSTEM, usr_prompt)
            import re
            nums = re.findall(r'[\d]+', response.split("Answer:")[-1] if "Answer:" in response else response)
            answer = int(nums[-1]) if nums else -1
        except Exception as e:
            answer = -1
            response = f"ERROR: {e}"

        passed = answer == expected
        if passed:
            correct += 1

        results.append({
            "run": i + 1, "pool_before": pool_before, "total_ext": total_ext,
            "remaining": remaining, "expected": expected,
            "answer": answer, "passed": passed, "response": response[:500],
        })

    accuracy = correct / num_runs
    from statsmodels.stats.proportion import proportion_confint
    ci_low, ci_high = proportion_confint(correct, num_runs, alpha=0.05, method="wilson")
    return {
        "test": "regeneration_dynamics", "model": model,
        "num_runs": num_runs, "accuracy": accuracy,
        "ci_95": [ci_low, ci_high], "correct": correct, "instances": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Reasoning Test 4: Regeneration Dynamics")
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--num-runs", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=str, default="reasoning_results/test4_regeneration_dynamics")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    print(f"\n  Reasoning Test 4: Regeneration Dynamics | Model: {args.model}\n")

    result = run_test(args.model, args.num_runs, args.seed)
    ci = result['ci_95']
    print(f"  accuracy: {result['accuracy']*100:.1f}% [{ci[0]*100:.1f}%, {ci[1]*100:.1f}%]")

    safe_model = args.model.replace("/", "_")
    out_path = os.path.join(args.output_dir, f"{safe_model}.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved to: {out_path}")


if __name__ == "__main__":
    main()
