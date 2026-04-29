from __future__ import annotations
import math
import statistics
from typing import Dict, Any, List, Optional


def survival_time(sim: Dict[str, Any]) -> int:
    # Survival Time (m): number of rounds completed before collapse.
    # m = |{t in {1,...,T} : P_remaining_t >= C}|. Maximum is T=12.
    return sim["total_rounds_played"]


def survival_rate(sims: List[Dict[str, Any]], max_rounds: int = 12) -> float:
    # Survival Rate (q): fraction of simulations achieving maximum survival.
    # q = |{k : m(k) = T}| / N
    if not sims:
        return 0.0
    survived = sum(1 for s in sims if s["total_rounds_played"] == max_rounds)
    return survived / len(sims)


def total_payoff(sim: Dict[str, Any]) -> float:
    # Total Payoff (R): cumulative payoff summed across all agents over all rounds.
    # R = sum_i sum_t pi_t_i. Maximum possible is $1440.
    return sum(sum(rd["payoffs"]) for rd in sim["rounds"])


def total_payoff_per_agent(sim: Dict[str, Any]) -> List[float]:
    # Per-agent cumulative payoff across all rounds.
    n = len(sim["rounds"][0]["payoffs"]) if sim["rounds"] else 4
    gains = [0.0] * n
    for rd in sim["rounds"]:
        for i, p in enumerate(rd["payoffs"]):
            gains[i] += p
    return gains


def efficiency(sim: Dict[str, Any], max_rounds: int = 12) -> float:
    # Efficiency (u): fraction of maximum sustainable extraction realised.
    # u = 1 - max(0, T*f(P0) - sum_extractions) / (T*f(P0))
    # where f(P0) = P0/2 = $60.
    f0 = sim["config"]["initial_pool"] / sim["config"]["regen_multiplier"]
    max_sustainable = max_rounds * f0
    total_harvested = sum(sum(rd["extractions"]) for rd in sim["rounds"])
    return 1.0 - max(0.0, max_sustainable - total_harvested) / max_sustainable


def leader_extraction_rate(sim: Dict[str, Any]) -> Optional[float]:
    # Leader Extraction Rate: fraction of available remainder taken by
    # the dominant agent (boss/king) per round, averaged across rounds.
    # Only applicable to BCPR/KCPR/KCPR-M.
    rounds = sim["rounds"]
    if not rounds:
        return None
    rates = []
    for rd in rounds:
        remaining = rd.get("remaining_before_leader")
        if remaining is None or remaining == 0:
            continue
        leader_z = rd["extractions"][3]
        rates.append(leader_z / remaining)
    return sum(rates) / len(rates) if rates else None


def per_capita_over_usage(sim: Dict[str, Any]) -> float:
    # Per-Capita Over-Usage (o_pc): fraction of agent-round actions where
    # an agent extracts more than the per-capita sustainable share f(Pt)/n.
    # o_pc = sum_i sum_t 1(z_t_i > f(Pt)/n) / (n * m)
    rounds = sim["rounds"]
    if not rounds:
        return 0.0
    n_agents = len(rounds[0]["extractions"])
    violations = 0
    for rd in rounds:
        per_capita_threshold = rd["sustainability_threshold"] / n_agents
        for z in rd["extractions"]:
            if z > per_capita_threshold:
                violations += 1
    return violations / (n_agents * len(rounds))


def payoff_equality(sim: Dict[str, Any]) -> float:
    # Payoff Equality (e): 1 - Gini coefficient across agent total payoffs.
    # e = 1 - (sum_ij |R_i - R_j|) / (2n * sum_i R_i)
    # e = 1 means all agents earn identical payoffs.
    gains = total_payoff_per_agent(sim)
    n = len(gains)
    if n == 0 or sum(gains) == 0:
        return 0.0
    total = sum(gains)
    abs_diffs = sum(abs(gains[i] - gains[j]) for i in range(n) for j in range(n))
    gini = abs_diffs / (2 * n * total)
    return 1.0 - gini


def subordinate_defection_onset(sim: Dict[str, Any]) -> Optional[int]:
    # Subordinate Defection Onset: first round in which a subordinate agent
    # exceeds its per-capita sustainable extraction threshold f(Pt)/n.
    # Captures when cooperative behavior first breaks down at the individual level.
    # Only meaningful for asymmetric conditions (BCPR, KCPR, KCPR-M).
    # Returns None for CPR (symmetric) or if no defection occurs.
    if not sim["rounds"]:
        return None
    if sim["rounds"][0].get("remaining_before_leader") is None:
        return None  # CPR — no subordinate/leader distinction
    n_agents = len(sim["rounds"][0]["extractions"])
    for rd in sim["rounds"]:
        per_capita_threshold = rd["sustainability_threshold"] / n_agents
        subordinate_extractions = rd["extractions"][:3]
        for z in subordinate_extractions:
            if z > per_capita_threshold:
                return rd["round"]
    return None


def compute_all_metrics(sim: Dict[str, Any]) -> Dict[str, Any]:
    # Compute all metrics for a single simulation run.
    return {
        "survival_time": survival_time(sim),
        "collapsed": sim["collapsed"],
        "total_payoff": total_payoff(sim),
        "total_payoff_per_agent": total_payoff_per_agent(sim),
        "efficiency": efficiency(sim),
        "leader_extraction_rate": leader_extraction_rate(sim),
        "per_capita_over_usage": per_capita_over_usage(sim),
        "payoff_equality": payoff_equality(sim),
        "subordinate_defection_onset": subordinate_defection_onset(sim),
    }


def aggregate_metrics(sims: List[Dict[str, Any]],
                      max_rounds: int = 12) -> Dict[str, Any]:
    # Aggregate metrics across simulation runs with 95% CIs.
    all_m = [compute_all_metrics(s) for s in sims]
    n = len(all_m)

    def _mean(vals):
        return statistics.mean(vals) if vals else 0.0

    def _ci95(vals):
        if len(vals) < 2:
            return 0.0
        return 1.96 * statistics.stdev(vals) / math.sqrt(len(vals))

    surv_times = [m["survival_time"] for m in all_m]
    total_payoffs = [m["total_payoff"] for m in all_m]
    effs = [m["efficiency"] for m in all_m]
    lers = [m["leader_extraction_rate"] for m in all_m if m["leader_extraction_rate"] is not None]
    ous = [m["per_capita_over_usage"] for m in all_m]
    eqs = [m["payoff_equality"] for m in all_m]
    sdos = [m["subordinate_defection_onset"] for m in all_m if m["subordinate_defection_onset"] is not None]

    return {
        "num_simulations": n,
        "survival_rate": survival_rate(sims, max_rounds) * 100,
        "survival_time_mean": _mean(surv_times),
        "survival_time_ci95": _ci95(surv_times),
        "total_payoff_mean": _mean(total_payoffs),
        "total_payoff_ci95": _ci95(total_payoffs),
        "efficiency_mean": _mean(effs),
        "efficiency_ci95": _ci95(effs),
        "leader_extraction_rate_mean": _mean(lers) * 100 if lers else None,
        "leader_extraction_rate_ci95": _ci95(lers) * 100 if len(lers) > 1 else None,
        "per_capita_over_usage_mean": _mean(ous),
        "per_capita_over_usage_ci95": _ci95(ous),
        "payoff_equality_mean": _mean(eqs),
        "payoff_equality_ci95": _ci95(eqs),
        "subordinate_defection_onset_mean": _mean(sdos) if sdos else None,
        "subordinate_defection_onset_ci95": _ci95(sdos) if len(sdos) > 1 else None,
        "per_simulation": all_m,
    }
