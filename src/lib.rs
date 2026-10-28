//! tsepack — biblioteca base v0.1.
//!
//! Escopo da base: proveniência (hash + manifesto), inspeção,
//! benchmark de baselines reais (ZSTD) e verificação independente.
//! Formatos especializados (Fase 3) ainda NÃO existem nesta base.

pub mod benchmark;
pub mod hash;
pub mod inspect;
pub mod manifest;
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
