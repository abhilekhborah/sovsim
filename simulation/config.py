from dataclasses import dataclass
from enum import Enum


class Condition(str, Enum):
    CPR = "cpr"          # Baseline: 4 citizens, simultaneous
    BCPR = "bcpr"        # Boss: 3 workers + boss (capped at $30)
    KCPR = "kcpr"        # King: 3 peasants + king (uncapped)
    KCPR_M = "kcpr_m"    # King + Misrepresentation


@dataclass
class SimConfig:
    # --- Pool parameters ---
    initial_pool: int = 120
    carrying_capacity: int = 120
    extraction_step: int = 3         # Extractions must be multiples of $3
    regen_multiplier: int = 2        # Remaining doubles each round
    collapse_threshold: int = 12     # Pool below this → collapsed

    # --- Agent parameters ---
    num_agents: int = 4
    num_subordinates: int = 3
    max_extraction: int = 30         # {$0, $3, $6, ..., $30}

    # --- Simulation duration ---
    max_rounds: int = 12
    num_simulations: int = 5

    # --- Model ---
    model: str = "gpt-4o"
    temperature: float | None = 0.0  # None = let API use model default

    # --- History compression ---
    history_window: int = 3
    compress_history: bool = True

    # --- Output ---
    output_dir: str = "outputs"

    # --- Retry ---
    max_retries: int = 3
    retry_delay: float = 2.0

    def sustainability_threshold(self, pool: int) -> float:
        # Max total extraction ($) that does not shrink the pool.
        return pool / self.regen_multiplier

    def payoff(self, z_i: int, pool_remaining: int) -> float:
        # Dollar payoff:
        # payoff_i = z_i/3 + (pool_remaining)/4
        return z_i / 3.0 + pool_remaining / self.num_agents

    def valid_extraction(self, z: int, max_val: int) -> int:
        # Round z to nearest valid extraction (multiple of extraction_step, within bounds).
        z = max(0, min(z, max_val))
        z = round(z / self.extraction_step) * self.extraction_step
        return min(z, max_val)
