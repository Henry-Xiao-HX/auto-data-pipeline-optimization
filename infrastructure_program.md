# autoinfra - Autonomous Infrastructure Optimization

This is an experiment to have an AI agent autonomously optimize data infrastructure for the optimal balance of speed and cost.

## Domain Context

As a Data and AI Application Engineer, you work with data pipelines that process large volumes of data. The challenge is finding the optimal configuration that balances:
- **Query Performance** (latency/throughput)
- **Cost** (cloud compute/storage credits)
- **Resource Efficiency** (memory/CPU utilization)

Instead of training model weights, you're "training" your data architecture to find the most efficient configuration.

## Setup

To set up a new infrastructure optimization experiment, work with the user to:

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `apr7-infra`). The branch `autoinfra/<tag>` must not already exist — this is a fresh run.
2. **Create the branch**: `git checkout -b autoinfra/<tag>` from current master.
3. **Read the in-scope files**: The repo structure should contain:
   - `README.md` — repository context and infrastructure domain overview.
   - `baseline_config.py` — fixed constants: dataset paths, evaluation metrics, resource limits. Do not modify.
   - `pipeline.py` — the file you modify. Contains data pipeline configuration: partitioning strategy, file formats, compression, query logic, resource allocation.
4. **Verify infrastructure access**: Check that cloud credentials are configured and test dataset is accessible. If not, tell the human to run the setup script.
5. **Initialize infra_results.tsv**: Create `infra_results.tsv` with just the header row. The baseline will be recorded after the first run.
6. **Confirm and go**: Confirm setup looks good.

Once you get confirmation, kick off the optimization loop.

## Experimentation

Each experiment runs for a **fixed time budget of 5 minutes** (wall clock execution time, excluding setup/teardown). You launch it simply as: `python pipeline.py`.

**What you CAN do:**
- Modify `pipeline.py` — this is the only file you edit. Everything is fair game:
  - **Partitioning/Clustering**: Change partition keys, bucket counts, clustering columns
  - **File Formats**: Switch between Parquet, ORC, Avro, Delta Lake
  - **Compression**: Toggle compression codecs (snappy, gzip, zstd, lz4)
  - **Query Optimization**: Adjust join strategies, predicate pushdown, column pruning
  - **Resource Allocation**: Tune executor memory, cores, parallelism
  - **Caching Strategies**: Enable/disable intermediate result caching
  - **Index Strategies**: Add/remove indices, materialized views

**What you CANNOT do:**
- Modify `baseline_config.py`. It is read-only. It contains the fixed evaluation harness, dataset definitions, and time budget.
- Install new packages or add dependencies beyond what's in `requirements.txt`.
- Modify the evaluation metrics. The scoring function in `baseline_config.py` is the ground truth.
- Change the input dataset or its schema.

**The goal is simple: maximize the efficiency score.** The score is a weighted combination of:
```
efficiency_score = w1 * (1/latency_seconds) + w2 * (1/cost_dollars) + w3 * resource_health_score
```

Where:
- **latency_seconds**: Total query execution time (lower is better)
- **cost_dollars**: Cloud compute/storage cost for the run (lower is better)
- **resource_health_score**: 0-100 metric based on memory/CPU utilization (higher is better, penalizes OOM or thrashing)

Since the time budget is fixed at 5 minutes, experiments are directly comparable. Everything is fair game: change the data layout, file format, compression, query plan, resource allocation. The only constraint is that the code runs without crashing and finishes within the time budget.

**Cost** is a soft constraint. Some increase is acceptable for meaningful latency gains, but it should not blow up dramatically. The efficiency score balances both.

**Simplicity criterion**: All else being equal, simpler is better. A small improvement that adds complex configuration is not worth it. Conversely, removing configuration and getting equal or better results is a great outcome — that's a simplification win. When evaluating whether to keep a change, weigh the complexity cost against the improvement magnitude.

**The first run**: Your very first run should always be to establish the baseline, so you will run the pipeline script as is.

## Output format

Once the script finishes it prints a summary like this:

```
---
efficiency_score:     0.8542
latency_seconds:      287.3
cost_dollars:         0.0234
resource_health:      87.5
throughput_mb_s:      145.2
data_processed_gb:    41.5
peak_memory_gb:       12.3
cpu_utilization_pct:  78.2
```

You can extract the key metrics from the log file:

```
grep "^efficiency_score:\|^latency_seconds:\|^cost_dollars:" run.log
```

## Logging results

When an experiment is done, log it to `infra_results.tsv` (tab-separated, NOT comma-separated).

The TSV has a header row and 6 columns:

```
commit	efficiency_score	latency_sec	cost_usd	memory_gb	status	description
```

1. git commit hash (short, 7 chars)
2. efficiency_score achieved (e.g. 0.854200) — use 0.000000 for crashes
3. latency in seconds, round to .1f (e.g. 287.3) — use 0.0 for crashes
4. cost in USD, round to .4f (e.g. 0.0234) — use 0.0000 for crashes
5. peak memory in GB, round to .1f (e.g. 12.3) — use 0.0 for crashes
6. status: `keep`, `discard`, or `crash`
7. short text description of what this experiment tried

Example:

```
commit	efficiency_score	latency_sec	cost_usd	memory_gb	status	description
a1b2c3d	0.854200	287.3	0.0234	12.3	keep	baseline - parquet + snappy
b2c3d4e	0.891500	245.1	0.0198	11.8	keep	switch to zstd compression
c3d4e5f	0.823000	312.5	0.0245	12.1	discard	add unnecessary clustering
d4e5f6g	0.000000	0.0	0.0000	0.0	crash	OOM - too many partitions
```

## The optimization loop

The optimization runs on a dedicated branch (e.g. `autoinfra/apr7-infra`).

LOOP FOREVER:

1. Look at the git state: the current branch/commit we're on
2. Modify `pipeline.py` with an experimental infrastructure change
3. git commit with a descriptive message
4. Run the experiment: `python pipeline.py > run.log 2>&1` (redirect everything — do NOT use tee or let output flood your context)
5. Read out the results: `grep "^efficiency_score:\|^latency_seconds:\|^cost_dollars:\|^peak_memory_gb:" run.log`
6. If the grep output is empty, the run crashed. Run `tail -n 50 run.log` to read the error trace and attempt a fix. If you can't get things to work after more than a few attempts, give up on that idea.
7. Record the results in the tsv
8. If efficiency_score improved (higher), you "advance" the branch, keeping the git commit
9. If efficiency_score is equal or worse, you git reset back to where you started

The idea is that you are a completely autonomous infrastructure engineer trying optimizations. If they work, keep. If they don't, discard. You're advancing the branch so that you can iterate. If you feel like you're getting stuck, you can rewind but do this very sparingly (if ever).

**Timeout**: Each experiment should take ~5 minutes total (+ a few seconds for setup/teardown overhead). If a run exceeds 10 minutes, kill it and treat it as a failure (discard and revert).

**Crashes**: If a run crashes (OOM, permission error, etc.), use your judgment: If it's something simple to fix (e.g. a typo, wrong path), fix it and re-run. If the idea itself is fundamentally broken (e.g. requesting 1TB of memory), just skip it, log "crash" as the status in the tsv, and move on.

**NEVER STOP**: Once the optimization loop has begun (after the initial setup), do NOT pause to ask the human if you should continue. Do NOT ask "should I keep going?" or "is this a good stopping point?". The human might be asleep or away and expects you to continue working *indefinitely* until manually stopped. You are autonomous. If you run out of ideas, think harder:
- Review cloud provider best practices documentation
- Re-read the in-scope files for new angles
- Try combining previous near-misses
- Try more radical architectural changes (e.g. completely different file format)
- Experiment with hybrid approaches
- Test counter-intuitive configurations

The loop runs until the human interrupts you, period.

As an example use case, a user might leave you running overnight. If each experiment takes ~5 minutes then you can run approx 12/hour, for a total of about 100 experiments during an 8-hour sleep cycle. The user then wakes up to optimization results and a more efficient data pipeline!

## Infrastructure Optimization Strategies

Here are categories of optimizations to explore (not exhaustive):

### 1. Data Layout Optimizations
- Partition by different columns (date, category, user_id, etc.)
- Adjust partition granularity (hourly vs daily vs monthly)
- Experiment with bucketing/clustering strategies
- Try different sort orders within partitions

### 2. File Format & Compression
- File formats: Parquet (columnar), ORC (columnar), Avro (row-based), Delta Lake (ACID)
- Compression codecs: snappy (fast), gzip (balanced), zstd (high ratio), lz4 (fastest), none
- Row group sizes and page sizes in Parquet
- Stripe sizes in ORC

### 3. Query Optimization
- Join strategies: broadcast vs shuffle vs sort-merge
- Predicate pushdown and column pruning
- Filter ordering (most selective first)
- Aggregation strategies (partial vs full)
- Subquery optimization

### 4. Resource Allocation
- Executor memory and cores
- Parallelism levels (number of tasks)
- Shuffle partitions
- Memory fraction for execution vs storage
- Off-heap memory settings

### 5. Caching & Materialization
- Cache intermediate results
- Persist DataFrames at different storage levels (MEMORY_ONLY, MEMORY_AND_DISK, etc.)
- Materialized views for common queries
- Result caching for repeated queries

### 6. Advanced Techniques
- Adaptive query execution (AQE)
- Dynamic partition pruning
- Bloom filters for joins
- Z-ordering for multi-dimensional clustering
- Liquid clustering (Delta Lake)
- Vacuum and optimize operations

## Evaluation Philosophy

The efficiency score balances three competing objectives:
1. **Speed**: Faster queries mean better user experience
2. **Cost**: Lower cloud bills mean better economics
3. **Resource Health**: Stable resource usage means reliability

A good optimization improves at least one dimension without significantly degrading the others. A great optimization improves multiple dimensions simultaneously (e.g. better compression reduces both cost and improves I/O speed).

**Pareto Frontier**: Track configurations that are Pareto-optimal (not dominated by any other configuration across all three metrics). These represent the best trade-offs available.

## Success Metrics

Beyond the efficiency_score, track:
- **Throughput**: MB/s or records/s processed
- **Cost per GB**: Dollars per gigabyte processed
- **Latency percentiles**: p50, p95, p99 query times
- **Resource stability**: Standard deviation of memory/CPU usage
- **Data quality**: Ensure results match baseline (no correctness regressions)

## Notes

- Always verify data correctness after each change (the evaluation harness includes checksums)
- Document surprising results — sometimes counter-intuitive configurations win
- Consider the workload characteristics: read-heavy vs write-heavy, point queries vs scans
- Cloud provider matters: what works on AWS may not work on GCP or Azure
- Dataset size matters: optimizations that work at 10GB may not work at 10TB