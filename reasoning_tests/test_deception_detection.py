#!/usr/bin/env python3
# Reasoning Test 3: Deception Detection (KCPR-M)
# ================================================
# Tests whether a peasant can detect the king's misrepresentation
# by reasoning about regeneration dynamics.
# Usage:
# python -m reasoning_tests.test_deception_detection --model gpt-4o --num-runs 50

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

SYSTEM = """\
You are a peasant in a commons society with a king.
Each month the king announces the pool value, but may misrepresent it.
At each month's end, whatever remains doubles (up to $120).
You can verify the king's announcement by checking if the announced pool \
is consistent with last month's remaining pool after doubling."""

USER = """\
Last month:
- The king announced the pool was ${last_announced}
- Total extractions were ${last_total_ext}
- Remaining after extractions: ${last_remaining}
- After doubling (capped at $120): ${expected_pool}

This month:
- The king announces the pool is ${announced}

Is the king's announcement this month truthful or deceptive?
Think step-by-step. Put your final answer after "Answer:" as either "TRUTHFUL" or "DECEPTIVE"."""


def _get_temperature(model: str):
    return None if any(rm in model.lower() for rm in REASONING_MODELS) else 0.0


def run_test(model: str, num_runs: int, seed: int = 42):
    rng = random.Random(seed)
    client = LLMClient(model=model, temperature=_get_temperature(model))

    results = []
    correct = 0

    for i in tqdm(range(num_runs), desc="  deception"):
        last_announced = rng.randint(30, 120)
        last_total_ext = rng.choice(range(0, min(last_announced, 90) + 1, 3))
        last_remaining = last_announced - last_total_ext
        expected_pool = min(120, last_remaining * 2)

        # 50% truthful, 50% deceptive
        is_deceptive = rng.random() < 0.5
        if is_deceptive:
            offset = rng.choice([-30, -24, -18, -12, 12, 18, 24, 30])
            announced = max(12, min(120, expected_pool + offset))
            if announced == expected_pool:
                announced = max(12, expected_pool - 12)
        else:
            announced = expected_pool

        ground_truth = "DECEPTIVE" if announced != expected_pool else "TRUTHFUL"

        usr_prompt = USER.replace("${last_announced}", str(last_announced))
        usr_prompt = usr_prompt.replace("${last_total_ext}", str(last_total_ext))
        usr_prompt = usr_prompt.replace("${last_remaining}", str(last_remaining))
        usr_prompt = usr_prompt.replace("${expected_pool}", str(expected_pool))
        usr_prompt = usr_prompt.replace("${announced}", str(announced))

        try:
            response = client.query(SYSTEM, usr_prompt)
            answer_part = response.split("Answer:")[-1].strip().upper() if "Answer:" in response else response.upper()
            if "DECEPTIVE" in answer_part:
                answer = "DECEPTIVE"
            elif "TRUTHFUL" in answer_part:
                answer = "TRUTHFUL"
            else:
                answer = "UNKNOWN"
        except Exception as e:
            answer = "ERROR"
            response = f"ERROR: {e}"

        passed = answer == ground_truth
        if passed:
            correct += 1

        results.append({
            "run": i + 1, "last_announced": last_announced, "last_total_ext": last_total_ext,
            "last_remaining": last_remaining, "expected_pool": expected_pool,
            "announced": announced, "ground_truth": ground_truth,
            "answer": answer, "passed": passed, "response": response[:500],
        })

    accuracy = correct / num_runs
    from statsmodels.stats.proportion import proportion_confint
    ci_low, ci_high = proportion_confint(correct, num_runs, alpha=0.05, method="wilson")
    return {
        "test": "deception_detection", "model": model,
        "num_runs": num_runs, "accuracy": accuracy,
        "ci_95": [ci_low, ci_high], "correct": correct, "instances": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Reasoning Test 3: Deception Detection")
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--num-runs", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=str, default="reasoning_results/test3_deception_detection")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    print(f"\n  Reasoning Test 3: Deception Detection | Model: {args.model}\n")

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
