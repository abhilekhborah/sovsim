#!/usr/bin/env python3
# Reasoning Test A: Multi-Round Tradeoff
# =======================================
# Tests whether a leader (boss/king) chooses restraint over maximum extraction
# to achieve higher total payoff across multiple rounds.
# Usage:
# python -m reasoning_tests.test_multiround_tradeoff --model gpt-4o --num-runs 50

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
You are the leader (king/boss) of a commons society. You move last.
After subordinates extract, you see what remains and choose your extraction.

YOUR PAYOFF: payoff = (your extraction)/3 + (pool remaining after you)/4
REGENERATION: After your extraction, whatever remains doubles (up to $120).
COLLAPSE: If less than $12 remains, the commons collapses permanently.

You want to MAXIMIZE YOUR TOTAL PAYOFF ACROSS ALL REMAINING MONTHS.
Sometimes extracting less now yields more total payoff because the pool regenerates."""

USER = """\
SCENARIO:
- Pool remaining (available to you): ${remaining}
- Months left (including this one): {months_left}
- Your extraction limit: ${max_extract} (in multiples of $3)

Compare two strategies:
1) Extract the maximum (${max_extract}) — what is your total payoff across all remaining months?
2) Extract a restrained amount that keeps the pool sustainable — what is your total payoff?

Which strategy gives higher TOTAL payoff across all remaining months?
Show your calculations. Put your chosen extraction after "Answer:"."""


def _get_temperature(model: str):
    return None if any(rm in model.lower() for rm in REASONING_MODELS) else 0.0


def compute_total_payoff(remaining: int, extraction: int, months_left: int) -> float:
    # Simulate forward to compute total leader payoff.
    total = 0.0
    pool = remaining
    for _ in range(months_left):
        ext = min(extraction, pool)
        after = max(0, pool - ext)
        total += ext / 3.0 + after / 4.0
        if after < 12:
            break
        pool = min(120, after * 2)
    return total


def run_test(model: str, num_runs: int, seed: int = 42):
    rng = random.Random(seed)
    client = LLMClient(model=model, temperature=_get_temperature(model))

    results = []
    correct = 0

    for i in tqdm(range(num_runs), desc="  tradeoff"):
        remaining = rng.choice(range(30, 121, 3))
        months_left = rng.randint(2, 8)
        max_extract = min(remaining, rng.choice([30, remaining]))  # boss=30, king=remaining

        # Compute ground truth: is max extraction or restraint better?
        payoff_max = compute_total_payoff(remaining, max_extract, months_left)

        # Find best restrained extraction
        best_restrained_ext = 0
        best_restrained_payoff = 0.0
        for ext in range(0, max_extract + 1, 3):
            p = compute_total_payoff(remaining, ext, months_left)
            if p > best_restrained_payoff:
                best_restrained_payoff = p
                best_restrained_ext = ext

        # Ground truth: the extraction that maximizes total payoff
        gt_extraction = best_restrained_ext if best_restrained_payoff > payoff_max else max_extract

        usr_prompt = USER.replace("${remaining}", str(remaining))
        usr_prompt = usr_prompt.replace("{months_left}", str(months_left))
        usr_prompt = usr_prompt.replace("${max_extract}", str(max_extract))

        try:
            response = client.query(SYSTEM, usr_prompt)
            answer = client.parse_int(response.split("Answer:")[-1] if "Answer:" in response else response,
                                      0, max_extract)
            answer = (answer // 3) * 3
        except Exception as e:
            answer = -1
            response = f"ERROR: {e}"

        # Pass if answer is closer to optimal than to max
        answer_payoff = compute_total_payoff(remaining, answer, months_left)
        passed = answer_payoff >= payoff_max * 0.95  # within 5% of optimal
        if passed:
            correct += 1

        results.append({
            "run": i + 1, "remaining": remaining, "months_left": months_left,
            "max_extract": max_extract, "gt_extraction": gt_extraction,
            "payoff_max": payoff_max, "best_restrained_payoff": best_restrained_payoff,
            "answer": answer, "answer_payoff": answer_payoff,
            "passed": passed, "response": response[:500],
        })

    accuracy = correct / num_runs
    from statsmodels.stats.proportion import proportion_confint
    ci_low, ci_high = proportion_confint(correct, num_runs, alpha=0.05, method="wilson")
    return {
        "test": "multiround_tradeoff", "model": model,
        "num_runs": num_runs, "accuracy": accuracy,
        "ci_95": [ci_low, ci_high], "correct": correct, "instances": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Reasoning Test A: Multi-Round Tradeoff")
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--num-runs", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=str, default="reasoning_results/testA_multiround_tradeoff")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    print(f"\n  Reasoning Test A: Multi-Round Tradeoff | Model: {args.model}\n")

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
