//! Análise descritiva BU web (Etapa 5A): contrato, controles e agregações.
//!
//! Entrada: CSV canônico do BU web ou diretório de view da Etapa 4. O perfil
//! fixa MT/2026/t1 e o snapshot aceito. Nenhuma ocorrência é deduplicada:
//! duplicatas, conflitos e divergências de contexto são contados, localizados
//! e bloqueiam os usos afetados.

use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fmt::Write as _;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::time::{Instant, SystemTime, UNIX_EPOCH};

pub const ANALYSIS_CONTRACT_VERSION: u32 = 1;
pub const ANALYSIS_CODE_VERSION: &str = "0.2.0-etapa5a-audited";
pub const PROFILE_ID: &str = "mt-2026-t1-bweb-v1";
pub const HEADER_FINGERPRINT_SHA256: &str =
    "c93ec8fe8f0ad3403b583e77ea166ac7c9db29246f79a0fdd27dfa30e48372c8";

const OCCURRENCE_FIELDS: [&str; 10] = [
    "ANO_ELEICAO",
    "CD_PLEITO",
    "CD_ELEICAO",
    "NR_TURNO",
    "SG_UF",
    "CD_MUNICIPIO",
    "NR_ZONA",
    "NR_SECAO",
    "CD_CARGO_PERGUNTA",
    "NR_VOTAVEL",
];
const CONTEXT_FIELDS: [&str; 9] = [
    "ANO_ELEICAO",
    "CD_PLEITO",
    "CD_ELEICAO",
    "NR_TURNO",
    "SG_UF",
    "CD_MUNICIPIO",
    "NR_ZONA",
    "NR_SECAO",
    "CD_CARGO_PERGUNTA",
];
const CONTEXT_EQUALITY_FIELDS: [&str; 20] = [
    "DT_BU_RECEBIDO",
    "QT_APTOS",
    "QT_COMPARECIMENTO",
    "QT_ABSTENCOES",
    "CD_TIPO_URNA",
    "DS_TIPO_URNA",
    "NR_LOCAL_VOTACAO",
    "NR_URNA_EFETIVADA",
    "CD_CARGA_1_URNA_EFETIVADA",
    "CD_CARGA_2_URNA_EFETIVADA",
    "CD_FLASHCARD_URNA_EFETIVADA",
    "DT_CARGA_URNA_EFETIVADA",
    "DS_CARGO_PERGUNTA_SECAO",
    "DS_SECOES_AGREGADAS",
    "DT_ABERTURA",
    "DT_ENCERRAMENTO",
    "QT_ELEI_BIOM_SEM_HABILITACAO",
    "DT_EMISSAO_BU",
    "NR_JUNTA_APURADORA",
    "NR_TURMA_APURADORA",
];
const CHECK_ORDER: [(&str, bool); 15] = [
    ("header", true),
    ("header_fingerprint", true),
    ("source_bytes", true),
    ("source_hash", true),
    ("records", true),
    ("scope", true),
    ("numeric_votes", true),
    ("numeric_context", true),
    ("arithmetic", true),
    ("occurrence_key", true),
    ("context_equality", true),
    ("election_cargo", true),
    ("category_description", true),
    ("lexical_fields", true),
    ("category_domain", false),
];

#[derive(Clone, Debug)]
pub struct AnalysisProfile {
    pub id: String,
    pub year: String,
    pub pleito: String,
    pub turno: String,
    pub uf: String,
    pub dt_geracao: String,
    pub hh_geracao: String,
    pub dt_pleito: String,
    pub expected_source_sha256: Option<String>,
    pub expected_records: Option<u64>,
    pub expected_zip_sha256: Option<String>,
    pub expected_member_name: Option<String>,
    pub expected_member_ordinal: Option<u64>,
}

pub fn profile_mt_2026_t1_bweb_v1() -> AnalysisProfile {
    AnalysisProfile {
        id: PROFILE_ID.into(),
        year: "2026".into(),
        pleito: "3220".into(),
        turno: "1".into(),
        uf: "MT".into(),
        dt_geracao: "05/10/2026".into(),
        hh_geracao: "14:03:43".into(),
        dt_pleito: "2026-10-04 00:00:00".into(),
        expected_source_sha256: Some(
            "5f9f344b44c9488157de9030ea474d15cc4da4135218e9d0d0c6364065a7bdd3".into(),
        ),
        expected_records: Some(891_997),
        expected_zip_sha256: Some(
            "610eda446fb6bab25f29ceea31adf8f91acf68db14a179228516d11c0fac226f".into(),
        ),
        expected_member_name: Some("bweb_1t_MT_051020261403.csv".into()),
        expected_member_ordinal: Some(0),
    }
}

/// Registro de perfis suportados. Novo snapshot exige novo perfil versionado;
/// perfil desconhecido nunca é inferido a partir dos dados.
pub fn profile_for_id(id: &str) -> Option<AnalysisProfile> {
    match id {
        PROFILE_ID => Some(profile_mt_2026_t1_bweb_v1()),
        _ => None,
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct Source {
    pub kind: String,
    pub view_sha256: Option<String>,
    pub csv_bytes: Option<u64>,
    pub expected_csv_bytes: Option<u64>,
    pub csv_sha256: Option<String>,
    pub expected_csv_sha256: Option<String>,
    pub records: u64,
    pub expected_records: Option<u64>,
    pub zip_path: Option<String>,
    pub zip_sha256: Option<String>,
    pub member_name: Option<String>,
    pub member_ordinal: Option<u64>,
    pub verification: String,
    pub snapshot: Option<Snapshot>,
}

#[derive(Clone, Debug, Serialize)]
pub struct Snapshot {
    pub dt_geracao: String,
    pub hh_geracao: String,
    pub ano_eleicao: String,
    pub cd_tipo_eleicao: String,
    pub nm_tipo_eleicao: String,
    pub cd_pleito: String,
    pub dt_pleito: String,
    pub nr_turno: String,
    pub sg_uf: String,
    pub cd_tipo_urna: String,
    pub ds_tipo_urna: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct Check {
    pub id: String,
    pub status: String,
    pub mandatory: bool,
    pub executed: bool,
    pub failures: u64,
    pub detail: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct Issue {
    pub check: String,
    pub record: Option<u64>,
    pub column: Option<String>,
    pub detail: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct NamedCount {
    pub code: String,
    pub name: String,
    pub count: u64,
}

#[derive(Clone, Debug, Serialize)]
pub struct DuplicateEvidence {
    pub record: u64,
    pub first_record: u64,
    pub key: Vec<String>,
    pub kind: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct ContextEvidence {
    pub group: Vec<String>,
    pub record: u64,
    pub first_record: u64,
    pub column: String,
    pub first_value: String,
    pub observed_value: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct UnexpectedValue {
    pub column: String,
    pub value: String,
    pub status: String,
    pub count: u64,
    pub first_record: u64,
}

#[derive(Clone, Debug, Serialize)]
pub struct CategoryInfo {
    pub code: String,
    pub description: String,
    pub status: String,
    pub votes: String,
    pub rows: u64,
}

#[derive(Clone, Debug, Serialize)]
pub struct KeyQuality {
    pub occurrence_fields: Vec<String>,
    pub context_fields: Vec<String>,
    pub records: u64,
    pub distinct_occurrences: u64,
    pub duplicate_keys: u64,
    pub repeated_occurrences: u64,
    pub conflicts: u64,
    pub evidence: Vec<DuplicateEvidence>,
}

#[derive(Clone, Debug, Serialize)]
pub struct ContextQuality {
    pub key_fields: Vec<String>,
    pub equality_fields: Vec<String>,
    pub groups: u64,
    pub divergent_groups: u64,
    pub divergence_rows: u64,
    pub evidence: Vec<ContextEvidence>,
    pub zero_denominator_groups: u64,
    pub arithmetic_checked: u64,
    pub arithmetic_failures: u64,
}

#[derive(Clone, Debug, Serialize)]
pub struct AggregatedSections {
    pub status: String,
    pub distinct_values: u64,
    pub context_groups_with_value: u64,
    pub context_groups_with_non_sentinel: u64,
    pub values: Vec<NamedCount>,
    pub values_overflow: u64,
    pub reason: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct Coverage {
    pub records: u64,
    pub fields: u64,
    pub header_fingerprint_sha256: String,
    pub elections: Vec<NamedCount>,
    pub offices: Vec<NamedCount>,
    pub municipalities: u64,
    pub municipality_name_conflicts: u64,
    pub zones: u64,
    pub context_groups: u64,
    pub context_groups_by_office: Vec<NamedCount>,
    pub categories: Vec<CategoryInfo>,
    pub parties: u64,
    pub notes: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct UseStatus {
    pub id: String,
    pub status: String,
    pub reason: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct QualityReport {
    pub artifact_kind: String,
    pub format_version: u32,
    pub analysis_contract_version: u32,
    pub profile: String,
    pub status: String,
    pub approved: bool,
    pub source: Source,
    pub scope: ScopeInfo,
    pub checks: Vec<Check>,
    pub errors: Vec<Issue>,
    pub error_count: u64,
    pub sentinels: BTreeMap<String, BTreeMap<String, u64>>,
    pub unexpected_values: Vec<UnexpectedValue>,
    pub unexpected_values_overflow: u64,
    pub keys: KeyQuality,
    pub context: ContextQuality,
    pub ds_secoes_agregadas: AggregatedSections,
    pub coverage: Coverage,
    pub uses: Vec<UseStatus>,
    pub limitations: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct ScopeInfo {
    pub year: String,
    pub pleito: String,
    pub turno: String,
    pub uf: String,
    pub elections: Vec<NamedCount>,
    pub offices: Vec<NamedCount>,
}

#[derive(Clone, Debug, Serialize)]
pub struct OfficeVotes {
    pub cargo: String,
    pub cargo_nome: String,
    pub votos: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct OfficeCategoryVotes {
    pub cargo: String,
    pub cargo_nome: String,
    pub categoria_codigo: String,
    pub categoria: String,
    pub categoria_status: String,
    pub votos: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct OfficeMunicipalityVotes {
    pub cargo: String,
    pub cargo_nome: String,
    pub municipio: String,
    pub municipio_nome: String,
    pub categoria_codigo: String,
    pub categoria: String,
    pub categoria_status: String,
    pub votos: String,
    pub total_cargo_municipio: String,
    pub fracao: Option<String>,
    pub fracao_motivo: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct VotesResults {
    pub status: String,
    pub blocked_reason: Option<String>,
    pub total: Option<String>,
    pub by_office: Vec<OfficeVotes>,
    pub by_office_category: Vec<OfficeCategoryVotes>,
    pub by_office_municipality: Vec<OfficeMunicipalityVotes>,
}

#[derive(Clone, Debug, Serialize)]
pub struct ContextRow {
    pub cargo: String,
    pub cargo_nome: String,
    pub municipio: Option<String>,
    pub municipio_nome: Option<String>,
    pub zona: Option<String>,
    pub grupos_contexto: u64,
    pub aptos: String,
    pub comparecimento: String,
    pub abstencoes: String,
    pub comparecimento_por_aptos: Option<String>,
    pub comparecimento_por_aptos_motivo: Option<String>,
    pub abstencao_por_aptos: Option<String>,
    pub abstencao_por_aptos_motivo: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct ContextResults {
    pub status: String,
    pub blocked_reason: Option<String>,
    pub by_office: Vec<ContextRow>,
    pub by_office_municipality: Vec<ContextRow>,
    pub by_office_zone: Vec<ContextRow>,
}

#[derive(Clone, Debug, Serialize)]
pub struct AnalysisResults {
    pub artifact_kind: String,
    pub format_version: u32,
    pub analysis_contract_version: u32,
    pub profile: String,
    pub source: Source,
    pub definitions: BTreeMap<String, String>,
    pub votes: VotesResults,
    pub context: ContextResults,
}

#[derive(Clone, Debug, Serialize)]
pub struct OutputFile {
    pub bytes: u64,
    pub sha256: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct RunReceipt {
    pub artifact_kind: String,
    pub format_version: u32,
    pub analysis_contract_version: u32,
    pub analysis_code_version: String,
    pub profile: String,
    pub tool_version: String,
    pub started_at_unix_seconds: u64,
    pub finished_at_unix_seconds: u64,
    pub duration_ms: u128,
    pub peak_rss_kib: Option<u64>,
    pub input: String,
    pub output: String,
    pub approved: bool,
    pub status: String,
    pub parameters: BTreeMap<String, String>,
    pub source: Source,
    pub outputs: BTreeMap<String, OutputFile>,
    pub variable_metadata: Vec<String>,
}

pub struct AnalysisOutcome {
    pub approved: bool,
    pub status: String,
    pub output: PathBuf,
    pub records: u64,
    pub votes_total: Option<String>,
    pub error_count: u64,
}

struct Cols {
    dt_geracao: usize,
    hh_geracao: usize,
    ano_eleicao: usize,
    cd_tipo_eleicao: usize,
    nm_tipo_eleicao: usize,
    cd_pleito: usize,
    dt_pleito: usize,
    nr_turno: usize,
    cd_eleicao: usize,
    ds_eleicao: usize,
    sg_uf: usize,
    cd_municipio: usize,
    nm_municipio: usize,
    nr_zona: usize,
    nr_secao: usize,
    nr_local_votacao: usize,
    cd_cargo: usize,
    ds_cargo: usize,
    nr_partido: usize,
    dt_bu_recebido: usize,
    qt_aptos: usize,
    qt_comparecimento: usize,
    qt_abstencoes: usize,
    cd_tipo_urna: usize,
    ds_tipo_urna: usize,
    cd_tipo_votavel: usize,
    ds_tipo_votavel: usize,
    nr_votavel: usize,
    qt_votos: usize,
    nr_urna: usize,
    cd_carga1: usize,
    cd_carga2: usize,
    cd_flashcard: usize,
    dt_carga: usize,
    ds_cargo_secao: usize,
    ds_secoes_agregadas: usize,
    dt_abertura: usize,
    dt_encerramento: usize,
    qt_biom: usize,
    dt_emissao: usize,
    nr_junta: usize,
    nr_turma: usize,
}

fn col(name: &str) -> usize {
    crate::bweb::BWEB_HEADER
        .iter()
        .position(|candidate| *candidate == name)
        .unwrap_or_else(|| panic!("coluna canônica ausente: {name}"))
}

impl Cols {
    fn new() -> Self {
        Self {
            dt_geracao: col("DT_GERACAO"),
            hh_geracao: col("HH_GERACAO"),
            ano_eleicao: col("ANO_ELEICAO"),
            cd_tipo_eleicao: col("CD_TIPO_ELEICAO"),
            nm_tipo_eleicao: col("NM_TIPO_ELEICAO"),
            cd_pleito: col("CD_PLEITO"),
            dt_pleito: col("DT_PLEITO"),
            nr_turno: col("NR_TURNO"),
            cd_eleicao: col("CD_ELEICAO"),
            ds_eleicao: col("DS_ELEICAO"),
            sg_uf: col("SG_UF"),
            cd_municipio: col("CD_MUNICIPIO"),
            nm_municipio: col("NM_MUNICIPIO"),
            nr_zona: col("NR_ZONA"),
            nr_secao: col("NR_SECAO"),
            nr_local_votacao: col("NR_LOCAL_VOTACAO"),
            cd_cargo: col("CD_CARGO_PERGUNTA"),
            ds_cargo: col("DS_CARGO_PERGUNTA"),
            nr_partido: col("NR_PARTIDO"),
            dt_bu_recebido: col("DT_BU_RECEBIDO"),
            qt_aptos: col("QT_APTOS"),
            qt_comparecimento: col("QT_COMPARECIMENTO"),
            qt_abstencoes: col("QT_ABSTENCOES"),
            cd_tipo_urna: col("CD_TIPO_URNA"),
            ds_tipo_urna: col("DS_TIPO_URNA"),
            cd_tipo_votavel: col("CD_TIPO_VOTAVEL"),
            ds_tipo_votavel: col("DS_TIPO_VOTAVEL"),
            nr_votavel: col("NR_VOTAVEL"),
            qt_votos: col("QT_VOTOS"),
            nr_urna: col("NR_URNA_EFETIVADA"),
            cd_carga1: col("CD_CARGA_1_URNA_EFETIVADA"),
            cd_carga2: col("CD_CARGA_2_URNA_EFETIVADA"),
            cd_flashcard: col("CD_FLASHCARD_URNA_EFETIVADA"),
            dt_carga: col("DT_CARGA_URNA_EFETIVADA"),
            ds_cargo_secao: col("DS_CARGO_PERGUNTA_SECAO"),
            ds_secoes_agregadas: col("DS_SECOES_AGREGADAS"),
            dt_abertura: col("DT_ABERTURA"),
            dt_encerramento: col("DT_ENCERRAMENTO"),
            qt_biom: col("QT_ELEI_BIOM_SEM_HABILITACAO"),
            dt_emissao: col("DT_EMISSAO_BU"),
            nr_junta: col("NR_JUNTA_APURADORA"),
            nr_turma: col("NR_TURMA_APURADORA"),
        }
    }

    fn occurrence(&self) -> [usize; 10] {
        [
            self.ano_eleicao,
            self.cd_pleito,
            self.cd_eleicao,
            self.nr_turno,
            self.sg_uf,
            self.cd_municipio,
            self.nr_zona,
            self.nr_secao,
            self.cd_cargo,
            self.nr_votavel,
        ]
    }

    fn context(&self) -> [usize; 9] {
        [
            self.ano_eleicao,
            self.cd_pleito,
            self.cd_eleicao,
            self.nr_turno,
            self.sg_uf,
            self.cd_municipio,
            self.nr_zona,
            self.nr_secao,
            self.cd_cargo,
        ]
    }

    fn equality(&self) -> [usize; 20] {
        [
            self.dt_bu_recebido,
            self.qt_aptos,
            self.qt_comparecimento,
            self.qt_abstencoes,
            self.cd_tipo_urna,
            self.ds_tipo_urna,
            self.nr_local_votacao,
            self.nr_urna,
            self.cd_carga1,
            self.cd_carga2,
            self.cd_flashcard,
            self.dt_carga,
            self.ds_cargo_secao,
            self.ds_secoes_agregadas,
            self.dt_abertura,
            self.dt_encerramento,
            self.qt_biom,
            self.dt_emissao,
            self.nr_junta,
            self.nr_turma,
        ]
    }
}

#[derive(Clone, Copy)]
enum LexicalKind {
    Digits,
    Signed,
    Dotted,
    Hex,
    DateBr,
    Time,
    DateTime,
    Year4,
}

struct LexicalRule {
    index: usize,
    name: &'static str,
    kind: LexicalKind,
}

fn lexical_rules(c: &Cols) -> Vec<LexicalRule> {
    let mut rules = Vec::new();
    for (index, name) in [
        (c.qt_aptos, "QT_APTOS"),
        (c.qt_comparecimento, "QT_COMPARECIMENTO"),
        (c.qt_abstencoes, "QT_ABSTENCOES"),
        (c.qt_votos, "QT_VOTOS"),
        (c.qt_biom, "QT_ELEI_BIOM_SEM_HABILITACAO"),
    ] {
        rules.push(LexicalRule {
            index,
            name,
            kind: LexicalKind::Digits,
        });
    }
    for (index, name) in [
        (c.nr_zona, "NR_ZONA"),
        (c.nr_secao, "NR_SECAO"),
        (c.nr_local_votacao, "NR_LOCAL_VOTACAO"),
        (c.nr_votavel, "NR_VOTAVEL"),
        (c.nr_urna, "NR_URNA_EFETIVADA"),
        (c.nr_junta, "NR_JUNTA_APURADORA"),
        (c.nr_turma, "NR_TURMA_APURADORA"),
        (c.cd_municipio, "CD_MUNICIPIO"),
        (c.nr_partido, "NR_PARTIDO"),
    ] {
        rules.push(LexicalRule {
            index,
            name,
            kind: LexicalKind::Signed,
        });
    }
    for (index, name) in [
        (c.cd_carga1, "CD_CARGA_1_URNA_EFETIVADA"),
        (c.cd_carga2, "CD_CARGA_2_URNA_EFETIVADA"),
    ] {
        rules.push(LexicalRule {
            index,
            name,
            kind: LexicalKind::Dotted,
        });
    }
    rules.push(LexicalRule {
        index: c.cd_flashcard,
        name: "CD_FLASHCARD_URNA_EFETIVADA",
        kind: LexicalKind::Hex,
    });
    rules.push(LexicalRule {
        index: c.ano_eleicao,
        name: "ANO_ELEICAO",
        kind: LexicalKind::Year4,
    });
    rules.push(LexicalRule {
        index: c.dt_geracao,
        name: "DT_GERACAO",
        kind: LexicalKind::DateBr,
    });
    rules.push(LexicalRule {
        index: c.hh_geracao,
        name: "HH_GERACAO",
        kind: LexicalKind::Time,
    });
    for (index, name) in [
        (c.dt_pleito, "DT_PLEITO"),
        (c.dt_bu_recebido, "DT_BU_RECEBIDO"),
        (c.dt_carga, "DT_CARGA_URNA_EFETIVADA"),
        (c.dt_abertura, "DT_ABERTURA"),
        (c.dt_encerramento, "DT_ENCERRAMENTO"),
        (c.dt_emissao, "DT_EMISSAO_BU"),
    ] {
        rules.push(LexicalRule {
            index,
            name,
            kind: LexicalKind::DateTime,
        });
    }
    rules
}

fn valid_lexical(kind: LexicalKind, value: &[u8]) -> bool {
    match kind {
        LexicalKind::Digits => is_digits(value),
        LexicalKind::Signed => is_signed(value),
        LexicalKind::Dotted => is_dotted(value),
        LexicalKind::Hex => is_hex(value),
        LexicalKind::DateBr => is_date_br(value),
        LexicalKind::Time => is_time(value),
        LexicalKind::DateTime => is_datetime(value),
        LexicalKind::Year4 => value.len() == 4 && is_digits(value),
    }
}

fn is_digits(value: &[u8]) -> bool {
    !value.is_empty() && value.iter().all(u8::is_ascii_digit)
}
fn is_signed(value: &[u8]) -> bool {
    let digits = value.strip_prefix(b"-").unwrap_or(value);
    is_digits(digits)
}
fn is_dotted(value: &[u8]) -> bool {
    // Compatível com o validador canônico (`^[\d.]+$`): sanity de alfabeto,
    // sem semântica de versão. Trailing dot observado em MT é aceito.
    !value.is_empty()
        && value
            .iter()
            .all(|byte| byte.is_ascii_digit() || *byte == b'.')
}
fn is_hex(value: &[u8]) -> bool {
    !value.is_empty() && value.iter().all(u8::is_ascii_hexdigit)
}
fn two_digits(value: &[u8]) -> Option<u32> {
    if value.len() == 2 && value.iter().all(u8::is_ascii_digit) {
        Some(u32::from(value[0] - b'0') * 10 + u32::from(value[1] - b'0'))
    } else {
        None
    }
}
fn four_digits(value: &[u8]) -> Option<u32> {
    if value.len() == 4 && value.iter().all(u8::is_ascii_digit) {
        Some(
            u32::from(value[0] - b'0') * 1000
                + u32::from(value[1] - b'0') * 100
                + u32::from(value[2] - b'0') * 10
                + u32::from(value[3] - b'0'),
        )
    } else {
        None
    }
}
fn is_date_br(value: &[u8]) -> bool {
    if value.len() != 10 || value[2] != b'/' || value[5] != b'/' {
        return false;
    }
    if !value
        .iter()
        .enumerate()
        .all(|(i, byte)| i == 2 || i == 5 || byte.is_ascii_digit())
    {
        return false;
    }
    let day = two_digits(&value[0..2]);
    let month = two_digits(&value[3..5]);
    let year = four_digits(&value[6..10]);
    match (day, month, year) {
        (Some(day), Some(month), Some(year)) => {
            (1..=31).contains(&day) && (1..=12).contains(&month) && (1900..=2100).contains(&year)
        }
        _ => false,
    }
}
fn is_time(value: &[u8]) -> bool {
    if value.len() != 8 || value[2] != b':' || value[5] != b':' {
        return false;
    }
    if !value
        .iter()
        .enumerate()
        .all(|(i, byte)| i == 2 || i == 5 || byte.is_ascii_digit())
    {
        return false;
    }
    match (
        two_digits(&value[0..2]),
        two_digits(&value[3..5]),
        two_digits(&value[6..8]),
    ) {
        (Some(hour), Some(minute), Some(second)) => hour <= 23 && minute <= 59 && second <= 59,
        _ => false,
    }
}
fn is_datetime(value: &[u8]) -> bool {
    if value.len() != 19
        || value[4] != b'-'
        || value[7] != b'-'
        || value[10] != b' '
        || value[13] != b':'
        || value[16] != b':'
        || !value
            .iter()
            .enumerate()
            .all(|(i, byte)| matches!(i, 4 | 7 | 10 | 13 | 16) || byte.is_ascii_digit())
    {
        return false;
    }
    let month = two_digits(&value[5..7]);
    let day = two_digits(&value[8..10]);
    let hour = two_digits(&value[11..13]);
    let minute = two_digits(&value[14..16]);
    let second = two_digits(&value[17..19]);
    let year = four_digits(&value[0..4]);
    match (year, month, day, hour, minute, second) {
        (Some(year), Some(month), Some(day), Some(hour), Some(minute), Some(second)) => {
            (1900..=2100).contains(&year)
                && (1..=12).contains(&month)
                && (1..=31).contains(&day)
                && hour <= 23
                && minute <= 59
                && second <= 59
        }
        _ => false,
    }
}

fn latin1(value: &[u8]) -> String {
    value.iter().map(|byte| char::from(*byte)).collect()
}

fn field(record: &csv::ByteRecord, index: usize) -> &[u8] {
    record.get(index).unwrap_or(b"")
}

fn push_component(buffer: &mut Vec<u8>, value: &[u8]) {
    buffer.extend_from_slice(&(value.len() as u32).to_le_bytes());
    buffer.extend_from_slice(value);
}

fn key_bytes(record: &csv::ByteRecord, columns: &[usize]) -> Vec<u8> {
    let mut key = Vec::with_capacity(128);
    for index in columns {
        push_component(&mut key, field(record, *index));
    }
    key
}

fn key_strings(record: &csv::ByteRecord, columns: &[usize]) -> Vec<String> {
    columns
        .iter()
        .map(|index| latin1(field(record, *index)))
        .collect()
}

fn record_digest(record: &csv::ByteRecord) -> [u8; 32] {
    let mut hash = Sha256::new();
    for value in record.iter() {
        hash.update((value.len() as u32).to_le_bytes());
        hash.update(value);
    }
    hash.finalize().into()
}

fn is_sentinel(value: &[u8]) -> bool {
    value.is_empty()
        || value == b"#NULO"
        || value == b"#NULO#"
        || value == b"#NE"
        || value == b"#NE#"
        || value == b"-1"
        || value == b"-3"
}

fn parse_u64(value: &[u8]) -> Option<u64> {
    if !is_digits(value) {
        return None;
    }
    let mut total = 0u64;
    for digit in value {
        total = total
            .checked_mul(10)?
            .checked_add(u64::from(digit - b'0'))?;
    }
    Some(total)
}

fn ratio(numerator: u64, denominator: u64) -> (Option<String>, Option<String>) {
    if denominator == 0 {
        return (None, Some("denominator_zero".into()));
    }
    let scaled =
        (u128::from(numerator) * 1_000_000 + u128::from(denominator) / 2) / u128::from(denominator);
    (
        Some(format!("{}.{:06}", scaled / 1_000_000, scaled % 1_000_000)),
        None,
    )
}

fn named_counts(values: &BTreeMap<String, (String, u64)>) -> Vec<NamedCount> {
    values
        .iter()
        .map(|(code, (name, count))| NamedCount {
            code: code.clone(),
            name: name.clone(),
            count: *count,
        })
        .collect()
}

fn add_map_value<K: Ord>(map: &mut BTreeMap<K, u64>, key: K, value: u64) -> bool {
    match map.get_mut(&key) {
        Some(total) => match total.checked_add(value) {
            Some(updated) => {
                *total = updated;
                true
            }
            None => false,
        },
        None => {
            map.insert(key, value);
            true
        }
    }
}

struct HashingReader<R> {
    inner: R,
    hash: Sha256,
    bytes: u64,
}
impl<R> HashingReader<R> {
    fn new(inner: R) -> Self {
        Self {
            inner,
            hash: Sha256::new(),
            bytes: 0,
        }
    }
    fn finish(self) -> (u64, String) {
        (self.bytes, hex::encode(self.hash.finalize()))
    }
}
impl<R: Read> Read for HashingReader<R> {
    fn read(&mut self, buffer: &mut [u8]) -> std::io::Result<usize> {
        let count = self.inner.read(buffer)?;
        self.hash.update(&buffer[..count]);
        self.bytes += count as u64;
        Ok(count)
    }
}

struct CheckState {
    executed: bool,
    failures: u64,
    detail: String,
}

struct OccEntry {
    first_record: u64,
    digest: [u8; 32],
}

struct ContextEntry {
    first_record: u64,
    office: String,
    municipality: String,
    zone: String,
    aptos: u64,
    comparecimento: u64,
    abstencoes: u64,
    fields: Vec<Vec<u8>>,
    divergent: bool,
}

struct ContextAgg {
    groups: u64,
    aptos: u64,
    comparecimento: u64,
    abstencoes: u64,
}

struct State {
    profile: AnalysisProfile,
    cols: Cols,
    rules: Vec<LexicalRule>,
    checks: BTreeMap<&'static str, CheckState>,
    errors: Vec<Issue>,
    error_count: u64,
    evidence_limit: usize,
    value_limit: usize,
    max_keys: u64,
    max_record_bytes: u64,
    max_csv_records: u64,
    max_field_bytes: u64,
    profile_mismatch: bool,
    source_kind: String,
    source_view_sha256: Option<String>,
    source_zip_path: Option<String>,
    source_zip_sha256: Option<String>,
    source_member_name: Option<String>,
    source_member_ordinal: Option<u64>,
    expected_bytes: Option<u64>,
    observed_bytes: Option<u64>,
    expected_sha256: Option<String>,
    observed_sha256: Option<String>,
    expected_records: Option<u64>,
    rows: u64,
    complete: bool,
    header_ok: bool,
    header_fingerprint: String,
    snapshot: Option<Snapshot>,
    votes_office: BTreeMap<String, u64>,
    votes_office_category: BTreeMap<(String, String, String), u64>,
    votes_office_municipality_category: BTreeMap<(String, String, String, String, String), u64>,
    votes_overflow: bool,
    occurrences: HashMap<Vec<u8>, OccEntry>,
    duplicate_keys: u64,
    repeated_occurrences: u64,
    conflicts: u64,
    duplicate_evidence: Vec<DuplicateEvidence>,
    contexts: HashMap<Vec<u8>, ContextEntry>,
    context_divergences: u64,
    context_divergence_rows: u64,
    context_evidence: Vec<ContextEvidence>,
    zero_denominator_groups: u64,
    arithmetic_checked: u64,
    arithmetic_failures: u64,
    sentinels: BTreeMap<String, BTreeMap<String, u64>>,
    unexpected: BTreeMap<(String, String), UnexpectedValue>,
    unexpected_overflow: u64,
    municipality_names: BTreeMap<String, String>,
    municipality_name_conflicts: u64,
    elections: BTreeMap<String, (String, u64)>,
    offices: BTreeMap<String, (String, u64)>,
    categories: BTreeMap<(String, String), u64>,
    parties: BTreeSet<String>,
}

impl State {
    fn new(
        profile: AnalysisProfile,
        source_kind: &str,
        expected_bytes: Option<u64>,
        expected_sha256: Option<String>,
        expected_records: Option<u64>,
    ) -> Result<Self> {
        let cols = Cols::new();
        let rules = lexical_rules(&cols);
        let mut checks = BTreeMap::new();
        for (id, _) in CHECK_ORDER {
            checks.insert(
                id,
                CheckState {
                    executed: false,
                    failures: 0,
                    detail: String::new(),
                },
            );
        }
        Ok(Self {
            profile,
            cols,
            rules,
            checks,
            errors: Vec::new(),
            error_count: 0,
            evidence_limit: crate::limits::get("MAX_ANALYZE_EVIDENCE")? as usize,
            value_limit: crate::limits::get("MAX_ANALYZE_DISTINCT_VALUES")? as usize,
            max_keys: crate::limits::get("MAX_BWEB_OCCURRENCE_KEYS")?,
            max_record_bytes: crate::limits::get("MAX_RECORD_BYTES")?,
            max_csv_records: crate::limits::get("MAX_CSV_RECORDS")?,
            max_field_bytes: crate::limits::get("MAX_FIELD_BYTES")?,
            profile_mismatch: false,
            source_kind: source_kind.into(),
            source_view_sha256: None,
            source_zip_path: None,
            source_zip_sha256: None,
            source_member_name: None,
            source_member_ordinal: None,
            expected_bytes,
            observed_bytes: None,
            expected_sha256,
            observed_sha256: None,
            expected_records,
            rows: 0,
            complete: false,
            header_ok: false,
            header_fingerprint: String::new(),
            snapshot: None,
            votes_office: BTreeMap::new(),
            votes_office_category: BTreeMap::new(),
            votes_office_municipality_category: BTreeMap::new(),
            votes_overflow: false,
            occurrences: HashMap::new(),
            duplicate_keys: 0,
            repeated_occurrences: 0,
            conflicts: 0,
            duplicate_evidence: Vec::new(),
            contexts: HashMap::new(),
            context_divergences: 0,
            context_divergence_rows: 0,
            context_evidence: Vec::new(),
            zero_denominator_groups: 0,
            arithmetic_checked: 0,
            arithmetic_failures: 0,
            sentinels: BTreeMap::new(),
            unexpected: BTreeMap::new(),
            unexpected_overflow: 0,
            municipality_names: BTreeMap::new(),
            municipality_name_conflicts: 0,
            elections: BTreeMap::new(),
            offices: BTreeMap::new(),
            categories: BTreeMap::new(),
            parties: BTreeSet::new(),
        })
    }

    fn check_mut(&mut self, id: &'static str) -> &mut CheckState {
        self.checks
            .get_mut(id)
            .unwrap_or_else(|| panic!("check desconhecido: {id}"))
    }

    fn fail(
        &mut self,
        check: &'static str,
        record: Option<u64>,
        column: Option<&str>,
        detail: impl Into<String>,
    ) {
        let detail = detail.into();
        self.error_count += 1;
        {
            let state = self.check_mut(check);
            state.failures += 1;
            if state.detail.is_empty() {
                state.detail = detail.clone();
            }
        }
        if self.errors.len() < self.evidence_limit {
            self.errors.push(Issue {
                check: check.into(),
                record,
                column: column.map(str::to_string),
                detail,
            });
        }
    }

    fn note_check(&mut self, check: &'static str, detail: impl Into<String>) {
        self.check_mut(check).detail = detail.into();
    }

    fn mark_executed(&mut self, check: &'static str) {
        self.check_mut(check).executed = true;
    }

    fn unexpected(&mut self, column: &str, value: &[u8], status: &str, record: u64) {
        let key = (column.to_string(), latin1(value));
        if let Some(entry) = self.unexpected.get_mut(&key) {
            entry.count += 1;
            return;
        }
        if self.unexpected.len() >= self.value_limit {
            self.unexpected_overflow += 1;
            return;
        }
        self.unexpected.insert(
            key,
            UnexpectedValue {
                column: column.into(),
                value: latin1(value),
                status: status.into(),
                count: 1,
                first_record: record,
            },
        );
    }

    fn accept_header(&mut self, record: &csv::ByteRecord) {
        self.mark_executed("header");
        let matches = record.len() == crate::bweb::BWEB_HEADER.len()
            && record
                .iter()
                .eq(crate::bweb::BWEB_HEADER.iter().map(|name| name.as_bytes()));
        if !matches {
            self.fail(
                "header",
                Some(0),
                None,
                format!("cabeçalho diverge do canônico: {} campos", record.len()),
            );
            return;
        }
        self.mark_executed("header_fingerprint");
        let header: Vec<String> = crate::bweb::BWEB_HEADER
            .iter()
            .map(|name| (*name).to_string())
            .collect();
        let fingerprint =
            crate::hash::sha256_bytes(&serde_json::to_vec(&header).unwrap_or_default());
        self.header_fingerprint = fingerprint.clone();
        if fingerprint != HEADER_FINGERPRINT_SHA256 {
            self.fail(
                "header_fingerprint",
                Some(0),
                None,
                format!("fingerprint do cabeçalho diverge: {fingerprint}"),
            );
            return;
        }
        self.header_ok = true;
    }

    fn accept(&mut self, record: &csv::ByteRecord) {
        self.rows += 1;
        let ordinal = self.rows;
        for check in [
            "scope",
            "numeric_votes",
            "numeric_context",
            "arithmetic",
            "occurrence_key",
            "context_equality",
            "election_cargo",
            "category_description",
            "lexical_fields",
            "category_domain",
        ] {
            self.mark_executed(check);
        }
        if self.rows > self.max_csv_records {
            self.fail(
                "records",
                Some(ordinal),
                None,
                format!("MAX_CSV_RECORDS excedido no registro {ordinal}"),
            );
            return;
        }
        for (index, value) in record.iter().enumerate() {
            if value.len() as u64 > self.max_field_bytes {
                let column = crate::bweb::BWEB_HEADER
                    .get(index)
                    .copied()
                    .unwrap_or("desconhecida");
                self.fail(
                    "lexical_fields",
                    Some(ordinal),
                    Some(column),
                    format!("MAX_FIELD_BYTES excedido no registro {ordinal}"),
                );
                self.unexpected(column, b"<campo excessivo>", "limit_exceeded", ordinal);
                return;
            }
        }

        for (index, value) in record.iter().enumerate() {
            if is_sentinel(value) {
                let column = crate::bweb::BWEB_HEADER[index].to_string();
                *self
                    .sentinels
                    .entry(column)
                    .or_default()
                    .entry(latin1(value))
                    .or_default() += 1;
            }
        }

        let rules: Vec<(usize, &'static str, LexicalKind)> = self
            .rules
            .iter()
            .map(|rule| (rule.index, rule.name, rule.kind))
            .collect();
        for (index, name, kind) in rules {
            let value = field(record, index);
            if !valid_lexical(kind, value) {
                self.fail(
                    "lexical_fields",
                    Some(ordinal),
                    Some(name),
                    format!("valor lexical inválido: {}", latin1(value)),
                );
                self.unexpected(name, value, "lexical_violation", ordinal);
            }
        }

        self.check_scope(record, ordinal);
        self.check_election_and_cargo(record, ordinal);
        self.check_category(record, ordinal);
        self.check_municipality_name(record, ordinal);
        self.check_context(record, ordinal);
        self.check_occurrence(record, ordinal);
        self.aggregate_votes(record, ordinal);
    }

    fn check_scope(&mut self, record: &csv::ByteRecord, ordinal: u64) {
        let current = Snapshot {
            dt_geracao: latin1(field(record, self.cols.dt_geracao)),
            hh_geracao: latin1(field(record, self.cols.hh_geracao)),
            ano_eleicao: latin1(field(record, self.cols.ano_eleicao)),
            cd_tipo_eleicao: latin1(field(record, self.cols.cd_tipo_eleicao)),
            nm_tipo_eleicao: latin1(field(record, self.cols.nm_tipo_eleicao)),
            cd_pleito: latin1(field(record, self.cols.cd_pleito)),
            dt_pleito: latin1(field(record, self.cols.dt_pleito)),
            nr_turno: latin1(field(record, self.cols.nr_turno)),
            sg_uf: latin1(field(record, self.cols.sg_uf)),
            cd_tipo_urna: latin1(field(record, self.cols.cd_tipo_urna)),
            ds_tipo_urna: latin1(field(record, self.cols.ds_tipo_urna)),
        };
        let checks = [
            (
                "DT_GERACAO",
                self.cols.dt_geracao,
                self.profile.dt_geracao.clone(),
            ),
            (
                "HH_GERACAO",
                self.cols.hh_geracao,
                self.profile.hh_geracao.clone(),
            ),
            (
                "ANO_ELEICAO",
                self.cols.ano_eleicao,
                self.profile.year.clone(),
            ),
            (
                "CD_PLEITO",
                self.cols.cd_pleito,
                self.profile.pleito.clone(),
            ),
            (
                "DT_PLEITO",
                self.cols.dt_pleito,
                self.profile.dt_pleito.clone(),
            ),
            ("NR_TURNO", self.cols.nr_turno, self.profile.turno.clone()),
            ("SG_UF", self.cols.sg_uf, self.profile.uf.clone()),
            (
                "CD_TIPO_ELEICAO",
                self.cols.cd_tipo_eleicao,
                "0".to_string(),
            ),
            (
                "NM_TIPO_ELEICAO",
                self.cols.nm_tipo_eleicao,
                "Eleição Ordinária".to_string(),
            ),
            ("CD_TIPO_URNA", self.cols.cd_tipo_urna, "1".to_string()),
            (
                "DS_TIPO_URNA",
                self.cols.ds_tipo_urna,
                "Apurada".to_string(),
            ),
        ];
        for (name, index, expected) in checks {
            let value = field(record, index);
            if latin1(value) != expected {
                self.fail(
                    "scope",
                    Some(ordinal),
                    Some(name),
                    format!("fora do escopo do perfil: {}", latin1(value)),
                );
                self.unexpected(name, value, "out_of_scope", ordinal);
            }
        }
        let same = self
            .snapshot
            .as_ref()
            .map(|first| {
                first.dt_geracao == current.dt_geracao
                    && first.hh_geracao == current.hh_geracao
                    && first.ano_eleicao == current.ano_eleicao
                    && first.cd_tipo_eleicao == current.cd_tipo_eleicao
                    && first.nm_tipo_eleicao == current.nm_tipo_eleicao
                    && first.cd_pleito == current.cd_pleito
                    && first.dt_pleito == current.dt_pleito
                    && first.nr_turno == current.nr_turno
                    && first.sg_uf == current.sg_uf
                    && first.cd_tipo_urna == current.cd_tipo_urna
                    && first.ds_tipo_urna == current.ds_tipo_urna
            })
            .unwrap_or(true);
        if self.snapshot.is_none() {
            self.snapshot = Some(current);
        } else if !same {
            self.fail(
                "scope",
                Some(ordinal),
                None,
                "snapshot/escopo diverge entre registros",
            );
        }
    }

    fn check_election_and_cargo(&mut self, record: &csv::ByteRecord, ordinal: u64) {
        let election = field(record, self.cols.cd_eleicao);
        let election_name = field(record, self.cols.ds_eleicao);
        let cargo = field(record, self.cols.cd_cargo);
        let cargo_name = field(record, self.cols.ds_cargo);
        let expected_election_name = match election {
            b"6257" => Some("Eleição Geral Federal 2026"),
            b"6259" => Some("Eleições Gerais Estaduais 2026"),
            _ => None,
        };
        match expected_election_name {
            Some(name) if latin1(election_name) == name => {}
            Some(_) => {
                self.fail(
                    "election_cargo",
                    Some(ordinal),
                    Some("DS_ELEICAO"),
                    format!("descrição incompatível com CD_ELEICAO={}", latin1(election)),
                );
                self.unexpected(
                    "DS_ELEICAO",
                    election_name,
                    "inconsistent_description",
                    ordinal,
                );
            }
            None => {
                self.fail(
                    "election_cargo",
                    Some(ordinal),
                    Some("CD_ELEICAO"),
                    format!("eleição fora do perfil: {}", latin1(election)),
                );
                self.unexpected("CD_ELEICAO", election, "out_of_scope", ordinal);
            }
        }
        if !matches!(cargo, b"1" | b"3" | b"5" | b"6" | b"7") {
            self.fail(
                "election_cargo",
                Some(ordinal),
                Some("CD_CARGO_PERGUNTA"),
                format!("cargo fora do perfil: {}", latin1(cargo)),
            );
            self.unexpected("CD_CARGO_PERGUNTA", cargo, "out_of_scope", ordinal);
        }
        let expected_cargo_name = match cargo {
            b"1" => Some("Presidente"),
            b"3" => Some("Governador"),
            b"5" => Some("Senador"),
            b"6" => Some("Deputado Federal"),
            b"7" => Some("Deputado Estadual"),
            _ => None,
        };
        if let Some(name) = expected_cargo_name {
            if latin1(cargo_name) != name {
                self.fail(
                    "election_cargo",
                    Some(ordinal),
                    Some("DS_CARGO_PERGUNTA"),
                    format!("descrição incompatível com cargo {}", latin1(cargo)),
                );
                self.unexpected(
                    "DS_CARGO_PERGUNTA",
                    cargo_name,
                    "inconsistent_description",
                    ordinal,
                );
            }
        }
        if !((election == b"6257" && cargo == b"1") || (election == b"6259" && cargo != b"1")) {
            self.fail(
                "election_cargo",
                Some(ordinal),
                None,
                "eleição/cargo incompatíveis",
            );
        }
        let entry = self
            .offices
            .entry(latin1(cargo))
            .or_insert_with(|| (latin1(cargo_name), 0));
        entry.1 += 1;
        let entry = self
            .elections
            .entry(latin1(election))
            .or_insert_with(|| (latin1(election_name), 0));
        entry.1 += 1;
    }

    fn check_category(&mut self, record: &csv::ByteRecord, ordinal: u64) {
        let code = field(record, self.cols.cd_tipo_votavel);
        let description = field(record, self.cols.ds_tipo_votavel);
        let expected = match code {
            b"1" => Some("Nominal"),
            b"2" => Some("Branco"),
            b"3" => Some("Nulo"),
            b"4" => Some("Legenda"),
            _ => None,
        };
        match expected {
            Some(name) => {
                if latin1(description) != name {
                    self.fail(
                        "category_description",
                        Some(ordinal),
                        Some("DS_TIPO_VOTAVEL"),
                        format!("descrição incompatível com categoria {}", latin1(code)),
                    );
                    self.unexpected(
                        "DS_TIPO_VOTAVEL",
                        description,
                        "inconsistent_description",
                        ordinal,
                    );
                }
            }
            None => {
                self.fail(
                    "category_domain",
                    Some(ordinal),
                    Some("CD_TIPO_VOTAVEL"),
                    format!("categoria não confirmada: {}", latin1(code)),
                );
                self.unexpected("CD_TIPO_VOTAVEL", code, "unknown_category", ordinal);
            }
        }
        *self
            .categories
            .entry((latin1(code), latin1(description)))
            .or_default() += 1;
    }

    fn check_municipality_name(&mut self, record: &csv::ByteRecord, ordinal: u64) {
        let code = latin1(field(record, self.cols.cd_municipio));
        let name = latin1(field(record, self.cols.nm_municipio));
        let conflict = self
            .municipality_names
            .get(&code)
            .is_some_and(|first| first != &name);
        if conflict {
            self.municipality_name_conflicts += 1;
            self.unexpected(
                "NM_MUNICIPIO",
                name.as_bytes(),
                "municipality_name_conflict",
                ordinal,
            );
        } else {
            self.municipality_names.entry(code).or_insert(name);
        }
    }

    fn check_context(&mut self, record: &csv::ByteRecord, ordinal: u64) {
        let key_columns = self.cols.context();
        let key = key_bytes(record, &key_columns);
        let aptos = match parse_u64(field(record, self.cols.qt_aptos)) {
            Some(value) => value,
            None => {
                self.fail(
                    "numeric_context",
                    Some(ordinal),
                    Some("QT_APTOS"),
                    "QT_APTOS não numérico",
                );
                return;
            }
        };
        let comparecimento = match parse_u64(field(record, self.cols.qt_comparecimento)) {
            Some(value) => value,
            None => {
                self.fail(
                    "numeric_context",
                    Some(ordinal),
                    Some("QT_COMPARECIMENTO"),
                    "QT_COMPARECIMENTO não numérico",
                );
                return;
            }
        };
        let abstencoes = match parse_u64(field(record, self.cols.qt_abstencoes)) {
            Some(value) => value,
            None => {
                self.fail(
                    "numeric_context",
                    Some(ordinal),
                    Some("QT_ABSTENCOES"),
                    "QT_ABSTENCOES não numérico",
                );
                return;
            }
        };
        self.arithmetic_checked += 1;
        match comparecimento.checked_add(abstencoes) {
            Some(total) if total == aptos => {}
            Some(total) => {
                self.arithmetic_failures += 1;
                self.fail(
                    "arithmetic",
                    Some(ordinal),
                    None,
                    format!("aptos={aptos} comp={comparecimento} abst={abstencoes} (soma={total})"),
                );
            }
            None => {
                self.arithmetic_failures += 1;
                self.fail(
                    "arithmetic",
                    Some(ordinal),
                    None,
                    "overflow em comparecimento + abstenções",
                );
            }
        }
        let equality_columns = self.cols.equality();
        let values: Vec<Vec<u8>> = equality_columns
            .iter()
            .map(|index| field(record, *index).to_vec())
            .collect();
        if self.contexts.contains_key(&key) {
            let mut divergence = None;
            {
                let entry = self.contexts.get_mut(&key).expect("contexto existente");
                if !entry.divergent {
                    for (position, value) in values.iter().enumerate() {
                        if entry.fields[position] != *value {
                            entry.divergent = true;
                            self.context_divergences += 1;
                            self.context_divergence_rows += 1;
                            divergence = Some((
                                CONTEXT_EQUALITY_FIELDS[position],
                                entry.first_record,
                                entry.fields[position].clone(),
                                value.clone(),
                            ));
                            break;
                        }
                    }
                }
            }
            if let Some((column, first_record, first_value, observed_value)) = divergence {
                self.fail(
                    "context_equality",
                    Some(ordinal),
                    Some(column),
                    format!("contexto diverge na seção/cargo; primeiro registro {first_record}"),
                );
                if self.context_evidence.len() < self.evidence_limit {
                    self.context_evidence.push(ContextEvidence {
                        group: key_strings(record, &key_columns),
                        record: ordinal,
                        first_record,
                        column: column.into(),
                        first_value: latin1(&first_value),
                        observed_value: latin1(&observed_value),
                    });
                }
            }
            return;
        }
        if aptos == 0 {
            self.zero_denominator_groups += 1;
        }
        let entry = ContextEntry {
            first_record: ordinal,
            office: latin1(field(record, self.cols.cd_cargo)),
            municipality: latin1(field(record, self.cols.cd_municipio)),
            zone: latin1(field(record, self.cols.nr_zona)),
            aptos,
            comparecimento,
            abstencoes,
            fields: values,
            divergent: false,
        };
        self.contexts.insert(key, entry);
        if self.contexts.len() as u64 > self.max_keys {
            self.fail(
                "context_equality",
                Some(ordinal),
                None,
                "limite de grupos de contexto excedido",
            );
        }
    }

    fn check_occurrence(&mut self, record: &csv::ByteRecord, ordinal: u64) {
        let key_columns = self.cols.occurrence();
        let key = key_bytes(record, &key_columns);
        let digest = record_digest(record);
        if let Some(entry) = self.occurrences.get(&key) {
            let first_record = entry.first_record;
            let same = entry.digest == digest;
            self.duplicate_keys += 1;
            let kind = if same {
                self.repeated_occurrences += 1;
                "repeated_occurrence"
            } else {
                self.conflicts += 1;
                "conflict"
            };
            if self.duplicate_evidence.len() < self.evidence_limit {
                self.duplicate_evidence.push(DuplicateEvidence {
                    record: ordinal,
                    first_record,
                    key: key_strings(record, &key_columns),
                    kind: kind.into(),
                });
            }
            self.fail(
                "occurrence_key",
                Some(ordinal),
                None,
                format!("chave de ocorrência repetida ({kind})"),
            );
            return;
        }
        self.occurrences.insert(
            key,
            OccEntry {
                first_record: ordinal,
                digest,
            },
        );
        if self.occurrences.len() as u64 > self.max_keys {
            self.fail(
                "occurrence_key",
                Some(ordinal),
                None,
                "limite de chaves de ocorrência excedido",
            );
        }
    }

    fn aggregate_votes(&mut self, record: &csv::ByteRecord, ordinal: u64) {
        let votes = match parse_u64(field(record, self.cols.qt_votos)) {
            Some(value) => value,
            None => {
                self.fail(
                    "numeric_votes",
                    Some(ordinal),
                    Some("QT_VOTOS"),
                    "QT_VOTOS não numérico",
                );
                return;
            }
        };
        let cargo = latin1(field(record, self.cols.cd_cargo));
        let municipality = latin1(field(record, self.cols.cd_municipio));
        let municipality_name = self
            .municipality_names
            .get(&municipality)
            .cloned()
            .unwrap_or_default();
        let category_code = latin1(field(record, self.cols.cd_tipo_votavel));
        let category_name = latin1(field(record, self.cols.ds_tipo_votavel));
        let party = latin1(field(record, self.cols.nr_partido));
        if !is_sentinel(party.as_bytes()) {
            self.parties.insert(party);
        }
        let mut overflow = None;
        if !add_map_value(&mut self.votes_office, cargo.clone(), votes) {
            overflow = Some("cargo");
        }
        if !add_map_value(
            &mut self.votes_office_category,
            (cargo.clone(), category_code.clone(), category_name.clone()),
            votes,
        ) {
            overflow = Some("categoria");
        }
        if !add_map_value(
            &mut self.votes_office_municipality_category,
            (
                cargo,
                municipality,
                municipality_name,
                category_code,
                category_name,
            ),
            votes,
        ) {
            overflow = Some("município");
        }
        if let Some(scope) = overflow {
            self.votes_overflow = true;
            self.fail(
                "numeric_votes",
                Some(ordinal),
                Some("QT_VOTOS"),
                format!("overflow na soma de votos ({scope})"),
            );
        }
    }

    fn finish_source(&mut self, bytes: Option<u64>, sha256: Option<String>, complete: bool) {
        self.complete = complete;
        if complete {
            self.observed_bytes = bytes;
            self.observed_sha256 = sha256;
            self.mark_executed("source_bytes");
            self.mark_executed("source_hash");
            self.mark_executed("records");
            match (&self.expected_sha256, &self.observed_sha256) {
                (Some(expected), Some(observed)) if expected == observed => {}
                (Some(expected), Some(observed)) => {
                    self.fail(
                        "source_hash",
                        None,
                        None,
                        format!("SHA-256 diverge: esperado {expected}, observado {observed}"),
                    );
                }
                (None, _) => {
                    self.note_check("source_hash", "hash não fixado pelo perfil");
                }
                (Some(_), None) => {
                    self.fail("source_hash", None, None, "SHA-256 não calculado");
                }
            }
            match (self.expected_bytes, self.observed_bytes) {
                (Some(expected), Some(observed)) if expected == observed => {}
                (Some(expected), Some(observed)) => {
                    self.fail(
                        "source_bytes",
                        None,
                        None,
                        format!("tamanho diverge: esperado {expected}, observado {observed}"),
                    );
                }
                (None, _) => {}
                (Some(_), None) => {
                    self.fail("source_bytes", None, None, "tamanho não observado");
                }
            }
            if let Some(expected) = self.expected_records {
                if expected != self.rows {
                    self.fail(
                        "records",
                        None,
                        None,
                        format!(
                            "contagem diverge: esperado {expected}, observado {}",
                            self.rows
                        ),
                    );
                }
            }
        } else if self.rows > 0 {
            self.note_check("source_hash", "leitura não chegou ao EOF");
            self.note_check("records", "contagem parcial; leitura não chegou ao EOF");
        }
    }

    fn finish(mut self) -> Result<Evaluation> {
        if !self.complete {
            self.note_check("source_hash", "leitura não concluída");
            self.note_check("records", "contagem parcial; leitura não concluída");
        }
        let votes_gate = self.votes_gate();
        let context_gate = self.context_gate();
        let category_gate = self.category_gate();
        let ds_info = self.aggregated_sections_info();
        let coverage = self.coverage(&ds_info);
        let source = self.build_source();
        let checks = self.build_checks();
        let approved = checks
            .iter()
            .filter(|check| check.mandatory)
            .all(|check| check.status == "pass");
        let status = if approved { "approved" } else { "failed" };
        let uses = self.build_uses(&votes_gate, &context_gate, &category_gate, &ds_info);
        let keys = KeyQuality {
            occurrence_fields: OCCURRENCE_FIELDS.iter().map(|s| (*s).to_string()).collect(),
            context_fields: CONTEXT_FIELDS.iter().map(|s| (*s).to_string()).collect(),
            records: self.rows,
            distinct_occurrences: self.occurrences.len() as u64,
            duplicate_keys: self.duplicate_keys,
            repeated_occurrences: self.repeated_occurrences,
            conflicts: self.conflicts,
            evidence: self.duplicate_evidence.clone(),
        };
        let context_quality = ContextQuality {
            key_fields: CONTEXT_FIELDS.iter().map(|s| (*s).to_string()).collect(),
            equality_fields: CONTEXT_EQUALITY_FIELDS
                .iter()
                .map(|s| (*s).to_string())
                .collect(),
            groups: self.contexts.len() as u64,
            divergent_groups: self.context_divergences,
            divergence_rows: self.context_divergence_rows,
            evidence: self.context_evidence.clone(),
            zero_denominator_groups: self.zero_denominator_groups,
            arithmetic_checked: self.arithmetic_checked,
            arithmetic_failures: self.arithmetic_failures,
        };
        let mut unexpected_values: Vec<UnexpectedValue> =
            self.unexpected.values().cloned().collect();
        unexpected_values
            .sort_by(|left, right| (&left.column, &left.value).cmp(&(&right.column, &right.value)));
        let quality = QualityReport {
            artifact_kind: "bweb_descriptive_quality".into(),
            format_version: 1,
            analysis_contract_version: ANALYSIS_CONTRACT_VERSION,
            profile: self.profile.id.clone(),
            status: status.into(),
            approved,
            source: source.clone(),
            scope: ScopeInfo {
                year: self.profile.year.clone(),
                pleito: self.profile.pleito.clone(),
                turno: self.profile.turno.clone(),
                uf: self.profile.uf.clone(),
                elections: named_counts(&self.elections),
                offices: named_counts(&self.offices),
            },
            checks,
            errors: self.errors.clone(),
            error_count: self.error_count,
            sentinels: self.sentinels.clone(),
            unexpected_values,
            unexpected_values_overflow: self.unexpected_overflow,
            keys,
            context: context_quality,
            ds_secoes_agregadas: ds_info.clone(),
            coverage,
            uses,
            limitations: limitations(),
        };
        let (results, votes_total) = self.build_results(&source, &votes_gate, &context_gate)?;
        Ok(Evaluation {
            approved,
            status: status.into(),
            quality,
            results,
            records: self.rows,
            votes_total,
            error_count: self.error_count,
            source,
        })
    }

    fn context_gate(&self) -> (String, Option<String>) {
        for id in [
            "header",
            "header_fingerprint",
            "source_bytes",
            "source_hash",
            "records",
            "scope",
            "numeric_votes",
            "numeric_context",
            "arithmetic",
            "occurrence_key",
            "context_equality",
            "election_cargo",
            "lexical_fields",
        ] {
            let check = &self.checks[id];
            if !check.executed || check.failures > 0 {
                return (
                    "blocked".into(),
                    Some(format!("controle obrigatório não aprovado: {id}")),
                );
            }
        }
        ("approved".into(), None)
    }

    fn votes_gate(&self) -> (String, Option<String>) {
        if self.votes_overflow {
            return ("blocked".into(), Some("overflow na soma de votos".into()));
        }
        for id in [
            "header",
            "header_fingerprint",
            "source_bytes",
            "source_hash",
            "records",
            "scope",
            "numeric_votes",
            "occurrence_key",
            "election_cargo",
            "lexical_fields",
        ] {
            let check = &self.checks[id];
            if !check.executed || check.failures > 0 {
                return (
                    "blocked".into(),
                    Some(format!("controle obrigatório não aprovado: {id}")),
                );
            }
        }
        ("approved".into(), None)
    }

    fn category_gate(&self) -> (String, Option<String>) {
        let votes = self.votes_gate();
        if votes.0 != "approved" {
            return ("blocked".into(), votes.1);
        }
        if self.checks["category_description"].failures > 0 {
            return (
                "blocked".into(),
                Some("código/descrição de categoria inconsistente".into()),
            );
        }
        if self.checks["category_domain"].failures > 0 {
            return (
                "blocked".into(),
                Some("categoria sem interpretação confirmada".into()),
            );
        }
        ("approved".into(), None)
    }

    fn aggregated_sections_info(&self) -> AggregatedSections {
        let mut values: BTreeMap<String, u64> = BTreeMap::new();
        let mut non_sentinel = 0u64;
        let mut with_value = 0u64;
        let position = CONTEXT_EQUALITY_FIELDS
            .iter()
            .position(|field| *field == "DS_SECOES_AGREGADAS")
            .unwrap_or(0);
        for entry in self.contexts.values() {
            let value = entry.fields.get(position).cloned().unwrap_or_default();
            let text = latin1(&value);
            *values.entry(text).or_default() += 1;
            with_value += 1;
            if !is_sentinel(&value) {
                non_sentinel += 1;
            }
        }
        let status = if non_sentinel > 0 {
            "blocked"
        } else {
            "approved"
        };
        let distinct = values.len() as u64;
        let limit = self.value_limit as u64;
        let overflow = distinct.saturating_sub(limit.min(distinct));
        let kept: Vec<NamedCount> = values
            .into_iter()
            .take(self.value_limit)
            .map(|(value, count)| NamedCount {
                code: value.clone(),
                name: value,
                count,
            })
            .collect();
        let mut reason = if non_sentinel > 0 {
            "DS_SECOES_AGREGADAS contém valores não sentinela; a interpretação da lista e a contagem de seções físicas não foram validadas nesta etapa."
                .to_string()
        } else {
            "Somente sentinelas observados em DS_SECOES_AGREGADAS; a contagem de grupos de contexto coincide com a contagem de seções do arquivo."
                .to_string()
        };
        if overflow > 0 {
            reason.push_str(&format!(
                " {overflow} valores distintos omitidos pelo teto MAX_ANALYZE_DISTINCT_VALUES; contagens totais preservadas."
            ));
        }
        AggregatedSections {
            status: status.into(),
            distinct_values: distinct,
            context_groups_with_value: with_value,
            context_groups_with_non_sentinel: non_sentinel,
            values: kept,
            values_overflow: overflow,
            reason,
        }
    }

    fn coverage(&self, ds_info: &AggregatedSections) -> Coverage {
        let mut zones = BTreeSet::new();
        let mut municipalities = BTreeSet::new();
        let mut context_by_office: BTreeMap<String, u64> = BTreeMap::new();
        for entry in self.contexts.values() {
            zones.insert((entry.municipality.clone(), entry.zone.clone()));
            municipalities.insert(entry.municipality.clone());
            *context_by_office.entry(entry.office.clone()).or_default() += 1;
        }
        let categories: BTreeMap<(String, String), u64> = self.categories.clone();
        let mut category_infos = Vec::new();
        for ((code, description), rows) in categories {
            let expected = category_label(&code);
            let status = match expected {
                Some(name) if description == name => "confirmed",
                Some(_) => "inconsistent",
                None => "unconfirmed",
            };
            let votes = self
                .votes_office_category
                .iter()
                .filter(|((_, category_code, category_description), _)| {
                    category_code == &code && category_description == &description
                })
                .try_fold(0u64, |total, (_, value)| total.checked_add(*value))
                .unwrap_or_default();
            category_infos.push(CategoryInfo {
                code,
                description,
                status: status.into(),
                votes: votes.to_string(),
                rows,
            });
        }
        category_infos.sort_by(|left, right| {
            (&left.code, &left.description).cmp(&(&right.code, &right.description))
        });
        let mut notes = vec![
            format!(
                "Cobertura observada no arquivo; {} grupos de contexto e {} grupos com DS_SECOES_AGREGADAS não sentinela. Não é declaração de completude do universo eleitoral.",
                ds_info.context_groups_with_value,
                ds_info.context_groups_with_non_sentinel
            ),
            "Código municipal TSE não foi convertido para código IBGE.".into(),
        ];
        if self.municipality_name_conflicts > 0 {
            notes.push(format!(
                "{} registros com mesmo CD_MUNICIPIO e NM_MUNICIPIO divergente; primeiro nome preservado, cobertura territorial bloqueada.",
                self.municipality_name_conflicts
            ));
        }
        Coverage {
            records: self.rows,
            fields: crate::bweb::BWEB_HEADER.len() as u64,
            header_fingerprint_sha256: self.header_fingerprint.clone(),
            elections: named_counts(&self.elections),
            offices: named_counts(&self.offices),
            municipalities: municipalities.len() as u64,
            municipality_name_conflicts: self.municipality_name_conflicts,
            zones: zones.len() as u64,
            context_groups: self.contexts.len() as u64,
            context_groups_by_office: context_by_office
                .into_iter()
                .map(|(office, count)| NamedCount {
                    code: office.clone(),
                    name: self
                        .offices
                        .get(&office)
                        .map(|entry| entry.0.clone())
                        .unwrap_or_default(),
                    count,
                })
                .collect(),
            categories: category_infos,
            parties: self.parties.len() as u64,
            notes,
        }
    }

    fn build_source(&self) -> Source {
        let verification = if self.profile_mismatch {
            "mismatch"
        } else if !self.complete {
            "not_completed"
        } else if self
            .checks
            .iter()
            .filter(|(id, _)| matches!(**id, "source_bytes" | "source_hash" | "records"))
            .all(|(_, check)| check.failures == 0)
        {
            "verified"
        } else {
            "mismatch"
        };
        Source {
            kind: self.source_kind.clone(),
            view_sha256: self.source_view_sha256.clone(),
            csv_bytes: self.observed_bytes,
            expected_csv_bytes: self.expected_bytes,
            csv_sha256: self.observed_sha256.clone(),
            expected_csv_sha256: self.expected_sha256.clone(),
            records: self.rows,
            expected_records: self.expected_records,
            zip_path: self.source_zip_path.clone(),
            zip_sha256: self.source_zip_sha256.clone(),
            member_name: self.source_member_name.clone(),
            member_ordinal: self.source_member_ordinal,
            verification: verification.into(),
            snapshot: self.snapshot.clone(),
        }
    }

    fn build_checks(&self) -> Vec<Check> {
        CHECK_ORDER
            .iter()
            .map(|(id, mandatory)| {
                let state = &self.checks[id];
                let status = if state.failures > 0 {
                    if *mandatory {
                        "fail"
                    } else {
                        "blocked"
                    }
                } else if !state.executed {
                    "not_executed"
                } else {
                    "pass"
                };
                Check {
                    id: (*id).into(),
                    status: status.into(),
                    mandatory: *mandatory,
                    executed: state.executed,
                    failures: state.failures,
                    detail: state.detail.clone(),
                }
            })
            .collect()
    }

    fn build_uses(
        &self,
        votes: &(String, Option<String>),
        context: &(String, Option<String>),
        category: &(String, Option<String>),
        ds: &AggregatedSections,
    ) -> Vec<UseStatus> {
        let mut uses = Vec::new();
        for id in ["votes_by_office", "votes_by_office_municipality"] {
            uses.push(UseStatus {
                id: id.into(),
                status: votes.0.clone(),
                reason: votes.1.clone().unwrap_or_default(),
            });
        }
        for id in ["votes_by_category", "category_shares"] {
            uses.push(UseStatus {
                id: id.into(),
                status: category.0.clone(),
                reason: category.1.clone().unwrap_or_default(),
            });
        }
        for id in [
            "context_aptos_comparecimento_abstentions",
            "comparecimento_abstention_rates",
        ] {
            uses.push(UseStatus {
                id: id.into(),
                status: context.0.clone(),
                reason: context.1.clone().unwrap_or_default(),
            });
        }
        let (physical_status, physical_reason) = if context.0 != "approved" {
            ("blocked".to_string(), context.1.clone().unwrap_or_default())
        } else {
            (ds.status.clone(), ds.reason.clone())
        };
        uses.push(UseStatus {
            id: "physical_section_count".into(),
            status: physical_status,
            reason: physical_reason,
        });
        let (territorial_status, territorial_reason) = if context.0 != "approved" {
            ("blocked".to_string(), context.1.clone().unwrap_or_default())
        } else if self.municipality_name_conflicts > 0 {
            (
                "blocked".to_string(),
                format!(
                    "{} conflitos de NM_MUNICIPIO para o mesmo CD_MUNICIPIO; primeiro nome preservado.",
                    self.municipality_name_conflicts
                ),
            )
        } else {
            (
                "approved".to_string(),
                "Contagem observada no arquivo; não representa completude do universo.".to_string(),
            )
        };
        uses.push(UseStatus {
            id: "territorial_coverage_observed".into(),
            status: territorial_status,
            reason: territorial_reason,
        });
        uses.push(UseStatus {
            id: "cross_office_electorate_total".into(),
            status: "blocked".into(),
            reason: "Contextos de cargos diferentes não são somados; falta população de referência validada.".into(),
        });
        for (id, reason) in [
            (
                "universe_completeness",
                "Sem referência de universo validada nesta etapa.",
            ),
            (
                "turn_comparison",
                "Acervo do segundo turno é parcial; comparação não executada.",
            ),
            (
                "reconciliation_bu_votacao_rdv",
                "Reconciliação entre fontes não executada nesta etapa.",
            ),
            (
                "statistical_models_anomalies",
                "Modelos e detecção de anomalias não executados nesta etapa.",
            ),
            (
                "web_interface",
                "Interface web/painel não executada nesta etapa.",
            ),
        ] {
            uses.push(UseStatus {
                id: id.into(),
                status: "not_executed".into(),
                reason: reason.into(),
            });
        }
        uses
    }

    fn build_results(
        &self,
        source: &Source,
        votes_gate: &(String, Option<String>),
        context_gate: &(String, Option<String>),
    ) -> Result<(AnalysisResults, Option<String>)> {
        let votes_approved = votes_gate.0 == "approved";
        let mut votes_total = None;
        let mut by_office = Vec::new();
        let mut by_office_category = Vec::new();
        let mut by_office_municipality = Vec::new();
        if votes_approved {
            let total = self
                .votes_office
                .values()
                .try_fold(0u64, |total, value| total.checked_add(*value))
                .context("overflow no total de votos")?;
            votes_total = Some(total.to_string());
            for (cargo, votes) in &self.votes_office {
                by_office.push(OfficeVotes {
                    cargo: cargo.clone(),
                    cargo_nome: self.office_name(cargo),
                    votos: votes.to_string(),
                });
            }
            for ((cargo, code, description), votes) in &self.votes_office_category {
                by_office_category.push(OfficeCategoryVotes {
                    cargo: cargo.clone(),
                    cargo_nome: self.office_name(cargo),
                    categoria_codigo: code.clone(),
                    categoria: description.clone(),
                    categoria_status: category_status(code, description).into(),
                    votos: votes.to_string(),
                });
            }
            let mut municipality_totals: BTreeMap<(String, String), u64> = BTreeMap::new();
            for ((cargo, municipality, _, _, _), votes) in &self.votes_office_municipality_category
            {
                let entry = municipality_totals
                    .entry((cargo.clone(), municipality.clone()))
                    .or_default();
                *entry = entry
                    .checked_add(*votes)
                    .context("overflow no total de votos por município")?;
            }
            for ((cargo, municipality, municipality_name, code, description), votes) in
                &self.votes_office_municipality_category
            {
                let total = municipality_totals
                    .get(&(cargo.clone(), municipality.clone()))
                    .copied()
                    .unwrap_or_default();
                let (fraction, fraction_reason) = ratio(*votes, total);
                by_office_municipality.push(OfficeMunicipalityVotes {
                    cargo: cargo.clone(),
                    cargo_nome: self.office_name(cargo),
                    municipio: municipality.clone(),
                    municipio_nome: municipality_name.clone(),
                    categoria_codigo: code.clone(),
                    categoria: description.clone(),
                    categoria_status: category_status(code, description).into(),
                    votos: votes.to_string(),
                    total_cargo_municipio: total.to_string(),
                    fracao: fraction,
                    fracao_motivo: fraction_reason,
                });
            }
        }
        let context_approved = context_gate.0 == "approved";
        let mut by_office_context = Vec::new();
        let mut by_office_municipality_context = Vec::new();
        let mut by_office_zone_context = Vec::new();
        if context_approved {
            let mut offices: BTreeMap<String, ContextAgg> = BTreeMap::new();
            let mut municipalities: BTreeMap<(String, String), ContextAgg> = BTreeMap::new();
            let mut zones: BTreeMap<(String, String, String), ContextAgg> = BTreeMap::new();
            for entry in self.contexts.values() {
                accumulate_context(
                    offices.entry(entry.office.clone()).or_insert(ContextAgg {
                        groups: 0,
                        aptos: 0,
                        comparecimento: 0,
                        abstencoes: 0,
                    }),
                    entry,
                )?;
                accumulate_context(
                    municipalities
                        .entry((entry.office.clone(), entry.municipality.clone()))
                        .or_insert(ContextAgg {
                            groups: 0,
                            aptos: 0,
                            comparecimento: 0,
                            abstencoes: 0,
                        }),
                    entry,
                )?;
                accumulate_context(
                    zones
                        .entry((
                            entry.office.clone(),
                            entry.municipality.clone(),
                            entry.zone.clone(),
                        ))
                        .or_insert(ContextAgg {
                            groups: 0,
                            aptos: 0,
                            comparecimento: 0,
                            abstencoes: 0,
                        }),
                    entry,
                )?;
            }
            for (cargo, aggregate) in offices {
                by_office_context.push(context_row(
                    &cargo,
                    &self.office_name(&cargo),
                    None,
                    None,
                    None,
                    &aggregate,
                ));
            }
            for ((cargo, municipality), aggregate) in municipalities {
                by_office_municipality_context.push(context_row(
                    &cargo,
                    &self.office_name(&cargo),
                    Some(municipality.clone()),
                    Some(
                        self.municipality_names
                            .get(&municipality)
                            .cloned()
                            .unwrap_or_default(),
                    ),
                    None,
                    &aggregate,
                ));
            }
            for ((cargo, municipality, zone), aggregate) in zones {
                by_office_zone_context.push(context_row(
                    &cargo,
                    &self.office_name(&cargo),
                    Some(municipality.clone()),
                    Some(
                        self.municipality_names
                            .get(&municipality)
                            .cloned()
                            .unwrap_or_default(),
                    ),
                    Some(zone),
                    &aggregate,
                ));
            }
        }
        let mut definitions = BTreeMap::new();
        definitions.insert("occurrence_key".into(), OCCURRENCE_FIELDS.join(","));
        definitions.insert("context_key".into(), CONTEXT_FIELDS.join(","));
        definitions.insert(
            "context_equality_fields".into(),
            CONTEXT_EQUALITY_FIELDS.join(","),
        );
        definitions.insert(
            "category_codes".into(),
            "1=Nominal,2=Branco,3=Nulo,4=Legenda".into(),
        );
        definitions.insert(
            "rate_rule".into(),
            "numerador/denominador com 6 casas decimais e arredondamento meio para cima; null quando o denominador é zero".into(),
        );
        definitions.insert(
            "votes_denominator".into(),
            "QT_VOTOS somado por categoria; total do cargo/município é a soma das categorias"
                .into(),
        );
        definitions.insert(
            "category_share_denominator".into(),
            "votos totais do mesmo cargo e município".into(),
        );
        definitions.insert(
            "electors_rule".into(),
            "contextos de cargos diferentes não são somados; total de eleitores exige população de referência validada".into(),
        );
        let results = AnalysisResults {
            artifact_kind: "bweb_descriptive_analysis".into(),
            format_version: 1,
            analysis_contract_version: ANALYSIS_CONTRACT_VERSION,
            profile: self.profile.id.clone(),
            source: source.clone(),
            definitions,
            votes: VotesResults {
                status: votes_gate.0.clone(),
                blocked_reason: votes_gate.1.clone(),
                total: votes_total.clone(),
                by_office,
                by_office_category,
                by_office_municipality,
            },
            context: ContextResults {
                status: context_gate.0.clone(),
                blocked_reason: context_gate.1.clone(),
                by_office: by_office_context,
                by_office_municipality: by_office_municipality_context,
                by_office_zone: by_office_zone_context,
            },
        };
        Ok((results, votes_total))
    }

    fn office_name(&self, code: &str) -> String {
        self.offices
            .get(code)
            .map(|entry| entry.0.clone())
            .unwrap_or_default()
    }
}

fn category_label(code: &str) -> Option<&'static str> {
    match code {
        "1" => Some("Nominal"),
        "2" => Some("Branco"),
        "3" => Some("Nulo"),
        "4" => Some("Legenda"),
        _ => None,
    }
}

fn category_status(code: &str, description: &str) -> &'static str {
    match category_label(code) {
        Some(name) if description == name => "confirmed",
        Some(_) => "inconsistent",
        None => "unconfirmed",
    }
}

fn accumulate_context(target: &mut ContextAgg, entry: &ContextEntry) -> Result<()> {
    target.groups = target.groups.checked_add(1).context("overflow de grupos")?;
    target.aptos = target
        .aptos
        .checked_add(entry.aptos)
        .context("overflow de aptos")?;
    target.comparecimento = target
        .comparecimento
        .checked_add(entry.comparecimento)
        .context("overflow de comparecimento")?;
    target.abstencoes = target
        .abstencoes
        .checked_add(entry.abstencoes)
        .context("overflow de abstenções")?;
    Ok(())
}

fn context_row(
    cargo: &str,
    cargo_nome: &str,
    municipio: Option<String>,
    municipio_nome: Option<String>,
    zona: Option<String>,
    aggregate: &ContextAgg,
) -> ContextRow {
    let (comparecimento_rate, comparecimento_reason) =
        ratio(aggregate.comparecimento, aggregate.aptos);
    let (abstencao_rate, abstencao_reason) = ratio(aggregate.abstencoes, aggregate.aptos);
    ContextRow {
        cargo: cargo.into(),
        cargo_nome: cargo_nome.into(),
        municipio,
        municipio_nome,
        zona,
        grupos_contexto: aggregate.groups,
        aptos: aggregate.aptos.to_string(),
        comparecimento: aggregate.comparecimento.to_string(),
        abstencoes: aggregate.abstencoes.to_string(),
        comparecimento_por_aptos: comparecimento_rate,
        comparecimento_por_aptos_motivo: comparecimento_reason,
        abstencao_por_aptos: abstencao_rate,
        abstencao_por_aptos_motivo: abstencao_reason,
    }
}

fn limitations() -> Vec<String> {
    vec![
        "Cobertura observada no arquivo não prova completude do universo eleitoral.".into(),
        "DS_SECOES_AGREGADAS foi preservado; contagem de seções físicas e cobertura territorial dependente da lista permanecem bloqueadas.".into(),
        "Contextos de cargos diferentes não foram somados; não há total geral de eleitores.".into(),
        "Código municipal TSE não foi convertido nem equiparado a código IBGE.".into(),
        "Comparação entre turnos, reconciliação com votação/RDV, modelos e detecção de anomalias não foram executados.".into(),
        "Nenhuma conclusão de fraude ou autenticidade eleitoral é produzida.".into(),
    ]
}

struct Evaluation {
    approved: bool,
    status: String,
    quality: QualityReport,
    results: AnalysisResults,
    records: u64,
    votes_total: Option<String>,
    error_count: u64,
    source: Source,
}

enum InputKind {
    Csv(PathBuf),
    View(PathBuf),
}

fn detect_input(path: &Path) -> Result<InputKind> {
    if path.is_dir() {
        let view = path.join("view.json");
        if view.is_file() {
            Ok(InputKind::View(path.to_path_buf()))
        } else {
            bail!("diretório de entrada sem view.json")
        }
    } else if path.is_file() {
        Ok(InputKind::Csv(path.to_path_buf()))
    } else {
        bail!("entrada inexistente: {}", path.display())
    }
}

fn parse_stream<R: Read>(hashing: HashingReader<R>, state: &mut State) -> (HashingReader<R>, bool) {
    let bounded = crate::bweb::BoundedCsv {
        inner: hashing,
        quoted: false,
        bytes: 0,
        maximum: state.max_record_bytes,
    };
    let mut reader = csv::ReaderBuilder::new()
        .has_headers(false)
        .flexible(false)
        .delimiter(b';')
        .from_reader(bounded);
    let mut record = csv::ByteRecord::new();
    let mut complete = false;
    match reader.read_byte_record(&mut record) {
        Ok(true) => {
            state.accept_header(&record);
            if state.header_ok {
                loop {
                    match reader.read_byte_record(&mut record) {
                        Ok(true) => {
                            state.accept(&record);
                            if state.rows > state.max_csv_records {
                                break;
                            }
                        }
                        Ok(false) => {
                            complete = true;
                            break;
                        }
                        Err(error) => {
                            state.fail(
                                "records",
                                None,
                                None,
                                format!("erro de leitura CSV: {error}"),
                            );
                            break;
                        }
                    }
                }
            }
        }
        Ok(false) => state.fail("header", Some(0), None, "CSV vazio"),
        Err(error) => state.fail(
            "header",
            Some(0),
            None,
            format!("erro de leitura do cabeçalho: {error}"),
        ),
    }
    let bounded = reader.into_inner();
    (bounded.inner, complete)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ViewDescriptor {
    artifact_kind: String,
    format_version: u32,
    guarantee: String,
    kind: String,
    source: ViewSource,
    encoded: ViewObject,
    codec: Option<String>,
    dictionary: Option<ViewObject>,
    pack_manifest: Option<ViewObject>,
    decoded_stream: Option<ViewObject>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ViewSource {
    bytes: u64,
    sha256: String,
    records: u64,
    zip_path: Option<String>,
    zip_sha256: Option<String>,
    member_name: Option<String>,
    member_ordinal: Option<u64>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ViewObject {
    file: String,
    bytes: u64,
    sha256: String,
}

fn safe_object_name(name: &str) -> bool {
    !name.is_empty()
        && name != "."
        && name != ".."
        && !name.contains('/')
        && !name.contains('\\')
        && !name.contains('\0')
}

fn checked_view_object(root: &Path, object: &ViewObject) -> Result<PathBuf> {
    if object.bytes > crate::limits::get("MAX_SOURCE_FILE_BYTES")? {
        bail!("MAX_SOURCE_FILE_BYTES excedido no objeto de view");
    }
    if !safe_object_name(&object.file) {
        bail!("nome de objeto de view inválido");
    }
    let path = root.join(&object.file);
    let metadata = std::fs::symlink_metadata(&path)
        .with_context(|| format!("objeto de view ausente: {}", object.file))?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        bail!("objeto de view não é arquivo regular: {}", object.file);
    }
    let root = root.canonicalize()?;
    let canonical = path.canonicalize()?;
    if !canonical.starts_with(&root) {
        bail!("objeto de view fora do diretório");
    }
    if metadata.len() != object.bytes || crate::hash::sha256_file(&path)? != object.sha256 {
        bail!("objeto de view diverge do descritor: {}", object.file);
    }
    Ok(path)
}

fn evaluate_csv(path: &Path, profile: &AnalysisProfile) -> Result<Evaluation> {
    let metadata = std::fs::metadata(path)?;
    if !metadata.is_file() {
        bail!("entrada não é arquivo");
    }
    let size = metadata.len();
    if size > crate::limits::get("MAX_SOURCE_FILE_BYTES")? {
        bail!("MAX_SOURCE_FILE_BYTES excedido");
    }
    let mut state = State::new(
        profile.clone(),
        "csv",
        Some(size),
        profile.expected_source_sha256.clone(),
        profile.expected_records,
    )?;
    let file = std::fs::File::open(path)?;
    let hashing = HashingReader::new(file);
    let (hashing, complete) = parse_stream(hashing, &mut state);
    let (bytes, sha256) = hashing.finish();
    state.finish_source(Some(bytes), Some(sha256), complete);
    state.finish()
}

fn evaluate_view(path: &Path, profile: &AnalysisProfile) -> Result<Evaluation> {
    let descriptor_path = path.join("view.json");
    let size = std::fs::metadata(&descriptor_path)?.len();
    if size > crate::limits::get("MAX_PACK_MANIFEST_BYTES")? {
        bail!("descritor de view excessivo");
    }
    let descriptor_bytes = std::fs::read(&descriptor_path)?;
    let descriptor_sha256 = crate::hash::sha256_bytes(&descriptor_bytes);
    let descriptor: ViewDescriptor = serde_json::from_slice(&descriptor_bytes)?;
    if descriptor.source.bytes > crate::limits::get("MAX_SOURCE_FILE_BYTES")? {
        bail!("MAX_SOURCE_FILE_BYTES excedido na expansão da view");
    }
    if descriptor.artifact_kind != "bweb_storage_view"
        || descriptor.format_version != 1
        || descriptor.guarantee != "exact-csv-member-bytes"
        || descriptor.kind != "csv-codec"
        || descriptor.dictionary.is_some()
        || descriptor.pack_manifest.is_some()
        || descriptor.decoded_stream.is_some()
    {
        bail!("descritor de view incompatível com o perfil CSV");
    }
    let codec = descriptor
        .codec
        .as_deref()
        .context("codec de view ausente")?;
    let payload = checked_view_object(path, &descriptor.encoded)?;
    let source = &descriptor.source;
    let mut state = State::new(
        profile.clone(),
        "view",
        Some(source.bytes),
        Some(source.sha256.clone()),
        Some(source.records),
    )?;
    state.source_view_sha256 = Some(descriptor_sha256);
    state.source_zip_path = source.zip_path.clone();
    state.source_zip_sha256 = source.zip_sha256.clone();
    state.source_member_name = source.member_name.clone();
    state.source_member_ordinal = source.member_ordinal;
    let mut profile_mismatch = false;
    if let Some(expected) = &profile.expected_source_sha256 {
        if expected != &source.sha256 {
            state.fail(
                "source_hash",
                None,
                None,
                "view não corresponde ao snapshot aceito pelo perfil",
            );
            profile_mismatch = true;
        }
    }
    if let Some(expected) = profile.expected_records {
        if expected != source.records {
            state.fail(
                "records",
                None,
                None,
                "contagem da view não corresponde ao perfil",
            );
            profile_mismatch = true;
        }
    }
    if let Some(expected) = &profile.expected_zip_sha256 {
        if source.zip_sha256.as_ref() != Some(expected) {
            state.fail(
                "source_hash",
                None,
                None,
                "SHA-256 do ZIP da view não corresponde ao perfil",
            );
            profile_mismatch = true;
        }
    }
    if let Some(expected) = &profile.expected_member_name {
        if source.member_name.as_ref() != Some(expected) {
            state.fail(
                "source_hash",
                None,
                None,
                "membro da view não corresponde ao perfil",
            );
            profile_mismatch = true;
        }
    }
    if let Some(expected) = profile.expected_member_ordinal {
        if source.member_ordinal != Some(expected) {
            state.fail(
                "source_hash",
                None,
                None,
                "ordinal do membro da view não corresponde ao perfil",
            );
            profile_mismatch = true;
        }
    }
    if profile_mismatch {
        state.profile_mismatch = true;
        state.complete = false;
        return state.finish();
    }
    let decoded = crate::codec::reader(&payload, codec, None, source.bytes.saturating_add(1))?;
    let hashing = HashingReader::new(decoded);
    let (hashing, complete) = parse_stream(hashing, &mut state);
    let HashingReader { inner, hash, bytes } = hashing;
    let sha256 = hex::encode(hash.finalize());
    if complete {
        inner.finish()?;
    }
    state.finish_source(Some(bytes), Some(sha256), complete);
    state.finish()
}

fn evaluate(input: &Path, profile: &AnalysisProfile) -> Result<Evaluation> {
    match detect_input(input)? {
        InputKind::Csv(path) => evaluate_csv(&path, profile),
        InputKind::View(path) => evaluate_view(&path, profile),
    }
}

fn write_json(path: &Path, value: &impl Serialize) -> Result<()> {
    let mut bytes = serde_json::to_vec_pretty(value)?;
    bytes.push(b'\n');
    std::fs::write(path, bytes)?;
    Ok(())
}

fn write_csv(path: &Path, headers: &[&str], rows: impl Iterator<Item = Vec<String>>) -> Result<()> {
    let mut writer = csv::WriterBuilder::new()
        .delimiter(b',')
        .from_writer(Vec::new());
    writer.write_record(headers)?;
    for row in rows {
        writer.write_record(row)?;
    }
    writer.flush()?;
    let bytes = writer
        .into_inner()
        .map_err(|error| anyhow::anyhow!("finalizar CSV: {error}"))?;
    std::fs::write(path, bytes)?;
    Ok(())
}

fn describe_file(path: &Path) -> Result<OutputFile> {
    Ok(OutputFile {
        bytes: std::fs::metadata(path)?.len(),
        sha256: crate::hash::sha256_file(path)?,
    })
}

fn write_outputs(
    evaluation: &Evaluation,
    output: &Path,
    input: &Path,
    started_at: u64,
    finished_at: u64,
    duration_ms: u128,
) -> Result<()> {
    let results_path = output.join("results.json");
    let quality_path = output.join("quality.json");
    let report_path = output.join("REPORT.md");
    write_json(&results_path, &evaluation.results)?;
    write_json(&quality_path, &evaluation.quality)?;

    let mut outputs = BTreeMap::new();
    outputs.insert("results.json".into(), describe_file(&results_path)?);
    outputs.insert("quality.json".into(), describe_file(&quality_path)?);

    let votes_office_path = output.join("votes_by_office.csv");
    write_csv(
        &votes_office_path,
        &["cargo", "cargo_nome", "votos"],
        evaluation
            .results
            .votes
            .by_office
            .iter()
            .map(|row| vec![row.cargo.clone(), row.cargo_nome.clone(), row.votos.clone()]),
    )?;
    outputs.insert(
        "votes_by_office.csv".into(),
        describe_file(&votes_office_path)?,
    );

    let votes_municipality_path = output.join("votes_by_office_municipality.csv");
    write_csv(
        &votes_municipality_path,
        &[
            "cargo",
            "cargo_nome",
            "municipio",
            "municipio_nome",
            "categoria_codigo",
            "categoria",
            "categoria_status",
            "votos",
            "total_cargo_municipio",
            "fracao",
            "fracao_motivo",
        ],
        evaluation
            .results
            .votes
            .by_office_municipality
            .iter()
            .map(|row| {
                vec![
                    row.cargo.clone(),
                    row.cargo_nome.clone(),
                    row.municipio.clone(),
                    row.municipio_nome.clone(),
                    row.categoria_codigo.clone(),
                    row.categoria.clone(),
                    row.categoria_status.clone(),
                    row.votos.clone(),
                    row.total_cargo_municipio.clone(),
                    row.fracao.clone().unwrap_or_default(),
                    row.fracao_motivo.clone().unwrap_or_default(),
                ]
            }),
    )?;
    outputs.insert(
        "votes_by_office_municipality.csv".into(),
        describe_file(&votes_municipality_path)?,
    );

    let context_office_path = output.join("context_by_office.csv");
    write_csv(
        &context_office_path,
        &[
            "cargo",
            "cargo_nome",
            "municipio",
            "municipio_nome",
            "zona",
            "grupos_contexto",
            "aptos",
            "comparecimento",
            "abstencoes",
            "comparecimento_por_aptos",
            "comparecimento_por_aptos_motivo",
            "abstencao_por_aptos",
            "abstencao_por_aptos_motivo",
        ],
        evaluation
            .results
            .context
            .by_office
            .iter()
            .map(context_csv_row),
    )?;
    outputs.insert(
        "context_by_office.csv".into(),
        describe_file(&context_office_path)?,
    );

    let context_municipality_path = output.join("context_by_office_municipality.csv");
    write_csv(
        &context_municipality_path,
        &[
            "cargo",
            "cargo_nome",
            "municipio",
            "municipio_nome",
            "zona",
            "grupos_contexto",
            "aptos",
            "comparecimento",
            "abstencoes",
            "comparecimento_por_aptos",
            "comparecimento_por_aptos_motivo",
            "abstencao_por_aptos",
            "abstencao_por_aptos_motivo",
        ],
        evaluation
            .results
            .context
            .by_office_municipality
            .iter()
            .map(context_csv_row),
    )?;
    outputs.insert(
        "context_by_office_municipality.csv".into(),
        describe_file(&context_municipality_path)?,
    );

    let context_zone_path = output.join("context_by_office_zone.csv");
    write_csv(
        &context_zone_path,
        &[
            "cargo",
            "cargo_nome",
            "municipio",
            "municipio_nome",
            "zona",
            "grupos_contexto",
            "aptos",
            "comparecimento",
            "abstencoes",
            "comparecimento_por_aptos",
            "comparecimento_por_aptos_motivo",
            "abstencao_por_aptos",
            "abstencao_por_aptos_motivo",
        ],
        evaluation
            .results
            .context
            .by_office_zone
            .iter()
            .map(context_csv_row),
    )?;
    outputs.insert(
        "context_by_office_zone.csv".into(),
        describe_file(&context_zone_path)?,
    );

    write_markdown(&report_path, evaluation)?;
    outputs.insert("REPORT.md".into(), describe_file(&report_path)?);

    let receipt = RunReceipt {
        artifact_kind: "bweb_descriptive_run".into(),
        format_version: 1,
        analysis_contract_version: ANALYSIS_CONTRACT_VERSION,
        analysis_code_version: ANALYSIS_CODE_VERSION.into(),
        profile: evaluation.quality.profile.clone(),
        tool_version: crate::TOOL_VERSION.into(),
        started_at_unix_seconds: started_at,
        finished_at_unix_seconds: finished_at,
        duration_ms,
        peak_rss_kib: peak_rss_kib(),
        input: input.display().to_string(),
        output: output.display().to_string(),
        approved: evaluation.approved,
        status: evaluation.status.clone(),
        parameters: BTreeMap::from([
            ("profile".into(), evaluation.quality.profile.clone()),
            (
                "analysis_contract_version".into(),
                ANALYSIS_CONTRACT_VERSION.to_string(),
            ),
            ("rate_decimals".into(), "6".into()),
            ("streaming".into(), "sim".into()),
        ]),
        source: evaluation.source.clone(),
        outputs,
        variable_metadata: vec![
            "started_at_unix_seconds".into(),
            "finished_at_unix_seconds".into(),
            "duration_ms".into(),
            "peak_rss_kib".into(),
            "input".into(),
            "output".into(),
        ],
    };
    write_json(&output.join("run.json"), &receipt)?;
    Ok(())
}

fn context_csv_row(row: &ContextRow) -> Vec<String> {
    vec![
        row.cargo.clone(),
        row.cargo_nome.clone(),
        row.municipio.clone().unwrap_or_default(),
        row.municipio_nome.clone().unwrap_or_default(),
        row.zona.clone().unwrap_or_default(),
        row.grupos_contexto.to_string(),
        row.aptos.clone(),
        row.comparecimento.clone(),
        row.abstencoes.clone(),
        row.comparecimento_por_aptos.clone().unwrap_or_default(),
        row.comparecimento_por_aptos_motivo
            .clone()
            .unwrap_or_default(),
        row.abstencao_por_aptos.clone().unwrap_or_default(),
        row.abstencao_por_aptos_motivo.clone().unwrap_or_default(),
    ]
}

fn write_markdown(path: &Path, evaluation: &Evaluation) -> Result<()> {
    let quality = &evaluation.quality;
    let results = &evaluation.results;
    let mut text = String::new();
    writeln!(text, "# Análise descritiva — BU web MT 2026 t1")?;
    writeln!(text)?;
    writeln!(text, "Perfil: `{}`  ", quality.profile)?;
    writeln!(
        text,
        "Status: **{}** (aprovado={})  ",
        quality.status,
        if quality.approved { "sim" } else { "não" }
    )?;
    writeln!(
        text,
        "Contrato analítico: v{}; código: `{}`  ",
        quality.analysis_contract_version, ANALYSIS_CODE_VERSION
    )?;
    writeln!(text, "Registros lidos: {}.", quality.coverage.records)?;
    writeln!(text)?;
    writeln!(text, "## Fonte e snapshot")?;
    writeln!(text)?;
    writeln!(text, "- Origem: `{}`", quality.source.kind)?;
    if let Some(hash) = &quality.source.view_sha256 {
        writeln!(text, "- SHA-256 da view: `{hash}`")?;
    }
    if let Some(hash) = &quality.source.csv_sha256 {
        writeln!(text, "- SHA-256 do CSV: `{hash}`")?;
    }
    if let Some(zip) = &quality.source.zip_sha256 {
        writeln!(text, "- SHA-256 do ZIP: `{zip}`")?;
    }
    if let Some(member) = &quality.source.member_name {
        writeln!(
            text,
            "- Membro: `{}` (ordinal {})",
            member,
            quality
                .source
                .member_ordinal
                .map(|value| value.to_string())
                .unwrap_or_else(|| "n/a".into())
        )?;
    }
    if let Some(snapshot) = &quality.source.snapshot {
        writeln!(
            text,
            "- Geração: {} {}; pleito {}; turno {}; UF {}",
            snapshot.dt_geracao,
            snapshot.hh_geracao,
            snapshot.cd_pleito,
            snapshot.nr_turno,
            snapshot.sg_uf
        )?;
    }
    writeln!(
        text,
        "- Verificação da fonte: `{}`",
        quality.source.verification
    )?;
    writeln!(text)?;
    writeln!(text, "## Controles")?;
    writeln!(text)?;
    writeln!(text, "| controle | status | obrigatório | falhas |")?;
    writeln!(text, "|---|---|---:|---:|")?;
    for check in &quality.checks {
        writeln!(
            text,
            "| {} | {} | {} | {} |",
            check.id, check.status, check.mandatory, check.failures
        )?;
    }
    writeln!(text)?;
    writeln!(text, "## Usos liberados e bloqueados")?;
    writeln!(text)?;
    writeln!(text, "| uso | status | motivo |")?;
    writeln!(text, "|---|---|---|")?;
    for use_status in &quality.uses {
        writeln!(
            text,
            "| {} | {} | {} |",
            use_status.id,
            use_status.status,
            use_status.reason.replace('|', "/")
        )?;
    }
    writeln!(text)?;
    writeln!(text, "## Votos por cargo")?;
    writeln!(text)?;
    if let Some(total) = &results.votes.total {
        writeln!(text, "Total de votos (todos os cargos): **{total}**.")?;
        writeln!(text)?;
    }
    writeln!(text, "| cargo | nome | votos |")?;
    writeln!(text, "|---|---|---:|")?;
    for row in &results.votes.by_office {
        writeln!(
            text,
            "| {} | {} | {} |",
            row.cargo, row.cargo_nome, row.votos
        )?;
    }
    writeln!(text)?;
    writeln!(text, "## Contexto por cargo")?;
    writeln!(text)?;
    writeln!(
        text,
        "| cargo | grupos | aptos | comparecimento | abstenções | comp/aptos | abst/aptos |"
    )?;
    writeln!(text, "|---|---:|---:|---:|---:|---:|---:|")?;
    for row in &results.context.by_office {
        writeln!(
            text,
            "| {} | {} | {} | {} | {} | {} | {} |",
            row.cargo,
            row.grupos_contexto,
            row.aptos,
            row.comparecimento,
            row.abstencoes,
            row.comparecimento_por_aptos.as_deref().unwrap_or("-"),
            row.abstencao_por_aptos.as_deref().unwrap_or("-")
        )?;
    }
    writeln!(text)?;
    writeln!(text, "## Categorias")?;
    writeln!(text)?;
    writeln!(text, "| código | categoria | status | votos |")?;
    writeln!(text, "|---|---|---|---:|")?;
    for category in &quality.coverage.categories {
        writeln!(
            text,
            "| {} | {} | {} | {} |",
            category.code, category.description, category.status, category.votes
        )?;
    }
    writeln!(text)?;
    writeln!(text, "## Cobertura observada")?;
    writeln!(text)?;
    writeln!(
        text,
        "- Municípios (código TSE): {}",
        quality.coverage.municipalities
    )?;
    writeln!(text, "- Zonas: {}", quality.coverage.zones)?;
    writeln!(
        text,
        "- Grupos de contexto/seção principal: {}",
        quality.coverage.context_groups
    )?;
    writeln!(
        text,
        "- Grupos com `DS_SECOES_AGREGADAS` não sentinela: {}",
        quality.ds_secoes_agregadas.context_groups_with_non_sentinel
    )?;
    writeln!(
        text,
        "- Duplicatas: {} (repetidas {}, conflitos {})",
        quality.keys.duplicate_keys, quality.keys.repeated_occurrences, quality.keys.conflicts
    )?;
    writeln!(
        text,
        "- Divergências de contexto: {} grupos",
        quality.context.divergent_groups
    )?;
    if quality.unexpected_values_overflow > 0 {
        writeln!(
            text,
            "- Evidências de valores inesperados não retidas: {}",
            quality.unexpected_values_overflow
        )?;
    }
    writeln!(text)?;
    writeln!(text, "## Limitações")?;
    writeln!(text)?;
    for limitation in &quality.limitations {
        writeln!(text, "- {limitation}")?;
    }
    writeln!(text)?;
    writeln!(text, "## Reprodução")?;
    writeln!(text)?;
    writeln!(text, "```bash")?;
    writeln!(
        text,
        "./target/release/tsepack analyze \\\n  --input <view-ou-csv> \\\n  --output <novo-diretorio> \\\n  --profile mt-2026-t1-bweb-v1"
    )?;
    writeln!(text, "```")?;
    std::fs::write(path, text)?;
    Ok(())
}

fn now_unix() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or_default()
}

fn peak_rss_kib() -> Option<u64> {
    let status = std::fs::read_to_string("/proc/self/status").ok()?;
    status.lines().find_map(|line| {
        line.strip_prefix("VmHWM:")
            .and_then(|value| value.split_whitespace().next())
            .and_then(|value| value.parse().ok())
    })
}

fn failure_parameters(profile: &AnalysisProfile) -> BTreeMap<String, String> {
    BTreeMap::from([
        ("profile".into(), profile.id.clone()),
        (
            "analysis_contract_version".into(),
            ANALYSIS_CONTRACT_VERSION.to_string(),
        ),
        ("rate_decimals".into(), "6".into()),
        ("streaming".into(), "sim".into()),
    ])
}

fn write_failure_receipt(
    output: &Path,
    input: &Path,
    profile: &AnalysisProfile,
    error: &str,
    started_at: u64,
    duration_ms: u128,
) -> Result<()> {
    let value = serde_json::json!({
        "artifact_kind": "bweb_descriptive_run",
        "format_version": 1,
        "analysis_contract_version": ANALYSIS_CONTRACT_VERSION,
        "analysis_code_version": ANALYSIS_CODE_VERSION,
        "profile": profile.id,
        "tool_version": crate::TOOL_VERSION,
        "started_at_unix_seconds": started_at,
        "finished_at_unix_seconds": now_unix(),
        "duration_ms": duration_ms,
        "peak_rss_kib": peak_rss_kib(),
        "input": input.display().to_string(),
        "output": output.display().to_string(),
        "approved": false,
        "status": "failed",
        "parameters": failure_parameters(profile),
        "outputs": {},
        "error": error,
        "variable_metadata": ["started_at_unix_seconds", "finished_at_unix_seconds", "duration_ms", "peak_rss_kib", "input", "output", "error"]
    });
    write_json(&output.join("run.json"), &value)?;
    Ok(())
}

pub fn run(input: &Path, output: &Path, profile: &AnalysisProfile) -> Result<AnalysisOutcome> {
    crate::output::absent(output)?;
    if crate::output_path_conflicts(input, output)? {
        bail!("saída sobrepõe a entrada");
    }
    let stage = crate::output::Stage::new(output, true)?;
    let started_at = now_unix();
    let timer = Instant::now();
    let evaluation = match evaluate(input, profile) {
        Ok(evaluation) => evaluation,
        Err(error) => {
            write_failure_receipt(
                &stage.path,
                input,
                profile,
                &error.to_string(),
                started_at,
                timer.elapsed().as_millis(),
            )?;
            stage.publish(output)?;
            return Err(error);
        }
    };
    let finished_at = now_unix();
    write_outputs(
        &evaluation,
        &stage.path,
        input,
        started_at,
        finished_at,
        timer.elapsed().as_millis(),
    )?;
    stage.publish(output)?;
    Ok(AnalysisOutcome {
        approved: evaluation.approved,
        status: evaluation.status,
        output: output.to_path_buf(),
        records: evaluation.records,
        votes_total: evaluation.votes_total,
        error_count: evaluation.error_count,
    })
}

#[cfg(test)]
mod resource_tests {
    use super::*;

    #[test]
    fn record_limit_stops_reading_the_fixture_instead_of_scanning_the_remaining_rows() {
        let bytes = include_bytes!("../tests/fixtures/analyze/mt-valid.csv");
        let profile = profile_mt_2026_t1_bweb_v1();
        let mut state = State::new(profile, "synthetic-test", None, None, None).unwrap();
        state.max_csv_records = 1;
        let (_, complete) =
            parse_stream(HashingReader::new(std::io::Cursor::new(bytes)), &mut state);
        assert!(!complete);
        assert_eq!(state.rows, 2);
        assert!(state.checks["records"].failures > 0);
    }
}
