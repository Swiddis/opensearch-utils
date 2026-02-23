# PPL Query Generation Test Prompts

This document provides three difficulty levels of prompts for each analytics query in `example_queries.md`. Use these to test a model's ability to generate PPL queries from natural language requests.

**Difficulty Levels:**
- **Easy**: Procedural, specific instructions with explicit field names and operations
- **Medium**: Business-focused with some technical details but less prescriptive
- **Hard**: Fuzzy, high-level business questions requiring interpretation

---

## 1. Error Rate by Service and Environment

### Easy
"Join the request_logs to the hosts dimension table on host_key to get service_name and environment. Then join to http_status on status_key to get status_category. Filter out null service names. Group by service_name and environment, computing sum of request_count as total_requests, sum of is_error as errors, and average latency_ms. Calculate error_rate_pct as 100 * errors / total_requests rounded to 2 decimals. Filter to only rows where error_rate_pct > 0 and sort descending by error_rate_pct."

### Medium
"Show me error rates by service and environment. I need to see total requests, error counts, and average latency for each service-environment combination. Calculate the error rate as a percentage and only show services that have errors. Sort by highest error rate first."

### Hard
"Which services are having problems?"

---

## 2. Latency Percentiles by Region and Instance Type

### Easy
"From request_logs, lookup the hosts dimension to append region, instance_type, and service_name fields. Filter to non-null regions. Group by region and instance_type, calculating count as requests, avg(latency_ms), and the 50th, 95th, and 99th percentiles of latency_ms. Sort descending by p99."

### Medium
"Analyze performance across different regions and instance types. Show me request counts and latency percentiles (p50, p95, p99) grouped by region and instance type. Sort by worst p99 latency first."

### Hard
"Where is our infrastructure slow?"

---

## 3. Request Volume by Endpoint and Method

### Easy
"Join request_logs to endpoints dimension on endpoint_key to get endpoint_pattern, http_method, resource_type, and rate_limit_tier. Filter out null endpoint_patterns. Group by endpoint_pattern and http_method, summing request_count as total_requests, bytes_sent as total_bytes_sent, and averaging latency_ms. Calculate gb_sent as total_bytes_sent divided by 1024^3 rounded to 2 decimals. Sort descending by total_requests and limit to top 20."

### Medium
"Show me the top 20 most-used API endpoints with their HTTP methods. Include total requests, bandwidth sent in GB, and average latency. Sort by request volume."

### Hard
"What are our busiest APIs?"

---

## 4. Rate Limit Analysis by Tier

### Easy
"From request_logs, lookup endpoints to get rate_limit_tier and is_authenticated, then lookup http_status to get status_code. Filter to non-null rate_limit_tier. Create a calculated field rate_limited that equals 1 if status_code is 429, else 0. Group by rate_limit_tier and is_authenticated, summing request_count and rate_limited. Calculate rate_limit_pct as 100 * rate_limited_requests / total_requests rounded to 2 decimals. Sort descending by rate_limit_pct."

### Medium
"Analyze rate limiting across different API tiers. Show me how often each tier (free, premium, enterprise) hits rate limits, broken down by authenticated vs unauthenticated requests. Calculate the percentage of requests that get rate limited."

### Hard
"Are we rate limiting too aggressively?"

---

## 5. Traffic by Client Country and Device Type

### Easy
"Join request_logs to clients dimension on client_key to append client_country, device_type, and is_bot. Filter to non-null client_country and is_bot='False'. Group by client_country and device_type, summing request_count as requests and bytes_sent, and averaging latency_ms. Calculate gb_sent as bytes_sent / (1024^3) rounded to 2 decimals. Sort descending by requests and take top 25."

### Medium
"Show me traffic patterns by country and device type, excluding bots. Include request counts, bandwidth in GB, and average latency. Give me the top 25 by request volume."

### Hard
"Where are our users coming from?"

---

## 6. Bot Traffic Analysis

### Easy
"From request_logs, lookup clients to get is_bot, user_agent_family, and client_country, then lookup endpoints to get endpoint_pattern and resource_type. Filter to is_bot='True'. Group by user_agent_family and resource_type, summing request_count as bot_requests and counting distinct client_key as unique_bots. Sort descending by bot_requests."

### Medium
"Analyze bot traffic patterns. Show me which user agents and what types of resources they're accessing. Include total bot requests and unique bot count grouped by user agent and resource type."

### Hard
"What are bots doing on our platform?"

---

## 7. Bandwidth Cost by Service and Region

### Easy
"Join request_logs to hosts on host_key to get service_name, region, and environment. Filter to non-null service_name and environment='prod'. Group by service_name and region, summing bytes_sent as total_bytes_sent and request_count as total_requests. Calculate gb_sent as total_bytes_sent / (1024^3) rounded to 2 decimals, and estimated_cost_usd as gb_sent * 0.09 rounded to 2 decimals. Sort descending by estimated_cost_usd."

### Medium
"Calculate bandwidth costs for production services by region. Assume $0.09 per GB. Show me total GB sent and estimated costs grouped by service and region, sorted by highest cost."

### Hard
"Which services cost the most in bandwidth?"

---

## 8. Compute Utilization by Cluster

### Easy
"From request_logs, lookup hosts to append cluster_name, availability_zone, instance_type, and service_name. Filter to non-null cluster_name. Group by cluster_name and availability_zone, summing request_count as requests, averaging latency_ms, and counting distinct host_key as unique_hosts. Sort descending by requests."

### Medium
"Show me how requests are distributed across clusters and availability zones. Include request counts, average latency, and number of unique hosts per cluster-AZ combination."

### Hard
"Is our load balanced properly?"

---

## 9. Business Hours vs Off-Hours Performance

### Easy
"Join request_logs to time_of_day dimension on time_key to get is_business_hour, time_period, and hour_24. Join to hosts on host_key to get service_name and environment. Filter to environment='prod' and non-null service_name. Group by service_name and is_business_hour, summing request_count as requests, averaging latency_ms, and summing is_error as errors. Calculate error_rate_pct as 100 * errors / requests rounded to 2 decimals."

### Medium
"Compare production service performance during business hours versus off-hours. Show me request volume, average latency, and error rates for each service, grouped by whether it's business hours or not."

### Hard
"Does performance change during the day?"

---

## 10. Weekend vs Weekday Traffic Patterns

### Easy
"From request_logs, lookup dates dimension on date_key to append is_weekend and day_name. Lookup hosts on host_key to get service_name. Filter to non-null service_name. Group by service_name and is_weekend, summing request_count as requests and bytes_sent, and averaging latency_ms. Calculate gb_sent as bytes_sent / (1024^3) rounded to 2 decimals."

### Medium
"Analyze weekend versus weekday traffic patterns by service. Show me request counts, bandwidth in GB, and average latency for each service, comparing weekends to weekdays."

### Hard
"How does weekend traffic differ?"

---

## 11. Full Service Health Dashboard

### Easy
"Join request_logs to hosts (get service_name, environment, region, instance_type), endpoints (get endpoint_pattern, http_method), http_status (get status_category), and clients (get device_type, is_bot). Filter to environment='prod', non-null service_name, and is_bot='False'. Group by service_name, region, and endpoint_pattern, calculating sum of request_count, sum of is_error, avg and p95 of latency_ms, and sum of bytes_sent. Calculate error_rate_pct as 100 * errors / total_requests and gb_sent as total_bytes / (1024^3), both rounded to 2 decimals. Filter to total_requests > 100, sort descending by total_requests, limit to 50."

### Medium
"Create a comprehensive service health view for production. Join request logs with hosts, endpoints, status, and client data. Show request volume, error rates, latency metrics (avg and p95), and bandwidth by service, region, and endpoint. Exclude bots and low-traffic endpoints (under 100 requests). Give me the top 50 by request volume."

### Hard
"Give me a complete picture of service health."

---

## 12. Client Experience by Geography and Endpoint

### Easy
"From request_logs, lookup clients to get client_country, client_region, device_type, and is_bot. Lookup endpoints to get endpoint_pattern and resource_type. Lookup http_status to get is_error. Filter to is_bot='False' and non-null client_country. Group by client_country, endpoint_pattern, and device_type, summing request_count as requests and is_error as errors, and calculating avg and p95 of latency_ms. Calculate error_rate_pct as 100 * errors / requests rounded to 2 decimals. Filter to requests > 50 and sort by client_country, then descending by requests."

### Medium
"Analyze user experience across different countries and endpoints. Show me request volume, latency percentiles, and error rates grouped by country, endpoint, and device type. Exclude bots and low-traffic combinations (under 50 requests). Sort by country and request volume."

### Hard
"How is the experience for users in different countries?"

---

## 13. High-Value Endpoint Performance Analysis

### Easy
"Join request_logs to endpoints (get endpoint_pattern, is_authenticated, rate_limit_tier), hosts (get service_name, environment, region), and http_status (get is_success). Filter to is_authenticated='True', environment='prod', and non-null endpoint_pattern. Create calculated field failure as 1 if is_success='False' else 0. Group by endpoint_pattern, service_name, and rate_limit_tier, summing request_count as requests and failure as failures, and calculating avg and p95 of latency_ms. Filter to requests > 1000. Calculate failure_rate as 100 * failures / requests rounded to 2 decimals. Sort descending by p95_latency and limit to top 20."

### Medium
"Find slow, high-traffic authenticated endpoints in production. Show me endpoints with over 1000 requests, including their service, rate limit tier, latency metrics (avg and p95), and failure rates. Sort by worst p95 latency and give me the top 20."

### Hard
"Which important APIs are performing poorly?"

---

## 14. Service Version Rollout Analysis

### Easy
"From request_logs, lookup hosts to get service_name, service_version, environment, and region. Lookup http_status to get status_code. Filter to environment='prod' and non-null service_version. Group by service_name and service_version, summing request_count as requests and is_error as errors, averaging latency_ms, calculating p99 of latency_ms, and counting distinct host_key as host_count. Calculate error_rate_pct as 100 * errors / requests rounded to 2 decimals. Sort by service_name then service_version."

### Medium
"Compare performance across different service versions in production. Show me request volume, error rates, latency metrics (avg and p99), and host counts for each service version. Sort by service name and version."

### Hard
"How are different versions performing?"
