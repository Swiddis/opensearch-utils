mod file_reader;
mod progress;

use anyhow::{Context, Result};
use chrono::Utc;
use clap::Parser;
use regex::Regex;
use reqwest::Client;
use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::sync::{Arc, OnceLock};
use tokio::sync::{Semaphore, mpsc};

use file_reader::create_reader;
use progress::{ProgressEvent, handle_progress_events};

#[derive(Parser, Debug)]
#[command(name = "os-bulk-index")]
#[command(about = "Bulk index documents into OpenSearch/Elasticsearch, or scan/export them")]
struct Cli {
    /// Target index name
    #[arg(short, long)]
    index: String,

    /// OpenSearch/Elasticsearch endpoint URL
    #[arg(short, long, default_value = "http://localhost:9200")]
    endpoint: String,

    /// Username for HTTP basic authentication
    #[arg(short, long)]
    username: Option<String>,

    /// Password for HTTP basic authentication
    #[arg(short, long)]
    password: Option<String>,

    /// Scan mode: export documents from the index to stdout as NDJSON
    #[arg(long)]
    scan: bool,

    // Index mode options (only used when --scan is not set)
    /// Path to the dataset file (supports .json, .json.gz, .json.bz2, .json.zst). Defaults to stdin if not provided.
    #[arg(short, long)]
    file: Option<String>,

    /// Maximum number of lines to read (optional, reads all if not specified)
    #[arg(short, long)]
    limit: Option<usize>,

    /// Number of documents per batch
    #[arg(short, long, default_value_t = 8192)]
    batch_size: usize,

    /// Maximum number of concurrent requests
    #[arg(short, long, default_value_t = 32)]
    concurrent_requests: usize,

    /// Maximum number of in-progress batches to concurrently keep in memory
    #[arg(long, default_value_t = 64)]
    max_pending_batches: usize,

    /// Live mode: skip _id field and replace timestamps with current time
    #[arg(long)]
    live: bool,

    /// Rate limit in documents per second (optional, no limit if not specified)
    #[arg(short, long)]
    rate: Option<f64>,

    // Scan mode options (only used when --scan is set)
    /// Scroll timeout for scan operations (e.g., "1m", "30s")
    #[arg(long, default_value = "1m")]
    scroll_timeout: String,

    /// Query to filter documents during scan (JSON query DSL)
    #[arg(long)]
    query: Option<String>,

    /// Size of each scroll batch
    #[arg(long, default_value_t = 1000)]
    scroll_size: usize,

    /// Watch mode: monitor cluster and re-run indexing on restart
    #[arg(long)]
    watch: bool,
}

#[tokio::main]
async fn main() -> Result<()> {
    let args = Cli::parse();

    if args.scan {
        // Scan mode: export documents from index
        scan_index(&args).await
    } else {
        // Index mode: upload documents to index
        index_documents(&args).await
    }
}

async fn index_documents(args: &Cli) -> Result<()> {
    if !args.watch {
        // Normal mode: run once
        run_indexing_once(args).await?;
        return Ok(());
    }
    // Watch mode: run indefinitely, restarting when cluster restarts
    loop {
        eprintln!("Starting indexing...");
        let result = run_indexing_once(args).await;

        match result {
            Ok(_) => eprintln!("Indexing completed successfully"),
            Err(e) => eprintln!("Indexing failed: {}", e),
        }

        eprintln!("Watch mode: monitoring cluster...");

        // Wait for cluster to go down
        let client = Client::new();
        loop {
            tokio::time::sleep(tokio::time::Duration::from_secs(5)).await;
            if !check_cluster_health(&client, args).await {
                eprintln!("Cluster is down, waiting for it to come back up...");
                break;
            }
        }

        // Wait for cluster to come back up
        loop {
            tokio::time::sleep(tokio::time::Duration::from_secs(5)).await;
            if check_cluster_health(&client, args).await {
                eprintln!("Cluster is back up, restarting indexing...");
                break;
            }
        }
    }
}

async fn run_indexing_once(args: &Cli) -> Result<()> {
    let client = Client::new();
    let semaphore = Arc::new(Semaphore::new(args.concurrent_requests));
    let (progress_tx, progress_rx) = mpsc::unbounded_channel();

    let progress_handle = tokio::spawn(handle_progress_events(progress_rx, args.limit));
    let result = process_file(args, progress_tx, client, semaphore).await;

    progress_handle.await.context("Progress task panicked")??;
    result.context("Failed to process file")
}

#[derive(Deserialize)]
struct ScrollResponse {
    _scroll_id: String,
    hits: HitsWrapper,
}

#[derive(Deserialize)]
struct HitsWrapper {
    hits: Vec<Hit>,
}

#[derive(Deserialize)]
struct Hit {
    _source: Value,
}

async fn scan_index(args: &Cli) -> Result<()> {
    let client = Client::new();
    let query = parse_query(&args.query)?;

    let mut scroll_response = initiate_scroll(&client, args, &query).await?;

    while !scroll_response.hits.hits.is_empty() {
        scroll_response = continue_scroll(&client, args, &scroll_response._scroll_id).await?;
        output_hits(&scroll_response.hits.hits)?;
    }

    cleanup_scroll(&client, args, &scroll_response._scroll_id).await;

    Ok(())
}

fn parse_query(query_arg: &Option<String>) -> Result<Value> {
    if let Some(query_str) = query_arg {
        serde_json::from_str::<Value>(query_str).context("Failed to parse query JSON")
    } else {
        Ok(serde_json::json!({ "match_all": {} }))
    }
}

async fn initiate_scroll(client: &Client, args: &Cli, query: &Value) -> Result<ScrollResponse> {
    let search_body = serde_json::json!({
        "query": query,
        "size": args.scroll_size,
    });

    let search_url = format!(
        "{}/{}/_search?scroll={}",
        args.endpoint, args.index, args.scroll_timeout
    );

    let mut request = client
        .post(&search_url)
        .header("Content-Type", "application/json")
        .json(&search_body);

    if let (Some(user), Some(pass)) = (&args.username, &args.password) {
        request = request.basic_auth(user, Some(pass));
    }

    request
        .send()
        .await
        .context("Failed to send initial search request")?
        .error_for_status()
        .context("Initial search request failed")?
        .json()
        .await
        .context("Failed to parse initial search response")
}

async fn continue_scroll(client: &Client, args: &Cli, scroll_id: &str) -> Result<ScrollResponse> {
    let scroll_url = format!("{}/_search/scroll", args.endpoint);
    let scroll_body = serde_json::json!({
        "scroll": args.scroll_timeout,
        "scroll_id": scroll_id,
    });

    let mut request = client
        .post(&scroll_url)
        .header("Content-Type", "application/json")
        .json(&scroll_body);

    if let (Some(user), Some(pass)) = (&args.username, &args.password) {
        request = request.basic_auth(user, Some(pass));
    }

    request
        .send()
        .await
        .context("Failed to send scroll request")?
        .error_for_status()
        .context("Scroll request failed")?
        .json()
        .await
        .context("Failed to parse scroll response")
}

fn output_hits(hits: &[Hit]) -> Result<usize> {
    for hit in hits {
        println!("{}", serde_json::to_string(&hit._source)?);
    }
    Ok(hits.len())
}

async fn cleanup_scroll(client: &Client, args: &Cli, scroll_id: &str) {
    let clear_scroll_url = format!("{}/_search/scroll", args.endpoint);
    let clear_body = serde_json::json!({ "scroll_id": scroll_id });

    let mut request = client
        .delete(&clear_scroll_url)
        .header("Content-Type", "application/json")
        .json(&clear_body);

    if let (Some(user), Some(pass)) = (&args.username, &args.password) {
        request = request.basic_auth(user, Some(pass));
    }

    let _ = request.send().await;
}

async fn check_cluster_health(client: &Client, args: &Cli) -> bool {
    let mut request = client.get(&args.endpoint);

    if let (Some(user), Some(pass)) = (&args.username, &args.password) {
        request = request.basic_auth(user, Some(pass));
    }

    request
        .send()
        .await
        .map(|r| r.status().is_success())
        .unwrap_or(false)
}

async fn process_file(
    args: &Cli,
    progress_tx: mpsc::UnboundedSender<ProgressEvent>,
    client: Client,
    semaphore: Arc<Semaphore>,
) -> Result<()> {
    let reader = create_reader(args.file.as_deref())?;
    let mut current_batch: Vec<(String, chrono::DateTime<Utc>)> =
        Vec::with_capacity(args.batch_size);
    let mut pending_handles = Vec::new();
    let mut last_batch_time = tokio::time::Instant::now();

    // Initialize rate limiter if rate is specified
    let rate_limiter = args.rate.map(|rate| {
        let interval = std::time::Duration::from_secs_f64(1.0 / rate);
        (tokio::time::Instant::now(), interval, 0usize)
    });
    let mut rate_limiter = rate_limiter;

    for line in reader.lines().take(args.limit.unwrap_or(usize::MAX)) {
        let line = line.context("Failed to read line")?;
        let _ = progress_tx.send(ProgressEvent::LineRead);

        // Apply rate limiting if enabled
        if let Some((start_time, interval, docs_count)) = rate_limiter.as_mut() {
            *docs_count += 1;
            let expected_time = *start_time + interval.mul_f64(*docs_count as f64);
            let now = tokio::time::Instant::now();
            if expected_time > now {
                tokio::time::sleep(expected_time - now).await;
            }
        }

        // Capture timestamp after rate limiting
        let timestamp = Utc::now();
        current_batch.push((line, timestamp));

        // Check if we should flush: batch is full OR 1 second has elapsed with pending docs
        let time_elapsed = tokio::time::Instant::now().duration_since(last_batch_time);
        let should_flush = current_batch.len() >= args.batch_size
            || (!current_batch.is_empty() && time_elapsed >= std::time::Duration::from_secs(1));

        if should_flush {
            let batch = std::mem::replace(&mut current_batch, Vec::with_capacity(args.batch_size));
            let _ = progress_tx.send(ProgressEvent::BatchSubmitted);
            last_batch_time = tokio::time::Instant::now();
            pending_handles.push(spawn_upload_task(
                batch,
                Arc::clone(&semaphore),
                client.clone(),
                progress_tx.clone(),
                &args.endpoint,
                &args.index,
                args.username.as_deref(),
                args.password.as_deref(),
                args.live,
            ));

            // When we hit our limit, start going through the queue
            while pending_handles.len() >= args.max_pending_batches {
                remove_completed(&mut pending_handles).await?;
            }
        }
    }

    // Handle remaining documents
    if !current_batch.is_empty() {
        let _ = progress_tx.send(ProgressEvent::BatchSubmitted);
        pending_handles.push(spawn_upload_task(
            current_batch,
            Arc::clone(&semaphore),
            client.clone(),
            progress_tx.clone(),
            &args.endpoint,
            &args.index,
            args.username.as_deref(),
            args.password.as_deref(),
            args.live,
        ));
    }

    // Leftover tasks
    while !pending_handles.is_empty() {
        remove_completed(&mut pending_handles).await?;
    }

    let _ = progress_tx.send(ProgressEvent::Finished);

    Ok(())
}

async fn remove_completed(handles: &mut Vec<tokio::task::JoinHandle<Result<()>>>) -> Result<usize> {
    if handles.is_empty() {
        return Ok(0);
    }

    let (completed, idx, _) = futures::future::select_all(handles.iter_mut()).await;
    completed
        .context("Task panicked")?
        .context("Upload task failed")?;
    handles.remove(idx);
    Ok(1)
}

fn replace_timestamps(line: &str, timestamp: &chrono::DateTime<Utc>) -> String {
    static ISO_TIMESTAMP_RE: OnceLock<Regex> = OnceLock::new();
    let re = ISO_TIMESTAMP_RE.get_or_init(|| {
        // Match ISO 8601 timestamps like:
        // 2024-11-20T18:35:12.123Z
        // 2024-11-20T18:35:12Z
        // 2024-11-20T18:35:12.123+00:00
        // 2024-11-20 18:35:12
        Regex::new(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d{3,9})?(?:Z|[+-]\d{2}:\d{2})?")
            .unwrap()
    });

    let timestamp_str = timestamp.format("%Y-%m-%dT%H:%M:%S%.3fZ").to_string();
    re.replace_all(line, timestamp_str.as_str()).to_string()
}

fn create_bulk_body(chunk: &[(String, chrono::DateTime<Utc>)], index: &str, live: bool) -> String {
    let mut bulk_body = String::new();
    for (line, timestamp) in chunk {
        // In live mode, skip the _id field to let OpenSearch generate it
        if live {
            bulk_body.push_str(&format!("{{\"create\":{{\"_index\":\"{}\"}}}}\n", index));
            // Replace timestamps with the captured timestamp
            let updated_line = replace_timestamps(line, timestamp);
            bulk_body.push_str(&updated_line);
        } else {
            let id = hex::encode(&Sha256::digest(line.as_bytes())[..12]);
            bulk_body.push_str(&format!(
                "{{\"create\":{{\"_index\":\"{}\",\"_id\":\"{}\"}}}}\n",
                index, id
            ));
            bulk_body.push_str(line);
        }
        bulk_body.push('\n');
    }
    bulk_body
}

fn spawn_upload_task(
    chunk: Vec<(String, chrono::DateTime<Utc>)>,
    semaphore: Arc<Semaphore>,
    client: Client,
    progress_tx: mpsc::UnboundedSender<ProgressEvent>,
    endpoint: &str,
    index: &str,
    username: Option<&str>,
    password: Option<&str>,
    live: bool,
) -> tokio::task::JoinHandle<Result<()>> {
    let bulk_url = format!("{}/_bulk", endpoint);
    let index = index.to_string();
    let username = username.map(|s| s.to_string());
    let password = password.map(|s| s.to_string());

    tokio::spawn(async move {
        let _permit = semaphore.acquire().await?;
        let bulk_body = create_bulk_body(&chunk, &index, live);

        let _ = progress_tx.send(ProgressEvent::BatchStarted);

        let max_retries = 5;
        let mut retry_count = 0;
        let mut delay_ms = 500u64;

        loop {
            let mut request = client
                .post(&bulk_url)
                .header("Content-Type", "application/x-ndjson")
                .body(bulk_body.clone());

            if let (Some(user), Some(pass)) = (&username, &password) {
                request = request.basic_auth(user, Some(pass));
            }

            let response = request.send().await.context("Failed to send request")?;

            // Special case: exponential backoff for 429s
            if response.status() == reqwest::StatusCode::TOO_MANY_REQUESTS
                && retry_count < max_retries
            {
                retry_count += 1;
                tokio::time::sleep(tokio::time::Duration::from_millis(delay_ms)).await;
                delay_ms *= 2;
                continue;
            }

            response.error_for_status().context("Request failed")?;
            break;
        }

        let _ = progress_tx.send(ProgressEvent::BatchCompleted);
        Ok(())
    })
}
