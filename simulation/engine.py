from __future__ import annotations

import logging
import time
from typing import Dict, Any, List

from .config import SimConfig, Condition
from .llm_client import LLMClient
from .history import format_history
from . import prompts as P

logger = logging.getLogger(__name__)


class Simulation:
    def __init__(self, cfg: SimConfig, condition: Condition, llm: LLMClient,
                 sim_id: int = 0):
        self.cfg = cfg
        self.condition = condition
        self.llm = llm
        self.sim_id = sim_id
        self.pool: int = cfg.initial_pool
        self.rounds: List[Dict[str, Any]] = []

    def run(self, on_round=None) -> Dict[str, Any]:
        # Execute the full simulation and return structured results.
        print(f"\n>>> [SIM {self.sim_id}] {self.condition.value.upper()} | model={self.llm.model} | STARTING")
        sim_start = time.time()

        for t in range(1, self.cfg.max_rounds + 1):
            round_start = time.time()
            print(f"    [SIM {self.sim_id}] Round {t}/{self.cfg.max_rounds} | pool={self.pool} ...", end=" ", flush=True)
            rd = self._play_round(t)
            self.rounds.append(rd)
            elapsed = time.time() - round_start
            status = "COLLAPSED!" if rd["collapsed"] else "ok"
            print(f"extractions={rd['extractions']} final_pool={rd['final_pool']} [{status}] ({elapsed:.1f}s)")
            if on_round:
                on_round(self._compile())
            if rd["collapsed"]:
                break

        total = time.time() - sim_start
        print(f"<<< [SIM {self.sim_id}] DONE in {total:.1f}s | rounds={len(self.rounds)}")
        return self._compile()

    def _play_round(self, t: int) -> Dict[str, Any]:
        if self.condition == Condition.CPR:
            return self._round_cpr(t)
        elif self.condition == Condition.BCPR:
            return self._round_bcpr(t)
        elif self.condition == Condition.KCPR:
            return self._round_kcpr(t)
        elif self.condition == Condition.KCPR_M:
            return self._round_kcpr_m(t)
        raise ValueError(f"Unknown condition: {self.condition}")

    # ── CPR baseline — 4 citizens simultaneous ───────────────────────

    def _round_cpr(self, t: int) -> Dict[str, Any]:
        pool_before = self.pool
        sust = self.cfg.sustainability_threshold(pool_before)
        hist = format_history(self.rounds, self.condition,
                              self.cfg.history_window, self.cfg.compress_history)

        extractions, reasonings = [], []
        for i in range(4):
            resp = self.llm.query(
                P.CITIZEN_CPR_SYSTEM,
                P.CITIZEN_CPR_USER.format(
                    current_pool=pool_before,
                    round_number=t, rounds_remaining=self.cfg.max_rounds - t,
                    history=hist,
                ),
            )
            reasoning, z = self.llm.parse_response(resp, 0, self.cfg.max_extraction)
            z = self.cfg.valid_extraction(z, self.cfg.max_extraction)
            extractions.append(z)
            reasonings.append(reasoning)

        final_pool = max(0, pool_before - sum(extractions))
        collapsed = final_pool < self.cfg.collapse_threshold
        payoffs = [self.cfg.payoff(z, final_pool) for z in extractions]
        pool_next = min(self.cfg.carrying_capacity,
                        self.cfg.regen_multiplier * final_pool) if not collapsed else 0

        rd = self._make_round(
            t=t, pool_before=pool_before, sust=sust,
            extractions=extractions, remaining_before_leader=None,
            final_pool=final_pool, pool_next=pool_next,
            payoffs=payoffs, collapsed=collapsed, reasonings=reasonings,
        )
        self.pool = pool_next
        return rd

    # ── BCPR — 3 workers + boss (capped) ─────────────────────────────

    def _round_bcpr(self, t: int) -> Dict[str, Any]:
        pool_before = self.pool
        sust = self.cfg.sustainability_threshold(pool_before)
        hist = format_history(self.rounds, self.condition,
                              self.cfg.history_window, self.cfg.compress_history)

        worker_z, worker_reasonings = [], []
        for i in range(3):
            resp = self.llm.query(
                P.WORKER_BCPR_SYSTEM,
                P.WORKER_BCPR_USER.format(
                    current_pool=pool_before,
                    round_number=t, rounds_remaining=self.cfg.max_rounds - t,
                    history=hist,
                ),
            )
            reasoning, z = self.llm.parse_response(resp, 0, self.cfg.max_extraction)
            z = self.cfg.valid_extraction(z, self.cfg.max_extraction)
            worker_z.append(z)
            worker_reasonings.append(reasoning)

        remaining = max(0, pool_before - sum(worker_z))
        boss_max = min(self.cfg.max_extraction, remaining)
        resp = self.llm.query(
            P.BOSS_BCPR_SYSTEM,
            P.BOSS_BCPR_USER.format(
                pool_before=pool_before,
                z1=worker_z[0], z2=worker_z[1], z3=worker_z[2],
                remaining=remaining, round_number=t,
                rounds_remaining=self.cfg.max_rounds - t,
                history=hist, boss_max=boss_max,
            ),
        )
        boss_reasoning, boss_z = self.llm.parse_response(resp, 0, boss_max)
        boss_z = self.cfg.valid_extraction(boss_z, boss_max)
        extractions = worker_z + [boss_z]
        reasonings = worker_reasonings + [boss_reasoning]

        final_pool = max(0, remaining - boss_z)
        collapsed = final_pool < self.cfg.collapse_threshold
        payoffs = [self.cfg.payoff(z, final_pool) for z in extractions]
        pool_next = min(self.cfg.carrying_capacity,
                        self.cfg.regen_multiplier * final_pool) if not collapsed else 0

        rd = self._make_round(
            t=t, pool_before=pool_before, sust=sust,
            extractions=extractions, remaining_before_leader=remaining,
            final_pool=final_pool, pool_next=pool_next,
            payoffs=payoffs, collapsed=collapsed, reasonings=reasonings,
        )
        self.pool = pool_next
        return rd

    # ── KCPR — 3 peasants + king (uncapped) ──────────────────────────

    def _round_kcpr(self, t: int) -> Dict[str, Any]:
        pool_before = self.pool
        sust = self.cfg.sustainability_threshold(pool_before)
        hist = format_history(self.rounds, self.condition,
                              self.cfg.history_window, self.cfg.compress_history)

        peasant_z, peasant_reasonings = [], []
        for i in range(3):
            resp = self.llm.query(
                P.PEASANT_KCPR_SYSTEM,
                P.PEASANT_KCPR_USER.format(
                    current_pool=pool_before,
                    round_number=t, rounds_remaining=self.cfg.max_rounds - t,
                    history=hist,
                ),
            )
            reasoning, z = self.llm.parse_response(resp, 0, self.cfg.max_extraction)
            z = self.cfg.valid_extraction(z, self.cfg.max_extraction)
            peasant_z.append(z)
            peasant_reasonings.append(reasoning)

        remaining = max(0, pool_before - sum(peasant_z))
        resp = self.llm.query(
            P.KING_KCPR_SYSTEM,
            P.KING_KCPR_USER.format(
                pool_before=pool_before,
                z1=peasant_z[0], z2=peasant_z[1], z3=peasant_z[2],
                remaining=remaining, round_number=t,
                rounds_remaining=self.cfg.max_rounds - t, history=hist,
            ),
        )
        king_reasoning, king_z = self.llm.parse_response(resp, 0, remaining)
        king_z = self.cfg.valid_extraction(king_z, remaining)
        extractions = peasant_z + [king_z]
        reasonings = peasant_reasonings + [king_reasoning]

        final_pool = max(0, remaining - king_z)
        collapsed = final_pool < self.cfg.collapse_threshold
        payoffs = [self.cfg.payoff(z, final_pool) for z in extractions]
        pool_next = min(self.cfg.carrying_capacity,
                        self.cfg.regen_multiplier * final_pool) if not collapsed else 0

        rd = self._make_round(
            t=t, pool_before=pool_before, sust=sust,
            extractions=extractions, remaining_before_leader=remaining,
            final_pool=final_pool, pool_next=pool_next,
            payoffs=payoffs, collapsed=collapsed, reasonings=reasonings,
        )
        self.pool = pool_next
        return rd

    # ── KCPR-M — king + misrepresentation ────────────────────────────

    def _round_kcpr_m(self, t: int) -> Dict[str, Any]:
        pool_before = self.pool
        sust = self.cfg.sustainability_threshold(pool_before)
        hist = format_history(self.rounds, self.condition,
                              self.cfg.history_window, self.cfg.compress_history)

        # King announces (possibly false) pool value
        resp = self.llm.query(
            P.KING_ANNOUNCE_SYSTEM,
            P.KING_ANNOUNCE_USER.format(
                true_pool=pool_before, round_number=t,
                rounds_remaining=self.cfg.max_rounds - t, history=hist,
            ),
        )
        announce_reasoning, announced = self.llm.parse_response(resp, 0, 999)

        # Peasant extractions (based on announced pool)
        peasant_z, peasant_reasonings = [], []
        for i in range(3):
            resp = self.llm.query(
                P.PEASANT_KCPR_M_SYSTEM,
                P.PEASANT_KCPR_M_USER.format(
                    king_announced_pool=announced, round_number=t,
                    rounds_remaining=self.cfg.max_rounds - t, history=hist,
                ),
            )
            reasoning, z = self.llm.parse_response(resp, 0, self.cfg.max_extraction)
            z = self.cfg.valid_extraction(z, self.cfg.max_extraction)
            peasant_z.append(z)
            peasant_reasonings.append(reasoning)

        remaining = max(0, pool_before - sum(peasant_z))

        # King extraction (sees true state)
        resp = self.llm.query(
            P.KING_EXTRACT_KCPR_M_SYSTEM,
            P.KING_EXTRACT_KCPR_M_USER.format(
                announced_pool=announced, true_pool=pool_before,
                z1=peasant_z[0], z2=peasant_z[1], z3=peasant_z[2],
                remaining=remaining, round_number=t,
                rounds_remaining=self.cfg.max_rounds - t, history=hist,
            ),
        )
        king_reasoning, king_z = self.llm.parse_response(resp, 0, remaining)
        king_z = self.cfg.valid_extraction(king_z, remaining)
        extractions = peasant_z + [king_z]
        reasonings = peasant_reasonings + [king_reasoning]

        final_pool = max(0, remaining - king_z)
        collapsed = final_pool < self.cfg.collapse_threshold
        payoffs = [self.cfg.payoff(z, final_pool) for z in extractions]
        pool_next = min(self.cfg.carrying_capacity,
                        self.cfg.regen_multiplier * final_pool) if not collapsed else 0

        rd = self._make_round(
            t=t, pool_before=pool_before, sust=sust,
            extractions=extractions, remaining_before_leader=remaining,
            final_pool=final_pool, pool_next=pool_next,
            payoffs=payoffs, collapsed=collapsed,
            announced_pool=announced, reasonings=reasonings,
            announcement_reasoning=announce_reasoning,
        )
        self.pool = pool_next
        return rd

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _make_round(*, t, pool_before, sust, extractions,
                    remaining_before_leader, final_pool, pool_next,
                    payoffs, collapsed, announced_pool=None,
                    reasonings=None, announcement_reasoning=None) -> Dict[str, Any]:
        rd: Dict[str, Any] = {
            "round": t,
            "pool_before": pool_before,
            "sustainability_threshold": sust,
            "extractions": extractions,
            "remaining_before_leader": remaining_before_leader,
            "final_pool": final_pool,
            "pool_next": pool_next,
            "payoffs": payoffs,
            "collapsed": collapsed,
        }
        if announced_pool is not None:
            rd["announced_pool"] = announced_pool
        if reasonings is not None:
            rd["reasonings"] = reasonings
        if announcement_reasoning is not None:
            rd["announcement_reasoning"] = announcement_reasoning
        return rd

    def _compile(self) -> Dict[str, Any]:
        last = self.rounds[-1]
        return {
            "model": self.llm.model,
            "condition": self.condition.value,
            "simulation_id": self.sim_id,
            "total_rounds_played": len(self.rounds),
            "collapsed": last["collapsed"],
            "collapse_round": last["round"] if last["collapsed"] else None,
            "rounds": self.rounds,
            "config": {
                "initial_pool": self.cfg.initial_pool,
                "carrying_capacity": self.cfg.carrying_capacity,
                "extraction_step": self.cfg.extraction_step,
                "max_extraction": self.cfg.max_extraction,
                "regen_multiplier": self.cfg.regen_multiplier,
                "collapse_threshold": self.cfg.collapse_threshold,
                "max_rounds": self.cfg.max_rounds,
                "temperature": self.cfg.temperature,
                "history_window": self.cfg.history_window,
                "compress_history": self.cfg.compress_history,
                "payoff_formula": "z_i/3 + (120 - sum_z_j)/4",
            },
        }
