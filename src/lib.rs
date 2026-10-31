//! tsepack — biblioteca de compressão e verificação.
//!
//! Escopo da base: proveniência (hash + manifesto), inspeção,
//! baselines em streaming, pacote BU web, arquivos FORENSIC, consultas de
//! controle e análise descritiva controlada de MT 2026 t1.
//! O pacote é experimental; outros parsers e a expansão nacional são futuros.

pub mod analyze;
pub mod archive;
pub mod benchmark;
pub mod bweb;
pub mod codec;
pub mod hash;
pub mod inspect;
pub mod manifest;
pub mod queries;
pub mod traverse;
pub mod verify;

/// Versão do formato de manifesto de origem gerado por esta base.
/// v2 = v1 com rejeição de campos desconhecidos (Etapa 2). Leitura aceita
/// v1 (congelado) e v2; escrita gera v2. Mudança incompatível exige
/// versionamento explícito.
pub const FORMAT_VERSION: u32 = 2;

/// Versões de manifesto de origem aceitas na leitura (migração v1→v2).
pub const SUPPORTED_FORMAT_VERSIONS: [u32; 2] = [1, 2];

/// Versão da ferramenta (espelha Cargo.toml).
pub const TOOL_VERSION: &str = env!("CARGO_PKG_VERSION");

pub mod limits;
pub(crate) mod output;

/// Relatórios não podem sobrescrever nem contaminar a entrada do benchmark.
pub fn output_path_conflicts(
    input: &std::path::Path,
    output: &std::path::Path,
) -> anyhow::Result<bool> {
    let source = std::fs::canonicalize(input)?;
    let target = output::resolved_target(output)?;
    Ok(target == source || (source.is_dir() && target.starts_with(source)))
}
