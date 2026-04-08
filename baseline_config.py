"""
baseline_config.py - Fixed constants and evaluation harness for infrastructure optimization.
DO NOT MODIFY THIS FILE - it contains the ground truth evaluation metrics.
"""

import time
import psutil
import os
from pathlib import Path
from typing import Dict, Any
import hashlib

# ============================================================================
# FIXED CONSTANTS
# ============================================================================

# Time budget for each experiment (wall clock seconds, excluding setup)
TIME_BUDGET_SECONDS = 300  # 5 minutes

# Dataset configuration
DATASET_DIR = Path.home() / ".cache" / "autoinfra" / "data"
DATASET_SIZE_GB = 1.0  # Size of test dataset
NUM_RECORDS = 1_000_000  # Number of records in dataset

# Evaluation weights for efficiency score
WEIGHT_LATENCY = 100.0    # Weight for 1/latency (higher = prioritize speed)
WEIGHT_COST = 1000.0      # Weight for 1/cost (higher = prioritize cost savings)
WEIGHT_RESOURCE = 0.01    # Weight for resource health (0-100 scale)

# Cost model (simplified cloud pricing per second of compute)
COST_PER_CORE_SECOND = 0.0001  # $0.0001 per core-second
COST_PER_GB_MEMORY_SECOND = 0.00001  # $0.00001 per GB-second
COST_PER_GB_IO = 0.0001  # $0.0001 per GB read/written

# Resource health thresholds
MEMORY_HEALTHY_MAX_PCT = 80.0  # Memory usage below this is healthy
CPU_HEALTHY_MAX_PCT = 90.0     # CPU usage below this is healthy

# Data schema
SCHEMA = {
    'user_id': 'int64',
    'timestamp': 'datetime64[ns]',
    'event_type': 'string',
    'value': 'float64',
    'category': 'string',
    'metadata': 'string'
}

# Query workload - what operations the pipeline must perform
QUERY_OPERATIONS = [
    'filter',      # Filter by date range and category
    'aggregate',   # Group by and aggregate
    'join',        # Join with dimension table
    'sort',        # Sort results
]

# ============================================================================
# EVALUATION FUNCTIONS
# ============================================================================

class ResourceMonitor:
    """Monitor CPU and memory usage during pipeline execution."""
    
    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.peak_memory_gb = 0.0
        self.cpu_samples = []
        self.memory_samples = []
        self.start_time = None
        self.monitoring = False
        
    def start(self):
        """Start monitoring resources."""
        self.start_time = time.time()
        self.monitoring = True
        self.peak_memory_gb = 0.0
        self.cpu_samples = []
        self.memory_samples = []
        
    def sample(self):
        """Take a sample of current resource usage."""
        if not self.monitoring:
            return
            
        # Memory usage in GB
        mem_info = self.process.memory_info()
        memory_gb = mem_info.rss / (1024 ** 3)
        self.peak_memory_gb = max(self.peak_memory_gb, memory_gb)
        self.memory_samples.append(memory_gb)
        
        # CPU usage percentage
        cpu_pct = self.process.cpu_percent(interval=0.1)
        self.cpu_samples.append(cpu_pct)
        
    def stop(self):
        """Stop monitoring and return statistics."""
        self.monitoring = False
        
        avg_memory_gb = sum(self.memory_samples) / len(self.memory_samples) if self.memory_samples else 0.0
        avg_cpu_pct = sum(self.cpu_samples) / len(self.cpu_samples) if self.cpu_samples else 0.0
        
        return {
            'peak_memory_gb': self.peak_memory_gb,
            'avg_memory_gb': avg_memory_gb,
            'avg_cpu_pct': avg_cpu_pct,
            'num_samples': len(self.cpu_samples)
        }


def calculate_resource_health_score(peak_memory_gb: float, avg_cpu_pct: float, 
                                    total_memory_gb: float) -> float:
    """
    Calculate resource health score (0-100).
    Higher is better. Penalizes high memory usage and CPU thrashing.
    """
    # Memory health (0-100)
    memory_usage_pct = (peak_memory_gb / total_memory_gb) * 100
    if memory_usage_pct > 95:
        memory_health = 0.0  # Critical - near OOM
    elif memory_usage_pct > MEMORY_HEALTHY_MAX_PCT:
        # Linear penalty above healthy threshold
        memory_health = 100 - ((memory_usage_pct - MEMORY_HEALTHY_MAX_PCT) / (95 - MEMORY_HEALTHY_MAX_PCT)) * 100
    else:
        memory_health = 100.0
    
    # CPU health (0-100)
    if avg_cpu_pct > CPU_HEALTHY_MAX_PCT:
        cpu_health = 100 - ((avg_cpu_pct - CPU_HEALTHY_MAX_PCT) / (100 - CPU_HEALTHY_MAX_PCT)) * 50
    else:
        cpu_health = 100.0
    
    # Combined health score (weighted average)
    health_score = 0.6 * memory_health + 0.4 * cpu_health
    return max(0.0, min(100.0, health_score))


def calculate_cost(latency_seconds: float, peak_memory_gb: float, 
                   data_processed_gb: float, num_cores: int = 1) -> float:
    """
    Calculate estimated cloud cost for the pipeline run.
    Simplified model based on compute time, memory, and I/O.
    """
    # Compute cost (core-seconds)
    compute_cost = num_cores * latency_seconds * COST_PER_CORE_SECOND
    
    # Memory cost (GB-seconds)
    memory_cost = peak_memory_gb * latency_seconds * COST_PER_GB_MEMORY_SECOND
    
    # I/O cost (GB read/written - assume 2x for read + write)
    io_cost = data_processed_gb * 2 * COST_PER_GB_IO
    
    total_cost = compute_cost + memory_cost + io_cost
    return total_cost


def calculate_efficiency_score(latency_seconds: float, cost_dollars: float, 
                               resource_health: float) -> float:
    """
    Calculate the efficiency score - the metric to maximize.
    
    efficiency_score = w1 * (1/latency) + w2 * (1/cost) + w3 * resource_health
    
    Higher is better.
    """
    if latency_seconds <= 0 or cost_dollars <= 0:
        return 0.0
    
    latency_component = WEIGHT_LATENCY * (1.0 / latency_seconds)
    cost_component = WEIGHT_COST * (1.0 / cost_dollars)
    resource_component = WEIGHT_RESOURCE * resource_health
    
    efficiency_score = latency_component + cost_component + resource_component
    return efficiency_score


def verify_data_correctness(result_checksum: str, expected_checksum: str) -> bool:
    """
    Verify that the pipeline output matches expected results.
    Returns True if data is correct, False otherwise.
    """
    return result_checksum == expected_checksum


def compute_result_checksum(data) -> str:
    """
    Compute a checksum of the pipeline result for correctness verification.
    """
    # Convert data to string representation and hash it
    # Sort by string representation to ensure deterministic ordering
    data_str = str(sorted(data.to_dict('records'), key=lambda x: str(sorted(x.items())))) if hasattr(data, 'to_dict') else str(data)
    return hashlib.md5(data_str.encode()).hexdigest()


# ============================================================================
# EVALUATION HARNESS
# ============================================================================

def evaluate_pipeline(pipeline_func, dataset_path: Path, expected_checksum: str | None = None) -> Dict[str, Any]:
    """
    Main evaluation function - runs the pipeline and computes all metrics.
    
    Args:
        pipeline_func: The pipeline function to evaluate
        dataset_path: Path to the input dataset
        expected_checksum: Expected checksum for correctness verification (optional)
    
    Returns:
        Dictionary with all evaluation metrics
    """
    monitor = ResourceMonitor()
    total_memory_gb = psutil.virtual_memory().total / (1024 ** 3)
    
    # Start monitoring
    monitor.start()
    start_time = time.time()
    
    try:
        # Run the pipeline
        result = pipeline_func(dataset_path)
        
        # Stop timing
        latency_seconds = time.time() - start_time
        
        # Stop monitoring and get resource stats
        resource_stats = monitor.stop()
        
        # Compute result checksum
        result_checksum = compute_result_checksum(result)
        
        # Verify correctness if expected checksum provided
        data_correct = True
        if expected_checksum:
            data_correct = verify_data_correctness(result_checksum, expected_checksum)
        
        # Calculate metrics
        data_processed_gb = DATASET_SIZE_GB  # Simplified - actual would track I/O
        cost_dollars = calculate_cost(
            latency_seconds, 
            resource_stats['peak_memory_gb'],
            data_processed_gb
        )
        
        resource_health = calculate_resource_health_score(
            resource_stats['peak_memory_gb'],
            resource_stats['avg_cpu_pct'],
            total_memory_gb
        )
        
        efficiency_score = calculate_efficiency_score(
            latency_seconds,
            cost_dollars,
            resource_health
        )
        
        # Calculate throughput
        throughput_mb_s = (data_processed_gb * 1024) / latency_seconds if latency_seconds > 0 else 0.0
        
        return {
            'efficiency_score': efficiency_score,
            'latency_seconds': latency_seconds,
            'cost_dollars': cost_dollars,
            'resource_health': resource_health,
            'throughput_mb_s': throughput_mb_s,
            'data_processed_gb': data_processed_gb,
            'peak_memory_gb': resource_stats['peak_memory_gb'],
            'cpu_utilization_pct': resource_stats['avg_cpu_pct'],
            'data_correct': data_correct,
            'result_checksum': result_checksum,
            'status': 'success'
        }
        
    except Exception as e:
        # Pipeline crashed
        monitor.stop()
        return {
            'efficiency_score': 0.0,
            'latency_seconds': 0.0,
            'cost_dollars': 0.0,
            'resource_health': 0.0,
            'throughput_mb_s': 0.0,
            'data_processed_gb': 0.0,
            'peak_memory_gb': 0.0,
            'cpu_utilization_pct': 0.0,
            'data_correct': False,
            'result_checksum': '',
            'status': 'crash',
            'error': str(e)
        }


def print_results(metrics: Dict[str, Any]):
    """Print results in the standard format."""
    print("---")
    print(f"efficiency_score:     {metrics['efficiency_score']:.4f}")
    print(f"latency_seconds:      {metrics['latency_seconds']:.1f}")
    print(f"cost_dollars:         {metrics['cost_dollars']:.4f}")
    print(f"resource_health:      {metrics['resource_health']:.1f}")
    print(f"throughput_mb_s:      {metrics['throughput_mb_s']:.1f}")
    print(f"data_processed_gb:    {metrics['data_processed_gb']:.1f}")
    print(f"peak_memory_gb:       {metrics['peak_memory_gb']:.1f}")
    print(f"cpu_utilization_pct:  {metrics['cpu_utilization_pct']:.1f}")
    if 'data_correct' in metrics:
        print(f"data_correct:         {metrics['data_correct']}")
    if metrics['status'] == 'crash':
        print(f"status:               CRASH")
        print(f"error:                {metrics.get('error', 'Unknown error')}")

# Made with Bob
