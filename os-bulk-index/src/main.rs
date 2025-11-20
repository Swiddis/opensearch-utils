use anyhow::{Context, Result};
use clap::Parser;
use flate2::read::GzDecoder;
use indicatif::{MultiProgress, ProgressBar, ProgressStyle};
use reqwest::Client;
use sha2::{Digest, Sha256};
use std::io::{BufRead, BufReader};
use std::sync::Arc;
use tokio::sync::Semaphore;
use zstd::Decoder;

#[derive(Parser, Debug)]
#[command(name = "os-bulk-index")]
#[command(about = "Bulk index documents into OpenSearch/Elasticsearch")]
struct Cli {
    /// Path to the dataset file (supports .json, .json.gz, .json.zst)
    #[arg(short, long)]
    file: String,

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

    /// Maximum number of lines to read (optional, reads all if not specified)
    #[arg(short, long)]
    limit: Option<usize>,

    /// Number of documents per batch
    #[arg(short, long, default_value_t = 8192)]
    batch_size: usize,

    /// Maximum number of concurrent requests
    #[arg(short, long, default_value_t = 32)]
    concurrent_requests: usize,

    /// Maximum number of batches to queue while waiting for requests to complete
    #[arg(long, default_value_t = 64)]
    max_pending_batches: usize,
}

#[tokio::main]
async fn main() -> Result<()> {
    let args = Cli::parse();

    let progress = setup_progress_bars(args.limit);
    let client = Client::new();
    let semaphore = Arc::new(Semaphore::new(args.concurrent_requests));

    process_file(&args, progress.clone(), client, semaphore)
        .await
        .context("Failed to process file")
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
    args: &Cli,
    progress: ProgressBars,
    client: Client,
    semaphore: Arc<Semaphore>,
) -> Result<()> {
    let reader = create_reader(&args.file)?;
    let mut current_batch = Vec::with_capacity(args.batch_size);
    let mut pending_handles = Vec::new();

    for line in reader.lines().take(args.limit.unwrap_or(usize::MAX)) {
        let line = line.context("Failed to read line")?;
        current_batch.push(line);
        progress.lines.inc(1);

        if current_batch.len() >= args.batch_size {
            let batch = std::mem::replace(&mut current_batch, Vec::with_capacity(args.batch_size));
            progress.submitted.inc(1);
            pending_handles.push(spawn_upload_task(
                batch,
                Arc::clone(&semaphore),
                client.clone(),
                progress.clone(),
                &args.endpoint,
                &args.index,
                args.username.as_deref(),
                args.password.as_deref(),
            ));

            // When we hit our limit, start going through the queue
            while pending_handles.len() >= args.max_pending_batches {
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
            &args.endpoint,
            &args.index,
            args.username.as_deref(),
            args.password.as_deref(),
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

enum FileReader {
    Plain(BufReader<std::fs::File>),
    Gzip(BufReader<GzDecoder<std::fs::File>>),
    Zstd(BufReader<Decoder<'static, BufReader<std::fs::File>>>),
}

impl FileReader {
    fn lines(self) -> Box<dyn Iterator<Item = std::io::Result<String>>> {
        match self {
            FileReader::Plain(reader) => Box::new(reader.lines()),
            FileReader::Gzip(reader) => Box::new(reader.lines()),
            FileReader::Zstd(reader) => Box::new(reader.lines()),
        }
    }
}

fn create_reader(path: &str) -> Result<FileReader> {
    let file = std::fs::File::open(path).context("Failed to open file")?;

    if path.ends_with(".zst") {
        let decoder = Decoder::new(file).context("Failed to create zstd decoder")?;
        Ok(FileReader::Zstd(BufReader::new(decoder)))
    } else if path.ends_with(".gz") {
        let decoder = GzDecoder::new(file);
        Ok(FileReader::Gzip(BufReader::new(decoder)))
    } else {
        Ok(FileReader::Plain(BufReader::new(file)))
    }
}

fn create_bulk_body(chunk: &[String], index: &str) -> String {
    let mut bulk_body = String::new();
    for line in chunk {
        let id = hex::encode(&Sha256::digest(line.as_bytes())[..12]);
        bulk_body.push_str(&format!(
            "{{\"create\":{{\"_index\":\"{}\",\"_id\":\"{}\"}}}}\n",
            index, id
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
    endpoint: &str,
    index: &str,
    username: Option<&str>,
    password: Option<&str>,
) -> tokio::task::JoinHandle<Result<()>> {
    let bulk_url = format!("{}/_bulk", endpoint);
    let index = index.to_string();
    let username = username.map(|s| s.to_string());
    let password = password.map(|s| s.to_string());

    tokio::spawn(async move {
        let _permit = semaphore.acquire().await?;
        let bulk_body = create_bulk_body(&chunk, &index);

        progress.submitted.dec(1);
        progress.in_flight.inc(1);

        let mut request = client
            .post(&bulk_url)
            .header("Content-Type", "application/x-ndjson")
            .body(bulk_body);

        if let (Some(user), Some(pass)) = (username, password) {
            request = request.basic_auth(user, Some(pass));
        }

        request
            .send()
            .await
            .context("Failed to send request")?
            .error_for_status()
            .context("Request failed")?;

        progress.in_flight.dec(1);
        progress.completed.inc(1);
        Ok(())
    })
}
