use anyhow::{Context, Result};
use indicatif::{MultiProgress, ProgressBar, ProgressStyle};
use reqwest::Client;
use sha2::{Digest, Sha256};
use std::io::{BufRead, BufReader};
use std::sync::Arc;
use tokio::sync::Semaphore;
use zstd::Decoder;

const DATASET: &str = "datasets/documents-60.json.zst";
const INDEX: &str = "big5";
const BATCH_SIZE: usize = 8192;
const CONCURRENT_REQUESTS: usize = 32;
const MAX_PENDING_BATCHES: usize = 64;

#[tokio::main]
async fn main() -> Result<()> {
    let lines_to_read = parse_args()?;
    let progress = setup_progress_bars(lines_to_read);
    let client = Client::new();
    let semaphore = Arc::new(Semaphore::new(CONCURRENT_REQUESTS));

    process_file(lines_to_read, progress.clone(), client, semaphore)
        .await
        .context("Failed to process file")
}

fn parse_args() -> Result<Option<usize>> {
    std::env::args()
        .nth(1)
        .map(|s| s.parse())
        .transpose()
        .context("Failed to parse argument")
}

struct ProgressBars {
    multi: MultiProgress,
    lines: ProgressBar,
    submitted: ProgressBar,
    in_flight: ProgressBar,
    completed: ProgressBar,
}

impl Clone for ProgressBars {
    fn clone(&self) -> Self {
        Self {
            multi: self.multi.clone(),
            lines: self.lines.clone(),
            submitted: self.submitted.clone(),
            in_flight: self.in_flight.clone(),
            completed: self.completed.clone(),
        }
    }
}

fn setup_progress_bars(lines_to_read: Option<usize>) -> ProgressBars {
    let multi = MultiProgress::new();
    let style = ProgressStyle::default_spinner()
        .template("{spinner:.green} [{elapsed_precise}] {prefix}: {pos} {msg}")
        .unwrap();

    let lines = multi.add(ProgressBar::new(lines_to_read.unwrap_or(0) as u64));
    let submitted = multi.add(ProgressBar::new_spinner());
    let in_flight = multi.add(ProgressBar::new_spinner());
    let completed = multi.add(ProgressBar::new_spinner());

    lines.set_style(style.clone());
    submitted.set_style(style.clone());
    in_flight.set_style(style.clone());
    completed.set_style(style);

    lines.set_prefix("Lines read");
    submitted.set_prefix("Batches pending");
    in_flight.set_prefix("Requests in flight");
    completed.set_prefix("Batches completed");

    ProgressBars {
        multi,
        lines,
        submitted,
        in_flight,
        completed,
    }
}

async fn process_file(
    lines_to_read: Option<usize>,
    progress: ProgressBars,
    client: Client,
    semaphore: Arc<Semaphore>,
) -> Result<()> {
    let reader = create_reader()?;
    let mut current_batch = Vec::with_capacity(BATCH_SIZE);
    let mut pending_handles = Vec::new();

    for line in reader.lines().take(lines_to_read.unwrap_or(usize::MAX)) {
        let line = line.context("Failed to read line")?;
        current_batch.push(line);
        progress.lines.inc(1);

        if current_batch.len() >= BATCH_SIZE {
            let batch = std::mem::replace(&mut current_batch, Vec::with_capacity(BATCH_SIZE));
            progress.submitted.inc(1);
            pending_handles.push(spawn_upload_task(
                batch,
                Arc::clone(&semaphore),
                client.clone(),
                progress.clone(),
            ));

            // When we hit our limit, start going through the queue
            while pending_handles.len() >= MAX_PENDING_BATCHES {
                remove_completed(&mut pending_handles).await?;
            }
        }
    }
    progress.lines.finish_with_message("Done");

    // Handle remaining documents
    if !current_batch.is_empty() {
        progress.submitted.inc(1);
        pending_handles.push(spawn_upload_task(
            current_batch,
            Arc::clone(&semaphore),
            client.clone(),
            progress.clone(),
        ));
    }

    // Wait for all remaining tasks to complete
    while !pending_handles.is_empty() {
        remove_completed(&mut pending_handles).await?;
    }
    progress.submitted.finish_with_message("Done");
    progress.in_flight.finish_with_message("Done");
    progress.completed.finish_with_message("Done");

    Ok(())
}

async fn remove_completed(
    handles: &mut Vec<tokio::task::JoinHandle<Result<()>>>,
) -> Result<usize> {
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

fn create_reader() -> Result<BufReader<Decoder<'static, BufReader<std::fs::File>>>> {
    let file = std::fs::File::open(DATASET).context("Failed to open file")?;
    let decoder = Decoder::new(file).context("Failed to create decoder")?;
    Ok(BufReader::new(decoder))
}

fn create_bulk_body(chunk: &[String]) -> String {
    let mut bulk_body = String::new();
    for line in chunk {
        let id = hex::encode(&Sha256::digest(line.as_bytes())[..12]);
        bulk_body.push_str(&format!(
            "{{\"create\":{{\"_index\":\"{}\",\"_id\":\"{}\"}}}}\n",
            INDEX, id
        ));
        bulk_body.push_str(line);
        bulk_body.push('\n');
    }
    bulk_body
}

fn spawn_upload_task(
    chunk: Vec<String>,
    semaphore: Arc<Semaphore>,
    client: Client,
    progress: ProgressBars,
) -> tokio::task::JoinHandle<Result<()>> {
    tokio::spawn(async move {
        let _permit = semaphore.acquire().await?;
        let bulk_body = create_bulk_body(&chunk);

        progress.in_flight.inc(1);
        client
            .post("http://localhost:9200/_bulk")
            .header("Content-Type", "application/x-ndjson")
            .body(bulk_body)
            .send()
            .await
            .context("Failed to send request")?
            .error_for_status()
            .context("Request failed")?;

        progress.in_flight.dec(1);
        progress.submitted.dec(1);
        progress.completed.inc(1);
        Ok(())
    })
}
