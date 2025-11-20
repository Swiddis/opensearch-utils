use anyhow::{Context, Result};
use flate2::read::GzDecoder;
use std::io::{BufRead, BufReader};
use zstd::Decoder;

pub enum FileReader {
    Plain(BufReader<std::fs::File>),
    Gzip(BufReader<GzDecoder<std::fs::File>>),
    Zstd(BufReader<Decoder<'static, BufReader<std::fs::File>>>),
}

impl FileReader {
    pub fn lines(self) -> Box<dyn Iterator<Item = std::io::Result<String>>> {
        match self {
            FileReader::Plain(reader) => Box::new(reader.lines()),
            FileReader::Gzip(reader) => Box::new(reader.lines()),
            FileReader::Zstd(reader) => Box::new(reader.lines()),
        }
    }
}

pub fn create_reader(path: &str) -> Result<FileReader> {
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
