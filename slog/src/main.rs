use std::env;
use std::fs::File;
use std::io::{self, BufRead, BufWriter, Write};
use std::path::PathBuf;
use std::sync::mpsc::{SendError, SyncSender, sync_channel};
use std::thread;

use colored::{ColoredString, Colorize};
use glob::{Paths, glob};
use itertools::merge;

/// Max log lines to buffer in-memory per channel. 2k capacity ~ 1M memory per file.
const CHAN_CAPACITY: usize = 2048;
const LOG_START_PATTERN: &str = "[dddd-dd-ddT";

type LogReceiver = std::sync::mpsc::IntoIter<String>;

/// Combinator that takes the string up to, not including, c. Takes the whole string if c is absent.
fn take_until(s: &str, c: char) -> (&str, &str) {
    match s.find(c) {
        Some(idx) => (&s[..idx], &s[idx..]),
        None => (s, ""),
    }
}

/// Combinator that takes the string up to and including c. Takes the whole string if c is absent.
fn take_to(s: &str, c: char) -> (&str, &str) {
    match s.find(c) {
        Some(idx) => (&s[..idx + 1], &s[idx + 1..]),
        None => (s, ""),
    }
}

fn colorize_severity(sev: &str) -> ColoredString {
    match sev {
        "DEBUG" | "TRACE" => sev.dimmed(),
        "WARN " => sev.yellow(),
        "ERROR" => sev.red(),
        "FATAL" => sev.red().bold(),
        _ => sev.into(),
    }
}

fn colorize(es_log: &str) -> String {
    // Cute combinator-based zero-copy parsing. Not the most elegant way to do this, but fast,
    // cheap, and gives us easy parts to reassemble colored logs from, without needing to pull in
    // the massive regex crate
    let (br0, tail) = take_to(es_log, '[');
    let (timestamp, tail) = take_until(tail, ']');
    let (br1, tail) = take_to(tail, '[');
    let (severity, tail) = take_until(tail, ']');
    let (br2, tail) = take_to(tail, '[');
    let (class, tail) = take_until(tail, ']');
    let (br3, tail) = take_to(tail, '[');
    let (node_id, tail) = take_until(tail, ']');

    format!(
        "{br0}{}{br1}{}{br2}{}{br3}{}{tail}",
        timestamp.blue(),
        colorize_severity(severity),
        class.purple(),
        node_id.green(),
    )
}

/// Determine whether the provided line is the start of an ES log. Just checks for the start of an
/// ISO date.
fn is_log_line_start(s: &str) -> bool {
    s.chars().zip(LOG_START_PATTERN.chars()).all(|(c, p)| match p {
        'd' => c.is_ascii_digit(),
        _ => c == p,
    })
}

/// Send the contents of the buffer to the channel (if present), clearing the buffer.
fn send_buf(buf: &mut String, tx: &SyncSender<String>) -> Result<(), SendError<String>> {
    if !buf.is_empty() {
        tx.send(colorize(buf))?;
        buf.clear();
    }
    Ok(())
}

fn send_lines(handle: File, tx: SyncSender<String>) -> Result<(), SendError<String>> {
    let mut buf = String::new();

    for line in io::BufReader::new(handle).lines().map_while(Result::ok) {
        if is_log_line_start(&line) {
            send_buf(&mut buf, &tx)?;
        }
        if !buf.is_empty() {
            buf.push('\n');
        }
        buf.push_str(&line);
    }

    send_buf(&mut buf, &tx)
}

fn scan_log_lines<'s>(file: PathBuf, scope: &'s thread::Scope<'s, '_>) -> LogReceiver {
    let (tx, rx) = sync_channel(CHAN_CAPACITY);
    scope.spawn(move || {
        match File::open(&file) {
            Ok(handle) => {
                let _ = send_lines(handle, tx);
            }
            Err(err) => {
                eprintln!("Unable to open {}: {err}", file.to_string_lossy());
            }
        };
    });
    rx.into_iter()
}

fn collect_receivers<'s>(paths: Paths, scope: &'s thread::Scope<'s, '_>) -> Vec<LogReceiver> {
    paths
        .filter_map(|res| match res {
            Ok(file) => Some(scan_log_lines(file.to_path_buf(), scope)),
            Err(err) => {
                eprintln!("Unable to load path: {err}");
                None
            }
        })
        .collect()
}

fn spawn_merge<'s>(
    left: LogReceiver,
    right: LogReceiver,
    scope: &'s thread::Scope<'s, '_>,
) -> LogReceiver {
    let (tx, rx) = sync_channel(CHAN_CAPACITY);
    scope.spawn(move || {
        for s in merge(left, right) {
            if tx.send(s).is_err() {
                return;
            }
        }
    });
    rx.into_iter()
}

/// Merge all the provided receivers into one merged iterator. Equivalent to itertools::kmerge, but
/// parallelizes all the merges.
fn merge_receivers<'s>(
    mut recs: Vec<LogReceiver>,
    scope: &'s thread::Scope<'s, '_>,
) -> LogReceiver {
    if recs.is_empty() {
        let (_, rx) = sync_channel(0); // empty iterator as tx is instantly dropped
        return rx.into_iter();
    }

    while recs.len() > 1 {
        let left = recs.pop().unwrap();
        let right = recs.pop().unwrap();
        recs.insert(0, spawn_merge(left, right, scope));
    }

    recs.pop().unwrap()
}

fn set_color_control() {
    colored::control::set_override(!env::args().any(|a| a == "--no-color"));
}

fn main() {
    if env::args().len() <= 1 {
        eprintln!("Usage: slog <pattern> [pattern2 ...] [--no-color]");
        return;
    }
    set_color_control();

    thread::scope(|s| {
        let mut receivers = Vec::new();
        for arg in env::args().skip(1) {
            if arg.starts_with("--") {
                continue; // Skip flags
            }
            if let Ok(paths) = glob(&arg) {
                receivers.extend(collect_receivers(paths, s));
            }
        }

        let mut stdout = BufWriter::new(std::io::stdout());
        for entry in merge_receivers(receivers, s) {
            if writeln!(stdout, "{entry}").is_err() {
                return;
            }
        }
    });
}
