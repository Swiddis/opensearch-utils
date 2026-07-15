use anyhow::{Context, Result};
use bzip2::read::BzDecoder;
use flate2::read::GzDecoder;
use rusqlite::{Connection, Row};
use serde_json::{json, Value};
use std::io::{BufRead, BufReader, Stdin};
use zstd::Decoder;

pub enum FileReader {
    Plain(BufReader<std::fs::File>),
    Gzip(BufReader<GzDecoder<std::fs::File>>),
    Bzip2(BufReader<BzDecoder<std::fs::File>>),
    Zstd(BufReader<Decoder<'static, BufReader<std::fs::File>>>),
    Stdin(BufReader<Stdin>),
    Sqlite(SqliteReader),
}

pub struct SqliteReader {
    conn: Connection,
    table: String,
}

impl SqliteReader {
    pub fn new(db_path: &str, table: &str) -> Result<Self> {
        let conn = Connection::open(db_path)
            .context(format!("Failed to open SQLite database at {}", db_path))?;
        Ok(Self {
            conn,
            table: table.to_string(),
        })
    }

    fn row_to_json(row: &Row, column_names: &[String]) -> rusqlite::Result<String> {
        let mut map = serde_json::Map::new();

        for (idx, col_name) in column_names.iter().enumerate() {
            let value: Value = match row.get_ref(idx)? {
                rusqlite::types::ValueRef::Null => Value::Null,
                rusqlite::types::ValueRef::Integer(i) => json!(i),
                rusqlite::types::ValueRef::Real(f) => json!(f),
                rusqlite::types::ValueRef::Text(s) => {
                    json!(std::str::from_utf8(s).unwrap_or(""))
                }
                rusqlite::types::ValueRef::Blob(b) => {
                    // Convert blob to base64
                    json!(base64_encode(b))
                }
            };
            map.insert(col_name.clone(), value);
        }

        Ok(serde_json::to_string(&map).unwrap())
    }

    pub fn lines(self) -> Box<dyn Iterator<Item = std::io::Result<String>>> {
        let query = format!("SELECT * FROM {}", self.table);

        let result: std::io::Result<Vec<String>> = (|| {
            let mut stmt = self.conn.prepare(&query)
                .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?;

            let column_names: Vec<String> = stmt.column_names()
                .iter()
                .map(|s| s.to_string())
                .collect();

            let rows = stmt.query_map([], |row| {
                Self::row_to_json(row, &column_names)
            }).map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?;

            rows.collect::<Result<Vec<_>, _>>()
                .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))
        })();

        match result {
            Ok(lines) => Box::new(lines.into_iter().map(Ok)),
            Err(e) => Box::new(std::iter::once(Err(e))),
        }
    }
}

fn base64_encode(data: &[u8]) -> String {
    use std::fmt::Write;
    const CHARS: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

    let mut result = String::new();
    let mut i = 0;
    while i < data.len() {
        let b1 = data[i];
        let b2 = if i + 1 < data.len() { data[i + 1] } else { 0 };
        let b3 = if i + 2 < data.len() { data[i + 2] } else { 0 };

        let _ = write!(result, "{}", CHARS[(b1 >> 2) as usize] as char);
        let _ = write!(result, "{}", CHARS[(((b1 & 0x03) << 4) | (b2 >> 4)) as usize] as char);
        let _ = write!(result, "{}", if i + 1 < data.len() { CHARS[(((b2 & 0x0f) << 2) | (b3 >> 6)) as usize] as char } else { '=' });
        let _ = write!(result, "{}", if i + 2 < data.len() { CHARS[(b3 & 0x3f) as usize] as char } else { '=' });

        i += 3;
    }
    result
}

impl FileReader {
    pub fn lines(self) -> Box<dyn Iterator<Item = std::io::Result<String>>> {
        match self {
            FileReader::Plain(reader) => Box::new(reader.lines()),
            FileReader::Gzip(reader) => Box::new(reader.lines()),
            FileReader::Bzip2(reader) => Box::new(reader.lines()),
            FileReader::Zstd(reader) => Box::new(reader.lines()),
            FileReader::Stdin(reader) => Box::new(reader.lines()),
            FileReader::Sqlite(reader) => reader.lines(),
        }
    }
}

pub fn create_reader(path: Option<&str>, sqlite_db: Option<&str>, sqlite_table: Option<&str>) -> Result<FileReader> {
    // SQLite mode takes precedence
    if let (Some(db_path), Some(table)) = (sqlite_db, sqlite_table) {
        let reader = SqliteReader::new(db_path, table)?;
        return Ok(FileReader::Sqlite(reader));
    }

    match path {
        None => {
            // Read from stdin
            let stdin = std::io::stdin();
            Ok(FileReader::Stdin(BufReader::new(stdin)))
        }
        Some(path) => {
            let file = std::fs::File::open(path).context("Failed to open file")?;

            if path.ends_with(".zst") {
                let decoder = Decoder::new(file).context("Failed to create zstd decoder")?;
                Ok(FileReader::Zstd(BufReader::new(decoder)))
            } else if path.ends_with(".gz") {
                let decoder = GzDecoder::new(file);
                Ok(FileReader::Gzip(BufReader::new(decoder)))
            } else if path.ends_with(".bz2") {
                let decoder = BzDecoder::new(file);
                Ok(FileReader::Bzip2(BufReader::new(decoder)))
            } else {
                Ok(FileReader::Plain(BufReader::new(file)))
            }
        }
    }
}
