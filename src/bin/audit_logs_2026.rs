//! Contagens de eventos de log com hash, cobertura e confronto por seção.
use anyhow::{bail, ensure, Context, Result};
use clap::Parser;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet, HashSet};
use std::io::{BufRead, BufReader, Read};
use std::path::PathBuf;
#[path = "../audit_io.rs"]
mod audit_io;
use audit_io::{publish_file, HashingRead};
const SECTION_ASSIGNMENT: &str = "GAP municipality/zone/section inside each text body; official outer filename is expected key. Unknown context blocks reconciliation; other keys counted separately.";

fn bounded_line<R: BufRead>(reader: &mut R, out: &mut Vec<u8>, limit: usize) -> Result<usize> {
    out.clear();
    loop {
        let available = reader.fill_buf()?;
        if available.is_empty() {
            return Ok(out.len());
        }
        let end = available
            .iter()
            .position(|byte| *byte == b'\n')
            .map(|i| i + 1);
        let take = end.unwrap_or(available.len());
        ensure!(
            out.len() + take <= limit,
            "linha excede limite centralizado"
        );
        out.extend_from_slice(&available[..take]);
        reader.consume(take);
        if end.is_some() {
            return Ok(out.len());
        }
    }
}

#[derive(Parser)]
struct Args {
    #[arg(long)]
    output: PathBuf,
    #[arg(long)]
    sections_output: Option<PathBuf>,
    #[arg(long, conflicts_with = "sections_output")]
    aggregate_manifest: Option<PathBuf>,
}

#[derive(Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
enum Frame {
    Log {
        format_version: u32,
        section_key: String,
        uf: String,
        expected_turnout: Option<u64>,
        brt_shift_seconds: Option<i32>,
        source_zip_url: String,
        source_zip_sha256: String,
        source_member: String,
        nested_member: String,
        bytes: u64,
        sha256: String,
    },
    End {
        format_version: u32,
        files: u64,
        expected_sections: u64,
        expected_section_keys_sha256: String,
        policy_sha256: String,
        sections_export_sha256: String,
    },
}

#[derive(Default, Clone, Serialize, Deserialize, PartialEq, Debug)]
#[serde(deny_unknown_fields)]
struct Events {
    completed_electors: u64,
    president_confirmations: u64,
    completed_after_17_brt: u64,
    president_after_17_brt: u64,
    completed_after_19_brt: u64,
    president_after_19_brt: u64,
}

impl Events {
    fn add(&mut self, other: &Self) {
        self.completed_electors += other.completed_electors;
        self.president_confirmations += other.president_confirmations;
        self.completed_after_17_brt += other.completed_after_17_brt;
        self.president_after_17_brt += other.president_after_17_brt;
        self.completed_after_19_brt += other.completed_after_19_brt;
        self.president_after_19_brt += other.president_after_19_brt;
    }
}

#[derive(Serialize)]
struct SectionResult {
    key: String,
    uf: String,
    expected_turnout: Option<u64>,
    brt_shift_seconds: Option<i32>,
    files: u64,
    duplicate_body_files: u64,
    duplicate_relevant_lines: u64,
    malformed_lines: u64,
    unknown_context_relevant_events: u64,
    matched: bool,
    events: Events,
}

struct Group {
    result: SectionResult,
    seen_events: HashSet<Vec<u8>>,
    seen_files: HashSet<String>,
}

#[derive(Serialize)]
struct Summary {
    format_version: u32,
    success: bool,
    scope: &'static str,
    timestamp_policy: &'static str,
    section_assignment: &'static str,
    ufs: BTreeSet<String>,
    frames: u64,
    lines_all_dates_apps: u64,
    blank_lines: u64,
    sections: u64,
    expected_sections: u64,
    coverage_complete: bool,
    expected_section_keys_sha256: String,
    parsed_section_keys_sha256: String,
    matched_sections: u64,
    mismatched_sections: u64,
    duplicate_body_files: u64,
    duplicate_relevant_lines: u64,
    malformed_lines: u64,
    malformed_line_examples: Vec<serde_json::Value>,
    unknown_context_relevant_events: u64,
    other_context_relevant_events: BTreeMap<String, u64>,
    other_dates_relevant_events: BTreeMap<String, u64>,
    all_parsed_events: Events,
    events_in_matched_sections: Events,
    mismatch_examples: Vec<SectionResult>,
    wire_sha256: String,
    wire_bytes: u64,
    policy_sha256: String,
    sections_export_sha256: String,
    limitations: Vec<&'static str>,
}

fn clock_seconds(timestamp: &[u8]) -> Result<i32> {
    ensure!(
        timestamp.len() == 19
            && timestamp[2] == b'/'
            && timestamp[5] == b'/'
            && timestamp[10] == b' '
            && timestamp[13] == b':'
            && timestamp[16] == b':',
        "timestamp fora do leiaute"
    );
    for i in [0, 1, 3, 4, 6, 7, 8, 9, 11, 12, 14, 15, 17, 18] {
        ensure!(timestamp[i].is_ascii_digit(), "timestamp não numérico");
    }
    let hour = std::str::from_utf8(&timestamp[11..13])?.parse::<i32>()?;
    let minute = std::str::from_utf8(&timestamp[14..16])?.parse::<i32>()?;
    let second = std::str::from_utf8(&timestamp[17..19])?.parse::<i32>()?;
    ensure!(
        hour < 24 && minute < 60 && second < 60,
        "hora inválida no log"
    );
    Ok(hour * 3600 + minute * 60 + second)
}

fn digest_valid(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|v| v.is_ascii_digit() || (b'a'..=b'f').contains(&v))
}

fn finish_group(mut group: Group, sections: &mut Vec<SectionResult>) {
    let result = &mut group.result;
    result.matched = result.expected_turnout == Some(result.events.completed_electors)
        && result.duplicate_relevant_lines == 0
        && result.malformed_lines == 0
        && result.unknown_context_relevant_events == 0
        && (result.uf == "ZZ" || result.brt_shift_seconds.is_some());
    sections.push(group.result);
}

fn parse_stream<R: BufRead>(reader: &mut R) -> Result<(Summary, Vec<SectionResult>)> {
    let max_line = tsepack::limits::get("MAX_RECORD_BYTES")? as usize;
    let max_events = tsepack::limits::get("MAX_AUDIT_LOG_EVENTS_PER_SECTION")? as usize;
    let max_sections = tsepack::limits::get("MAX_BWEB_OCCURRENCE_KEYS")? as usize;
    let max_lines = tsepack::limits::get("MAX_AUDIT_LOG_LINES")?;
    let max_member = tsepack::limits::get("MAX_ZIP_MEMBER_BYTES")?;
    let mut summary = Summary {
        format_version: 1, success: false,
        scope: "Eventos VOTA em 25/10/2026; confirmações para Presidente e eventos de eleitor computado são métricas distintas. Cobertura limitada às UFs/arquivos efetivamente importados.",
        timestamp_policy: "Relógio registrado + deslocamento nominal para Brasília fornecido pela política documentada; cortes estritos >17:00:00 e >19:00:00. ZZ não entra nas métricas BRT.",
        section_assignment: SECTION_ASSIGNMENT,
        ufs: BTreeSet::new(), frames: 0, lines_all_dates_apps: 0, blank_lines: 0, sections: 0,
        expected_sections: 0, coverage_complete: false, expected_section_keys_sha256: String::new(), parsed_section_keys_sha256: String::new(),
        matched_sections: 0, mismatched_sections: 0, duplicate_body_files: 0, duplicate_relevant_lines: 0,
        malformed_lines: 0, malformed_line_examples: Vec::new(),
        unknown_context_relevant_events: 0, other_context_relevant_events: BTreeMap::new(),
        other_dates_relevant_events: BTreeMap::new(), all_parsed_events: Events::default(),
        events_in_matched_sections: Events::default(), mismatch_examples: Vec::new(),
        wire_sha256: String::new(), wire_bytes: 0, policy_sha256: String::new(), sections_export_sha256: String::new(),
        limitations: vec!["Autenticadores de linhas, assinaturas e cadeia de certificados não verificados.", "Relógios nominalmente normalizados; não prova o instante físico de cada voto.", "O log não revela candidato escolhido.", "Contingências, rotação, duplicação ou cobertura incompleta que impeçam conciliação bloqueiam a classificação de sucesso.", "Um resultado parcial por UF não é contagem nacional."],
    };
    let mut sections = Vec::new();
    let mut current: Option<Group> = None;
    let mut header = Vec::new();
    loop {
        ensure!(
            bounded_line(reader, &mut header, max_line)? > 0,
            "fluxo interrompido sem marcador final"
        );
        let frame: Frame =
            serde_json::from_slice(&header).context("cabeçalho de frame inválido")?;
        match frame {
            Frame::End {
                format_version,
                files,
                expected_sections,
                expected_section_keys_sha256,
                policy_sha256,
                sections_export_sha256,
            } => {
                ensure!(
                    format_version == 1 && files == summary.frames && files > 0,
                    "final/contagem de frames inválidos"
                );
                ensure!(
                    digest_valid(&policy_sha256) && digest_valid(&sections_export_sha256),
                    "hash de política/exportação inválido"
                );
                summary.policy_sha256 = policy_sha256;
                summary.sections_export_sha256 = sections_export_sha256;
                ensure!(
                    digest_valid(&expected_section_keys_sha256),
                    "hash do conjunto esperado inválido"
                );
                summary.expected_sections = expected_sections;
                summary.expected_section_keys_sha256 = expected_section_keys_sha256;
                let mut tail = [0];
                ensure!(reader.read(&mut tail)? == 0, "bytes após o marcador final");
                break;
            }
            Frame::Log {
                format_version,
                section_key,
                uf,
                expected_turnout,
                brt_shift_seconds,
                source_zip_url,
                source_zip_sha256,
                source_member,
                nested_member,
                bytes,
                sha256,
            } => {
                ensure!(
                    format_version == 1
                        && digest_valid(&sha256)
                        && digest_valid(&source_zip_sha256),
                    "versão/hash de frame inválido"
                );
                ensure!(bytes <= max_member, "membro de log excede limite");
                ensure!(
                    source_zip_url.starts_with("https://cdn.tse.jus.br/")
                        && !source_member.is_empty()
                        && !nested_member.is_empty(),
                    "procedência do frame incompleta"
                );
                ensure!(
                    uf.len() == 2 && section_key.starts_with(&format!("{uf}/")),
                    "UF/chave de frame inválida"
                );
                ensure!(
                    brt_shift_seconds.is_none_or(|v| matches!(v, -3600 | 0 | 3600 | 7200)),
                    "deslocamento de relógio fora da política"
                );
                if current.as_ref().is_none_or(|g| g.result.key != section_key) {
                    if let Some(previous) = current.take() {
                        ensure!(
                            previous.result.key < section_key,
                            "frames de seções fora de ordem ou seção repetida"
                        );
                        finish_group(previous, &mut sections);
                    }
                    ensure!(
                        sections.len() < max_sections,
                        "limite de seções de log excedido"
                    );
                    current = Some(Group {
                        result: SectionResult {
                            key: section_key,
                            uf: uf.clone(),
                            expected_turnout,
                            brt_shift_seconds,
                            files: 0,
                            duplicate_body_files: 0,
                            duplicate_relevant_lines: 0,
                            malformed_lines: 0,
                            unknown_context_relevant_events: 0,
                            matched: false,
                            events: Events::default(),
                        },
                        seen_events: HashSet::new(),
                        seen_files: HashSet::new(),
                    });
                }
                let group = current.as_mut().unwrap();
                ensure!(
                    group.result.expected_turnout == expected_turnout
                        && group.result.brt_shift_seconds == brt_shift_seconds,
                    "contexto de seção divergente entre frames"
                );
                if !group.seen_files.insert(sha256.clone()) {
                    group.result.duplicate_body_files += 1;
                }
                group.result.files += 1;
                summary.frames += 1;
                summary.ufs.insert(uf);
                let mut hashed = HashingRead {
                    inner: reader.take(bytes),
                    hash: Sha256::new(),
                    bytes: 0,
                };
                {
                    let mut lines = BufReader::new(&mut hashed);
                    let mut line = Vec::new();
                    let mut body_line = 0u64;
                    let expected_geo: Vec<u32> = group
                        .result
                        .key
                        .split('/')
                        .skip(1)
                        .map(str::parse)
                        .collect::<Result<_, _>>()?;
                    ensure!(expected_geo.len() == 3, "chave geográfica incompleta");
                    let mut active_geo = [None; 3];
                    while bounded_line(&mut lines, &mut line, max_line)? > 0 {
                        body_line += 1;
                        summary.lines_all_dates_apps += 1;
                        ensure!(
                            summary.lines_all_dates_apps <= max_lines,
                            "limite de linhas de log excedido"
                        );
                        while matches!(line.last(), Some(b'\n' | b'\r')) {
                            line.pop();
                        }
                        if line.is_empty() {
                            summary.blank_lines += 1;
                            continue;
                        }
                        let parts: Vec<_> = line.split(|v| *v == b'\t').collect();
                        let parsed_time = if parts.len() < 6 {
                            None
                        } else {
                            clock_seconds(parts[0]).ok()
                        };
                        let Some(seconds) = parsed_time else {
                            group.result.malformed_lines += 1;
                            if summary.malformed_line_examples.len()
                                < tsepack::limits::get("MAX_AUDIT_LOG_EVIDENCE")? as usize
                            {
                                summary.malformed_line_examples.push(serde_json::json!({
                                    "section_key": group.result.key, "source_member": source_member,
                                    "nested_member": nested_member, "body_line": body_line,
                                    "line_bytes_without_eol": line.len(), "line_sha256_without_eol": hex::encode(Sha256::digest(&line)),
                                    "reason": "campos/timestamp fora do leiaute; linha não interpretada, seção impedida de conciliar"}));
                            }
                            continue;
                        };
                        let message = parts[4..parts.len() - 1].join(&b'\t');
                        if parts[3] == b"GAP" {
                            for (index, prefix) in [
                                b"Munic\xedpio: ".as_slice(),
                                b"Zona Eleitoral: ",
                                b"Se\xe7\xe3o Eleitoral: ",
                            ]
                            .iter()
                            .enumerate()
                            {
                                if let Some(value) = message.strip_prefix(*prefix) {
                                    active_geo[index] = std::str::from_utf8(value)
                                        .ok()
                                        .and_then(|s| s.trim().parse::<u32>().ok());
                                    for item in active_geo.iter_mut().skip(index + 1) {
                                        *item = None;
                                    }
                                }
                            }
                        }
                        let president = message == b"Voto confirmado para [Presidente]";
                        let completed = message == b"O voto do eleitor foi computado";
                        if parts[3] != b"VOTA" || (!president && !completed) {
                            continue;
                        }
                        if &parts[0][..10] != b"25/10/2026" {
                            *summary
                                .other_dates_relevant_events
                                .entry(std::str::from_utf8(&parts[0][..10])?.to_owned())
                                .or_default() += 1;
                            continue;
                        }
                        if active_geo.iter().any(Option::is_none) {
                            group.result.unknown_context_relevant_events += 1;
                            continue;
                        }
                        if active_geo
                            .iter()
                            .zip(&expected_geo)
                            .any(|(actual, expected)| *actual != Some(*expected))
                        {
                            let key = format!(
                                "{}/{:05}/{:04}/{:04}",
                                group.result.uf,
                                active_geo[0].unwrap(),
                                active_geo[1].unwrap(),
                                active_geo[2].unwrap()
                            );
                            *summary
                                .other_context_relevant_events
                                .entry(key)
                                .or_default() += 1;
                            continue;
                        }
                        if !group.seen_events.insert(line.clone()) {
                            group.result.duplicate_relevant_lines += 1;
                        }
                        ensure!(
                            group.seen_events.len() <= max_events,
                            "limite de eventos por seção excedido"
                        );
                        let events = &mut group.result.events;
                        if president {
                            events.president_confirmations += 1;
                        }
                        if completed {
                            events.completed_electors += 1;
                        }
                        if group.result.uf != "ZZ" {
                            if let Some(shift) = group.result.brt_shift_seconds {
                                if seconds + shift > 17 * 3600 {
                                    events.president_after_17_brt += u64::from(president);
                                    events.completed_after_17_brt += u64::from(completed);
                                }
                                if seconds + shift > 19 * 3600 {
                                    events.president_after_19_brt += u64::from(president);
                                    events.completed_after_19_brt += u64::from(completed);
                                }
                            }
                        }
                    }
                }
                ensure!(
                    hashed.bytes == bytes && hex::encode(hashed.hash.finalize()) == sha256,
                    "tamanho/SHA-256 de log divergente"
                );
            }
        }
    }
    if let Some(group) = current {
        finish_group(group, &mut sections);
    }
    for section in &sections {
        summary.sections += 1;
        summary.duplicate_body_files += section.duplicate_body_files;
        summary.malformed_lines += section.malformed_lines;
        summary.unknown_context_relevant_events += section.unknown_context_relevant_events;
        summary.duplicate_relevant_lines += section.duplicate_relevant_lines;
        summary.all_parsed_events.add(&section.events);
        if section.matched {
            summary.matched_sections += 1;
            summary.events_in_matched_sections.add(&section.events);
        } else {
            summary.mismatched_sections += 1;
        }
    }
    let evidence = tsepack::limits::get("MAX_AUDIT_LOG_EVIDENCE")? as usize;
    for section in sections.iter().filter(|s| !s.matched).take(evidence) {
        summary.mismatch_examples.push(SectionResult {
            key: section.key.clone(),
            uf: section.uf.clone(),
            expected_turnout: section.expected_turnout,
            brt_shift_seconds: section.brt_shift_seconds,
            files: section.files,
            duplicate_body_files: section.duplicate_body_files,
            duplicate_relevant_lines: section.duplicate_relevant_lines,
            malformed_lines: section.malformed_lines,
            unknown_context_relevant_events: section.unknown_context_relevant_events,
            matched: false,
            events: section.events.clone(),
        });
    }
    let mut key_hash = Sha256::new();
    for section in &sections {
        key_hash.update(section.key.as_bytes());
        key_hash.update(b"\n");
    }
    summary.parsed_section_keys_sha256 = hex::encode(key_hash.finalize());
    summary.coverage_complete = summary.sections == summary.expected_sections
        && summary.parsed_section_keys_sha256 == summary.expected_section_keys_sha256;
    summary.success =
        summary.sections > 0 && summary.mismatched_sections == 0 && summary.coverage_complete;
    Ok((summary, sections))
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct AggregateInput {
    format_version: u32,
    official: AggregateFile,
    inputs: Vec<AggregateFile>,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct AggregateFile {
    path: PathBuf,
    bytes: u64,
    sha256: String,
}

fn verified_json(input: &AggregateFile) -> Result<serde_json::Value> {
    ensure!(
        input.bytes <= tsepack::limits::get("MAX_ARCHIVE_MANIFEST_BYTES")?,
        "relatório excede limite centralizado"
    );
    let file = std::fs::File::open(&input.path)?;
    let mut reader = HashingRead {
        inner: file,
        hash: Sha256::new(),
        bytes: 0,
    };
    let value = serde_json::from_reader(&mut reader)?;
    ensure!(
        reader.bytes == input.bytes && hex::encode(reader.hash.finalize()) == input.sha256,
        "tamanho/SHA-256 divergente na consolidação: {}",
        input.path.display()
    );
    Ok(value)
}

fn aggregate(manifest: &std::path::Path, output: &std::path::Path) -> Result<()> {
    ensure!(!output.exists(), "saída existente");
    let input: AggregateInput = serde_json::from_reader(std::fs::File::open(manifest)?)?;
    ensure!(
        input.format_version == 1,
        "versão de manifesto desconhecida"
    );
    let official = verified_json(&input.official)?;
    ensure!(
        official["ele"] == "6258" && official["t"] == "2",
        "totalização fora do recorte"
    );
    let installed: u64 = official["s"]["si"]
        .as_str()
        .context("si ausente")?
        .parse()?;
    let turnout: u64 = official["e"]["c"].as_str().context("c ausente")?.parse()?;
    let expected_ufs: BTreeSet<String> =
        "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO ZZ"
            .split_whitespace()
            .map(str::to_owned)
            .collect();
    let mut ufs = BTreeSet::new();
    let mut all = Events::default();
    let mut matched = Events::default();
    let mut sections = 0u64;
    let mut expected_sections = 0u64;
    let mut mismatched = 0u64;
    let mut uf_reports = BTreeMap::new();
    let mut valid = true;
    let mut policy = None;
    let mut export = None;
    for source in &input.inputs {
        let report = verified_json(source)?;
        ensure!(
            report["format_version"] == 1,
            "versão de relatório desconhecida"
        );
        ensure!(
            report["section_assignment"] == SECTION_ASSIGNMENT,
            "relatório sem controle interno de seção compatível"
        );
        let report_ufs: Vec<String> = serde_json::from_value(report["ufs"].clone())?;
        ensure!(
            report_ufs.len() == 1 && expected_ufs.contains(&report_ufs[0]),
            "escopo de UF inválido"
        );
        let uf = &report_ufs[0];
        ensure!(ufs.insert(uf.clone()), "UF duplicada na consolidação");
        let p = report["policy_sha256"]
            .as_str()
            .context("hash de política ausente")?;
        let e = report["sections_export_sha256"]
            .as_str()
            .context("hash de exportação ausente")?;
        ensure!(
            digest_valid(p) && digest_valid(e),
            "hash de política/exportação inválido"
        );
        ensure!(
            policy.as_ref().is_none_or(|v| v == p) && export.as_ref().is_none_or(|v| v == e),
            "políticas ou universos diferentes; não consolidar"
        );
        policy = Some(p.to_owned());
        export = Some(e.to_owned());
        let count = |key: &str| -> Result<u64> {
            report[key]
                .as_u64()
                .with_context(|| format!("contador ausente: {key}"))
        };
        sections += count("sections")?;
        expected_sections += count("expected_sections")?;
        mismatched += count("mismatched_sections")?;
        valid &= report["success"] == true && report["coverage_complete"] == true;
        all.add(&serde_json::from_value(
            report["all_parsed_events"].clone(),
        )?);
        matched.add(&serde_json::from_value(
            report["events_in_matched_sections"].clone(),
        )?);
        uf_reports.insert(uf.clone(), report);
    }
    let national_coverage_complete =
        ufs == expected_ufs && sections == installed && expected_sections == installed;
    let success =
        valid && national_coverage_complete && mismatched == 0 && all.completed_electors == turnout;
    ensure!(
        matched.completed_electors <= turnout,
        "comparecimento conciliado excede universo oficial"
    );
    let unresolved_turnout = turnout - matched.completed_electors;
    let completed_after_17_bounds = serde_json::json!({
        "lower": matched.completed_after_17_brt,
        "upper": matched.completed_after_17_brt + unresolved_turnout,
        "unresolved_turnout": unresolved_turnout,
        "definition": "Intervalo conservador: seções conciliadas contribuem sua contagem; todo o comparecimento restante pode estar antes ou depois do corte. Depende da associação dos pacotes oficiais às seções e da política nominal de relógio. ZZ permanece excluído do corte BRT."});
    let result = serde_json::json!({"format_version": 1, "success": success,
        "scope": "Consolidação de relatórios de logs; diagnóstico enquanto houver falhas ou cobertura incompleta.",
        "national_coverage_complete": national_coverage_complete, "ufs": ufs,
        "missing_ufs": expected_ufs.difference(&ufs).collect::<Vec<_>>(),
        "sections": sections, "expected_sections": expected_sections, "official_installed_sections": installed,
        "official_turnout": turnout, "mismatched_sections": mismatched,
        "all_parsed_events": all, "events_in_matched_sections": matched,
        "completed_after_17_brt_bounds": completed_after_17_bounds,
        "policy_sha256": policy, "sections_export_sha256": export, "per_uf": uf_reports,
        "inputs": input.inputs, "official_input": input.official,
        "limitations": ["Relógios nominais; não prova o instante físico do voto.",
            "ZZ excluído dos cortes BRT.", "Confirmação presidencial e conclusão do eleitor são métricas distintas.",
            "Assinaturas e autenticadores não verificados. Não revela candidato escolhido.",
            "Sem conciliação completa, somas são diagnóstico, não contagem nacional validada."]});
    publish_file(output, |file| {
        serde_json::to_writer_pretty(file, &result)?;
        Ok(())
    })?;
    ensure!(
        success,
        "consolidação diagnóstica: cobertura/conciliação nacional incompleta"
    );
    Ok(())
}

fn main() -> Result<()> {
    let args = Args::parse();
    if let Some(manifest) = args.aggregate_manifest {
        return aggregate(&manifest, &args.output);
    }
    let sections_output = args
        .sections_output
        .context("--sections-output obrigatório para ler logs")?;
    ensure!(
        !args.output.exists() && !sections_output.exists() && args.output != sections_output,
        "saída existente/conflitante"
    );
    let source = HashingRead {
        inner: std::io::stdin().lock(),
        hash: Sha256::new(),
        bytes: 0,
    };
    let mut reader = BufReader::new(source);
    let (mut summary, sections) = parse_stream(&mut reader)?;
    let source = reader.into_inner();
    summary.wire_sha256 = hex::encode(source.hash.finalize());
    summary.wire_bytes = source.bytes;
    publish_file(&sections_output, |file| {
        let mut csv = csv::Writer::from_writer(file);
        csv.write_record([
            "section_key",
            "expected_turnout",
            "completed_electors",
            "president_confirmations",
            "completed_after_17_brt",
            "president_after_17_brt",
            "duplicate_relevant_lines",
            "matched",
        ])?;
        for section in sections {
            csv.write_record([
                section.key,
                section
                    .expected_turnout
                    .map(|v| v.to_string())
                    .unwrap_or_default(),
                section.events.completed_electors.to_string(),
                section.events.president_confirmations.to_string(),
                section.events.completed_after_17_brt.to_string(),
                section.events.president_after_17_brt.to_string(),
                section.duplicate_relevant_lines.to_string(),
                section.matched.to_string(),
            ])?;
        }
        csv.flush()?;
        Ok(())
    })?;
    publish_file(&args.output, |file| {
        serde_json::to_writer_pretty(file, &summary)?;
        Ok(())
    })?;
    if !summary.success {
        bail!(
            "conciliação de logs reprovada; relatório diagnóstico publicado, sem selo de sucesso"
        );
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;

    fn fixture() -> (Value, Value, Vec<u8>) {
        let data: Value = serde_json::from_slice(include_bytes!(
            "../../tests/fixtures/audit-2026/log-frame-synthetic.json"
        ))
        .unwrap();
        (
            data["header"].clone(),
            data["end"].clone(),
            include_bytes!("../../tests/fixtures/audit-2026/logd-synthetic.dat").to_vec(),
        )
    }

    fn wire(header: &Value, body: &[u8], end: Option<&Value>) -> Vec<u8> {
        let mut out = serde_json::to_vec(header).unwrap();
        out.push(b'\n');
        out.extend(body);
        if let Some(end) = end {
            out.extend(serde_json::to_vec(end).unwrap());
            out.push(b'\n');
        }
        out
    }

    #[test]
    fn counts_synthetic_fixture_bytes_at_strict_time_boundary_and_excludes_other_day() {
        let (header, end, body) = fixture();
        let (summary, sections) =
            parse_stream(&mut std::io::Cursor::new(wire(&header, &body, Some(&end)))).unwrap();
        assert!(summary.success && summary.coverage_complete);
        assert_eq!(sections.len(), 1);
        assert_eq!(summary.all_parsed_events.completed_electors, 2);
        assert_eq!(summary.all_parsed_events.completed_after_17_brt, 1);
        assert_eq!(summary.all_parsed_events.president_after_17_brt, 1);
        assert_eq!(summary.other_dates_relevant_events["04/10/2026"], 1);
    }

    #[test]
    fn changed_hash_and_interrupted_stream_fail() {
        let (header, end, mut body) = fixture();
        let last = body.len() - 2;
        body[last] = if body[last] == b'0' { b'1' } else { b'0' };
        assert!(parse_stream(&mut std::io::Cursor::new(wire(&header, &body, Some(&end)))).is_err());
        let (header, _, body) = fixture();
        assert!(parse_stream(&mut std::io::Cursor::new(wire(&header, &body, None))).is_err());
    }

    #[test]
    fn missing_expected_section_prevents_success_even_when_present_section_matches() {
        let (header, mut end, body) = fixture();
        let keys = "MT/00001/0001/0001\nMT/00001/0001/0002\n";
        end["expected_sections"] = 2.into();
        end["expected_section_keys_sha256"] = hex::encode(Sha256::digest(keys)).into();
        let (summary, _) =
            parse_stream(&mut std::io::Cursor::new(wire(&header, &body, Some(&end)))).unwrap();
        assert_eq!(summary.matched_sections, 1);
        assert!(!summary.success && !summary.coverage_complete);
    }

    #[test]
    fn duplicate_events_are_counted_and_block_reconciliation() {
        let (mut header, end, mut body) = fixture();
        let duplicate = body
            .split_inclusive(|b| *b == b'\n')
            .next_back()
            .unwrap()
            .to_vec();
        body.extend(duplicate);
        header["bytes"] = (body.len() as u64).into();
        header["sha256"] = hex::encode(Sha256::digest(&body)).into();
        let (summary, _) =
            parse_stream(&mut std::io::Cursor::new(wire(&header, &body, Some(&end)))).unwrap();
        assert!(!summary.success);
        assert_eq!(summary.duplicate_relevant_lines, 1);
        assert_eq!(summary.all_parsed_events.completed_electors, 3);
    }

    #[test]
    fn repeated_bodies_are_preserved_and_current_day_duplicates_block_success() {
        let (header, mut end, body) = fixture();
        let mut input = wire(&header, &body, None);
        input.extend(wire(&header, &body, None));
        end["files"] = 2.into();
        input.extend(serde_json::to_vec(&end).unwrap());
        input.push(b'\n');
        let (summary, _) = parse_stream(&mut std::io::Cursor::new(input)).unwrap();
        assert!(!summary.success);
        assert_eq!(summary.duplicate_body_files, 1);
        assert_eq!(summary.duplicate_relevant_lines, 4);
        assert_eq!(summary.all_parsed_events.completed_electors, 4);
        assert_eq!(summary.other_dates_relevant_events["04/10/2026"], 2);
    }

    #[test]
    fn malformed_line_is_hashed_and_blocks_section_without_stopping_coverage() {
        let (mut header, end, mut body) = fixture();
        let offset = body.windows(10).position(|v| v == b"04/10/2026").unwrap();
        body.insert(offset, 0);
        header["bytes"] = (body.len() as u64).into();
        header["sha256"] = hex::encode(Sha256::digest(&body)).into();
        let (summary, _) =
            parse_stream(&mut std::io::Cursor::new(wire(&header, &body, Some(&end)))).unwrap();
        assert!(!summary.success && summary.coverage_complete);
        assert_eq!(summary.malformed_lines, 1);
        assert_eq!(summary.all_parsed_events.completed_electors, 2);
        assert_eq!(summary.malformed_line_examples[0]["body_line"], 4);
        assert_eq!(
            summary.malformed_line_examples[0]["line_sha256_without_eol"],
            hex::encode(Sha256::digest(body.split(|b| *b == b'\n').nth(3).unwrap()))
        );
    }

    #[test]
    fn other_internal_section_is_counted_separately_instead_of_assigned_by_filename() {
        let (mut header, end, body) = fixture();
        let mut text = body.clone();
        // Modifica somente a linha de contexto da seção na fixture identificada.
        let prefix = b"Se\xe7\xe3o Eleitoral: 0001";
        let start = text
            .windows(prefix.len())
            .position(|v| v == prefix)
            .unwrap();
        text[start + prefix.len() - 1] = b'2';
        header["bytes"] = (text.len() as u64).into();
        header["sha256"] = hex::encode(Sha256::digest(&text)).into();
        let (summary, _) =
            parse_stream(&mut std::io::Cursor::new(wire(&header, &text, Some(&end)))).unwrap();
        assert!(!summary.success);
        assert_eq!(summary.all_parsed_events.completed_electors, 0);
        assert_eq!(
            summary.other_context_relevant_events["MT/00001/0001/0002"],
            4
        );
        assert_eq!(summary.unknown_context_relevant_events, 0);
    }

    #[test]
    fn bounded_line_rejects_before_consuming_excessive_record() {
        let mut reader = std::io::Cursor::new(b"abcdef\n");
        assert!(bounded_line(&mut reader, &mut Vec::new(), 3).is_err());
        assert!(clock_seconds(b"25/10/2026 24:00:00").is_err());
    }
}
