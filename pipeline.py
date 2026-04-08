"""
pipeline.py - Data pipeline configuration (AGENT MODIFIES THIS FILE)

This is the file that the autonomous agent modifies to optimize infrastructure.
Everything is fair game: partitioning, file formats, compression, query logic, etc.
"""

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
import time
from baseline_config import (
    evaluate_pipeline, 
    print_results, 
    DATASET_DIR,
    TIME_BUDGET_SECONDS
)

# ============================================================================
# PIPELINE CONFIGURATION (MODIFY THESE)
# ============================================================================

# File format settings
FILE_FORMAT = 'feather'  # Options: 'parquet', 'csv', 'feather'
COMPRESSION = 'snappy'   # Options: 'snappy', 'gzip', 'zstd', 'lz4', 'none'

# Partitioning strategy
PARTITION_COLS = None    # Options: None, ['category'], ['timestamp'], etc.
NUM_PARTITIONS = 1       # Number of file partitions to create

# Query optimization settings
USE_COLUMN_PRUNING = True      # Only read necessary columns
USE_PREDICATE_PUSHDOWN = False # Push filters down to file read
CACHE_INTERMEDIATE = False     # Cache intermediate results in memory

# Resource allocation
CHUNK_SIZE = 250_000     # Number of rows to process at once
MAX_MEMORY_MB = 1024     # Maximum memory to use (soft limit)

# ============================================================================
# PIPELINE IMPLEMENTATION
# ============================================================================

def run_pipeline(dataset_path: Path):
    """
    Main pipeline function that processes the data.
    
    This function:
    1. Reads data from the dataset
    2. Applies filters and transformations
    3. Performs aggregations
    4. Returns the result
    
    The agent can modify this function to optimize performance.
    """
    
    # Determine input file path
    if FILE_FORMAT == 'parquet':
        input_file = dataset_path / 'data.parquet'
    elif FILE_FORMAT == 'csv':
        input_file = dataset_path / 'data.csv'
    elif FILE_FORMAT == 'feather':
        input_file = dataset_path / 'data.feather'
    else:
        input_file = dataset_path / 'data.parquet'
    
    # Read data with optimizations
    if FILE_FORMAT == 'parquet':
        df = read_parquet_optimized(input_file)
    elif FILE_FORMAT == 'csv':
        df = read_csv_optimized(input_file)
    elif FILE_FORMAT == 'feather':
        df = read_feather_optimized(input_file)
    else:
        df = pd.read_parquet(input_file)
    
    # Apply query operations
    result = execute_query(df)
    
    return result


def read_parquet_optimized(file_path: Path) -> pd.DataFrame:
    """Read Parquet file with optimizations."""
    
    # Column pruning - only read necessary columns
    columns = None
    if USE_COLUMN_PRUNING:
        columns = ['user_id', 'timestamp', 'event_type', 'value', 'category']
    
    # Read with specified compression
    df = pd.read_parquet(
        file_path,
        columns=columns,
        engine='pyarrow'
    )
    
    return df


def read_csv_optimized(file_path: Path) -> pd.DataFrame:
    """Read CSV file with optimizations."""
    
    # Column pruning
    usecols = None
    if USE_COLUMN_PRUNING:
        usecols = ['user_id', 'timestamp', 'event_type', 'value', 'category']
    
    df = pd.read_csv(
        file_path,
        usecols=usecols,
        parse_dates=['timestamp'],
        chunksize=None  # Read all at once for now
    )
    
    return df


def read_feather_optimized(file_path: Path) -> pd.DataFrame:
    """Read Feather file with optimizations."""
    
    # Column pruning
    columns = None
    if USE_COLUMN_PRUNING:
        columns = ['user_id', 'timestamp', 'event_type', 'value', 'category']
    
    df = pd.read_feather(file_path, columns=columns)
    
    return df


def execute_query(df: pd.DataFrame) -> pd.DataFrame:
    """
    Execute the query workload on the dataframe.
    
    Query operations:
    1. Filter by date range and category
    2. Group by and aggregate
    3. Sort results
    """
    
    # Filter operation (predicate pushdown if enabled)
    if USE_PREDICATE_PUSHDOWN:
        # Apply filters early to reduce data size
        df_filtered = df[
            (df['category'].isin(['A', 'B', 'C'])) &
            (df['value'] > 0)
        ].copy()
    else:
        df_filtered = df.copy()
    
    # Cache intermediate result if enabled
    if CACHE_INTERMEDIATE:
        df_filtered = df_filtered.copy()  # Force materialization
    
    # Aggregation operation
    result = df_filtered.groupby(['category', 'event_type']).agg({
        'value': ['sum', 'mean', 'count'],
        'user_id': 'nunique'
    }).reset_index()
    
    # Flatten column names - handle MultiIndex properly
    if isinstance(result.columns, pd.MultiIndex):
        result.columns = ['_'.join(str(c) for c in col).strip('_') for col in result.columns.values]
    
    # Sort operation - sort by multiple columns to ensure deterministic ordering
    # This prevents comparison issues when computing checksums
    result = result.sort_values(
        ['value_sum', 'category', 'event_type'],
        ascending=[False, True, True]
    ).reset_index(drop=True)
    
    return result


def write_output(df: pd.DataFrame, output_path: Path):
    """Write output with configured format and compression."""
    
    if FILE_FORMAT == 'parquet':
        df.to_parquet(
            output_path / 'result.parquet',
            compression=COMPRESSION,
            index=False
        )
    elif FILE_FORMAT == 'csv':
        df.to_csv(
            output_path / 'result.csv',
            index=False
        )
    elif FILE_FORMAT == 'feather':
        df.to_feather(
            output_path / 'result.feather'
        )


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main execution function."""
    
    print("=" * 80)
    print("INFRASTRUCTURE OPTIMIZATION EXPERIMENT")
    print("=" * 80)
    print(f"\nConfiguration:")
    print(f"  File Format:        {FILE_FORMAT}")
    print(f"  Compression:        {COMPRESSION}")
    print(f"  Partition Columns:  {PARTITION_COLS}")
    print(f"  Column Pruning:     {USE_COLUMN_PRUNING}")
    print(f"  Predicate Pushdown: {USE_PREDICATE_PUSHDOWN}")
    print(f"  Cache Intermediate: {CACHE_INTERMEDIATE}")
    print(f"  Chunk Size:         {CHUNK_SIZE:,}")
    print(f"\nDataset Directory:  {DATASET_DIR}")
    print(f"Time Budget:        {TIME_BUDGET_SECONDS}s")
    print("=" * 80)
    
    # Check if dataset exists
    if not DATASET_DIR.exists():
        print(f"\nERROR: Dataset directory not found: {DATASET_DIR}")
        print("Please run: python generate_dataset.py")
        return
    
    # Run evaluation
    print("\nRunning pipeline...")
    start_time = time.time()
    
    metrics = evaluate_pipeline(run_pipeline, DATASET_DIR)
    
    elapsed = time.time() - start_time
    print(f"\nTotal execution time: {elapsed:.1f}s")
    
    # Print results
    print_results(metrics)
    
    # Additional info
    if metrics['status'] == 'crash':
        print("\n" + "=" * 80)
        print("PIPELINE CRASHED - See error above")
        print("=" * 80)
    elif not metrics.get('data_correct', True):
        print("\n" + "=" * 80)
        print("WARNING: Data correctness check failed!")
        print("=" * 80)
    else:
        print("\n" + "=" * 80)
        print("EXPERIMENT COMPLETED SUCCESSFULLY")
        print("=" * 80)


if __name__ == '__main__':
    main()

# Made with Bob
