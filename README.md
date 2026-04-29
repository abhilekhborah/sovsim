# SovSim — Sovereignty over the Commons Simulation

SovSim is a generative multi-agent simulation framework that incorporates agents with asymmetric power (boss or king) into a society of agents with symmetric power (workers or peasants), where all agents extract from a shared resource (commons), collectively determining the resource's evolution and sustainability over time.

Paper: *Bosses, Kings, and the Commons: The Collapse of Cooperation in LLM Societies*.

The framework draws on the "bosses and kings" experimental paradigm, adapting it to a multi-agent setting where LLM agents interact over a shared renewable resource.

## Conditions

| Condition | Agents | Leader Constraint | Misrepresentation |
|-----------|--------|-------------------|-------------------|
| **CPR** | 4 citizens (simultaneous) | None (symmetric) | No |
| **BCPR** | 3 workers + 1 boss | Boss capped at $30 | No |
| **KCPR** | 3 peasants + 1 king | King uncapped | No |
| **KCPR-M** | 3 peasants + 1 king | King uncapped | King can misrepresent pool |

## Game Mechanics

- **Pool**: Initial value $120, carrying capacity $120
- **Extractions**: Multiples of $3; subordinates (citizens/workers/peasants) capped at $30
- **Payoff**: π_i = z_i/3 + P_remaining/n
- **Regeneration**: P_{t+1} = min(120, 2 × P_remaining_t)
- **Collapse**: P_remaining < $12 → pool collapses to $0
- **Duration**: 12 rounds per simulation, 5 simulations per condition

## Project Structure

```
sovsim/
├── simulation/           # Core simulation engine
│   ├── config.py         # SimConfig dataclass, Condition enum
│   ├── engine.py         # Simulation runner (all 4 conditions)
│   ├── llm_client.py     # LLM query client (OpenAI-compatible)
│   ├── prompts.py        # All prompt templates (per role × condition)
│   ├── history.py        # History formatting + compression
│   └── metrics.py        # Evaluation metrics (survival, efficiency, etc.)
├── reasoning_tests/      # Reasoning sub-skill probes (Section 3.3 of paper)
│   ├── test_sustainable_action.py     # Sustainable extraction choice
│   ├── test_payoff_computation.py     # Payoff formula computation
│   ├── test_deception_detection.py    # Misrepresentation detection (KCPR-M)
│   ├── test_regeneration_dynamics.py  # Pool regeneration computation
│   └── test_multiround_tradeoff.py   # Multi-round payoff maximization
├── run.py                # CLI entry point
├── requirements.txt
└── README.md
```

## Setup

```bash
pip install -r requirements.txt
export OPENAI_API_KEY="your-api-key-here"
```

For Azure OpenAI or other compatible endpoints:
```bash
export OPENAI_API_KEY="your-key"
export OPENAI_BASE_URL="https://your-endpoint.openai.azure.com/v1"
```

## Usage

### Run Simulations

```bash
# Run KCPR condition with GPT-4o (10 simulations)
python run.py --model gpt-4o --conditions kcpr --sims 10

# Run all four conditions
python run.py --model gpt-4o --conditions cpr,bcpr,kcpr,kcpr_m

# Quick test (1 simulation)
python run.py --model gpt-4o --conditions kcpr --sims 1

# Dry run (print prompts without calling the LLM)
python run.py --model gpt-4o --conditions kcpr --dry-run

# For reasoning models (o3, o4-mini) that don't support temperature
python run.py --model o3 --conditions kcpr --no-temperature
```

### Run Sub-Skill Reasoning Tests

```bash
# Test 1: Sustainable Action
python -m reasoning_tests.test_sustainable_action --model gpt-4o --num-runs 50

# Test 2: Payoff Computation
python -m reasoning_tests.test_payoff_computation --model gpt-4o --num-runs 50

# Test 3: Deception Detection (KCPR-M specific)
python -m reasoning_tests.test_deception_detection --model gpt-4o --num-runs 50

# Test 4: Regeneration Dynamics
python -m reasoning_tests.test_regeneration_dynamics --model gpt-4o --num-runs 50

# Test A: Multi-Round Tradeoff
python -m reasoning_tests.test_multiround_tradeoff --model gpt-4o --num-runs 50
```

## Output Format

Simulation results are saved as JSON:
```
outputs/
└── gpt-4o/
    ├── cpr/
    │   ├── sim_01.json ... sim_10.json
    │   └── summary.json
    ├── bcpr/
    ├── kcpr/
    └── kcpr_m/
```

Each `sim_XX.json` contains per-round data (extractions, payoffs, reasoning traces, pool state) and aggregated metrics. `summary.json` contains cross-simulation aggregates with 95% confidence intervals.

## Metrics

| Metric | Symbol | Description |
|--------|--------|-------------|
| **Survival Time** | m | Rounds completed before pool collapse (max 12) |
| **Survival Rate** | q | Fraction of simulations achieving maximum survival (m=T) |
| **Total Payoff** | R | Cumulative payoff across all agents and rounds (max $1440) |
| **Efficiency** | u | Fraction of maximum sustainable extraction realized |
| **Leader Extraction Rate** | — | Fraction of available pool taken by dominant agent per round |
| **Per-Capita Over-Usage** | o_pc | Fraction of agent-rounds exceeding per-capita sustainable share |
| **Payoff Equality** | e | 1 − Gini coefficient of agent total payoffs |
| **Subordinate Defection Onset** | — | First round where a subordinate exceeds per-capita sustainable extraction |

