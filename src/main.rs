//! tsepack — CLI base v0.1.
//!
//! Implementados: `inspect`, `benchmark`, `verify` (+ geração de
//! manifesto via `inspect --manifest`).
//! Demais subcomandos existem como contrato de interface, mas
//! retornam erro explícito de "não implementado nesta base"
//! (ver docs/PLANO.md para a fase de cada um). Nenhum comando
//! finge sucesso.

use anyhow::{bail, Context, Result};
use clap::{Parser, Subcommand};
use std::path::PathBuf;

#[derive(Parser)]
#[command(
    name = "tsepack",
    version,
    about = "Compressão extrema e verificável dos dados do TSE — base v0.1"
)]
struct Cli {
    /// Threads de CPU (0 = automático via Rayon).
    #[arg(long, global = true, default_value_t = 0)]
    threads: usize,

    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// Lista conjuntos oficiais conhecidos (Fase 1; nesta base: só registra a limitação).
    Discover {
        #[arg(long, default_value_t = 2026)]
        year: u16,
    },
    /// Baixa arquivos oficiais com hash + manifesto (Fase 2; não implementado na base).
    Download {
        #[arg(long, default_value_t = 2026)]
        year: u16,
        #[arg(long)]
        round: Option<u8>,
        #[arg(long)]
        state: Option<String>,
        #[arg(long, default_value = "./dados")]
        out: PathBuf,
    },
    /// Inspeciona um diretório: contagem/tamanhos por tipo; gera manifesto com --manifest.
    Inspect {
        #[arg(long)]
        input: PathBuf,
        #[arg(long)]
        manifest: Option<PathBuf>,
        #[arg(long, default_value = "tse-dados-abertos:amostra-local")]
        source: String,
    },
    /// Benchmark real de baselines (stored + ZSTD) sobre arquivo ou diretório.
    Benchmark {
        #[arg(long)]
        input: PathBuf,
        #[arg(long, default_value = "quick")]
        profile: String,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    /// Compressão otimizada (Fase 3+; não implementada na base).
    Optimize {
        #[arg(long)]
        input: PathBuf,
        #[arg(long, default_value = "forensic")]
        mode: String,
        #[arg(long, default_value = "./compactado")]
        output: PathBuf,
    },
    /// Verifica arquivos de origem contra um manifesto (Nível 1).
    Verify {
        #[arg(long)]
        manifest: PathBuf,
        #[arg(long)]
        source: PathBuf,
    },
    /// Restaura originais (perfil FORENSIC; não implementado na base).
    Restore {
        #[arg(long)]
        dataset: PathBuf,
        #[arg(long)]
        output: PathBuf,
    },
    /// Auditoria eleitoral (Fase 5; não implementada na base).
    Audit {
        #[arg(long)]
        dataset: PathBuf,
    },
    /// Relatório consolidado (não implementado na base).
    Report {
        #[arg(long)]
        dataset: PathBuf,
    },
}

fn apply_threads(n: usize) {
    if n > 0 {
        let _ = rayon::ThreadPoolBuilder::new()
            .num_threads(n)
            .build_global();
    }
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    apply_threads(cli.threads);
    match cli.cmd {
        Cmd::Discover { year } => {
            bail!("discover: não implementado na base v0.1 (Fase 1). Ano solicitado: {year}. Veja docs/PLANO.md.");
        }
        Cmd::Download {
            year,
            round,
            state,
            out,
        } => {
            let _ = (year, round, state, out);
            bail!("download: não implementado na base v0.1 (Fase 2). Veja docs/PLANO.md.");
        }
        Cmd::Inspect {
            input,
            manifest,
            source,
        } => {
            let report = tsepack::inspect::scan(&input)
                .with_context(|| format!("inspecionar {}", input.display()))?;
            println!("arquivos: {}", report.file_count);
            println!("bytes:    {}", report.total_bytes);
            for t in &report.by_type {
                println!(
                    "  {:>16}  {:>6} arq  {:>12} bytes",
                    t.extension, t.count, t.bytes
                );
            }
            if let Some(mpath) = manifest {
                let m = tsepack::manifest::Manifest::build_from_dir(&input, &source)?;
                m.save(&mpath)?;
                println!(
                    "manifesto: {} ({} arquivos)",
                    mpath.display(),
                    m.files.len()
                );
            }
        }
        Cmd::Benchmark {
            input,
            profile,
            output,
        } => {
            if profile != "quick" && profile != "exhaustive" {
                bail!("profile deve ser 'quick' ou 'exhaustive' (recebido: {profile})");
            }
            let reports = tsepack::benchmark::run_on_path(&input, &profile)?;
            for r in &reports {
                println!("== {} [{}]", r.input, r.profile);
                for c in &r.cases {
                    println!(
                        "  {:<10} {:>12} -> {:>12}  razão {:>6.2}x  {:>+7.1}%  comp {:>6}ms  decomp {:>6}ms  round_trip={}",
                        c.method, c.input_bytes, c.output_bytes, c.ratio,
                        c.saved_pct, c.compress_ms, c.decompress_ms, c.round_trip_ok
                    );
                    if !c.round_trip_ok {
                        bail!("round-trip FALHOU para {} em {}", c.method, r.input);
                    }
                }
            }
            if let Some(opath) = output {
                let json = serde_json::to_string_pretty(&reports)?;
                std::fs::write(&opath, json)?;
                println!("relatório JSON: {}", opath.display());
            }
        }
        Cmd::Optimize { .. } => {
            bail!("optimize: não implementado na base v0.1 (Fases 3–4). Use `benchmark` para baselines. Veja docs/PLANO.md.");
        }
        Cmd::Verify { manifest, source } => {
            let rep = tsepack::verify::verify(&manifest, &source)?;
            println!(
                "verificação: {}/{} aprovados  aprovado={}",
                rep.passed, rep.files_checked, rep.approved
            );
            for v in rep
                .verdicts
                .iter()
                .filter(|v| v.status != tsepack::verify::VerifyStatus::Ok)
            {
                println!("  FALHA {:?} {}", v.status, v.path);
            }
            println!("{}", serde_json::to_string_pretty(&rep)?);
            if !rep.approved {
                std::process::exit(1);
            }
        }
        Cmd::Restore { .. } => {
            bail!("restore: não implementado na base v0.1 (perfil FORENSIC, Fase 4). Veja docs/PLANO.md.");
        }
        Cmd::Audit { .. } => {
            bail!("audit: não implementado na base v0.1 (Fase 5). Veja docs/PLANO.md.");
        }
        Cmd::Report { .. } => {
            bail!("report: não implementado na base v0.1 (Fase 4). Veja docs/PLANO.md.");
        }
    }
    Ok(())
}
