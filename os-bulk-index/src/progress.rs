use anyhow::Result;
use indicatif::{MultiProgress, ProgressBar, ProgressStyle};
use tokio::sync::mpsc;

#[derive(Debug)]
pub enum ProgressEvent {
    LineRead,
    BatchSubmitted,
    BatchStarted,
    BatchCompleted,
    Finished,
}

pub struct ProgressBars {
    lines: ProgressBar,
    submitted: ProgressBar,
    in_flight: ProgressBar,
    completed: ProgressBar,
}

pub fn setup_progress_bars(lines_to_read: Option<usize>) -> ProgressBars {
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
        lines,
        submitted,
        in_flight,
        completed,
    }
}

pub async fn handle_progress_events(
    mut rx: mpsc::UnboundedReceiver<ProgressEvent>,
    lines_limit: Option<usize>,
) -> Result<()> {
    let progress = setup_progress_bars(lines_limit);

    while let Some(event) = rx.recv().await {
        match event {
            ProgressEvent::LineRead => progress.lines.inc(1),
            ProgressEvent::BatchSubmitted => progress.submitted.inc(1),
            ProgressEvent::BatchStarted => {
                progress.submitted.dec(1);
                progress.in_flight.inc(1);
            }
            ProgressEvent::BatchCompleted => {
                progress.in_flight.dec(1);
                progress.completed.inc(1);
            }
            ProgressEvent::Finished => break,
        }
    }

    progress.lines.finish_with_message("Done");
    progress.submitted.finish_with_message("Done");
    progress.in_flight.finish_with_message("Done");
    progress.completed.finish_with_message("Done");

    Ok(())
}
