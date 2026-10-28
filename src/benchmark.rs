//! Benchmark de baselines reais de compressão (Fase 2, parcial).
//!
//! Base v0.1: mede `stored` (sem compressão) + ZSTD em níveis
//! representativos. Cada caso inclui verificação de round-trip
//! (descomprime e compara bytes). Perfis:
//! - `quick`: níveis 1 e 3 (rápido, para triagem).
//! - `exhaustive`: níveis 1, 3, 10 e 19 (caro; para decisão final).
//!
//! Comparações com LZMA2/XZ, Brotli, Parquet e dicionários ZSTD
//! estão planejadas (ver docs/PLANO.md) e NÃO estão nesta base.

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::path::Path;
use std::time::Instant;

/// Resultado medido para um método sobre uma entrada.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BenchCase {
    pub method: String,
    pub input_bytes: u64,
    pub output_bytes: u64,
    /// input / output (>1 = comprimiu).
    pub ratio: f64,
    /// 100 * (1 - output/input). Negativa = expandiu.
    pub saved_pct: f64,
    pub compress_ms: u128,
    pub decompress_ms: u128,
    /// Round-trip byte a byte conferido nesta execução.
    pub round_trip_ok: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BenchReport {
    pub input: String,
    pub profile: String,
    pub cases: Vec<BenchCase>,
}

fn levels_for_profile(profile: &str) -> Vec<(String, i32)> {
    match profile {
        "exhaustive" => vec![
            ("zstd-1".into(), 1),
            ("zstd-3".into(), 3),
            ("zstd-10".into(), 10),
            ("zstd-19".into(), 19),
        ],
        _ => vec![("zstd-1".into(), 1), ("zstd-3".into(), 3)],
    }
}

/// Executa o benchmark sobre um único arquivo.
pub fn run_on_file(input: &Path, profile: &str) -> Result<BenchReport> {
    let data = std::fs::read(input).with_context(|| format!("ler {}", input.display()))?;
    let input_bytes = data.len() as u64;
    let mut cases = vec![BenchCase {
        method: "stored".into(),
        input_bytes,
        output_bytes: input_bytes,
        ratio: 1.0,
        saved_pct: 0.0,
        compress_ms: 0,
        decompress_ms: 0,
        round_trip_ok: true,
    }];

    for (name, level) in levels_for_profile(profile) {
        let t0 = Instant::now();
        let compressed =
            zstd::bulk::compress(&data, level).with_context(|| format!("comprimir {name}"))?;
        let compress_ms = t0.elapsed().as_millis();

        let t1 = Instant::now();
        let back = zstd::bulk::decompress(&compressed, data.len())
            .with_context(|| format!("descomprimir {name}"))?;
        let decompress_ms = t1.elapsed().as_millis();

        let output_bytes = compressed.len() as u64;
        cases.push(BenchCase {
            method: name,
            input_bytes,
            output_bytes,
            ratio: input_bytes as f64 / output_bytes.max(1) as f64,
            saved_pct: 100.0 * (1.0 - output_bytes as f64 / input_bytes.max(1) as f64),
            compress_ms,
            decompress_ms,
            round_trip_ok: back == data,
        });
    }

    Ok(BenchReport {
        input: input.to_string_lossy().into_owned(),
        profile: profile.to_string(),
        cases,
    })
}

/// Executa sobre todos os arquivos regulares de um diretório
/// (não recursivo para amostras) ou um arquivo único.
/// Retorna um relatório por arquivo + linha `TOTAL` agregada.
pub fn run_on_path(input: &Path, profile: &str) -> Result<Vec<BenchReport>> {
    if input.is_file() {
        return Ok(vec![run_on_file(input, profile)?]);
    }
    let mut out = Vec::new();
    let mut entries: Vec<_> = std::fs::read_dir(input)
        .with_context(|| format!("listar {}", input.display()))?
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.is_file())
        .collect();
    entries.sort();
    for p in entries {
        out.push(run_on_file(&p, profile)?);
    }
    Ok(out)
}
