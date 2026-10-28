//! Baselines em streaming. Relatório v2: tempos medidos, artefatos e retomada.
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::Digest;
use std::collections::BTreeMap;
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};
use std::time::Instant;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BenchCase {
    pub method: String,
    pub input_bytes: u64,
    pub output_bytes: u64,
    pub ratio: Option<f64>,
    pub saved_pct: Option<f64>,
    pub compress_ms: Option<u128>,
    pub decompress_ms: Option<u128>,
    pub compress_ns: Option<u128>,
    pub decompress_ns: Option<u128>,
    pub round_trip_ok: bool,
    pub compression_reused: bool,
    pub compressed_file: Option<String>,
    pub compressed_sha256: Option<String>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BenchReport {
    pub format_version: u32,
    pub input: String,
    pub source_sha256: String,
    pub profile: String,
    pub cases: Vec<BenchCase>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PackColumnBench {
    pub file: String,
    pub input_bytes: u64,
    pub zstd_bytes: BTreeMap<String, u64>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PackBenchReport {
    pub format_version: u32,
    pub complete: bool,
    pub pack_dir: String,
    pub profile: String,
    /// Denominador: bytes do CSV original, e não bytes inflados das colunas.
    pub input_bytes: u64,
    pub pack_uncompressed_bytes: u64,
    pub pack_json_bytes: u64,
    pub manifest_sha256: String,
    pub environment: String,
    pub storage_scope: String,
    pub cases: Vec<BenchCase>,
    pub columns: Vec<PackColumnBench>,
}
fn levels(profile: &str) -> Result<Vec<(String, i32)>> {
    let values = match profile {
        "quick" => vec![1, 3],
        "exhaustive" => vec![1, 3, 10, 19],
        _ => bail!("profile deve ser quick ou exhaustive"),
    };
    Ok(values
        .into_iter()
        .map(|n| (format!("zstd-{n}"), n))
        .collect())
}
fn digest_files(paths: &[PathBuf]) -> Result<(String, u64)> {
    let mut out = crate::bweb::HashWriter::new();
    for path in paths {
        std::io::copy(&mut std::fs::File::open(path)?, &mut out)?;
    }
    Ok((hex::encode(out.hash.finalize()), out.bytes))
}
fn check_decoded(path: &Path, codec: &str, expected: &(String, u64)) -> Result<u128> {
    let t = Instant::now();
    let input = std::fs::File::open(path)?;
    let mut reader: Box<dyn Read> = if codec.starts_with("zstd-") {
        Box::new(zstd::stream::read::Decoder::new(input)?)
    } else {
        Box::new(brotli::Decompressor::new(
            input,
            crate::limits::get("IO_BUFFER_BYTES")? as usize,
        ))
    };
    let mut hash = crate::bweb::HashWriter::new();
    std::io::copy(
        &mut reader.by_ref().take(expected.1.saturating_add(1)),
        &mut hash,
    )?;
    if hash.bytes != expected.1 || hex::encode(hash.hash.finalize()) != expected.0 {
        bail!("round-trip FALHOU: {}", path.display());
    }
    Ok(t.elapsed().as_nanos())
}

fn check_column_frames(
    path: &Path,
    sizes: &[u64],
    columns: &[crate::bweb::ColumnMeta],
) -> Result<()> {
    let mut offset = 0u64;
    for (size, column) in sizes.iter().zip(columns) {
        let mut file = std::fs::File::open(path)?;
        file.seek(SeekFrom::Start(offset))?;
        let mut decoder = zstd::stream::read::Decoder::new(file.take(*size))?;
        let mut actual = crate::bweb::HashWriter::new();
        std::io::copy(
            &mut decoder.by_ref().take(column.bytes.saturating_add(1)),
            &mut actual,
        )?;
        if actual.bytes != column.bytes || hex::encode(actual.hash.finalize()) != column.sha256 {
            bail!("limites de frame do checkpoint divergem: {}", column.file);
        }
        offset = offset.checked_add(*size).context("overflow dos frames")?;
    }
    Ok(())
}
fn encode(paths: &[PathBuf], path: &Path, level: Option<i32>, separate: bool) -> Result<Vec<u64>> {
    let mut sizes = Vec::new();
    if separate {
        for (index, input) in paths.iter().enumerate() {
            eprintln!("  coluna {}/{}", index + 1, paths.len());
            let before = std::fs::metadata(path)?.len();
            let output = std::fs::OpenOptions::new().append(true).open(path)?;
            let mut encoder =
                zstd::stream::write::Encoder::new(output, level.context("nível ausente")?)?;
            std::io::copy(&mut std::fs::File::open(input)?, &mut encoder)?;
            encoder.finish()?.flush()?;
            sizes.push(std::fs::metadata(path)?.len() - before);
        }
    } else if let Some(level) = level {
        let mut encoder = zstd::stream::write::Encoder::new(std::fs::File::create(path)?, level)?;
        for input in paths {
            std::io::copy(&mut std::fs::File::open(input)?, &mut encoder)?;
        }
        encoder.finish()?.flush()?;
    } else {
        let mut input: Box<dyn Read> = Box::new(std::io::empty());
        for source in paths {
            input = Box::new(input.chain(std::fs::File::open(source)?));
        }
        let mut output = std::io::BufWriter::with_capacity(
            crate::limits::get("IO_BUFFER_BYTES")? as usize,
            std::fs::File::create(path)?,
        );
        let params = brotli::enc::BrotliEncoderParams {
            quality: 5,
            lgwin: 22,
            ..Default::default()
        };
        brotli::BrotliCompress(&mut input, &mut output, &params)?;
        output.flush()?;
    }
    Ok(sizes)
}
fn case(
    method: String,
    original: u64,
    output: u64,
    comp: Option<u128>,
    dec: Option<u128>,
) -> BenchCase {
    BenchCase {
        method,
        input_bytes: original,
        output_bytes: output,
        ratio: if original > 0 && output > 0 {
            Some(original as f64 / output as f64)
        } else {
            None
        },
        saved_pct: if original > 0 {
            Some(100.0 * (1.0 - output as f64 / original as f64))
        } else {
            None
        },
        compress_ms: comp.map(|n| n / 1_000_000),
        decompress_ms: dec.map(|n| n / 1_000_000),
        compress_ns: comp,
        decompress_ns: dec,
        round_trip_ok: true,
        compression_reused: false,
        compressed_file: None,
        compressed_sha256: None,
    }
}
pub fn run_on_file(input: &Path, profile: &str) -> Result<BenchReport> {
    let methods = levels(profile)?;
    if !std::fs::metadata(input)?.is_file() {
        bail!("entrada não é arquivo regular");
    }
    let paths = [input.to_path_buf()];
    let expected = digest_files(&paths)?;
    let stage = crate::output::Stage::new(
        &std::env::temp_dir().join(format!("urnapack-filebench-{}", std::process::id())),
        true,
    )?;
    let mut cases = vec![case("stored".into(), expected.1, expected.1, None, None)];
    for (method, level) in methods
        .into_iter()
        .map(|(m, l)| (m, Some(l)))
        .chain(std::iter::once(("brotli-5".into(), None)))
    {
        eprintln!("benchmark: {method}: {}", input.display());
        let output = stage.path.join("compressed");
        let t = Instant::now();
        encode(&paths, &output, level, false)?;
        let compress_ns = t.elapsed().as_nanos();
        let decompress_ns = check_decoded(&output, &method, &expected)?;
        cases.push(case(
            method,
            expected.1,
            std::fs::metadata(output)?.len(),
            Some(compress_ns),
            Some(decompress_ns),
        ));
    }
    Ok(BenchReport {
        format_version: 2,
        input: input.display().to_string(),
        source_sha256: expected.0,
        profile: profile.into(),
        cases,
    })
}
fn save_checkpoint(path: &Path, report: &PackBenchReport) -> Result<()> {
    let temporary = crate::output::Stage::temporary(path, false)?;
    std::fs::write(&temporary.path, serde_json::to_vec_pretty(report)?)?;
    std::fs::rename(&temporary.path, path)?;
    Ok(())
}
pub fn run_pack_columns(pack: &Path, profile: &str) -> Result<PackBenchReport> {
    run_pack_checkpoint(pack, profile, None, false)
}
pub fn run_pack_checkpoint(
    pack: &Path,
    profile: &str,
    output: Option<&Path>,
    resume: bool,
) -> Result<PackBenchReport> {
    let methods = levels(profile)?;
    let manifest = crate::bweb::load_verified(pack)?;
    let original_bytes = crate::bweb::verify_restoration(pack, &manifest)?;
    let paths: Vec<_> = manifest
        .columns
        .iter()
        .map(|c| pack.join(&c.file))
        .collect();
    let expected = digest_files(&paths)?;
    let metadata_path = pack.join("pack.json");
    let metadata_bytes = std::fs::metadata(&metadata_path)?.len();
    let metadata_sha = crate::hash::sha256_file(&metadata_path)?;
    let cpu = std::fs::read_to_string("/proc/cpuinfo").ok().and_then(|s| {
        s.lines()
            .find(|l| l.starts_with("model name"))
            .map(str::to_string)
    });
    let environment=format!("{}-{} zstd={} cpu={:?}; streaming single-thread; compression includes input I/O; decoding includes SHA-256",std::env::consts::OS,std::env::consts::ARCH,zstd::zstd_safe::version_string(),cpu);
    let temporary;
    let assets = if let Some(output) = output {
        if crate::output::resolved_target(output)?.starts_with(std::fs::canonicalize(pack)?) {
            bail!("relatório dentro do pacote recusado");
        }
        if std::fs::symlink_metadata(output).is_ok_and(|m| m.file_type().is_symlink()) {
            bail!("symlink no relatório recusado");
        }
        if output.exists() && !resume {
            bail!("relatório existente; use --resume ou outra saída");
        }
        let dir = output.with_file_name(format!(
            "{}.assets",
            output
                .file_name()
                .context("nome de relatório ausente")?
                .to_string_lossy()
        ));
        if std::fs::symlink_metadata(&dir).is_ok_and(|m| m.file_type().is_symlink()) {
            bail!("symlink nos artefatos recusado");
        }
        if dir.exists() && !resume {
            bail!("diretório de artefatos existente");
        }
        std::fs::create_dir_all(&dir)?;
        dir
    } else {
        if resume {
            bail!("--resume exige --output");
        }
        temporary = crate::output::Stage::new(
            &std::env::temp_dir().join(format!("urnapack-packbench-{}", std::process::id())),
            true,
        )?;
        temporary.path.clone()
    };
    let mut report=PackBenchReport {format_version:2,complete:false,pack_dir:pack.display().to_string(),profile:profile.into(),input_bytes:original_bytes,
        pack_uncompressed_bytes:expected.1+metadata_bytes,pack_json_bytes:metadata_bytes,manifest_sha256:metadata_sha.clone(),environment:environment.clone(),
        storage_scope:"CSV member bytes + pack metadata; original ZIP, acquisition provenance and caches excluded; project-wide storage not established".into(),
        cases:vec![case("pack-stored".into(),original_bytes,expected.1+metadata_bytes,None,None)],
        columns:manifest.columns.iter().map(|c|PackColumnBench{file:c.file.clone(),input_bytes:c.bytes,zstd_bytes:BTreeMap::new()}).collect()};
    if resume {
        let output = output.context("--resume exige relatório")?;
        report = serde_json::from_slice(&std::fs::read(output).context("ler checkpoint")?)?;
        if report.format_version != 2
            || report.manifest_sha256 != metadata_sha
            || report.profile != profile
            || report.input_bytes != original_bytes
            || report.environment != environment
            || report.pack_uncompressed_bytes != expected.1 + metadata_bytes
            || report.pack_json_bytes != metadata_bytes
            || report.columns.len() != manifest.columns.len()
        {
            bail!("checkpoint incompatível com entrada, perfil, versão ou ambiente");
        }
        for (a, b) in report.columns.iter().zip(&manifest.columns) {
            if a.file != b.file || a.input_bytes != b.bytes {
                bail!("checkpoint com colunas divergentes");
            }
        }
    }
    let mut planned = vec![("pack-stored".to_string(), "stored".to_string(), None, false)];
    for (codec, level) in &methods {
        planned.push((
            format!("pack-col-{codec}"),
            codec.clone(),
            Some(*level),
            true,
        ));
        planned.push((
            format!("pack-solid-{codec}"),
            codec.clone(),
            Some(*level),
            false,
        ));
    }
    report.complete = false;
    if let Some(output) = output {
        save_checkpoint(output, &report)?;
    }
    let mut seen = std::collections::HashSet::new();
    if report.cases.is_empty() {
        bail!("checkpoint sem stored");
    }
    for (index, cached) in report.cases.iter_mut().enumerate() {
        if planned.get(index).map(|m| m.0.as_str()) != Some(cached.method.as_str()) {
            bail!("checkpoint não é prefixo dos métodos planejados");
        }
        if !seen.insert(cached.method.clone()) || !planned.iter().any(|m| m.0 == cached.method) {
            bail!("checkpoint com método duplicado/desconhecido");
        }
        if cached.input_bytes != original_bytes || !cached.round_trip_ok {
            bail!("checkpoint inválido");
        }
        if cached.method == "pack-stored" {
            if cached.output_bytes != expected.1 + metadata_bytes {
                bail!("stored divergente");
            }
            *cached = case(
                "pack-stored".into(),
                original_bytes,
                expected.1 + metadata_bytes,
                None,
                None,
            );
            continue;
        }
        if cached.compress_ns.is_none()
            || cached.compress_ms != cached.compress_ns.map(|n| n / 1_000_000)
        {
            bail!("tempos de checkpoint inconsistentes");
        }
        let mut frame_sizes = Vec::new();
        if cached.method.starts_with("pack-col-") {
            let codec = cached
                .method
                .strip_prefix("pack-col-")
                .context("codec ausente")?;
            let mut bytes = metadata_bytes;
            for column in &report.columns {
                let size = *column
                    .zstd_bytes
                    .get(codec)
                    .context("detalhe de coluna ausente")?;
                bytes = bytes.checked_add(size).context("overflow dos frames")?;
                frame_sizes.push(size);
            }
            if bytes != cached.output_bytes {
                bail!("detalhes de colunas do checkpoint divergem");
            }
        }
        let filename = format!("{}.zst", cached.method);
        if cached.compressed_file.as_deref() != Some(&filename) {
            bail!("caminho de cache inválido");
        }
        let file = assets.join(&filename);
        if std::fs::symlink_metadata(&file)?.file_type().is_symlink() {
            bail!("symlink de cache");
        }
        if cached.compressed_sha256.as_deref() != Some(&crate::hash::sha256_file(&file)?)
            || cached.output_bytes != std::fs::metadata(&file)?.len() + metadata_bytes
        {
            bail!("cache corrompido");
        }
        let codec = planned
            .iter()
            .find(|m| m.0 == cached.method)
            .context("codec ausente")?
            .1
            .clone();
        let ns = check_decoded(&file, &codec, &expected)?;
        if !frame_sizes.is_empty() {
            check_column_frames(&file, &frame_sizes, &manifest.columns)?;
        }
        let metrics = case(
            cached.method.clone(),
            original_bytes,
            cached.output_bytes,
            cached.compress_ns,
            Some(ns),
        );
        cached.ratio = metrics.ratio;
        cached.saved_pct = metrics.saved_pct;
        cached.decompress_ns = Some(ns);
        cached.decompress_ms = Some(ns / 1_000_000);
        cached.compression_reused = true;
    }
    report.complete = false;
    if let Some(output) = output {
        save_checkpoint(output, &report)?;
    }
    for (name, codec, level, separate) in planned.into_iter().skip(1) {
        if seen.contains(&name) {
            eprintln!("benchmark: {name}: cache reconferido");
            continue;
        }
        eprintln!("benchmark: iniciando {name}");
        let filename = format!("{name}.zst");
        let final_path = assets.join(&filename);
        if final_path.exists() {
            bail!(
                "artefato sem checkpoint correspondente: {}",
                final_path.display()
            );
        }
        let stage = crate::output::Stage::new(&final_path, false)?;
        let t = Instant::now();
        let sizes = encode(&paths, &stage.path, level, separate)?;
        let comp = t.elapsed().as_nanos();
        let dec = check_decoded(&stage.path, &codec, &expected)?;
        let mut measured = case(
            name,
            original_bytes,
            std::fs::metadata(&stage.path)?.len() + metadata_bytes,
            Some(comp),
            Some(dec),
        );
        measured.compressed_file = Some(filename);
        measured.compressed_sha256 = Some(crate::hash::sha256_file(&stage.path)?);
        stage.publish(&final_path)?;
        if separate {
            for (column, size) in report.columns.iter_mut().zip(sizes) {
                column.zstd_bytes.insert(codec.clone(), size);
            }
        }
        report.cases.push(measured);
        if let Some(output) = output {
            save_checkpoint(output, &report)?;
        }
    }
    report.complete = true;
    if let Some(output) = output {
        save_checkpoint(output, &report)?;
    }
    Ok(report)
}
pub fn run_on_path(input: &Path, profile: &str) -> Result<Vec<BenchReport>> {
    if input.is_file() {
        return Ok(vec![run_on_file(input, profile)?]);
    }
    let root = crate::traverse::resolve_root(input)?;
    crate::traverse::collect_files(&root)?
        .iter()
        .map(|p| run_on_file(p, profile))
        .collect()
}

pub fn save_reports(reports: &[BenchReport], output: &Path) -> Result<()> {
    let stage = crate::output::Stage::new(output, false)?;
    std::fs::write(&stage.path, serde_json::to_vec_pretty(reports)?)?;
    stage.publish(output)
}
