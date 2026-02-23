# Example Analytics Queries

This document contains example queries for the dimensional request logs. The generated data includes realistic patterns to make analytics queries produce interesting, actionable results.

## Realistic Patterns in the Data

The log generator creates the following realistic patterns:

### Error Rate Patterns
- **payment-service**: 10-15% error rate (simulates external payment gateway issues)
- **inventory-service**: 7-10% error rate (simulates database load issues, 503 errors)
- **notification-service**: 5-8% error rate (simulates timeout issues with external services)
- **order-service**: ~5% error rate (moderate complexity)
- **Other services**: 2-4% error rate (baseline)
- **POST/PUT/PATCH requests**: ~80% higher error rate than GET requests
- **Free tier endpoints**: Higher rate limiting (429 errors)
- **Bot traffic**: 2.5x more 4xx errors (bad requests, rate limits)

### Latency Patterns
- **Instance types**: c5.* (fastest, -30%), m5.* (baseline), t3.* (slower, +40%)
- **Regions**: us-east-1 (fastest, -10%), us-west-2 (baseline), ap-southeast-1/eu-central-1 (+30%)
- **Service versions**: v1.x (+50% latency), v2.x (baseline), v3.x (-15% latency)
- **Services**: payment-service (+60%), notification-service (+40%), inventory-service (+20%)
- **Geographic distance**: Japan/Brazil/Australia clients (+40%), Europe (+20%)
- **Time patterns**: Business hours +15% latency, weekends -15% latency
- **Error states**: Server errors have 4x higher latency

### Traffic Distribution
- **Countries**: US-dominated (~40%), UK (~15%), Germany (~10%), others (~5-10%)
- **Bot traffic**: ~15% of all requests, targets public endpoints
- **Rate limiting**: Free tier and bots hit 429 errors much more frequently

### Resource Patterns
- **POST/PUT/PATCH**: Include request bodies (100-50KB)
- **Successful responses**: Larger response bodies (200B-100KB)
- **Error responses**: Small response bodies (50-500B)

These patterns enable queries to produce insights like:
- "payment-service on t3.large in eu-central-1 has high latency"
- "Upgrading from v1.x to v3.x reduced errors by 40%"
- "Free tier users experience 10x more rate limiting than premium"
- "Weekend performance is 15% better due to reduced load"

---

## Service Health & Error Analysis

### 1. Error Rate by Service and Environment

Track which services and environments are experiencing errors.

**Expected Pattern**: `payment-service` should show highest error rates (~10-15%), followed by `inventory-service` (~7-10%) and `notification-service` (~5-8%). Other services should have lower error rates (~2-5%). Off-peak hours should show lower error rates.

```ppl
source=request_logs
| lookup hosts host_key append service_name, environment, region
| lookup http_status status_key append status_code, status_category
| where isnotnull(service_name)
| stats
    sum(request_count) as total_requests,
    sum(is_error) as errors,
    avg(latency_ms) as avg_latency
    by service_name, environment
| eval error_rate_pct = round(100.0 * errors / total_requests, 2)
| where error_rate_pct > 0
| sort - error_rate_pct
```

**Use Case**: Identify services with high error rates to prioritize incident response.

---

### 2. Latency Percentiles by Region and Instance Type

Analyze performance across different infrastructure configurations.

**Expected Pattern**: `c5.*` instances should show lowest latency, `t3.*` instances highest. `us-east-1` should be fastest, `ap-southeast-1` and `eu-central-1` slower. Payment/notification services will have higher latency overall.

```ppl
source=request_logs
| lookup hosts host_key
    append region, instance_type, service_name
| where isnotnull(region)
| stats
    count as requests,
    avg(latency_ms) as avg_latency,
    percentile(latency_ms, 50) as p50,
    percentile(latency_ms, 95) as p95,
    percentile(latency_ms, 99) as p99
    by region, instance_type
| sort - p99
```

**Use Case**: Capacity planning - identify if certain regions or instance types need scaling.

---

## API Usage & Rate Limiting

### 3. Request Volume by Endpoint and Method

Understand which API endpoints are most heavily used.

```ppl
source=request_logs
| lookup endpoints endpoint_key
    append endpoint_pattern, http_method, resource_type, rate_limit_tier
| where isnotnull(endpoint_pattern)
| stats
    sum(request_count) as total_requests,
    sum(bytes_sent) as total_bytes_sent,
    avg(latency_ms) as avg_latency
    by endpoint_pattern, http_method
| eval gb_sent = round(total_bytes_sent / (1024 * 1024 * 1024), 2)
| sort - total_requests
| head 20
```

**Use Case**: Identify hot paths for caching or optimization.

---

### 4. Rate Limit Analysis by Tier

Track API usage patterns across different rate limit tiers.

**Expected Pattern**: `free` tier should show significantly higher rate limiting (429 errors) compared to other tiers. Bot traffic will also show elevated rate limiting.

```ppl
source=request_logs
| lookup endpoints endpoint_key
    append rate_limit_tier, is_authenticated
| lookup http_status status_key
    append status_code
| where isnotnull(rate_limit_tier)
| eval rate_limited = if(status_code==429, 1, 0)
| stats
    sum(request_count) as total_requests,
    sum(rate_limited) as rate_limited_requests
    by rate_limit_tier, is_authenticated
| eval rate_limit_pct = round(100.0 * rate_limited_requests / total_requests, 2)
| sort - rate_limit_pct
```

**Use Case**: Determine if rate limits need adjustment for different tiers.

---

## Client & Traffic Analysis

### 5. Traffic by Client Country and Device Type

Geographic and device analysis for capacity planning.

**Expected Pattern**: United States should dominate traffic (~40%). Clients from Japan, Brazil, and Australia will show higher latency. Mobile/Desktop mix should be present.

```ppl
source=request_logs
| lookup clients client_key
    append client_country, device_type, is_bot
| where isnotnull(client_country) AND is_bot="False"
| stats
    sum(request_count) as requests,
    sum(bytes_sent) as bytes_sent,
    avg(latency_ms) as avg_latency
    by client_country, device_type
| eval gb_sent = round(bytes_sent / (1024 * 1024 * 1024), 2)
| sort - requests
| head 25
```

**Use Case**: Determine where to deploy regional CDN nodes or edge infrastructure.

---

### 6. Bot Traffic Analysis

Identify and analyze automated traffic patterns.

```ppl
source=request_logs
| lookup clients client_key
    append is_bot, user_agent_family, client_country
| lookup endpoints endpoint_key
    append endpoint_pattern, resource_type
| where is_bot="True"
| stats
    sum(request_count) as bot_requests,
    DISTINCT_COUNT(client_key) as unique_bots
    by user_agent_family, resource_type
| sort - bot_requests
```

**Use Case**: Understand bot behavior to optimize rate limiting or blocking policies.

---

## Cost & Resource Analysis

### 7. Bandwidth Cost by Service and Region

Calculate data transfer costs across services.

```ppl
source=request_logs
| lookup hosts host_key
    append service_name, region, environment
| where isnotnull(service_name) AND environment="prod"
| stats
    sum(bytes_sent) as total_bytes_sent,
    sum(request_count) as total_requests
    by service_name, region
| eval gb_sent = round(total_bytes_sent / (1024 * 1024 * 1024), 2)
| eval estimated_cost_usd = round(gb_sent * 0.09, 2)
| sort - estimated_cost_usd
```

**Use Case**: Cloud cost optimization - identify high bandwidth services for optimization.

---

### 8. Compute Utilization by Cluster

Track request distribution across clusters and availability zones.

```ppl
source=request_logs
| lookup hosts host_key
    append cluster_name, availability_zone, instance_type, service_name
| where isnotnull(cluster_name)
| stats
    sum(request_count) as requests,
    avg(latency_ms) as avg_latency,
    DISTINCT_COUNT(host_key) as unique_hosts
    by cluster_name, availability_zone
| sort - requests
```

**Use Case**: Load balancing - ensure even distribution across AZs.

---

## Time-Based Analysis

### 9. Business Hours vs Off-Hours Performance

Compare performance during business hours.

**Expected Pattern**: Business hours (9am-5pm) should show ~15% higher latency and slightly higher error rates due to increased load. Off-hours will have better performance.

```ppl
source=request_logs
| lookup time_of_day time_key
    append is_business_hour, time_period, hour_24
| lookup hosts host_key
    append service_name, environment
| where environment="prod" AND isnotnull(service_name)
| stats
    sum(request_count) as requests,
    avg(latency_ms) as avg_latency,
    sum(is_error) as errors
    by service_name, is_business_hour
| eval error_rate_pct = round(100.0 * errors / requests, 2)
```

**Use Case**: Identify if batch jobs or off-hours maintenance impact performance.

---

### 10. Weekend vs Weekday Traffic Patterns

Analyze traffic patterns for capacity planning.

**Expected Pattern**: Weekend traffic should show ~15% lower latency due to reduced load. Overall traffic volume may vary by service (e.g., consumer services might maintain volume, B2B services drop).

```ppl
source=request_logs
| lookup dates date_key
    append is_weekend, day_name
| lookup hosts host_key
    append service_name
| where isnotnull(service_name)
| stats
    sum(request_count) as requests,
    sum(bytes_sent) as bytes_sent,
    avg(latency_ms) as avg_latency
    by service_name, is_weekend
| eval gb_sent = round(bytes_sent / (1024 * 1024 * 1024), 2)
```

**Use Case**: Right-size infrastructure for weekend vs weekday traffic.

---

## Multi-Dimensional Analysis

### 11. Full Service Health Dashboard

Comprehensive view combining multiple dimensions.

```ppl
source=request_logs
| lookup hosts host_key
    append service_name, environment, region, instance_type
| lookup endpoints endpoint_key
    append endpoint_pattern, http_method
| lookup http_status status_key
    append status_category
| lookup clients client_key
    append device_type, is_bot
| where environment="prod"
    AND isnotnull(service_name)
    AND is_bot="False"
| stats
    sum(request_count) as total_requests,
    sum(is_error) as errors,
    avg(latency_ms) as avg_latency,
    percentile(latency_ms, 95) as p95_latency,
    sum(bytes_sent) as total_bytes
    by service_name, region, endpoint_pattern
| eval error_rate_pct = round(100.0 * errors / total_requests, 2)
| eval gb_sent = round(total_bytes / (1024 * 1024 * 1024), 2)
| where total_requests > 100
| sort - total_requests
| head 50
```

**Use Case**: Executive dashboard showing service health, performance, and scale.

---

### 12. Client Experience by Geography and Endpoint

Understand user experience across different regions and APIs.

```ppl
source=request_logs
| lookup clients client_key
    append client_country, client_region, device_type, is_bot
| lookup endpoints endpoint_key
    append endpoint_pattern, resource_type
| lookup http_status status_key
    append is_error
| where is_bot="False" AND isnotnull(client_country)
| stats
    sum(request_count) as requests,
    avg(latency_ms) as avg_latency,
    percentile(latency_ms, 95) as p95_latency,
    sum(is_error) as errors
    by client_country, endpoint_pattern, device_type
| eval error_rate_pct = round(100.0 * errors / requests, 2)
| where requests > 50
| sort client_country, - requests
```

**Use Case**: Identify geographic regions with poor user experience for CDN optimization.

---

## Advanced: Multiple Lookups with Filtering

### 13. High-Value Endpoint Performance Analysis

Find slow, high-traffic authenticated endpoints.

```ppl
source=request_logs
| lookup endpoints endpoint_key
    append endpoint_pattern, is_authenticated, rate_limit_tier
| lookup hosts host_key
    append service_name, environment, region
| lookup http_status status_key
    append is_success
| where is_authenticated="True"
    AND environment="prod"
    AND isnotnull(endpoint_pattern)
| eval failure = if(is_success="False", 1, 0)
| stats
    sum(request_count) as requests,
    avg(latency_ms) as avg_latency,
    percentile(latency_ms, 95) as p95_latency,
    sum(failure) as failures
    by endpoint_pattern, service_name, rate_limit_tier
| where requests > 1000
| eval failure_rate = round(100.0 * failures / requests, 2)
| sort - p95_latency
| head 20
```

**Use Case**: Prioritize optimization work on high-impact authenticated endpoints.

---

### 14. Service Version Rollout Analysis

Track performance differences between service versions.

**Expected Pattern**: Version 1.x services should show ~50% higher latency and more errors. Version 3.x should show best performance (~15% faster). This simulates technical debt and optimization in newer versions.

```ppl
source=request_logs
| lookup hosts host_key
    append service_name, service_version, environment, region
| lookup http_status status_key
    append status_code
| where environment="prod" AND isnotnull(service_version)
| stats
    sum(request_count) as requests,
    sum(is_error) as errors,
    avg(latency_ms) as avg_latency,
    percentile(latency_ms, 99) as p99_latency,
    DISTINCT_COUNT(host_key) as host_count
    by service_name, service_version
| eval error_rate_pct = round(100.0 * errors / requests, 2)
| sort service_name, service_version
```

**Use Case**: A/B testing or canary deployment analysis - compare versions.

