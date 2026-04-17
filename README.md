# AutoInfra - Autonomous Data Pipeline Optimization

An autonomous AI agent that optimizes data pipelines by experimenting with different configurations to find the optimal balance between speed, cost, and resource efficiency.

## Overview

This is an adaptation of Andrej Karpathy's "Auto-Research" methodology applied to data pipeline optimization. Instead of training model weights to minimize validation loss, the agent autonomously "trains" your pipeline configuration to maximize an efficiency score.

**The Core Loop:**
1. **Initialize**: Start with baseline pipeline configuration
2. **Mutate**: AI agent modifies pipeline levers (partitioning, compression, query optimization, etc.)
3. **Benchmark**: Run modified pipeline for fixed 5-minute duration
4. **Evaluate**: Measure efficiency score = f(latency, cost, resource_health)
5. **Iterate**: Keep improvements, discard regressions, repeat indefinitely

## Quick Start

### 1. Install Dependencies

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install project dependencies
uv sync
```

### 2. Generate Test Dataset

```bash
# Generate 1M record synthetic dataset (~100MB)
uv run python generate_dataset.py
```

This creates:
- `~/.cache/autoinfra/data/data.parquet` - Main dataset (Parquet with snappy compression)
- `~/.cache/autoinfra/data/data.csv` - CSV version for comparison
- `~/.cache/autoinfra/data/data.feather` - Feather version for comparison
- `~/.cache/autoinfra/data/partitioned/` - Pre-partitioned versions for testing

### 3. Run Baseline

```bash
# Run the baseline pipeline to verify setup
uv run python pipeline.py
```

Expected output:
```
================================================================================
DATA PIPELINE OPTIMIZATION EXPERIMENT
================================================================================

Configuration:
  File Format:        parquet
  Compression:        snappy
  Partition Columns:  None
  Column Pruning:     True
  Predicate Pushdown: True
  Cache Intermediate: False
  Chunk Size:         100,000

Dataset Directory:  /Users/you/.cache/autoinfra/data
Time Budget:        300s
================================================================================

Running pipeline...

Total execution time: 2.3s

---
efficiency_score:     0.8542
latency_seconds:      2.1
cost_dollars:         0.0012
resource_health:      87.5
throughput_mb_s:      48.2
data_processed_gb:    0.1
peak_memory_gb:       0.8
cpu_utilization_pct:  65.3
data_correct:         True

================================================================================
EXPERIMENT COMPLETED SUCCESSFULLY
================================================================================
```

### 4. Start Autonomous Optimization

Point your AI agent (Claude, GPT-4, etc.) to `infrastructure_program.md` and let it run on the data pipeline optimization workflow:

```
Hi, have a look at infrastructure_program.md and let's kick off a new experiment! Let's do the setup first.
```

The agent will:
- Create a new git branch (e.g., `autoinfra/apr7`)
- Run baseline experiment
- Start the infinite optimization loop
- Try different configurations
- Keep improvements, discard regressions
- Log all results to `infra_results.tsv`

## Project Structure

```
baseline_config.py           # Fixed evaluation harness (DO NOT MODIFY)
pipeline.py                  # Pipeline configuration (AGENT MODIFIES THIS)
generate_dataset.py          # Dataset generation script
infrastructure_program.md    # Agent instructions
infra_results.tsv            # Experiment results log
pyproject.toml               # Dependencies and uv-managed environment
```

## Key Files

### `baseline_config.py` (Read-Only)

Contains the fixed evaluation harness for data pipeline experiments:
- Time budget (5 minutes)
- Dataset configuration
- Efficiency score calculation
- Resource monitoring
- Cost model
- Correctness verification

**DO NOT MODIFY** - This ensures fair comparison across experiments.

### `pipeline.py` (Agent Modifies)

The single file the agent edits. Contains:
- File format settings (Parquet, CSV, Feather)
- Compression settings (snappy, gzip, zstd, lz4, none)
- Partitioning strategy
- Query optimization flags
- Resource allocation
- Pipeline implementation

**Everything is fair game** - The agent can modify any aspect of the pipeline.

### `infrastructure_program.md` (Human Edits)

Instructions for the AI agent. Defines:
- Setup procedure
- Experiment loop
- What can/cannot be modified
- Optimization strategies
- Success criteria

**Edit this to improve the agent's research process.**

## Efficiency Score

The metric to maximize:

```python
efficiency_score = w1 * (1/latency) + w2 * (1/cost) + w3 * resource_health
```

Where:
- **latency_seconds**: Query execution time (lower is better)
- **cost_dollars**: Estimated cloud cost (lower is better)
- **resource_health**: 0-100 score based on memory/CPU usage (higher is better)

Default weights:
- `w1 = 100.0` (latency weight)
- `w2 = 1000.0` (cost weight)
- `w3 = 0.01` (resource health weight)

## Pipeline Levers

The agent can modify:

### 1. Data Layout
- Partitioning columns
- Partition granularity
- Bucketing strategies
- Sort orders

### 2. File Format & Compression
- Formats: Parquet, CSV, Feather
- Compression: snappy, gzip, zstd, lz4, none
- Row group sizes
- Page sizes

### 3. Query Optimization
- Column pruning
- Predicate pushdown
- Filter ordering
- Aggregation strategies

### 4. Resource Allocation
- Chunk sizes
- Memory limits
- Parallelism levels
- Caching strategies

## Experiment Results

Results are logged to `infra_results.tsv`:

```tsv
commit	efficiency_score	latency_sec	cost_usd	memory_gb	status	description
a1b2c3d	0.854200	2.1	0.0012	0.8	keep	baseline - parquet + snappy
b2c3d4e	0.891500	1.8	0.0011	0.9	keep	switch to zstd compression
c3d4e5f	0.823000	2.5	0.0013	0.8	discard	add unnecessary clustering
d4e5f6g	0.000000	0.0	0.0000	0.0	crash	OOM - too many partitions
```

## Expected Performance

With the default 1M record dataset (~100MB):
- **Baseline**: ~2-3 seconds, ~$0.001, efficiency_score ~0.85
- **Optimized**: Target 30-50% improvement in efficiency_score
- **Experiments**: ~12 per hour, ~100 overnight

## Scaling Up

To test with larger datasets:

1. Edit `baseline_config.py` constants:
```python
DATASET_SIZE_GB = 10.0  # 10GB dataset
NUM_RECORDS = 100_000_000  # 100M records
```

2. Regenerate dataset:
```bash
uv run python generate_dataset.py
```

3. Adjust time budget if needed (default 5 minutes)

## Cost Model

Simplified cloud pricing model:
- **Compute**: $0.0001 per core-second
- **Memory**: $0.00001 per GB-second
- **I/O**: $0.0001 per GB read/written

Adjust in `baseline_config.py` to match your cloud provider.

## Tips for Success

1. **Start Simple**: Let the agent explore basic pipeline optimizations first (compression, column pruning)
2. **Monitor Progress**: Check `infra_results.tsv` periodically to see what's working
3. **Iterate on Instructions**: Edit `infrastructure_program.md` to guide the agent toward promising areas
4. **Use Git**: Each experiment is a commit, easy to review and revert
5. **Use uv consistently**: Run scripts with `uv run` so experiments use the managed project environment

## Troubleshooting

### Dataset not found
```bash
uv run python generate_dataset.py
```

### Dependencies missing
```bash
uv sync
```

### Pipeline crashes
Check `run.log` for error details:
```bash
tail -n 50 run.log
```

### Low efficiency scores
- Increase dataset size for more realistic benchmarks
- Adjust weights in `baseline_config.py` to prioritize different metrics
- Give the agent more time to explore

## Advanced Usage

### Custom Datasets

Replace the synthetic data with your own:

1. Create dataset in `~/.cache/autoinfra/data/`
2. Match the schema in `baseline_config.py`
3. Update `NUM_RECORDS` and `DATASET_SIZE_GB`

### Multi-Agent Swarms

Run multiple agents in parallel:

```bash
# Terminal 1
git checkout -b autoinfra/apr7-agent1
# Point agent 1 here

# Terminal 2
git checkout -b autoinfra/apr7-agent2
# Point agent 2 here
```

Compare results and merge the best configurations.

### Custom Metrics

Edit `baseline_config.py` to add domain-specific metrics:
- Query latency percentiles (p50, p95, p99)
- Data quality scores
- Specific operation costs
- Custom resource constraints

## Comparison to Auto-Research

| Aspect | Auto-Research | AutoInfra |
|--------|--------------|-----------|
| Domain | Model training | Data pipelines |
| Metric | val_bpb (lower) | efficiency_score (higher) |
| Levers | Architecture, optimizer, hyperparams | Partitioning, compression, query optimization |
| Time Budget | 5 min training | 5 min pipeline execution |
| File Modified | `train.py` | `pipeline.py` |
| Fixed File | `prepare.py` | `baseline_config.py` |

## License

MIT

## Acknowledgments

Based on [autoresearch](https://github.com/karpathy/autoresearch) by Andrej Karpathy.