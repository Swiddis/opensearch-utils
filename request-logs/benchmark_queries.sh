#!/bin/bash

# Benchmark all example queries with hyperfine
# Usage: ./benchmark_queries.sh

set -euo pipefail

# Create output directory if it doesn't exist
mkdir -p bench-results

echo "Benchmarking all example queries..."
echo "===================================="
echo ""

# Query 1: Error Rate by Service and Environment
hyperfine --warmup 2 --runs 10 \
  --export-json bench-results/results_q1.json \
  'echo "source=request_logs | lookup dim_lookup.host host_key append service_name, environment, region | lookup dim_lookup.http_status status_key append status_code, status_category | where isnotnull(service_name) | stats sum(request_count) as total_requests, sum(is_error) as errors, avg(latency_ms) as avg_latency by service_name, environment | eval error_rate_pct = round(100.0 * errors / total_requests, 2) | where error_rate_pct > 0 | sort - error_rate_pct" | ppl > /dev/null'

# Query 2: Latency Percentiles by Region and Instance Type
hyperfine --warmup 2 --runs 10 \
  --export-json bench-results/results_q2.json \
  'echo "source=request_logs | lookup dim_lookup.host host_key append region, instance_type, service_name | where isnotnull(region) | stats count as requests, avg(latency_ms) as avg_latency, percentile(latency_ms, 50) as p50, percentile(latency_ms, 95) as p95, percentile(latency_ms, 99) as p99 by region, instance_type | sort - p99" | ppl > /dev/null'

# Query 3: Request Volume by Endpoint and Method (with spaces in multiplication)
hyperfine --warmup 2 --runs 10 \
  --export-json bench-results/results_q3.json \
  'echo "source=request_logs | lookup dim_lookup.endpoint endpoint_key append endpoint_pattern, http_method, resource_type, rate_limit_tier | where isnotnull(endpoint_pattern) | stats sum(request_count) as total_requests, sum(bytes_sent) as total_bytes_sent, avg(latency_ms) as avg_latency by endpoint_pattern, http_method | eval gb_sent = round(total_bytes_sent / (1024 * 1024 * 1024), 2) | sort - total_requests | head 20" | ppl > /dev/null'

# Query 4: Rate Limit Analysis by Tier
hyperfine --warmup 2 --runs 10 \
  --export-json bench-results/results_q4.json \
  'echo "source=request_logs | lookup dim_lookup.endpoint endpoint_key append rate_limit_tier, is_authenticated | lookup dim_lookup.http_status status_key append status_code | where isnotnull(rate_limit_tier) | eval rate_limited = if(status_code==429, 1, 0) | stats sum(request_count) as total_requests, sum(rate_limited) as rate_limited_requests by rate_limit_tier, is_authenticated | eval rate_limit_pct = round(100.0 * rate_limited_requests / total_requests, 2) | sort - rate_limit_pct" | ppl > /dev/null'

# Query 5: Traffic by Client Country and Device Type
hyperfine --warmup 2 --runs 10 \
  --export-json bench-results/results_q5.json \
  'echo "source=request_logs | lookup dim_lookup.client client_key append client_country, device_type, is_bot | where isnotnull(client_country) AND is_bot=\"False\" | stats sum(request_count) as requests, sum(bytes_sent) as bytes_sent, avg(latency_ms) as avg_latency by client_country, device_type | eval gb_sent = round(bytes_sent / (1024 * 1024 * 1024), 2) | sort - requests | head 25" | ppl > /dev/null'

# Query 6: Bot Traffic Analysis
hyperfine --warmup 2 --runs 10 \
  --export-json bench-results/results_q6.json \
  'echo "source=request_logs | lookup dim_lookup.client client_key append is_bot, user_agent_family, client_country | lookup dim_lookup.endpoint endpoint_key append endpoint_pattern, resource_type | where is_bot=\"True\" | stats sum(request_count) as bot_requests, DISTINCT_COUNT(client_key) as unique_bots by user_agent_family, resource_type | sort - bot_requests" | ppl > /dev/null'

# Query 7: Bandwidth Cost by Service and Region
hyperfine --warmup 2 --runs 10 \
  --export-json bench-results/results_q7.json \
  'echo "source=request_logs | lookup dim_lookup.host host_key append service_name, region, environment | where isnotnull(service_name) AND environment=\"prod\" | stats sum(bytes_sent) as total_bytes_sent, sum(request_count) as total_requests by service_name, region | eval gb_sent = round(total_bytes_sent / (1024 * 1024 * 1024), 2) | eval estimated_cost_usd = round(gb_sent * 0.09, 2) | sort - estimated_cost_usd" | ppl > /dev/null'

# Query 8: Compute Utilization by Cluster
hyperfine --warmup 2 --runs 10 \
  --export-json bench-results/results_q8.json \
  'echo "source=request_logs | lookup dim_lookup.host host_key append cluster_name, availability_zone, instance_type, service_name | where isnotnull(cluster_name) | stats sum(request_count) as requests, avg(latency_ms) as avg_latency, DISTINCT_COUNT(host_key) as unique_hosts by cluster_name, availability_zone | sort - requests" | ppl > /dev/null'

# Query 9: Business Hours vs Off-Hours Performance
hyperfine --warmup 2 --runs 10 \
  --export-json bench-results/results_q9.json \
  'echo "source=request_logs | lookup dim_lookup.time_of_day time_key append is_business_hour, time_period, hour_24 | lookup dim_lookup.host host_key append service_name, environment | where environment=\"prod\" AND isnotnull(service_name) | stats sum(request_count) as requests, avg(latency_ms) as avg_latency, sum(is_error) as errors by service_name, is_business_hour | eval error_rate_pct = round(100.0 * errors / requests, 2)" | ppl > /dev/null'

# Query 10: Weekend vs Weekday Traffic Patterns
hyperfine --warmup 2 --runs 10 \
  --export-json bench-results/results_q10.json \
  'echo "source=request_logs | lookup dim_lookup.date date_key append is_weekend, day_name | lookup dim_lookup.host host_key append service_name | where isnotnull(service_name) | stats sum(request_count) as requests, sum(bytes_sent) as bytes_sent, avg(latency_ms) as avg_latency by service_name, is_weekend | eval gb_sent = round(bytes_sent / (1024 * 1024 * 1024), 2)" | ppl > /dev/null'

# Query 11: Full Service Health Dashboard
hyperfine --warmup 2 --runs 10 \
  --export-json bench-results/results_q11.json \
  'echo "source=request_logs | lookup dim_lookup.host host_key append service_name, environment, region, instance_type | lookup dim_lookup.endpoint endpoint_key append endpoint_pattern, http_method | lookup dim_lookup.http_status status_key append status_category | lookup dim_lookup.client client_key append device_type, is_bot | where environment=\"prod\" AND isnotnull(service_name) AND is_bot=\"False\" | stats sum(request_count) as total_requests, sum(is_error) as errors, avg(latency_ms) as avg_latency, percentile(latency_ms, 95) as p95_latency, sum(bytes_sent) as total_bytes by service_name, region, endpoint_pattern | eval error_rate_pct = round(100.0 * errors / total_requests, 2) | eval gb_sent = round(total_bytes / (1024 * 1024 * 1024), 2) | where total_requests > 100 | sort - total_requests | head 50" | ppl > /dev/null'

# Query 12: Client Experience by Geography and Endpoint
hyperfine --warmup 2 --runs 10 \
  --export-json bench-results/results_q12.json \
  'echo "source=request_logs | lookup dim_lookup.client client_key append client_country, client_region, device_type, is_bot | lookup dim_lookup.endpoint endpoint_key append endpoint_pattern, resource_type | where is_bot=\"False\" AND isnotnull(client_country) | stats sum(request_count) as requests, avg(latency_ms) as avg_latency, percentile(latency_ms, 95) as p95_latency, sum(is_error) as errors by client_country, endpoint_pattern, device_type | eval error_rate_pct = round(100.0 * errors / requests, 2) | where requests > 50 | sort client_country, - requests" | ppl > /dev/null'

# Query 13: High-Value Endpoint Performance Analysis
hyperfine --warmup 2 --runs 10 \
  --export-json bench-results/results_q13.json \
  'echo "source=request_logs | lookup dim_lookup.endpoint endpoint_key append endpoint_pattern, is_authenticated, rate_limit_tier | lookup dim_lookup.host host_key append service_name, environment, region | lookup dim_lookup.http_status status_key append is_success | where is_authenticated=\"True\" AND environment=\"prod\" AND isnotnull(endpoint_pattern) | eval failure = if(is_success=\"False\", 1, 0) | stats sum(request_count) as requests, avg(latency_ms) as avg_latency, percentile(latency_ms, 95) as p95_latency, sum(failure) as failures by endpoint_pattern, service_name, rate_limit_tier | where requests > 1000 | eval failure_rate = round(100.0 * failures / requests, 2) | sort - p95_latency | head 20" | ppl > /dev/null'

# Query 14: Service Version Rollout Analysis
hyperfine --warmup 2 --runs 10 \
  --export-json bench-results/results_q14.json \
  'echo "source=request_logs | lookup dim_lookup.host host_key append service_name, service_version, environment, region | lookup dim_lookup.http_status status_key append status_code | where environment=\"prod\" AND isnotnull(service_version) | stats sum(request_count) as requests, sum(is_error) as errors, avg(latency_ms) as avg_latency, percentile(latency_ms, 99) as p99_latency, DISTINCT_COUNT(host_key) as host_count by service_name, service_version | eval error_rate_pct = round(100.0 * errors / requests, 2) | sort service_name, service_version" | ppl > /dev/null'

echo ""
echo "===================================="
echo "Benchmark complete! Results saved to bench-results/"
echo ""
echo "Summary:"
for i in {1..14}; do
  if [ -f "bench-results/results_q${i}.json" ]; then
    mean=$(jq -r '.results[0].mean' "bench-results/results_q${i}.json")
    echo "Query ${i}: ${mean}s"
  fi
done

