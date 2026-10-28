//! Codecs interoperáveis: streaming, saída nova, limites e round-trip obrigatório.
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::Digest;
use std::io::{BufReader, Read, Write};
use std::path::Path;
use std::process::{Child, Command, Stdio};
use std::time::Instant;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Measurement {
    pub artifact_kind: String,
    pub format_version: u32,
    pub codec: String,
    pub input_bytes: u64,
    pub source_sha256: String,
    pub output_bytes: u64,
    pub encoded_sha256: String,
    pub dictionary_sha256: Option<String>,
    pub dictionary_bytes: u64,
    pub compress_ns: u128,
    pub decompress_ns: u128,
    pub round_trip_ok: bool,
}

fn parameters(method: &str) -> Result<(&str, i32)> {
    match method {
        "stored" => Ok(("stored", 0)),
        "xz-6" => Ok(("xz", 6)),
        "xz-9e" => Ok(("xz", 9)),
        "zstd-1" => Ok(("zstd", 1)),
        "zstd-3" => Ok(("zstd", 3)),
        "zstd-10" => Ok(("zstd", 10)),
        "zstd-19" => Ok(("zstd", 19)),
        "zstd-3-blocks" => Ok(("zstd", 3)),
        "zstd-19-blocks" => Ok(("zstd", 19)),
        "brotli-5" => Ok(("brotli", 5)),
        "brotli-11" => Ok(("brotli", 11)),
        _ => bail!("codec não suportado: {method}"),
    }
}
fn dictionary(path: Option<&Path>, kind: &str) -> Result<Vec<u8>> {
    if let Some(path) = path {
        if kind != "zstd"
            || std::fs::metadata(path)?.len() > crate::limits::get("MAX_DICTIONARY_BYTES")?
        {
            bail!("dicionário incompatível ou excessivo");
        }
        return Ok(std::fs::read(path)?);
    }
    Ok(Vec::new())
}

pub struct Decoded {
    reader: Box<dyn Read>,
    child: Option<Child>,
    bytes: u64,
    maximum: u64,
}
impl Read for Decoded {
    fn read(&mut self, data: &mut [u8]) -> std::io::Result<usize> {
        let n = self.reader.read(data)?;
        self.bytes += n as u64;
        if self.bytes > self.maximum {
            return Err(std::io::Error::other("limite de descompressão excedido"));
        }
        Ok(n)
    }
}
impl Decoded {
    pub fn finish(mut self) -> Result<()> {
        std::io::copy(&mut self, &mut std::io::sink())?;
        if let Some(mut child) = self.child.take() {
            if !child.wait()?.success() {
                bail!("xz: descompressão reprovada");
            }
        }
        Ok(())
    }
}
impl Drop for Decoded {
    fn drop(&mut self) {
        if let Some(child) = &mut self.child {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}
pub fn reader(input: &Path, method: &str, dict: Option<&Path>, maximum: u64) -> Result<Decoded> {
    let (kind, _) = parameters(method)?;
    let dict = dictionary(dict, kind)?;
    let mut child = None;
    let file = std::fs::File::open(input)?;
    let reader: Box<dyn Read> = match kind {
        "stored" => Box::new(file),
        "zstd" => Box::new(zstd::stream::read::Decoder::with_dictionary(
            BufReader::new(file),
            &dict,
        )?),
        "brotli" => Box::new(brotli::Decompressor::new(
            file,
            crate::limits::get("IO_BUFFER_BYTES")? as usize,
        )),
        "xz" => {
            let mut process = Command::new("xz")
                .args(["-d", "-c", "--threads=1", "--"])
                .arg(input)
                .stdin(Stdio::null())
                .stdout(Stdio::piped())
                .stderr(Stdio::inherit())
                .spawn()
                .context("executar xz")?;
            let pipe = process.stdout.take().context("stdout xz ausente")?;
            child = Some(process);
            Box::new(pipe)
        }
        _ => unreachable!(),
    };
    Ok(Decoded {
        reader,
        child,
        bytes: 0,
        maximum,
    })
}

pub fn compress(
    input: &Path,
    output: &Path,
    method: &str,
    dict: Option<&Path>,
) -> Result<Measurement> {
    let (kind, level) = parameters(method)?;
    if crate::output_path_conflicts(input, output)? {
        bail!("saída sobrepõe origem");
    }
    let size = std::fs::metadata(input)?.len();
    if !input.is_file() || size > crate::limits::get("MAX_PACK_BYTES")? {
        bail!("origem inválida/excessiva");
    }
    let dict_bytes = dictionary(dict, kind)?;
    let source_sha256 = crate::hash::sha256_file(input)?;
    let stage = crate::output::Stage::new(output, false)?;
    let start = Instant::now();
    let file = std::fs::File::create(&stage.path)?;
    let mut source = std::fs::File::open(input)?;
    match kind {
        "stored" => {
            std::io::copy(&mut source, &mut { file })?;
        }
        "zstd" => {
            if method.ends_with("-blocks") {
                let mut output = file;
                let mut buffer = vec![0; crate::limits::get("COMPRESSION_BLOCK_BYTES")? as usize];
                loop {
                    let mut n = 0;
                    while n < buffer.len() {
                        let read = source.read(&mut buffer[n..])?;
                        if read == 0 {
                            break;
                        }
                        n += read;
                    }
                    if n == 0 {
                        break;
                    }
                    let mut encoder = zstd::stream::write::Encoder::with_dictionary(
                        &mut output,
                        level,
                        &dict_bytes,
                    )?;
                    encoder.set_pledged_src_size(Some(n as u64))?;
                    encoder.write_all(&buffer[..n])?;
                    encoder.finish()?;
                }
                output.flush()?;
            } else {
                let mut encoder =
                    zstd::stream::write::Encoder::with_dictionary(file, level, &dict_bytes)?;
                std::io::copy(&mut source, &mut encoder)?;
                encoder.finish()?.flush()?;
            }
        }
        "brotli" => {
            let mut target = std::io::BufWriter::new(file);
            let params = brotli::enc::BrotliEncoderParams {
                quality: level,
                lgwin: if level == 11 { 24 } else { 22 },
                ..Default::default()
            };
            brotli::BrotliCompress(&mut source, &mut target, &params)?;
            target.flush()?;
        }
        "xz" => {
            let option = if level == 9 { "-9e" } else { "-6" };
            let status = Command::new("xz")
                .args([option, "--threads=1", "--check=crc64", "-c", "--"])
                .arg(input)
                .stdin(Stdio::null())
                .stdout(file)
                .stderr(Stdio::inherit())
                .status()
                .context("executar xz")?;
            if !status.success() {
                bail!("xz: compressão reprovada");
            }
        }
        _ => unreachable!(),
    }
    let compress_ns = start.elapsed().as_nanos();
    let decompress_ns = check(&stage.path, method, dict, &source_sha256, size)?;
    let result = Measurement {
        artifact_kind: "urnapack_codec_measurement".into(),
        format_version: 1,
        codec: method.into(),
        input_bytes: size,
        source_sha256,
        output_bytes: std::fs::metadata(&stage.path)?.len(),
        encoded_sha256: crate::hash::sha256_file(&stage.path)?,
        dictionary_sha256: if dict_bytes.is_empty() {
            None
        } else {
            Some(crate::hash::sha256_bytes(&dict_bytes))
        },
        dictionary_bytes: dict_bytes.len() as u64,
        compress_ns,
        decompress_ns,
        round_trip_ok: true,
    };
    stage.publish(output)?;
    Ok(result)
}

pub fn check(
    input: &Path,
    method: &str,
    dict: Option<&Path>,
    expected_sha: &str,
    size: u64,
) -> Result<u128> {
    if size > crate::limits::get("MAX_PACK_BYTES")? {
        bail!("limite de saída decodificada excedido");
    }
    let start = Instant::now();
    let mut decoded = reader(input, method, dict, size.saturating_add(1))?;
    let mut hash = crate::bweb::HashWriter::new();
    std::io::copy(&mut decoded, &mut hash)?;
    decoded.finish()?;
    if hash.bytes != size || hex::encode(hash.hash.finalize()) != expected_sha {
        bail!("round-trip diverge");
    }
    Ok(start.elapsed().as_nanos())
}

pub fn decompress(
    input: &Path,
    output: &Path,
    method: &str,
    dict: Option<&Path>,
    expected_sha: &str,
    expected_size: u64,
) -> Result<()> {
    if crate::output_path_conflicts(input, output)? {
        bail!("saída sobrepõe entrada");
    }
    let stage = crate::output::Stage::new(output, false)?;
    let mut reader = reader(input, method, dict, expected_size.saturating_add(1))?;
    let mut file = std::fs::File::create(&stage.path)?;
    let bytes = std::io::copy(&mut reader, &mut file)?;
    reader.finish()?;
    file.flush()?;
    if bytes != expected_size || crate::hash::sha256_file(&stage.path)? != expected_sha {
        bail!("SHA-256/tamanho restaurados divergem");
    }
    stage.publish(output)
}

pub fn train(input: &Path, output: &Path, size: usize) -> Result<()> {
    if size == 0 || size as u64 > crate::limits::get("MAX_DICTIONARY_BYTES")? {
        bail!("tamanho de dicionário inválido");
    }
    let maximum = crate::limits::get("MAX_DICT_TRAIN_BYTES")?;
    let sample_bytes = crate::limits::get("DICT_SAMPLE_BYTES")? as usize;
    let mut source = std::fs::File::open(input)?.take(maximum);
    let mut samples = Vec::new();
    loop {
        let mut chunk = vec![0; sample_bytes];
        let mut read = 0;
        while read < chunk.len() {
            let n = source.read(&mut chunk[read..])?;
            if n == 0 {
                break;
            }
            read += n;
        }
        if read == 0 {
            break;
        }
        chunk.truncate(read);
        samples.push(chunk);
    }
    let dictionary = zstd::dict::from_samples(&samples, size)?;
    let stage = crate::output::Stage::new(output, false)?;
    std::fs::write(&stage.path, dictionary)?;
    stage.publish(output)
}
