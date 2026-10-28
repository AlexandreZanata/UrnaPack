//! tsepack — biblioteca base v0.1.
//!
//! Escopo da base: proveniência (hash + manifesto), inspeção,
//! benchmark de baselines reais (ZSTD) e verificação independente.
//! Formatos especializados (Fase 3) ainda NÃO existem nesta base.

pub mod benchmark;
pub mod hash;
pub mod inspect;
pub mod manifest;
pub mod verify;

/// Versão do formato de manifesto/artefatos gerados por esta base.
/// Incrementar quando houver mudança incompatível no esquema.
pub const FORMAT_VERSION: u32 = 1;

/// Versão da ferramenta (espelha Cargo.toml).
pub const TOOL_VERSION: &str = env!("CARGO_PKG_VERSION");
