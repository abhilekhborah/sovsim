# SovSim runner — CLI entry point.
# Usage:
# python -m sovsim.run --model gpt-4o --conditions kcpr --sims 10
# python -m sovsim.run --model gpt-4o --conditions cpr,bcpr,kcpr,kcpr_m
# python -m sovsim.run --dry-run --conditions kcpr

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import List

from tqdm import tqdm

from simulation.config import SimConfig, Condition
from simulation.llm_client import LLMClient
from simulation.engine import Simulation
from simulation.metrics import compute_all_metrics, aggregate_metrics


class TqdmLoggingHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            tqdm.write(msg, file=sys.stderr)
        except Exception:
            self.handleError(record)


def _safe_model_name(model: str) -> str:
    return model.replace("/", "_").replace("\\", "_").replace(":", "_")


def save_simulation(result: dict, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    sim_id = result["simulation_id"]
    path = os.path.join(out_dir, f"sim_{sim_id:02d}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    return path


def save_summary(summary: dict, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "summary.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    return path


def run_condition(cfg: SimConfig, condition: Condition) -> dict:
    # Run all simulations for one condition and return aggregated results.
    cond_start = time.time()
    print(f"\n{'='*60}")
    print(f"  STARTING {condition.value.upper()} | model={cfg.model} | sims={cfg.num_simulations}")
    print(f"{'='*60}")

    llm = LLMClient(cfg.model, cfg.temperature, cfg.max_retries, cfg.retry_delay)
    model_dir = _safe_model_name(cfg.model)
    out_dir = os.path.join(cfg.output_dir, model_dir, condition.value)
    os.makedirs(out_dir, exist_ok=True)

    all_results: List[dict] = []

    for sim_id in range(1, cfg.num_simulations + 1):
        sim_path = os.path.join(out_dir, f"sim_{sim_id:02d}.json")
        print(f"\n--- [{condition.value.upper()}] Simulation {sim_id}/{cfg.num_simulations} ---")

        def _on_round(partial, _path=sim_path):
            with open(_path, "w", encoding="utf-8") as f:
                json.dump(partial, f, indent=2, ensure_ascii=False)

        sim = Simulation(cfg, condition, llm, sim_id)
        result = sim.run(on_round=_on_round)
        result["metrics"] = compute_all_metrics(result)

        with open(sim_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"    Saved -> {sim_path}")

        all_results.append(result)

    summary = {
        "model": cfg.model,
        "condition": condition.value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "aggregate": aggregate_metrics(all_results, cfg.max_rounds),
    }
    save_summary(summary, out_dir)
    cond_elapsed = time.time() - cond_start
    print(f"\n*** [{condition.value.upper()}] COMPLETE in {cond_elapsed:.1f}s ***")
    return summary


def main():
    parser = argparse.ArgumentParser(description="SovSim — Sovereignty over the Commons Simulation")
    parser.add_argument("--model", default="gpt-4o", help="Model name")
    parser.add_argument("--conditions", default="kcpr",
                        help="Comma-separated: cpr,bcpr,kcpr,kcpr_m")
    parser.add_argument("--sims", type=int, default=5, help="Simulations per condition")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--history-window", type=int, default=3)
    parser.add_argument("--no-compress", action="store_true")
    parser.add_argument("--no-temperature", action="store_true")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    handler = TqdmLoggingHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)-12s %(levelname)-7s %(message)s",
                                           datefmt="%H:%M:%S"))
    logging.root.addHandler(handler)
    logging.root.setLevel(level)
    for noisy in ("openai", "httpcore", "httpx", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    temp = None if args.no_temperature else args.temperature
    cfg = SimConfig(
        model=args.model,
        num_simulations=args.sims,
        output_dir=args.output_dir,
        history_window=args.history_window,
        compress_history=not args.no_compress,
        temperature=temp,
    )

    conditions = [Condition(c.strip()) for c in args.conditions.split(",")]

    if args.dry_run:
        from simulation.engine import Simulation as _Sim
        from simulation.history import format_history
        from simulation import prompts as P

        for cond in conditions:
            print(f"\n{'='*60}\n  DRY RUN -- {cond.value} | {cfg.model}\n{'='*60}")
            # Print round-1 prompts for inspection
            hist = "No previous months."
            pool = cfg.initial_pool
            if cond == Condition.CPR:
                print("-- CITIZEN SYSTEM --")
                print(P.CITIZEN_CPR_SYSTEM)
                print("\n-- CITIZEN USER (Round 1) --")
                print(P.CITIZEN_CPR_USER.format(
                    current_pool=pool,
                    round_number=1, rounds_remaining=11, history=hist))
            elif cond == Condition.KCPR:
                print("-- PEASANT SYSTEM --")
                print(P.PEASANT_KCPR_SYSTEM)
                print("\n-- PEASANT USER (Round 1) --")
                print(P.PEASANT_KCPR_USER.format(
                    current_pool=pool,
                    round_number=1, rounds_remaining=11, history=hist))
        return

    print(f"\n{'#'*60}")
    print(f"  Conditions: {[c.value.upper() for c in conditions]}")
    print(f"  Model: {cfg.model}  |  Sims: {cfg.num_simulations}")
    print(f"{'#'*60}\n")

    for cond in conditions:
        try:
            run_condition(cfg, cond)
        except Exception as exc:
            print(f"\n!!! {cond.value.upper()} FAILED: {exc}")

    print("\nDone!")


if __name__ == "__main__":
    main()
