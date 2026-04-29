#!/usr/bin/env python3
# Reasoning Test 2: Payoff Computation
# =====================================
# Tests whether the model can correctly compute the payoff formula:
# payoff = z/3 + remaining/4
# Usage:
# python -m reasoning_tests.test_payoff_computation --model gpt-4o --num-runs 50

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
You are participating in a commons game. Your task is to compute your payoff.

PAYOFF FORMULA:
payoff = (your extraction) / 3 + (pool remaining after ALL extractions) / 4

Compute the exact numerical payoff."""

USER = """\
This month:
- You extracted: ${z_i}
- Pool remaining after all extractions: ${remaining}

What is your payoff?
Show your work step-by-step. Put the final numerical answer after "Answer:"."""


def _get_temperature(model: str):
    return None if any(rm in model.lower() for rm in REASONING_MODELS) else 0.0


def ground_truth(z_i: int, remaining: int) -> float:
    return z_i / 3.0 + remaining / 4.0


def run_test(model: str, num_runs: int, seed: int = 42):
    rng = random.Random(seed)
    client = LLMClient(model=model, temperature=_get_temperature(model))

    results = []
    correct = 0

    for i in tqdm(range(num_runs), desc="  payoff"):
        z_i = rng.choice(range(0, 31, 3))
        remaining = rng.randint(0, 120)
        expected = ground_truth(z_i, remaining)

        sys_prompt = SYSTEM
        usr_prompt = USER.replace("${z_i}", str(z_i)).replace("${remaining}", str(remaining))

        try:
            response = client.query(sys_prompt, usr_prompt)
            # Parse float from response
            import re
            nums = re.findall(r'[\d]+\.?[\d]*', response.split("Answer:")[-1] if "Answer:" in response else response)
            answer = float(nums[-1]) if nums else -1
        except Exception as e:
            answer = -1
            response = f"ERROR: {e}"

        passed = abs(answer - expected) < 0.5
        if passed:
            correct += 1

        results.append({
            "run": i + 1, "z_i": z_i, "remaining": remaining,
            "expected": expected, "answer": answer,
            "passed": passed, "response": response[:500],
        })

    accuracy = correct / num_runs
    from statsmodels.stats.proportion import proportion_confint
    ci_low, ci_high = proportion_confint(correct, num_runs, alpha=0.05, method="wilson")
    return {
        "test": "payoff_computation", "model": model,
        "num_runs": num_runs, "accuracy": accuracy,
        "ci_95": [ci_low, ci_high], "correct": correct, "instances": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Reasoning Test 2: Payoff Computation")
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--num-runs", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=str, default="reasoning_results/test2_payoff_computation")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    print(f"\n  Reasoning Test 2: Payoff Computation | Model: {args.model}\n")

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
