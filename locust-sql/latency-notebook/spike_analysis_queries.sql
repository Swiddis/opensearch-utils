-- Latency Spike Analysis Queries
-- Quick reference for investigating load test spikes
-- Usage: sqlite3 query_response_times.db < spike_analysis_queries.sql
-- Or copy individual queries and run with your parameters

-- =============================================================================
-- CONFIGURATION - Update these for your analysis
-- =============================================================================
-- RUN_ID: '9e5f2898-cd96-4eb9-84d6-8f5ca9782a65'
-- SPIKE_START: '2026-03-31T18:08:00+00:00'
-- SPIKE_END: '2026-03-31T18:11:00+00:00'


-- =============================================================================
-- 1. GET RUN OVERVIEW
-- =============================================================================
-- Check timestamp range and total requests in the run

SELECT
  MIN(timestamp) as earliest,
  MAX(timestamp) as latest,
  COUNT(*) as total_records,
  SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures
FROM response_times
WHERE run_id = '9e5f2898-cd96-4eb9-84d6-8f5ca9782a65';


-- =============================================================================
-- 2. LATENCY TIMELINE (BY MINUTE)
-- =============================================================================
-- View average latency per minute to identify spike periods

SELECT
  strftime('%H:%M', timestamp) as time,
  COUNT(*) as count,
  ROUND(AVG(response_time_ms), 2) as avg_ms,
  ROUND(MIN(response_time_ms), 2) as min_ms,
  ROUND(MAX(response_time_ms), 2) as max_ms,
  SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures
FROM response_times
WHERE run_id = '9e5f2898-cd96-4eb9-84d6-8f5ca9782a65'
GROUP BY strftime('%H:%M', timestamp)
ORDER BY time;


-- =============================================================================
-- 3. COMPARE SPIKE VS BASELINE (SLOWDOWN RATIO)
-- =============================================================================
-- Find which queries had the biggest slowdown during the spike
-- This uses temp tables for clarity

CREATE TEMP TABLE spike_stats AS
SELECT
  query_name,
  COUNT(*) as spike_count,
  AVG(response_time_ms) as spike_avg,
  MAX(response_time_ms) as spike_max,
  MIN(response_time_ms) as spike_min
FROM response_times
WHERE run_id = '9e5f2898-cd96-4eb9-84d6-8f5ca9782a65'
  AND timestamp >= '2026-03-31T18:08:00+00:00'
  AND timestamp <= '2026-03-31T18:11:00+00:00'
GROUP BY query_name;

CREATE TEMP TABLE baseline_stats AS
SELECT
  query_name,
  COUNT(*) as baseline_count,
  AVG(response_time_ms) as baseline_avg,
  MAX(response_time_ms) as baseline_max,
  MIN(response_time_ms) as baseline_min
FROM response_times
WHERE run_id = '9e5f2898-cd96-4eb9-84d6-8f5ca9782a65'
  AND (timestamp < '2026-03-31T18:08:00+00:00' OR timestamp > '2026-03-31T18:11:00+00:00')
GROUP BY query_name;

-- Show queries with highest slowdown ratio
SELECT
  s.query_name,
  ROUND(s.spike_avg, 2) as spike_avg_ms,
  ROUND(b.baseline_avg, 2) as baseline_avg_ms,
  ROUND(s.spike_avg / b.baseline_avg, 2) as slowdown_ratio,
  s.spike_count,
  ROUND(s.spike_max, 2) as spike_max_ms
FROM spike_stats s
JOIN baseline_stats b ON s.query_name = b.query_name
WHERE b.baseline_count > 10
ORDER BY slowdown_ratio DESC
LIMIT 20;

-- Show queries with highest absolute latency during spike
SELECT
  s.query_name,
  ROUND(s.spike_avg, 2) as spike_avg_ms,
  ROUND(b.baseline_avg, 2) as baseline_avg_ms,
  ROUND(s.spike_avg / b.baseline_avg, 2) as slowdown_ratio,
  s.spike_count,
  ROUND(s.spike_max, 2) as spike_max_ms
FROM spike_stats s
JOIN baseline_stats b ON s.query_name = b.query_name
WHERE b.baseline_count > 10
ORDER BY spike_avg_ms DESC
LIMIT 20;


-- =============================================================================
-- 4. ANALYZE SPECIFIC TIME WINDOW
-- =============================================================================
-- Look at the slowest queries during a short window (e.g., P50 spike moment)

SELECT
  query_name,
  strftime('%H:%M:%S', timestamp) as time,
  ROUND(response_time_ms, 2) as ms,
  success
FROM response_times
WHERE run_id = '9e5f2898-cd96-4eb9-84d6-8f5ca9782a65'
  AND timestamp >= '2026-03-31T18:09:30+00:00'
  AND timestamp <= '2026-03-31T18:09:40+00:00'
ORDER BY response_time_ms DESC
LIMIT 30;


-- =============================================================================
-- 5. DEEP DIVE ON SPECIFIC QUERY
-- =============================================================================
-- Analyze how a specific problematic query performed over time

SELECT
  strftime('%H:%M', timestamp) as time,
  COUNT(*) as count,
  ROUND(AVG(response_time_ms), 2) as avg_ms,
  ROUND(MIN(response_time_ms), 2) as min_ms,
  ROUND(MAX(response_time_ms), 2) as max_ms,
  SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures
FROM response_times
WHERE run_id = '9e5f2898-cd96-4eb9-84d6-8f5ca9782a65'
  AND query_name = 'multi_terms_keyword'  -- UPDATE THIS
GROUP BY strftime('%H:%M', timestamp)
ORDER BY time;


-- =============================================================================
-- 6. PATTERN ANALYSIS - HEADLESS VS NON-HEADLESS
-- =============================================================================
-- Compare performance between headless and regular queries

SELECT
  CASE
    WHEN s.query_name LIKE '%headless%' THEN 'headless'
    ELSE 'regular'
  END as query_type,
  COUNT(DISTINCT s.query_name) as num_queries,
  ROUND(AVG(s.spike_avg / b.baseline_avg), 2) as avg_slowdown_ratio,
  ROUND(AVG(s.spike_avg), 2) as avg_spike_ms,
  ROUND(AVG(b.baseline_avg), 2) as avg_baseline_ms
FROM spike_stats s
JOIN baseline_stats b ON s.query_name = b.query_name
WHERE b.baseline_count > 10
GROUP BY query_type;


-- =============================================================================
-- 7. PERCENTILE ANALYSIS
-- =============================================================================
-- Get p50, p95, p99 for the entire run

-- P50 (median)
SELECT
  'p50' as percentile,
  ROUND(response_time_ms, 2) as value_ms
FROM response_times
WHERE run_id = '9e5f2898-cd96-4eb9-84d6-8f5ca9782a65'
ORDER BY response_time_ms
LIMIT 1 OFFSET (SELECT COUNT(*) FROM response_times WHERE run_id = '9e5f2898-cd96-4eb9-84d6-8f5ca9782a65') / 2;

-- P95
SELECT
  'p95' as percentile,
  ROUND(response_time_ms, 2) as value_ms
FROM response_times
WHERE run_id = '9e5f2898-cd96-4eb9-84d6-8f5ca9782a65'
ORDER BY response_time_ms
LIMIT 1 OFFSET (SELECT COUNT(*) FROM response_times WHERE run_id = '9e5f2898-cd96-4eb9-84d6-8f5ca9782a65') * 95 / 100;

-- P99
SELECT
  'p99' as percentile,
  ROUND(response_time_ms, 2) as value_ms
FROM response_times
WHERE run_id = '9e5f2898-cd96-4eb9-84d6-8f5ca9782a65'
ORDER BY response_time_ms
LIMIT 1 OFFSET (SELECT COUNT(*) FROM response_times WHERE run_id = '9e5f2898-cd96-4eb9-84d6-8f5ca9782a65') * 99 / 100;


-- =============================================================================
-- 8. LIST ALL RUNS
-- =============================================================================
-- See all available runs in the database

SELECT
  run_id,
  start_time,
  end_time,
  status,
  ROUND((julianday(end_time) - julianday(start_time)) * 86400, 2) as duration_seconds
FROM runs
ORDER BY start_time DESC;
