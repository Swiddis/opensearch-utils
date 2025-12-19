use anyhow::{Context, Result};
use bzip2::read::BzDecoder;
use flate2::read::GzDecoder;
use std::io::{BufRead, BufReader, Stdin};
use zstd::Decoder;

pub enum FileReader {
    Plain(BufReader<std::fs::File>),
    Gzip(BufReader<GzDecoder<std::fs::File>>),
    Bzip2(BufReader<BzDecoder<std::fs::File>>),
    Zstd(BufReader<Decoder<'static, BufReader<std::fs::File>>>),
    Stdin(BufReader<Stdin>),
}

impl FileReader {
    pub fn lines(self) -> Box<dyn Iterator<Item = std::io::Result<String>>> {
        match self {
            FileReader::Plain(reader) => Box::new(reader.lines()),
            FileReader::Gzip(reader) => Box::new(reader.lines()),
            FileReader::Bzip2(reader) => Box::new(reader.lines()),
            FileReader::Zstd(reader) => Box::new(reader.lines()),
            FileReader::Stdin(reader) => Box::new(reader.lines()),
        }
    }
}

pub fn create_reader(path: Option<&str>) -> Result<FileReader> {
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
