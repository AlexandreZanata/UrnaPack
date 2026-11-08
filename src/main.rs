//! tsepack — CLI de compressão e verificação.
//!
//! Implementados: inspect, benchmark, verify, pack/unpack, codec, archive,
//! optimize, restore, queries e analyze (+ manifesto via inspect --manifest).
//! Descoberta, download integrado, auditoria e relatório genérico ainda
//! retornam erro explícito de "não implementado nesta base"
//! (ver docs/PLANO.md para a fase de cada um). Nenhum comando
//! finge sucesso.

use anyhow::{bail, Context, Result};
use clap::{Parser, Subcommand};
use std::path::PathBuf;

fn optional(value: Option<impl std::fmt::Display>) -> String {
    value.map(|v| v.to_string()).unwrap_or_else(|| "n/a".into())
}

#[derive(Parser)]
#[command(
    name = "tsepack",
    version,
    about = "Compressão reversível e verificável dos dados do TSE"
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
    /// Codec reversível em streaming; compressão sempre confere o round-trip.
    Codec {
        #[arg(value_parser=["compress","decompress","train","check"])]
        action: String,
        #[arg(long)]
        input: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
        #[arg(long, default_value = "zstd-3")]
        method: String,
        #[arg(long)]
        dictionary: Option<PathBuf>,
        #[arg(long)]
        expected_sha: Option<String>,
        #[arg(long)]
        expected_bytes: Option<u64>,
        #[arg(long)]
        dictionary_size: Option<usize>,
    },
    /// TAR determinístico, selo verificável ou conferência integral de arquivo.
    Archive {
        #[arg(value_parser=["tar","seal","verify","individual"])]
        action: String,
        #[arg(long)]
        input: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
        #[arg(long)]
        manifest: Option<PathBuf>,
        #[arg(long, default_value = "stored")]
        codec: String,
    },
    /// Q1 votos, Q2 contexto presidencial e recuperação de uma seção de controle.
    Queries {
        #[arg(long)]
        input: PathBuf,
        #[arg(long)]
        output: PathBuf,
    },
    /// Análise descritiva controlada do BU web de MT (Etapa 5A).
    Analyze {
        #[arg(long)]
        input: PathBuf,
        #[arg(long)]
        output: PathBuf,
        #[arg(long, default_value = "mt-2026-t1-bweb-v1")]
        profile: String,
    },
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
    /// Baselines em streaming (stored/ZSTD/Brotli; pacote BU web: ZSTD colunar/sólido).
    Benchmark {
        #[arg(long)]
        input: PathBuf,
        #[arg(long, default_value = "quick")]
        profile: String,
        #[arg(long)]
        output: Option<PathBuf>,
        /// Retoma checkpoint do benchmark de pacote e reconfere artefatos.
        #[arg(long, requires = "output")]
        resume: bool,
    },
    /// Empacota um CSV canônico em colunas reversíveis (Etapa 3; hoje: bweb).
    Pack {
        #[arg(long)]
        family: String,
        #[arg(long)]
        input: PathBuf,
        #[arg(long)]
        output: PathBuf,
        /// SHA-256 esperado do membro de origem (gravado no pacote; o
        /// `unpack` reconfronta e reprova em divergência).
        #[arg(long)]
        source_sha: Option<String>,
    },
    /// Restaura o CSV byte a byte a partir do pacote (perfil FORENSIC).
    Unpack {
        #[arg(long)]
        input: PathBuf,
        #[arg(long)]
        output: PathBuf,
    },
    /// Seleciona menor codec por arquivo com restauração e recibo vinculados.
    Optimize {
        #[arg(long)]
        input: PathBuf,
        #[arg(long, default_value = "forensic")]
        mode: String,
        #[arg(long, default_value = "./compactado")]
        output: PathBuf,
        #[arg(long)]
        manifest: Option<PathBuf>,
        #[arg(long, default_value = "quick")]
        profile: String,
    },
    /// Verifica arquivos de origem contra um manifesto (Nível 1).
    Verify {
        #[arg(long)]
        manifest: PathBuf,
        #[arg(long)]
        source: PathBuf,
    },
    /// Restaura todos os caminhos e bytes de um arquivo FORENSIC selado.
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
        Cmd::Codec {
            action,
            input,
            output,
            method,
            dictionary,
            expected_sha,
            expected_bytes,
            dictionary_size,
        } => match action.as_str() {
            "compress" => println!(
                "{}",
                serde_json::to_string_pretty(&tsepack::codec::compress(
                    &input,
                    &output.context("--output obrigatório")?,
                    &method,
                    dictionary.as_deref()
                )?)?
            ),
            "decompress" => tsepack::codec::decompress(
                &input,
                &output.context("--output obrigatório")?,
                &method,
                dictionary.as_deref(),
                expected_sha
                    .as_deref()
                    .context("--expected-sha obrigatório")?,
                expected_bytes.context("--expected-bytes obrigatório")?,
            )?,
            "train" => tsepack::codec::train(
                &input,
                &output.context("--output obrigatório")?,
                dictionary_size.context("--dictionary-size obrigatório")?,
            )?,
            "check" => {
                let ns = tsepack::codec::check(
                    &input,
                    &method,
                    dictionary.as_deref(),
                    expected_sha
                        .as_deref()
                        .context("--expected-sha obrigatório")?,
                    expected_bytes.context("--expected-bytes obrigatório")?,
                )?;
                println!("{{\"verified\":true,\"decompress_ns\":{ns}}}");
            }
            _ => unreachable!(),
        },
        Cmd::Archive {
            action,
            input,
            output,
            manifest,
            codec,
        } => match action.as_str() {
            "tar" => tsepack::archive::create_tar(
                &input,
                &manifest.context("--manifest obrigatório")?,
                &output.context("--output obrigatório")?,
            )?,
            "seal" => println!(
                "{}",
                serde_json::to_string_pretty(&tsepack::archive::seal(
                    &input,
                    &codec,
                    &manifest.context("--manifest obrigatório")?,
                    &output.context("--output obrigatório")?
                )?)?
            ),
            "verify" => println!(
                "{}",
                serde_json::to_string_pretty(&tsepack::archive::verify(&input)?)?
            ),
            "individual" => println!(
                "{}",
                serde_json::to_string_pretty(&tsepack::archive::seal_individual(
                    &input,
                    &manifest.context("--manifest obrigatório")?,
                    &output.context("--output obrigatório")?
                )?)?
            ),
            _ => unreachable!(),
        },
        Cmd::Queries { input, output } => {
            if output.exists()
                || output.is_symlink()
                || tsepack::output_path_conflicts(&input, &output)?
            {
                bail!("saída de consultas existente/sobreposta");
            }
            let result = tsepack::queries::run(&input)?;
            std::fs::write(output, serde_json::to_vec_pretty(&result)?)?;
        }
        Cmd::Analyze {
            input,
            output,
            profile,
        } => {
            let Some(selected) = tsepack::analyze::profile_for_id(&profile) else {
                bail!(
                    "analyze: perfil não suportado: {profile} (suportado: {})",
                    tsepack::analyze::PROFILE_ID
                );
            };
            let outcome = tsepack::analyze::run(&input, &output, &selected)?;
            println!(
                "análise: {} registros; votos={}; status={}; erros={}",
                outcome.records,
                outcome.votes_total.as_deref().unwrap_or("indisponível"),
                outcome.status,
                outcome.error_count
            );
            println!("saída: {}", outcome.output.display());
            if !outcome.approved {
                eprintln!(
                    "analyze: controles obrigatórios reprovaram; consulte quality.json e REPORT.md"
                );
                std::process::exit(1);
            }
        }
        Cmd::Discover { year } => {
            bail!("discover: não implementado nesta versão. Ano solicitado: {year}. Veja docs/PLANO.md.");
        }
        Cmd::Download {
            year,
            round,
            state,
            out,
        } => {
            let _ = (year, round, state, out);
            bail!("download: use scripts/fetch_source.py; integração na CLI ainda não implementada. Veja docs/PLANO.md.");
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
            resume,
        } => {
            if profile != "quick" && profile != "exhaustive" {
                bail!("profile deve ser 'quick' ou 'exhaustive' (recebido: {profile})");
            }
            if input.is_dir() && input.join("pack.json").is_file() {
                let rep = tsepack::benchmark::run_pack_checkpoint(
                    &input,
                    &profile,
                    output.as_deref(),
                    resume,
                )?;
                println!(
                    "== pacote {} [{}] CSV original {} bytes; saídas incluem pack.json",
                    rep.pack_dir, rep.profile, rep.input_bytes
                );
                for c in &rep.cases {
                    println!(
                        "  {:<18} {:>12} -> {:>12}  razão {}x  {}%  round_trip={}",
                        c.method,
                        c.input_bytes,
                        c.output_bytes,
                        optional(c.ratio),
                        optional(c.saved_pct),
                        c.round_trip_ok
                    );
                    if !c.round_trip_ok {
                        bail!("round-trip FALHOU em {}", c.method);
                    }
                }
                return Ok(());
            }
            if resume {
                bail!("--resume disponível para benchmark de pacote");
            }
            if let Some(path) = &output {
                if tsepack::output_path_conflicts(&input, path)? {
                    bail!("relatório sobrepõe entrada");
                }
                if path.exists() || path.is_symlink() {
                    bail!("relatório existente recusado; use outra saída");
                }
            }
            let reports = tsepack::benchmark::run_on_path(&input, &profile)?;
            for r in &reports {
                println!("== {} [{}]", r.input, r.profile);
                for c in &r.cases {
                    println!(
                        "  {:<10} {:>12} -> {:>12}  razão {}x  {}%  comp {}ms  decomp {}ms  round_trip={}",
                        c.method, c.input_bytes, c.output_bytes, optional(c.ratio),
                        optional(c.saved_pct), optional(c.compress_ms), optional(c.decompress_ms), c.round_trip_ok
                    );
                    if !c.round_trip_ok {
                        bail!("round-trip FALHOU para {} em {}", c.method, r.input);
                    }
                }
            }
            if let Some(opath) = output {
                tsepack::benchmark::save_reports(&reports, &opath)?;
                println!("relatório JSON: {}", opath.display());
            }
        }
        Cmd::Pack {
            family,
            input,
            output,
            source_sha,
        } => {
            if family != "bweb" {
                bail!("pack: família não suportada nesta etapa: {family} (suportada: bweb)");
            }
            if let Some(s) = source_sha.as_deref() {
                if s.len() != 64 || !s.bytes().all(|b| b.is_ascii_hexdigit()) {
                    bail!("pack: source_sha inválido (esperado hex de 64)");
                }
            }
            let m = tsepack::bweb::pack(&input, &output, source_sha)?;
            println!(
                "pacote: {} linhas x {} colunas em {}",
                m.rows,
                m.columns.len(),
                output.display()
            );
            println!("{}", serde_json::to_string_pretty(&m)?);
        }
        Cmd::Unpack { input, output } => {
            let m = tsepack::bweb::unpack(&input, &output)?;
            let sha = tsepack::bweb::sha256_of(&output)?;
            println!(
                "restaurado: {} linhas de {} (SHA-256 {})",
                m.rows,
                output.display(),
                sha
            );
            if let Some(expected) = m.source_member_sha256.as_deref() {
                if expected != sha {
                    bail!("SHA-256 do restaurado diverge do membro de origem");
                }
                println!("FORENSIC: SHA-256 confere com o membro de origem");
            } else {
                println!("aviso: pacote sem source_member_sha256; conferência manual exigida");
            }
        }
        Cmd::Optimize {
            input,
            mode,
            output,
            manifest,
            profile,
        } => {
            if mode != "forensic" {
                bail!("somente mode=forensic é suportado");
            }
            println!(
                "{}",
                serde_json::to_string_pretty(&tsepack::archive::optimize(
                    &input,
                    manifest.as_deref(),
                    &output,
                    &profile
                )?)?
            );
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
        Cmd::Restore { dataset, output } => {
            tsepack::archive::restore(&dataset, &output)?;
            println!("restauração integral aprovada: {}", output.display());
        }
        Cmd::Audit { .. } => {
            bail!("audit: não implementado nesta versão (Etapa 5). Veja docs/PLANO.md.");
        }
        Cmd::Report { .. } => {
            bail!("report: relatório genérico não implementado; veja scripts/compression_stage.py e docs/ETAPA-4.md.");
        }
    }
    Ok(())
}
