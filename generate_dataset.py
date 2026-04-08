"""
generate_dataset.py - Generate synthetic dataset for infrastructure optimization experiments.

Run this once to create the test dataset:
    python generate_dataset.py
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import pyarrow as pa
import pyarrow.parquet as pq
from baseline_config import DATASET_DIR, NUM_RECORDS, DATASET_SIZE_GB, SCHEMA

def generate_synthetic_data(num_records: int = NUM_RECORDS) -> pd.DataFrame:
    """
    Generate synthetic data that mimics a real event log dataset.
    
    Schema:
    - user_id: int64 (1M unique users)
    - timestamp: datetime64[ns] (last 30 days)
    - event_type: string (10 event types)
    - value: float64 (transaction values)
    - category: string (5 categories)
    - metadata: string (JSON-like metadata)
    """
    
    print(f"Generating {num_records:,} records...")
    
    np.random.seed(42)
    
    # Generate timestamps (last 30 days)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    timestamps = pd.date_range(start=start_date, end=end_date, periods=num_records)
    
    # Generate user IDs (1M unique users, Zipfian distribution)
    num_users = 1_000_000
    user_ids = np.random.zipf(1.5, num_records) % num_users
    
    # Generate event types
    event_types = np.random.choice(
        ['login', 'logout', 'purchase', 'view', 'click', 'search', 'add_cart', 'checkout', 'review', 'share'],
        size=num_records,
        p=[0.15, 0.10, 0.20, 0.25, 0.15, 0.05, 0.05, 0.03, 0.01, 0.01]
    )
    
    # Generate values (transaction amounts, log-normal distribution)
    values = np.random.lognormal(mean=3.0, sigma=1.5, size=num_records)
    values = np.round(values, 2)
    
    # Generate categories
    categories = np.random.choice(
        ['A', 'B', 'C', 'D', 'E'],
        size=num_records,
        p=[0.3, 0.25, 0.2, 0.15, 0.1]
    )
    
    # Generate metadata (simple JSON-like strings)
    metadata_templates = [
        '{"device":"mobile","os":"ios"}',
        '{"device":"desktop","os":"windows"}',
        '{"device":"mobile","os":"android"}',
        '{"device":"tablet","os":"ios"}',
        '{"device":"desktop","os":"macos"}',
    ]
    metadata = np.random.choice(metadata_templates, size=num_records)
    
    # Create DataFrame
    df = pd.DataFrame({
        'user_id': user_ids,
        'timestamp': timestamps,
        'event_type': event_types,
        'value': values,
        'category': categories,
        'metadata': metadata
    })
    
    # Ensure correct dtypes
    df['user_id'] = df['user_id'].astype('int64')
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['event_type'] = df['event_type'].astype('string')
    df['value'] = df['value'].astype('float64')
    df['category'] = df['category'].astype('string')
    df['metadata'] = df['metadata'].astype('string')
    
    return df


def save_dataset(df: pd.DataFrame, output_dir: Path):
    """
    Save dataset in multiple formats for testing different configurations.
    """
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\nSaving dataset to {output_dir}...")
    
    # Save as Parquet (default format)
    print("  - Saving as Parquet (snappy compression)...")
    parquet_path = output_dir / 'data.parquet'
    df.to_parquet(
        parquet_path,
        compression='snappy',
        index=False,
        engine='pyarrow'
    )
    
    # Save as CSV (for comparison)
    print("  - Saving as CSV...")
    csv_path = output_dir / 'data.csv'
    df.to_csv(csv_path, index=False)
    
    # Save as Feather (for comparison)
    print("  - Saving as Feather...")
    feather_path = output_dir / 'data.feather'
    df.to_feather(feather_path)
    
    # Print file sizes
    print("\nFile sizes:")
    for path in [parquet_path, csv_path, feather_path]:
        size_mb = path.stat().st_size / (1024 * 1024)
        print(f"  {path.name:20s}: {size_mb:8.2f} MB")
    
    # Save dataset statistics
    stats_path = output_dir / 'dataset_stats.txt'
    with open(stats_path, 'w') as f:
        f.write("Dataset Statistics\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Number of records: {len(df):,}\n")
        f.write(f"Memory usage: {df.memory_usage(deep=True).sum() / (1024**2):.2f} MB\n\n")
        f.write("Column dtypes:\n")
        f.write(str(df.dtypes) + "\n\n")
        f.write("Summary statistics:\n")
        f.write(str(df.describe()) + "\n\n")
        f.write("Value counts by category:\n")
        f.write(str(df['category'].value_counts()) + "\n\n")
        f.write("Value counts by event_type:\n")
        f.write(str(df['event_type'].value_counts()) + "\n")
    
    print(f"\nDataset statistics saved to {stats_path}")


def create_partitioned_dataset(df: pd.DataFrame, output_dir: Path):
    """
    Create partitioned versions of the dataset for testing partitioning strategies.
    """
    
    partitioned_dir = output_dir / 'partitioned'
    
    # Partition by category
    print("\nCreating partitioned dataset (by category)...")
    category_dir = partitioned_dir / 'by_category'
    category_dir.mkdir(parents=True, exist_ok=True)
    
    for category in df['category'].unique():
        category_df = df[df['category'] == category]
        category_path = category_dir / f'category={category}.parquet'
        category_df.to_parquet(category_path, compression='snappy', index=False)
    
    print(f"  Created {len(df['category'].unique())} partition files in {category_dir}")
    
    # Partition by date (daily)
    print("\nCreating partitioned dataset (by date)...")
    date_dir = partitioned_dir / 'by_date'
    date_dir.mkdir(parents=True, exist_ok=True)
    
    df['date'] = df['timestamp'].dt.date
    for date in df['date'].unique():
        date_df = df[df['date'] == date]
        date_path = date_dir / f'date={date}.parquet'
        date_df.drop('date', axis=1).to_parquet(date_path, compression='snappy', index=False)
    
    print(f"  Created {len(df['date'].unique())} partition files in {date_dir}")
    df.drop('date', axis=1, inplace=True)


def main():
    """Main function to generate and save the dataset."""
    
    print("=" * 80)
    print("DATASET GENERATION FOR INFRASTRUCTURE OPTIMIZATION")
    print("=" * 80)
    print(f"\nTarget dataset size: {DATASET_SIZE_GB} GB")
    print(f"Number of records: {NUM_RECORDS:,}")
    print(f"Output directory: {DATASET_DIR}")
    print("=" * 80)
    
    # Generate data
    df = generate_synthetic_data(NUM_RECORDS)
    
    print("\nDataset preview:")
    print(df.head(10))
    print(f"\nDataset shape: {df.shape}")
    print(f"Memory usage: {df.memory_usage(deep=True).sum() / (1024**2):.2f} MB")
    
    # Save dataset
    save_dataset(df, DATASET_DIR)
    
    # Create partitioned versions
    create_partitioned_dataset(df, DATASET_DIR)
    
    print("\n" + "=" * 80)
    print("DATASET GENERATION COMPLETE")
    print("=" * 80)
    print(f"\nYou can now run the pipeline:")
    print("  python pipeline.py")
    print("\nOr start the autonomous optimization loop:")
    print("  Follow the instructions in infrastructure_program.md")
    print("=" * 80)


if __name__ == '__main__':
    main()

# Made with Bob
