//! Auditoria descritiva presidencial 2026/t2. Sem inferência causal.
use anyhow::{ensure, Context, Result};
use clap::Parser;
use csv::{ByteRecord, ReaderBuilder};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, HashMap};
use std::io::Read;
use std::path::PathBuf;
use tsepack::bweb::BWEB_HEADER;
#[path = "../audit_io.rs"]
mod audit_io;
use audit_io::{publish_file, HashingRead};

#[derive(Parser)]
struct Args {
    #[arg(long)]
    manifest: PathBuf,
    #[arg(long)]
    output: PathBuf,
    /// Exportação semântica por seção para confrontos com índices/locais/logs.
    #[arg(long)]
    sections_output: Option<PathBuf>,
    #[arg(long)]
    time_policy: Option<PathBuf>,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Input {
    path: PathBuf,
    sha256: String,
    bytes: u64,
    uf: String,
    zip_sha256: String,
    zip_url: String,
    member: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Manifest {
    format_version: u32,
    inputs: Vec<Input>,
}

#[derive(Default)]
struct Section {
    context: Vec<Vec<u8>>,
    votes: BTreeMap<String, u64>,
    turnout: u64,
    biometric: u64,
    close_seconds: Option<u32>,
    uf: String,
    municipality: String,
}

#[derive(Default, Serialize)]
struct Totals {
    sections: u64,
    turnout: u64,
    biometric_not_enabled: u64,
    votes: BTreeMap<String, u64>,
}

impl Totals {
    fn add(&mut self, s: &Section) {
        self.sections += 1;
        self.turnout += s.turnout;
        self.biometric_not_enabled += s.biometric;
        for (candidate, votes) in &s.votes {
            *self.votes.entry(candidate.clone()).or_default() += votes;
        }
    }
}

#[derive(Default, Serialize)]
struct Extremes {
    unanimity_13: u64,
    unanimity_22: u64,
    above_90_13: u64,
    above_90_22: u64,
    at_least_90_13: u64,
    at_least_90_22: u64,
    no_valid_votes: u64,
    // Exatamente 90% não entra em "mais de 90%".
    valid_votes_histogram: BTreeMap<String, u64>,
}

#[derive(Serialize)]
struct Correlation {
    n: usize,
    pearson: Option<f64>,
    spearman: Option<f64>,
    method: &'static str,
}

#[derive(Serialize)]
struct Report {
    format_version: u32,
    scope: &'static str,
    time_policy: &'static str,
    source_members: Vec<Input>,
    records_all_cargos: u64,
    excluded_records_by_cargo: BTreeMap<String, u64>,
    presidential: Totals,
    by_uf: BTreeMap<String, Totals>,
    raw_clock_windows: BTreeMap<String, Totals>,
    raw_minute_windows: BTreeMap<String, Totals>,
    raw_strict_after_19: Totals,
    raw_after_19_by_uf: BTreeMap<String, Totals>,
    extremes: Extremes,
    extremes_by_uf: BTreeMap<String, Extremes>,
    biometric_correlation: Correlation,
    within_municipality_pearson: Option<f64>,
    benford_first_digit_counts_13: [u64; 9],
    benford_first_digit_counts_22: [u64; 9],
    benford_expected_probabilities: [f64; 9],
    benford_scope: &'static str,
    closing_missing: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    normalized_closing: Option<NormalizedClosing>,
    limitations: Vec<&'static str>,
}

#[derive(Deserialize)]
struct TimePolicy {
    format_version: u32,
    brt_shift_seconds_by_uf: BTreeMap<String, Option<i32>>,
    municipality_overrides: BTreeMap<String, i32>,
}

#[derive(Default, Serialize)]
struct NormalizedClosing {
    policy_sha256: String,
    definition: &'static str,
    windows: BTreeMap<String, Totals>,
    foreign_excluded: Totals,
    missing_closing: Totals,
}

fn normalize_closing(
    policy: &TimePolicy,
    sections: &HashMap<String, Section>,
) -> Result<NormalizedClosing> {
    ensure!(
        policy.format_version == 1,
        "versão de política desconhecida"
    );
    let mut out = NormalizedClosing { definition: "Encerramento registrado + deslocamento nominal local para Brasília. Não identifica instante dos votos nem demonstra sincronização física do relógio. ZZ separado.", ..Default::default() };
    for section in sections.values() {
        if section.uf == "ZZ" {
            out.foreign_excluded.add(section);
            continue;
        }
        let key = format!("{}/{:05}", section.uf, section.municipality.parse::<u32>()?);
        let shift = policy
            .municipality_overrides
            .get(&key)
            .copied()
            .or_else(|| {
                policy
                    .brt_shift_seconds_by_uf
                    .get(&section.uf)
                    .copied()
                    .flatten()
            })
            .context("UF/município sem deslocamento nominal")?;
        ensure!(
            matches!(shift, -3600 | 0 | 3600 | 7200),
            "deslocamento nominal inválido"
        );
        let Some(raw) = section.close_seconds else {
            out.missing_closing.add(section);
            continue;
        };
        let seconds = raw as i32 + shift;
        for (name, included) in [
            ("ate_17h00m00s", seconds <= 17 * 3600),
            ("apos_17h00m00s", seconds > 17 * 3600),
            ("ate_17h00m59s", seconds < 17 * 3600 + 60),
            ("apos_17h00m59s", seconds >= 17 * 3600 + 60),
            ("desde_19h00m00s", seconds >= 19 * 3600),
            ("apos_19h00m00s", seconds > 19 * 3600),
        ] {
            if included {
                out.windows.entry(name.to_owned()).or_default().add(section);
            }
        }
    }
    Ok(out)
}

fn ascii(row: &ByteRecord, index: usize) -> Result<&str> {
    std::str::from_utf8(&row[index]).context("campo de controle não ASCII/UTF-8")
}

fn integer(row: &ByteRecord, index: usize) -> Result<u64> {
    let value = ascii(row, index)?;
    ensure!(
        !value.is_empty() && value.bytes().all(|v| v.is_ascii_digit()),
        "inteiro inválido em {}: {:?}",
        BWEB_HEADER[index],
        value
    );
    // Contagens de uma seção são u32; totais nacionais usam u64. Com o teto
    // de seções centralizado, todas as somas e produtos do relatório cabem em u64.
    Ok(u64::from(value.parse::<u32>()?))
}

fn closing(value: &str) -> Result<Option<u32>> {
    if value.is_empty() || value == "#NULO#" || value == "#NE#" {
        return Ok(None);
    }
    ensure!(
        value.is_ascii() && value.len() == 19 && value.starts_with("2026-10-25 "),
        "data/hora de encerramento fora do pleito: {value}"
    );
    let h: u32 = value[11..13].parse()?;
    let m: u32 = value[14..16].parse()?;
    let s: u32 = value[17..19].parse()?;
    ensure!(
        &value[13..14] == ":" && &value[16..17] == ":" && h < 24 && m < 60 && s < 60,
        "hora inválida: {value}"
    );
    Ok(Some(h * 3600 + m * 60 + s))
}

fn context(row: &ByteRecord) -> Vec<Vec<u8>> {
    // Contexto do cargo/seção: campos repetidos devem concordar em TODAS as linhas.
    [
        21, 22, 23, 24, 25, 26, 15, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44,
    ]
    .iter()
    .map(|i| row[*i].to_vec())
    .collect()
}

fn ingest<R: Read>(
    source: R,
    uf: &str,
    sections: &mut HashMap<String, Section>,
    records: &mut u64,
    excluded: &mut BTreeMap<String, u64>,
) -> Result<()> {
    let max_records = tsepack::limits::get("MAX_CSV_RECORDS")?;
    let max_field = tsepack::limits::get("MAX_FIELD_BYTES")? as usize;
    let max_sections = tsepack::limits::get("MAX_BWEB_OCCURRENCE_KEYS")? as usize;
    let mut file_records = 0;
    let mut reader = ReaderBuilder::new().delimiter(b';').from_reader(source);
    let header = reader.byte_headers()?;
    ensure!(
        header.len() == BWEB_HEADER.len()
            && header
                .iter()
                .zip(BWEB_HEADER)
                .all(|(actual, expected)| actual == expected.as_bytes()),
        "cabeçalho desconhecido: reprovado"
    );
    let mut row = ByteRecord::new();
    while reader.read_byte_record(&mut row)? {
        *records += 1;
        file_records += 1;
        ensure!(file_records <= max_records, "MAX_CSV_RECORDS excedido");
        ensure!(
            row.len() == BWEB_HEADER.len(),
            "largura de registro inválida"
        );
        ensure!(
            row.iter().all(|field| field.len() <= max_field),
            "MAX_FIELD_BYTES excedido"
        );
        ensure!(
            ascii(&row, 2)? == "2026" && ascii(&row, 7)? == "2" && ascii(&row, 10)? == uf,
            "ano/turno/UF divergente"
        );
        let cargo = ascii(&row, 16)?;
        if cargo != "1" {
            *excluded.entry(cargo.to_owned()).or_default() += 1;
            continue;
        }
        for index in [2, 5, 7, 8, 11, 13, 14, 16, 29] {
            ensure!(
                !row[index].is_empty() && row[index].iter().all(u8::is_ascii_digit),
                "identificador não numérico em {}",
                BWEB_HEADER[index]
            );
        }
        ensure!(
            ascii(&row, 5)? == "3221" && ascii(&row, 8)? == "6258",
            "pleito/eleição presidencial divergente"
        );
        let candidate = ascii(&row, 29)?.to_owned();
        let category = ascii(&row, 27)?;
        ensure!(
            matches!(
                (candidate.as_str(), category),
                ("13" | "22", "1") | ("95", "2") | ("96", "3")
            ),
            "votável/categoria desconhecido: {candidate}/{category}"
        );
        let key = [2, 5, 8, 7, 10, 11, 13, 14, 16]
            .iter()
            .map(|i| ascii(&row, *i))
            .collect::<Result<Vec<_>>>()?
            .join("/");
        ensure!(
            sections.contains_key(&key) || sections.len() < max_sections,
            "MAX_BWEB_OCCURRENCE_KEYS excedido"
        );
        let ctx = context(&row);
        let turnout = integer(&row, 23)?;
        ensure!(
            integer(&row, 22)? == turnout + integer(&row, 24)?,
            "aptos != comparecimento + abstenções em {key}"
        );
        let biometric = integer(&row, 41)?;
        ensure!(biometric <= turnout, "biometria > comparecimento em {key}");
        let close_seconds = closing(ascii(&row, 40)?)?;
        let section = sections.entry(key.clone()).or_insert_with(|| Section {
            context: ctx.clone(),
            turnout,
            biometric,
            close_seconds,
            uf: uf.to_owned(),
            municipality: ascii(&row, 11).unwrap().to_owned(),
            ..Section::default()
        });
        ensure!(
            section.context == ctx,
            "contexto repetido divergente em {key}"
        );
        ensure!(
            !section.votes.contains_key(&candidate),
            "ocorrência duplicada em {key}/{candidate}; sem deduplicação"
        );
        section.votes.insert(candidate, integer(&row, 31)?);
    }
    Ok(())
}

fn pearson(x: &[f64], y: &[f64]) -> Option<f64> {
    if x.len() < 2 || x.len() != y.len() {
        return None;
    }
    let mx = x.iter().sum::<f64>() / x.len() as f64;
    let my = y.iter().sum::<f64>() / y.len() as f64;
    let (mut xy, mut xx, mut yy) = (0., 0., 0.);
    for (a, b) in x.iter().zip(y) {
        xy += (a - mx) * (b - my);
        xx += (a - mx).powi(2);
        yy += (b - my).powi(2);
    }
    if xx == 0. || yy == 0. {
        None
    } else {
        Some(xy / (xx * yy).sqrt())
    }
}

fn ranks(values: &[f64]) -> Vec<f64> {
    let mut indices: Vec<usize> = (0..values.len()).collect();
    indices.sort_by(|a, b| values[*a].total_cmp(&values[*b]));
    let mut out = vec![0.; values.len()];
    let mut start = 0;
    while start < indices.len() {
        let mut end = start + 1;
        while end < indices.len() && values[indices[end]] == values[indices[start]] {
            end += 1;
        }
        let rank = (start + end - 1) as f64 / 2. + 1.;
        for idx in &indices[start..end] {
            out[*idx] = rank;
        }
        start = end;
    }
    out
}

fn extremes_add(out: &mut Extremes, lula: u64, flavio: u64) {
    let valid = lula + flavio;
    if valid == 0 {
        out.no_valid_votes += 1;
        return;
    }
    if lula == valid {
        out.unanimity_13 += 1;
    }
    if flavio == valid {
        out.unanimity_22 += 1;
    }
    if lula * 10 > valid * 9 {
        out.above_90_13 += 1;
    }
    if flavio * 10 > valid * 9 {
        out.above_90_22 += 1;
    }
    if lula * 10 >= valid * 9 {
        out.at_least_90_13 += 1;
    }
    if flavio * 10 >= valid * 9 {
        out.at_least_90_22 += 1;
    }
    let band = match valid {
        1..=10 => "1-10",
        11..=50 => "11-50",
        51..=100 => "51-100",
        101..=200 => "101-200",
        201..=400 => "201-400",
        _ => ">400",
    };
    *out.valid_votes_histogram
        .entry(band.to_owned())
        .or_default() += 1;
}

fn report(
    inputs: Vec<Input>,
    sections: &HashMap<String, Section>,
    records: u64,
    excluded: BTreeMap<String, u64>,
) -> Result<Report> {
    ensure!(
        !sections.is_empty(),
        "nenhuma seção presidencial; auditoria vazia reprovada"
    );
    let mut out = Report {
        format_version: 1, scope: "Presidente, 2026, segundo turno, CD_PLEITO=3221, CD_ELEICAO=6258; cobertura dada pelos membros listados",
        time_policy: "DT_ENCERRAMENTO lexical, sem ajuste de fuso. Cortes exatos em segundos: <=17:00:00; (17:00:00,17:15:59]; [17:16:00,18:59:59]; [19:00:00,23:59:59]. Não representa horário de cada voto.",
        source_members: inputs, records_all_cargos: records, excluded_records_by_cargo: excluded,
        presidential: Totals::default(), by_uf: BTreeMap::new(), raw_clock_windows: BTreeMap::new(), raw_after_19_by_uf: BTreeMap::new(),
        raw_minute_windows: BTreeMap::new(), raw_strict_after_19: Totals::default(),
        extremes: Extremes::default(), extremes_by_uf: BTreeMap::new(), biometric_correlation: Correlation {
            n: 0, pearson: None, spearman: None, method: "Seções com comparecimento>0 e válidos>0; x=QT_ELEI_BIOM_SEM_HABILITACAO/comparecimento; y=votos13/(votos13+votos22). Sem pesos; Spearman com postos médios nos empates; sem p-valor." },
        within_municipality_pearson: None, benford_first_digit_counts_13: [0; 9], benford_first_digit_counts_22: [0; 9],
        benford_expected_probabilities: std::array::from_fn(|i| (1. + 1./(i+1) as f64).log10()),
        benford_scope: "Primeiro dígito dos votos nominais POSITIVOS por candidato/seção; zeros excluídos da distribuição de dígitos. Descrição, sem classificação de fraude.",
        closing_missing: 0, normalized_closing: None, limitations: vec!["Sem hipótese causal ou conclusão de fraude/autenticidade.", "Fuso de DT_ENCERRAMENTO não estabelecido pelo dicionário: recorte lexical não equivale a corte nacional BRT.", "Agregação de seção não identifica o candidato votado por eleitores sem habilitação biométrica.", "Sem logs processados, não há contagem de votos efetivamente depositados após 17h.", "Ruralidade/coação não podem ser inferidas destes percentuais; classificação geográfica exige fonte própria.", "Correlação descritiva não reproduz estudo original sem base, filtros e código dele.", "Assinaturas de BU/RDV/JWS e cadeia de certificados não verificadas neste relatório."],
    };
    let (mut x, mut y, mut groups) = (Vec::new(), Vec::new(), Vec::new());
    let mut municipal: BTreeMap<String, (f64, f64, usize)> = BTreeMap::new();
    // Ordem estável torna o relatório reproduzível inclusive nos floats.
    let mut ordered: Vec<_> = sections.iter().collect();
    ordered.sort_by(|a, b| a.0.cmp(b.0));
    for (key, section) in ordered {
        ensure!(
            section.votes.values().sum::<u64>() == section.turnout,
            "soma votos != comparecimento em {key}"
        );
        out.presidential.add(section);
        out.by_uf
            .entry(section.uf.clone())
            .or_default()
            .add(section);
        let lula = *section.votes.get("13").unwrap_or(&0);
        let flavio = *section.votes.get("22").unwrap_or(&0);
        extremes_add(&mut out.extremes, lula, flavio);
        extremes_add(
            out.extremes_by_uf.entry(section.uf.clone()).or_default(),
            lula,
            flavio,
        );
        for (v, bins) in [
            (lula, &mut out.benford_first_digit_counts_13),
            (flavio, &mut out.benford_first_digit_counts_22),
        ] {
            if v > 0 {
                let mut d = v;
                while d >= 10 {
                    d /= 10;
                }
                bins[d as usize - 1] += 1;
            }
        }
        if section.turnout > 0 && lula + flavio > 0 {
            let a = section.biometric as f64 / section.turnout as f64;
            let b = lula as f64 / (lula + flavio) as f64;
            let group = format!("{}/{}", section.uf, section.municipality);
            let stats = municipal.entry(group.clone()).or_default();
            stats.0 += a;
            stats.1 += b;
            stats.2 += 1;
            x.push(a);
            y.push(b);
            groups.push(group);
        }
        if let Some(seconds) = section.close_seconds {
            let window = if seconds <= 17 * 3600 {
                "ate_17h00m00s"
            } else if seconds < 17 * 3600 + 16 * 60 {
                "apos_17h00m00s_ate_17h15m59s"
            } else if seconds < 19 * 3600 {
                "17h16m00s_ate_18h59m59s"
            } else {
                "desde_19h00m00s"
            };
            out.raw_clock_windows
                .entry(window.to_owned())
                .or_default()
                .add(section);
            let minute_window = if seconds < 17 * 3600 + 60 {
                "ate_17h00m59s"
            } else if seconds < 17 * 3600 + 16 * 60 {
                "17h01m00s_ate_17h15m59s"
            } else if seconds < 19 * 3600 {
                "17h16m00s_ate_18h59m59s"
            } else {
                "desde_19h00m00s"
            };
            out.raw_minute_windows
                .entry(minute_window.to_owned())
                .or_default()
                .add(section);
            if seconds > 19 * 3600 {
                out.raw_strict_after_19.add(section);
            }
            if seconds >= 19 * 3600 {
                out.raw_after_19_by_uf
                    .entry(section.uf.clone())
                    .or_default()
                    .add(section);
            }
        } else {
            out.closing_missing += 1;
        }
    }
    out.biometric_correlation.n = x.len();
    out.biometric_correlation.pearson = pearson(&x, &y);
    out.biometric_correlation.spearman = pearson(&ranks(&x), &ranks(&y));
    let mut residual_x = Vec::new();
    let mut residual_y = Vec::new();
    for (i, group) in groups.iter().enumerate() {
        let (sx, sy, n) = municipal[group];
        residual_x.push(x[i] - sx / n as f64);
        residual_y.push(y[i] - sy / n as f64);
    }
    out.within_municipality_pearson = pearson(&residual_x, &residual_y);
    Ok(out)
}

fn write_sections(path: &std::path::Path, sections: &HashMap<String, Section>) -> Result<()> {
    publish_file(path, |file| {
        let mut writer = csv::Writer::from_writer(file);
        writer.write_record([
            "ANO_ELEICAO",
            "CD_PLEITO",
            "CD_ELEICAO",
            "NR_TURNO",
            "SG_UF",
            "CD_MUNICIPIO",
            "NR_ZONA",
            "NR_SECAO",
            "CD_CARGO_PERGUNTA",
            "NR_LOCAL_VOTACAO",
            "NR_URNA_EFETIVADA",
            "DT_ENCERRAMENTO",
            "CD_TIPO_URNA",
            "QT_APTOS",
            "QT_COMPARECIMENTO",
            "QT_ABSTENCOES",
            "QT_ELEI_BIOM_SEM_HABILITACAO",
            "VOTOS_13",
            "VOTOS_22",
            "VOTOS_BRANCOS",
            "VOTOS_NULOS",
        ])?;
        let mut ordered: Vec<_> = sections.iter().collect();
        ordered.sort_by(|a, b| a.0.cmp(b.0));
        for (key, section) in ordered {
            let mut row: Vec<String> = key.split('/').map(str::to_owned).collect();
            for index in [6, 7, 15, 4] {
                row.push(std::str::from_utf8(&section.context[index])?.to_owned());
            }
            row.extend([
                std::str::from_utf8(&section.context[1])?.to_owned(),
                section.turnout.to_string(),
                std::str::from_utf8(&section.context[3])?.to_owned(),
                section.biometric.to_string(),
            ]);
            for candidate in ["13", "22", "95", "96"] {
                row.push(section.votes.get(candidate).unwrap_or(&0).to_string());
            }
            writer.write_record(row)?;
        }
        writer.flush()?;
        Ok(())
    })
}

fn run(args: Args) -> Result<()> {
    ensure!(
        !args.output.exists(),
        "saída já existe; preservar relatório anterior"
    );
    if let Some(path) = &args.sections_output {
        ensure!(
            !path.exists() && path != &args.output,
            "saída de seções existente ou igual ao relatório"
        );
    }
    let manifest: Manifest = serde_json::from_reader(std::fs::File::open(args.manifest)?)?;
    ensure!(
        manifest.format_version == 1,
        "versão de entrada desconhecida"
    );
    let mut ufs = std::collections::BTreeSet::new();
    let (mut sections, mut records, mut excluded) = (HashMap::new(), 0, BTreeMap::new());
    for input in &manifest.inputs {
        ensure!(
            ufs.insert(input.uf.clone()),
            "UF repetida no manifesto; snapshot ambíguo"
        );
        let bytes = std::fs::metadata(&input.path)?.len();
        ensure!(
            bytes <= tsepack::limits::get("MAX_ZIP_MEMBER_BYTES")?,
            "MAX_ZIP_MEMBER_BYTES excedido"
        );
        ensure!(
            bytes == input.bytes,
            "tamanho divergente: {}",
            input.path.display()
        );
        let mut source = HashingRead {
            inner: std::fs::File::open(&input.path)?,
            hash: Sha256::new(),
            bytes: 0,
        };
        ingest(
            &mut source,
            &input.uf,
            &mut sections,
            &mut records,
            &mut excluded,
        )
        .with_context(|| format!("membro {}", input.member))?;
        ensure!(
            source.bytes == input.bytes && hex::encode(source.hash.finalize()) == input.sha256,
            "SHA-256 divergente: {}",
            input.path.display()
        );
    }
    let mut result = report(manifest.inputs, &sections, records, excluded)?;
    if let Some(path) = &args.time_policy {
        let bytes = std::fs::read(path)?;
        let policy: TimePolicy = serde_json::from_slice(&bytes)?;
        let mut normalized = normalize_closing(&policy, &sections)?;
        normalized.policy_sha256 = hex::encode(Sha256::digest(&bytes));
        result.normalized_closing = Some(normalized);
    }
    if let Some(path) = &args.sections_output {
        write_sections(path, &sections)?;
    }
    publish_file(&args.output, |dest| {
        serde_json::to_writer_pretty(dest, &result)?;
        Ok(())
    })?;
    Ok(())
}

fn main() -> Result<()> {
    run(Args::parse())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn failed_publication_keeps_partial_without_final_file() {
        use std::io::Write;
        let temp = tempfile::tempdir().unwrap();
        let path = temp.path().join("failed.csv");
        assert!(publish_file(&path, |file| {
            file.write_all(&include_bytes!("../../tests/fixtures/audit-2026/synthetic.csv")[..7])?;
            anyhow::bail!("falha deliberada de teste")
        })
        .is_err());
        assert!(!path.exists());
        assert_eq!(std::fs::read_dir(temp.path()).unwrap().count(), 1);
    }

    #[test]
    fn section_export_preserves_keys_and_counts_once() {
        let mut sections = HashMap::new();
        ingest(
            &include_bytes!("../../tests/fixtures/audit-2026/synthetic.csv")[..],
            "MT",
            &mut sections,
            &mut 0,
            &mut BTreeMap::new(),
        )
        .unwrap();
        let temp = tempfile::tempdir().unwrap();
        let path = temp.path().join("sections.csv");
        write_sections(&path, &sections).unwrap();
        let mut reader = csv::Reader::from_path(&path).unwrap();
        let header = reader.headers().unwrap().clone();
        let turnout = header
            .iter()
            .position(|h| h == "QT_COMPARECIMENTO")
            .unwrap();
        let records = reader.records().collect::<Result<Vec<_>, _>>().unwrap();
        assert_eq!(records.len(), 2);
        assert_eq!(
            records
                .iter()
                .map(|r| r[turnout].parse::<u64>().unwrap())
                .sum::<u64>(),
            103
        );
        let before = std::fs::read(&path).unwrap();
        assert!(write_sections(&path, &sections).is_err());
        assert_eq!(std::fs::read(path).unwrap(), before);
    }

    #[test]
    fn nominal_clock_uses_municipality_override_and_preserves_totals() {
        let mut sections = HashMap::new();
        ingest(
            &include_bytes!("../../tests/fixtures/audit-2026/synthetic.csv")[..],
            "MT",
            &mut sections,
            &mut 0,
            &mut BTreeMap::new(),
        )
        .unwrap();
        let mut policy: TimePolicy = serde_json::from_slice(include_bytes!(
            "../../tests/fixtures/audit-2026/log-policy-synthetic.json"
        ))
        .unwrap();
        let result = normalize_closing(&policy, &sections).unwrap();
        assert_eq!(result.windows["apos_17h00m00s"].turnout, 103);
        assert_eq!(result.windows["apos_19h00m00s"].turnout, 3);
        policy
            .municipality_overrides
            .insert("MT/00001".to_owned(), 0);
        let result = normalize_closing(&policy, &sections).unwrap();
        assert_eq!(result.windows["ate_17h00m00s"].turnout, 100);
        assert_eq!(result.windows["desde_19h00m00s"].turnout, 3);
        assert!(!result.windows.contains_key("apos_19h00m00s"));
        policy.municipality_overrides.clear();
        policy.brt_shift_seconds_by_uf.clear();
        assert!(normalize_closing(&policy, &sections).is_err());
    }

    #[test]
    fn out_of_scope_negative_cargo_is_counted_without_losing_presidential_rows() {
        let fixture = include_bytes!("../../tests/fixtures/audit-2026/synthetic.csv");
        let mut reader = ReaderBuilder::new()
            .delimiter(b';')
            .from_reader(&fixture[..]);
        let header = reader.byte_headers().unwrap().clone();
        let rows = reader
            .byte_records()
            .collect::<Result<Vec<_>, _>>()
            .unwrap();
        let mut out = csv::WriterBuilder::new()
            .delimiter(b';')
            .from_writer(Vec::new());
        out.write_byte_record(&header).unwrap();
        for row in &rows {
            out.write_byte_record(row).unwrap();
        }
        let mut fields: Vec<Vec<u8>> = rows[0].iter().map(<[u8]>::to_vec).collect();
        fields[16] = b"-1".to_vec();
        fields[29] = b"-1".to_vec();
        out.write_record(fields).unwrap();
        let bytes = out.into_inner().unwrap();
        let (mut sections, mut records, mut excluded) = (HashMap::new(), 0, BTreeMap::new());
        ingest(&bytes[..], "MT", &mut sections, &mut records, &mut excluded).unwrap();
        assert_eq!(records, 5);
        assert_eq!(sections.len(), 2);
        assert_eq!(excluded.get("-1"), Some(&1));
    }

    #[test]
    fn exact_boundaries_and_bad_date() {
        assert_eq!(closing("2026-10-25 17:00:00").unwrap(), Some(61200));
        assert_eq!(closing("2026-10-25 19:00:00").unwrap(), Some(68400));
        assert!(closing("2026-10-04 17:00:00").is_err());
        assert!(closing("2026-10-25 25:00:00").is_err());
        assert_eq!(closing("#NULO#").unwrap(), None);
    }

    #[test]
    fn strict_extremes_and_empty_denominator() {
        let mut e = Extremes::default();
        extremes_add(&mut e, 90, 10);
        extremes_add(&mut e, 91, 9);
        extremes_add(&mut e, 3, 0);
        extremes_add(&mut e, 0, 0);
        assert_eq!(e.above_90_13, 2);
        assert_eq!(e.unanimity_13, 1);
        assert_eq!(e.at_least_90_13, 3);
        assert_eq!(e.no_valid_votes, 1);
    }

    #[test]
    fn correlations_and_ties() {
        assert_eq!(ranks(&[3., 1., 1., 5.]), vec![3., 1.5, 1.5, 4.]);
        assert!((pearson(&[1., 2., 3.], &[3., 2., 1.]).unwrap() + 1.).abs() < 1e-12);
        assert_eq!(pearson(&[1., 1.], &[1., 2.]), None);
    }
}
