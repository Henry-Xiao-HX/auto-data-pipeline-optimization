"""
baseline_config.py - Fixed constants and evaluation harness for infrastructure optimization.
DO NOT MODIFY THIS FILE - it contains the ground truth evaluation metrics.
"""

import time
import psutil
import os
from pathlib import Path
from typing import Dict, Any, Optional
import hashlib
import threading
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# FIXED CONSTANTS
# ============================================================================

# Dataset configuration
# Use cache directory to keep generated datasets out of the repo
DATASET_DIR = Path.home() / '.cache' / 'auto-data'
DATASET_SIZE_GB = 1.0  # Size of test dataset
TIME_BUDGET_SECONDS = 300  # Time budget for optimization experiments

# Evaluation weights for efficiency score
# These weights balance the three optimization objectives:
# - WEIGHT_LATENCY (100.0): Moderate weight on speed. At 10s latency, contributes ~10 points.
#   Chosen to make latency improvements meaningful but not dominate the score.
# - WEIGHT_COST (1000.0): High weight on cost efficiency. At $0.01 cost, contributes ~100 points.
#   10x higher than latency because cost savings compound over many runs and are the primary
#   business metric. Encourages solutions that reduce cloud spend.
# - WEIGHT_RESOURCE (0.01): Low weight on resource health (0-100 scale). At 100 health, contributes ~1 point.
#   Serves as a tiebreaker and prevents pathological resource usage, but doesn't override
#   latency/cost tradeoffs. Health is a constraint, not a primary objective.
WEIGHT_LATENCY = 100.0    # Weight for 1/latency (higher = prioritize speed)
WEIGHT_COST = 1000.0      # Weight for 1/cost (higher = prioritize cost savings)
WEIGHT_RESOURCE = 0.01    # Weight for resource health (0-100 scale)

# Cost model (simplified cloud pricing per second of compute)
COST_PER_CORE_SECOND = 0.0001  # $0.0001 per core-second
COST_PER_GB_MEMORY_SECOND = 0.00001  # $0.00001 per GB-second
COST_PER_GB_IO = 0.0001  # $0.0001 per GB read/written

# Resource health thresholds
# MEMORY_HEALTHY_MAX_PCT (80.0): Conservative threshold to avoid memory pressure and swapping.
#   Above 80% memory usage, systems often experience performance degradation. Leaves 20% headroom
#   for OS and other processes. Penalty scales linearly from 80% to 95% (critical).
# CPU_HEALTHY_MAX_PCT (90.0): High threshold since CPU can safely burst to high utilization.
#   Unlike memory, high CPU doesn't cause crashes. 90% allows efficient resource use while
#   penalizing sustained thrashing. Penalty is gentler (50% max) than memory penalty (100% max).
MEMORY_HEALTHY_MAX_PCT = 80.0  # Memory usage below this is healthy
CPU_HEALTHY_MAX_PCT = 90.0     # CPU usage below this is healthy
MEMORY_CRITICAL_PCT = 95.0     # Critical memory threshold (near OOM)
CPU_MAX_PENALTY_PCT = 50.0     # Maximum CPU penalty percentage
HEALTH_MEMORY_WEIGHT = 0.6     # Weight for memory in health score
HEALTH_CPU_WEIGHT = 0.4        # Weight for CPU in health score

# ============================================================================
# EVALUATION FUNCTIONS
# ============================================================================

class ResourceMonitor:
    """Monitor CPU and memory usage during pipeline execution."""
    
    def __init__(self, sample_interval: float = 0.5):
        """
        Initialize the resource monitor.
        
        Args:
            sample_interval: Time in seconds between samples (default: 0.5s)
        """
        self.process = psutil.Process(os.getpid())
        self.peak_memory_gb = 0.0
        self.cpu_samples = []
        self.memory_samples = []
        self.sample_interval = sample_interval
        self._monitor_thread = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        
    def start(self):
        """Start monitoring resources in a background thread."""
        with self._lock:
            self.peak_memory_gb = 0.0
            self.cpu_samples = []
            self.memory_samples = []
        self._stop_event.clear()
        
        # Prime CPU measurement (first call returns 0.0)
        self.process.cpu_percent(interval=None)
        
        # Start background sampling thread
        self._monitor_thread = threading.Thread(target=self._sampling_loop, daemon=True)
        self._monitor_thread.start()
        
    def _sampling_loop(self):
        """Background thread that continuously samples resource usage."""
        while not self._stop_event.wait(self.sample_interval):
            self._sample()
    
    def _sample(self):
        """Take a sample of current resource usage."""
        try:
            # Memory usage in GB
            mem_info = self.process.memory_info()
            memory_gb = mem_info.rss / (1024 ** 3)
            
            # CPU usage percentage (non-blocking)
            cpu_pct = self.process.cpu_percent(interval=None)
            
            # Thread-safe update
            with self._lock:
                self.peak_memory_gb = max(self.peak_memory_gb, memory_gb)
                self.memory_samples.append(memory_gb)
                self.cpu_samples.append(cpu_pct)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # Process may have ended or we lost access
            pass
        
    def stop(self):
        """Stop monitoring and return statistics."""
        self._stop_event.set()
        
        # Wait for monitoring thread to finish
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=1.0)
        
        with self._lock:
            avg_cpu_pct = sum(self.cpu_samples) / len(self.cpu_samples) if self.cpu_samples else 0.0
            
            return {
                'peak_memory_gb': self.peak_memory_gb,
                'avg_cpu_pct': avg_cpu_pct,
                'num_samples': len(self.cpu_samples)
            }


def calculate_resource_health_score(peak_memory_gb: float, avg_cpu_pct: float,
                                    total_memory_gb: float) -> float:
    """
    Calculate resource health score (0-100).
    Higher is better. Penalizes high memory usage and CPU thrashing.
    """
    # Guard against invalid inputs
    if total_memory_gb <= 0:
        logger.warning(f"Invalid total_memory_gb: {total_memory_gb}")
        return 0.0
    
    # Memory health (0-100)
    memory_usage_pct = (peak_memory_gb / total_memory_gb) * 100
    if memory_usage_pct > MEMORY_CRITICAL_PCT:
        memory_health = 0.0  # Critical - near OOM
    elif memory_usage_pct > MEMORY_HEALTHY_MAX_PCT:
        # Linear penalty above healthy threshold
        memory_health = 100 - ((memory_usage_pct - MEMORY_HEALTHY_MAX_PCT) /
                               (MEMORY_CRITICAL_PCT - MEMORY_HEALTHY_MAX_PCT)) * 100
    else:
        memory_health = 100.0
    
    # CPU health (0-100)
    if avg_cpu_pct > CPU_HEALTHY_MAX_PCT:
        cpu_health = 100 - ((avg_cpu_pct - CPU_HEALTHY_MAX_PCT) /
                           (100 - CPU_HEALTHY_MAX_PCT)) * CPU_MAX_PENALTY_PCT
    else:
        cpu_health = 100.0
    
    # Combined health score (weighted average)
    health_score = HEALTH_MEMORY_WEIGHT * memory_health + HEALTH_CPU_WEIGHT * cpu_health
    return max(0.0, min(100.0, health_score))


def calculate_cost(latency_seconds: float, peak_memory_gb: float,
                   data_processed_gb: float, avg_cpu_pct: float = 100.0) -> float:
    """
    Calculate estimated cloud cost for the pipeline run.
    Simplified model based on compute time, memory, and I/O.
    Uses actual CPU utilization to calculate effective cores used.
    
    Args:
        latency_seconds: Total execution time
        peak_memory_gb: Peak memory usage
        data_processed_gb: Amount of data processed
        avg_cpu_pct: Average CPU utilization percentage (default: 100.0)
    """
    # Calculate effective cores used based on actual CPU utilization
    total_cores = psutil.cpu_count(logical=True) or 1
    effective_cores = total_cores * (avg_cpu_pct / 100.0)
    
    # Compute cost (effective core-seconds)
    compute_cost = effective_cores * latency_seconds * COST_PER_CORE_SECOND
    
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
        logger.warning(f"Invalid metrics for efficiency score: latency={latency_seconds}, cost={cost_dollars}")
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
    Uses SHA-256 for deterministic checksums.
    """
    try:
        # Try pandas DataFrame first
        if hasattr(data, 'to_dict'):
            # Convert to records and use JSON for deterministic serialization
            records = data.to_dict('records')
            # Sort records by tuple of all field values for true determinism
            # This ensures identical records maintain stable ordering
            def sort_key(record):
                # Create a tuple of all values, converting to strings for comparison
                return tuple(str(record.get(k, '')) for k in sorted(record.keys()))
            
            sorted_records = sorted(records, key=sort_key)
            data_str = json.dumps(sorted_records, sort_keys=True, default=str)
        else:
            # Fallback for other data types
            data_str = json.dumps(data, sort_keys=True, default=str)
        
        return hashlib.sha256(data_str.encode()).hexdigest()
    except Exception as e:
        logger.error(f"Error computing checksum: {e}")
        # Fallback to string representation
        return hashlib.sha256(str(data).encode()).hexdigest()


# ============================================================================
# EVALUATION HARNESS
# ============================================================================

def evaluate_pipeline(pipeline_func, dataset_path: Path, expected_checksum: Optional[str] = None) -> Dict[str, Any]:
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
    
    logger.info(f"Starting pipeline evaluation for {dataset_path}")
    
    # Start monitoring
    monitor.start()
    start_time = time.time()
    
    try:
        # Run the pipeline
        result = pipeline_func(dataset_path)
        
        logger.info(f"Pipeline completed successfully")
        
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
            data_processed_gb,
            resource_stats['avg_cpu_pct']
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
        logger.error(f"Pipeline crashed: {e}", exc_info=True)
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
