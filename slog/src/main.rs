use std::fs::File;
use std::io::{self, BufRead, BufWriter, Write};
use std::path::PathBuf;
use std::sync::mpsc::{SendError, SyncSender, sync_channel};
use std::thread;

use clap::Parser;
use colored::{ColoredString, Colorize};
use glob::{Paths, glob};
use itertools::merge;
use regex::Regex;
use serde::Serialize;

/// Max log lines to buffer in-memory per channel. 2k capacity ~ 1M memory per file.
const CHAN_CAPACITY: usize = 2048;

type LogReceiver = std::sync::mpsc::IntoIter<String>;

#[derive(Parser)]
#[command(about = "OpenSearch log parser and viewer")]
struct Args {
    /// File patterns to process
    #[arg(required = true)]
    patterns: Vec<String>,

    /// Disable colored output
    #[arg(long)]
    no_color: bool,

    /// Output logs as NDJSON
    #[arg(long)]
    json: bool,
}

#[derive(Serialize)]
struct LogEntry {
    #[serde(rename = "@timestamp")]
    timestamp: String,
    log_type: String,
    severity: String,
    class: String,
    node_id: String,
    body: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    request_method: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    request_url: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    request_parameters: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    response_status: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    response_status_code: Option<u16>,
    #[serde(skip_serializing_if = "Option::is_none")]
    response_bytes: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    response_latency_ms: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    exception_type: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    exception_message: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    exception_trace: Option<String>,
}

struct LogParser {
    basic_regex: Regex,
    http_regex: Regex,
    exception_regex: Regex,
}

impl LogParser {
    fn new() -> Self {
        Self {
            // Basic log format: [timestamp][severity][class][node_id] - just headers
            basic_regex: Regex::new(
                r"^\[(?P<timestamp>[^\]]+)\]\[(?P<severity>[^\]]+)\]\[(?P<class>[^\]]+)\]\[(?P<node_id>[^\]]+)\]\s*"
            ).unwrap(),
            // HTTP request log format (first line only): [timestamp][severity][class][node_id] METHOD URL PARAMS STATUS_CODE STATUS_TEXT BYTES LATENCY_MS
            http_regex: Regex::new(
                r"^\[(?P<timestamp>[^\]]+)\]\[(?P<severity>[^\]]+)\]\[(?P<class>[^\]]+)\]\[(?P<node_id>[^\]]+)\]\s+(?P<request_method>\w+)\s+(?P<request_url>\S+)\s+(?P<request_parameters>\S+)\s+(?P<response_status_code>\d+)\s+(?P<response_status_text>\w+)\s+(?P<response_bytes>\d+)\s+(?P<response_latency_ms>\d+)"
            ).unwrap(),
            // Exception pattern: captures exception type and message
            exception_regex: Regex::new(
                r"(?P<exception_type>[a-zA-Z0-9_.]+(?:Exception|Error)): (?P<exception_message>[^\n]*)"
            ).unwrap(),
        }
    }

    fn parse(&self, log_line: &str) -> Option<LogEntry> {
        // Try HTTP format first (most specific)
        if let Some(entry) = self.parse_http_log(log_line) {
            return Some(entry);
        }

        // Try exception format
        if let Some(entry) = self.parse_exception_log(log_line) {
            return Some(entry);
        }

        // Fall back to basic format
        self.parse_basic_log(log_line)
    }

    fn parse_http_log(&self, log_line: &str) -> Option<LogEntry> {
        let caps = self.http_regex.captures(log_line)?;

        let response_status_code: u16 = caps.name("response_status_code")?.as_str().parse().ok()?;
        let response_status_text = caps.name("response_status_text")?.as_str();
        let request_parameters = caps.name("request_parameters")?.as_str();
        let request_parameters = if request_parameters == "-" {
            None
        } else {
            Some(request_parameters.to_string())
        };

        // The body is everything after the matched portion (may span multiple lines)
        let match_end = caps.get(0)?.end();
        let body = if match_end < log_line.len() {
            &log_line[match_end..]
        } else {
            ""
        };

        Some(LogEntry {
            timestamp: caps.name("timestamp")?.as_str().to_string(),
            log_type: "http".to_string(),
            severity: caps.name("severity")?.as_str().trim().to_string(),
            class: caps.name("class")?.as_str().trim().to_string(),
            node_id: caps.name("node_id")?.as_str().trim().to_string(),
            body: format!(
                "{} {} {} {} {} {} {}{}",
                caps.name("request_method")?.as_str(),
                caps.name("request_url")?.as_str(),
                request_parameters.as_deref().unwrap_or("-"),
                response_status_code,
                response_status_text,
                caps.name("response_bytes")?.as_str(),
                caps.name("response_latency_ms")?.as_str(),
                body
            ),
            request_method: Some(caps.name("request_method")?.as_str().to_string()),
            request_url: Some(caps.name("request_url")?.as_str().to_string()),
            request_parameters,
            response_status: Some(format!("{} {}", response_status_code, response_status_text)),
            response_status_code: Some(response_status_code),
            response_bytes: caps.name("response_bytes")?.as_str().parse().ok(),
            response_latency_ms: caps.name("response_latency_ms")?.as_str().parse().ok(),
            exception_type: None,
            exception_message: None,
            exception_trace: None,
        })
    }

    fn parse_exception_log(&self, log_line: &str) -> Option<LogEntry> {
        let caps = self.basic_regex.captures(log_line)?;

        // The body is everything after the matched headers
        let match_end = caps.get(0)?.end();
        let body = if match_end < log_line.len() {
            &log_line[match_end..]
        } else {
            ""
        };

        // Check if body contains exception indicators
        if !body.contains("Exception") && !body.contains("Error") && !body.contains("\tat ") {
            return None;
        }

        // Extract exception details
        let (exception_type, exception_message, exception_trace) = self.extract_exception_details(body);

        // Only return as exception log if we found exception details
        if exception_type.is_none() {
            return None;
        }

        Some(LogEntry {
            timestamp: caps.name("timestamp")?.as_str().to_string(),
            log_type: "exception".to_string(),
            severity: caps.name("severity")?.as_str().trim().to_string(),
            class: caps.name("class")?.as_str().trim().to_string(),
            node_id: caps.name("node_id")?.as_str().trim().to_string(),
            body: body.to_string(),
            request_method: None,
            request_url: None,
            request_parameters: None,
            response_status: None,
            response_status_code: None,
            response_bytes: None,
            response_latency_ms: None,
            exception_type,
            exception_message,
            exception_trace,
        })
    }

    fn parse_basic_log(&self, log_line: &str) -> Option<LogEntry> {
        let caps = self.basic_regex.captures(log_line)?;

        // The body is everything after the matched headers (may span multiple lines)
        let match_end = caps.get(0)?.end();
        let body = if match_end < log_line.len() {
            &log_line[match_end..]
        } else {
            ""
        };

        Some(LogEntry {
            timestamp: caps.name("timestamp")?.as_str().to_string(),
            log_type: "generic".to_string(),
            severity: caps.name("severity")?.as_str().trim().to_string(),
            class: caps.name("class")?.as_str().trim().to_string(),
            node_id: caps.name("node_id")?.as_str().trim().to_string(),
            body: body.to_string(),
            request_method: None,
            request_url: None,
            request_parameters: None,
            response_status: None,
            response_status_code: None,
            response_bytes: None,
            response_latency_ms: None,
            exception_type: None,
            exception_message: None,
            exception_trace: None,
        })
    }

    fn extract_exception_details(&self, body: &str) -> (Option<String>, Option<String>, Option<String>) {
        // Find the first exception type and message
        let (exception_type, exception_message) = if let Some(caps) = self.exception_regex.captures(body) {
            (
                caps.name("exception_type").map(|m| m.as_str().to_string()),
                caps.name("exception_message").map(|m| m.as_str().to_string()),
            )
        } else {
            (None, None)
        };

        // Extract stack trace (all lines starting with tab and "at ", plus "Caused by" lines)
        let trace_lines: Vec<&str> = body
            .lines()
            .filter(|line| line.trim_start().starts_with("at ") || line.contains("Caused by:"))
            .collect();

        let exception_trace = if trace_lines.is_empty() {
            None
        } else {
            Some(trace_lines.join("\n"))
        };

        (exception_type, exception_message, exception_trace)
    }
}

fn colorize_severity(sev: &str) -> ColoredString {
    match sev.trim() {
        "DEBUG" | "TRACE" => sev.dimmed(),
        "WARN" | "WARN " => sev.yellow(),
        "ERROR" => sev.red(),
        "FATAL" => sev.red().bold(),
        _ => sev.into(),
    }
}

fn colorize_entry(entry: &LogEntry) -> String {
    format!(
        "[{}][{}][{}][{}] {}",
        entry.timestamp.blue(),
        colorize_severity(&entry.severity),
        entry.class.purple(),
        entry.node_id.green(),
        entry.body
    )
}

fn format_entry(entry: &LogEntry, json_mode: bool) -> Option<String> {
    if json_mode {
        serde_json::to_string(entry).ok()
    } else {
        Some(colorize_entry(entry))
    }
}

/// Determine whether the provided line is the start of an ES log. Just checks for the start of an
/// ISO date.
fn is_log_line_start(s: &str) -> bool {
    s.starts_with('[') && s.len() > 11 && s.chars().nth(5) == Some('-')
}

/// Send the contents of the buffer to the channel (if present), clearing the buffer.
fn send_buf(
    buf: &mut String,
    tx: &SyncSender<String>,
    parser: &LogParser,
    json_mode: bool,
) -> Result<(), SendError<String>> {
    if !buf.is_empty() {
        if let Some(entry) = parser.parse(buf) {
            if let Some(formatted) = format_entry(&entry, json_mode) {
                tx.send(formatted)?;
            }
        }
        buf.clear();
    }
    Ok(())
}

fn send_lines(
    handle: File,
    tx: SyncSender<String>,
    parser: &LogParser,
    json_mode: bool,
) -> Result<(), SendError<String>> {
    let mut buf = String::new();

    for line in io::BufReader::new(handle).lines().map_while(Result::ok) {
        if is_log_line_start(&line) {
            send_buf(&mut buf, &tx, parser, json_mode)?;
        }
        if !buf.is_empty() {
            buf.push('\n');
        }
        buf.push_str(&line);
    }

    send_buf(&mut buf, &tx, parser, json_mode)
}

fn scan_log_lines<'s>(
    file: PathBuf,
    scope: &'s thread::Scope<'s, '_>,
    parser: &'s LogParser,
    json_mode: bool,
) -> LogReceiver {
    let (tx, rx) = sync_channel(CHAN_CAPACITY);
    scope.spawn(move || {
        match File::open(&file) {
            Ok(handle) => {
                let _ = send_lines(handle, tx, parser, json_mode);
            }
            Err(err) => {
                eprintln!("Unable to open {}: {err}", file.to_string_lossy());
            }
        };
    });
    rx.into_iter()
}

fn collect_receivers<'s>(
    paths: Paths,
    scope: &'s thread::Scope<'s, '_>,
    parser: &'s LogParser,
    json_mode: bool,
) -> Vec<LogReceiver> {
    paths
        .filter_map(|res| match res {
            Ok(file) => Some(scan_log_lines(file.to_path_buf(), scope, parser, json_mode)),
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

fn main() {
    let args = Args::parse();

    // Set color control based on flags
    colored::control::set_override(!args.no_color && !args.json);

    let parser = LogParser::new();

    thread::scope(|s| {
        let mut receivers = Vec::new();
        for pattern in &args.patterns {
            if let Ok(paths) = glob(pattern) {
                receivers.extend(collect_receivers(paths, s, &parser, args.json));
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_http_request() {
        let parser = LogParser::new();
        let log = "[2025-01-01T10:00:00,123][INFO ][o.o.n.c.logger           ][abc123node456] GET /_cluster/health local=true 200 OK 475 1";

        let entry = parser.parse(log).expect("Failed to parse HTTP log");

        assert_eq!(entry.timestamp, "2025-01-01T10:00:00,123");
        assert_eq!(entry.severity, "INFO");
        assert_eq!(entry.class, "o.o.n.c.logger");
        assert_eq!(entry.node_id, "abc123node456");
        assert_eq!(entry.request_method, Some("GET".to_string()));
        assert_eq!(entry.request_url, Some("/_cluster/health".to_string()));
        assert_eq!(entry.request_parameters, Some("local=true".to_string()));
        assert_eq!(entry.response_status_code, Some(200));
        assert_eq!(entry.response_bytes, Some(475));
        assert_eq!(entry.response_latency_ms, Some(1));
        assert!(entry.exception_type.is_none());
    }

    #[test]
    fn test_parse_http_request_no_params() {
        let parser = LogParser::new();
        let log = "[2025-01-01T10:00:00,123][INFO ][o.o.n.c.logger           ][abc123node456] GET / - 200 OK 578 1";

        let entry = parser.parse(log).expect("Failed to parse HTTP log");

        assert_eq!(entry.request_method, Some("GET".to_string()));
        assert_eq!(entry.request_url, Some("/".to_string()));
        assert_eq!(entry.request_parameters, None);
        assert_eq!(entry.response_status_code, Some(200));
    }

    #[test]
    fn test_parse_exception_log() {
        let parser = LogParser::new();
        let log = "[2025-01-01T10:00:00,123][ERROR][o.o.t.n.s.Transport      ][abc123node456] Exception during SSL: javax.net.ssl.SSLHandshakeException: Empty client certificate chain
javax.net.ssl.SSLHandshakeException: Empty client certificate chain
\tat java.base/sun.security.ssl.Alert.createSSLException(Alert.java:130)
\tat java.base/sun.security.ssl.Alert.createSSLException(Alert.java:117)
\tat java.base/sun.security.ssl.TransportContext.fatal(TransportContext.java:370)";

        let entry = parser.parse(log).expect("Failed to parse exception log");

        assert_eq!(entry.timestamp, "2025-01-01T10:00:00,123");
        assert_eq!(entry.severity, "ERROR");
        assert_eq!(entry.class, "o.o.t.n.s.Transport");
        assert_eq!(entry.node_id, "abc123node456");
        assert_eq!(entry.exception_type, Some("javax.net.ssl.SSLHandshakeException".to_string()));
        assert_eq!(entry.exception_message, Some("Empty client certificate chain".to_string()));
        assert!(entry.exception_trace.is_some());
        assert!(entry.exception_trace.as_ref().unwrap().contains("at java.base/sun.security.ssl.Alert.createSSLException"));
        assert!(entry.request_method.is_none());
    }

    #[test]
    fn test_parse_regular_log() {
        let parser = LogParser::new();
        let log = "[2025-01-01T10:00:00,123][INFO ][c.a.a.c.MetricClient     ][abc123node456] flush is invoked with sync false";

        let entry = parser.parse(log).expect("Failed to parse regular log");

        assert_eq!(entry.timestamp, "2025-01-01T10:00:00,123");
        assert_eq!(entry.severity, "INFO");
        assert_eq!(entry.class, "c.a.a.c.MetricClient");
        assert_eq!(entry.node_id, "abc123node456");
        assert_eq!(entry.body, "flush is invoked with sync false");
        assert!(entry.request_method.is_none());
        assert!(entry.exception_type.is_none());
    }

    #[test]
    fn test_parse_multiline_exception() {
        let parser = LogParser::new();
        let log = "[2025-01-01T10:00:00,123][WARN ][i.n.c.Handler            ][abc123node456] An exception was thrown
io.netty.handler.codec.DecoderException: javax.net.ssl.SSLHandshakeException: Empty cert
\tat io.netty.handler.codec.ByteToMessageDecoder.callDecode(ByteToMessageDecoder.java:500)
\tat io.netty.handler.codec.ByteToMessageDecoder.channelRead(ByteToMessageDecoder.java:290)
Caused by: javax.net.ssl.SSLHandshakeException: Empty cert
\tat java.base/sun.security.ssl.Alert.createSSLException(Alert.java:130)";

        let entry = parser.parse(log).expect("Failed to parse exception log");

        assert_eq!(entry.exception_type, Some("io.netty.handler.codec.DecoderException".to_string()));
        assert_eq!(entry.exception_message, Some("javax.net.ssl.SSLHandshakeException: Empty cert".to_string()));
        assert!(entry.exception_trace.is_some());
        let trace = entry.exception_trace.unwrap();
        assert!(trace.contains("at io.netty.handler.codec.ByteToMessageDecoder.callDecode"));
        assert!(trace.contains("Caused by:"));
    }

    #[test]
    fn test_parse_log_with_padded_fields() {
        let parser = LogParser::new();
        let log = "[2025-01-01T10:00:00,123][INFO ][c.a.a.c.MetricClient     ][abc123node456] test message";

        let entry = parser.parse(log).expect("Failed to parse log");

        // Verify fields are trimmed
        assert_eq!(entry.severity, "INFO");
        assert_eq!(entry.class, "c.a.a.c.MetricClient");
        assert_eq!(entry.node_id, "abc123node456");
    }

    #[test]
    fn test_is_log_line_start() {
        assert!(is_log_line_start("[2025-01-01T10:00:00,123][INFO ][test][node] message"));
        assert!(is_log_line_start("[2025-12-18T15:00:00,052][ERROR][class][node] error"));
        assert!(!is_log_line_start("\tat java.base/something"));
        assert!(!is_log_line_start("  continuation line"));
        assert!(!is_log_line_start("regular text"));
    }

    #[test]
    fn test_json_serialization() {
        let parser = LogParser::new();
        let log = "[2025-01-01T10:00:00,123][INFO ][o.o.n.c.logger           ][abc123node456] GET / - 200 OK 100 5";

        let entry = parser.parse(log).expect("Failed to parse log");
        let json = serde_json::to_string(&entry).expect("Failed to serialize to JSON");

        // Verify JSON contains expected fields with @timestamp
        assert!(json.contains("\"@timestamp\":\"2025-01-01T10:00:00,123\""));
        assert!(json.contains("\"severity\":\"INFO\""));
        assert!(json.contains("\"request_method\":\"GET\""));
        assert!(json.contains("\"response_status_code\":200"));

        // Verify optional fields are excluded when None
        let regular_log = "[2025-01-01T10:00:00,123][INFO ][test][node] message";
        let regular_entry = parser.parse(regular_log).expect("Failed to parse");
        let regular_json = serde_json::to_string(&regular_entry).expect("Failed to serialize");
        assert!(!regular_json.contains("request_method"));
        assert!(!regular_json.contains("exception_type"));
    }

    #[test]
    fn test_log_type_discriminator() {
        let parser = LogParser::new();

        // Test HTTP log type
        let http_log = "[2025-01-01T10:00:00,123][INFO ][o.o.n.c.logger][node] GET / - 200 OK 100 5";
        let http_entry = parser.parse(http_log).expect("Failed to parse HTTP log");
        let http_json = serde_json::to_string(&http_entry).expect("Failed to serialize");
        assert!(http_json.contains("\"log_type\":\"http\""));

        // Test exception log type
        let exc_log = "[2025-01-01T10:00:00,123][ERROR][o.o.t.n.s.Transport][node] Exception: java.lang.RuntimeException: Test\n\tat test.method(Test.java:10)";
        let exc_entry = parser.parse(exc_log).expect("Failed to parse exception log");
        let exc_json = serde_json::to_string(&exc_entry).expect("Failed to serialize");
        assert!(exc_json.contains("\"log_type\":\"exception\""));

        // Test generic log type
        let generic_log = "[2025-01-01T10:00:00,123][INFO ][c.a.a.c.MetricClient][node] regular message";
        let generic_entry = parser.parse(generic_log).expect("Failed to parse generic log");
        let generic_json = serde_json::to_string(&generic_entry).expect("Failed to serialize");
        assert!(generic_json.contains("\"log_type\":\"generic\""));
    }

    #[test]
    fn test_extract_exception_details_with_caused_by() {
        let parser = LogParser::new();
        let body = "Exception occurred: java.lang.RuntimeException: Test error
java.lang.RuntimeException: Test error
\tat com.example.Test.method(Test.java:10)
Caused by: java.io.IOException: IO failed
\tat com.example.IO.read(IO.java:20)";

        let (exc_type, exc_msg, exc_trace) = parser.extract_exception_details(body);

        assert_eq!(exc_type, Some("java.lang.RuntimeException".to_string()));
        assert_eq!(exc_msg, Some("Test error".to_string()));
        assert!(exc_trace.is_some());
        let trace = exc_trace.unwrap();
        assert!(trace.contains("at com.example.Test.method"));
        assert!(trace.contains("Caused by:"));
        assert!(trace.contains("at com.example.IO.read"));
    }
}
