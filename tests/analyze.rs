use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};
use tsepack::analyze::{self, AnalysisOutcome, AnalysisProfile};

fn fixture(name: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures/analyze")
        .join(name)
}

fn records(bytes: &[u8]) -> u64 {
    let newlines = bytes.windows(2).filter(|window| *window == b"\r\n").count();
    newlines.saturating_sub(1) as u64
}

fn profile_for(path: &Path) -> AnalysisProfile {
    let bytes = fs::read(path).unwrap();
    let mut profile = analyze::profile_mt_2026_t1_bweb_v1();
    profile.expected_source_sha256 = Some(tsepack::hash::sha256_bytes(&bytes));
    profile.expected_records = Some(records(&bytes));
    profile.expected_zip_sha256 = None;
    profile.expected_member_name = None;
    profile.expected_member_ordinal = None;
    profile
}

fn run(name: &str) -> (tempfile::TempDir, AnalysisOutcome, Value, Value) {
    let dir = tempfile::tempdir().unwrap();
    let input = fixture(name);
    let output = dir.path().join("out");
    let outcome = analyze::run(&input, &output, &profile_for(&input)).unwrap();
    let results = serde_json::from_slice(&fs::read(output.join("results.json")).unwrap()).unwrap();
    let quality = serde_json::from_slice(&fs::read(output.join("quality.json")).unwrap()).unwrap();
    (dir, outcome, results, quality)
}

fn find_row<'a>(value: &'a Value, conditions: &[(&str, &str)]) -> &'a Value {
    value
        .as_array()
        .unwrap()
        .iter()
        .find(|row| {
            conditions
                .iter()
                .all(|(field, expected)| row[*field].as_str() == Some(*expected))
        })
        .unwrap_or_else(|| panic!("linha não encontrada: {conditions:?} em {value}"))
}

#[test]
fn contexto_repetido_conta_uma_vez_e_preserva_zeros() {
    let (_dir, outcome, results, quality) = run("mt-valid.csv");
    assert!(outcome.approved, "quality: {quality}");
    let by_office = &results["context"]["by_office"];
    let cargo7 = find_row(by_office, &[("cargo", "7")]);
    assert_eq!(cargo7["grupos_contexto"], 3);
    assert_eq!(cargo7["aptos"], "10");
    assert_eq!(cargo7["comparecimento"], "7");
    assert_eq!(cargo7["abstencoes"], "3");
    let cargo3 = find_row(by_office, &[("cargo", "3")]);
    assert_eq!(cargo3["grupos_contexto"], 1);
    assert_eq!(cargo3["aptos"], "10");
    let muni2 = find_row(
        &results["context"]["by_office_municipality"],
        &[("cargo", "7"), ("municipio", "0002")],
    );
    assert_eq!(muni2["aptos"], "0");
    assert!(muni2["comparecimento_por_aptos"].is_null());
    assert_eq!(muni2["comparecimento_por_aptos_motivo"], "denominator_zero");
    assert_eq!(results["votes"]["total"], "19");
    let office7 = find_row(&results["votes"]["by_office"], &[("cargo", "7")]);
    assert_eq!(office7["votos"], "13");
    let nominal = find_row(
        &results["votes"]["by_office_municipality"],
        &[
            ("cargo", "7"),
            ("municipio", "0001"),
            ("categoria_codigo", "1"),
        ],
    );
    assert_eq!(nominal["votos"], "7");
    assert_eq!(nominal["fracao"], "0.538462");
    assert_eq!(quality["coverage"]["municipalities"], 2);
    assert_eq!(quality["coverage"]["zones"], 2);
    assert_eq!(quality["coverage"]["context_groups"], 4);
    assert_eq!(quality["context"]["zero_denominator_groups"], 2);
    assert_eq!(quality["sentinels"]["NR_PARTIDO"]["-1"], 3);
    assert_eq!(quality["sentinels"]["SG_PARTIDO"]["#NULO#"], 3);
    assert_eq!(quality["sentinels"]["NR_JUNTA_APURADORA"]["-1"], 8);
    assert_eq!(quality["sentinels"]["DS_SECOES_AGREGADAS"]["#NULO#"], 8);
    let zone = find_row(
        &results["context"]["by_office_zone"],
        &[("cargo", "7"), ("municipio", "0001"), ("zona", "0001")],
    );
    assert_eq!(zone["grupos_contexto"], 2);
}

#[test]
fn contexto_divergente_bloqueia_contexto_sem_arbitrar() {
    let (_dir, outcome, results, quality) = run("mt-context-divergent.csv");
    assert!(!outcome.approved);
    assert_eq!(quality["status"], "failed");
    assert_eq!(quality["context"]["divergent_groups"], 1);
    assert_eq!(quality["context"]["divergence_rows"], 1);
    assert_eq!(
        quality["context"]["evidence"][0]["column"],
        "QT_COMPARECIMENTO"
    );
    assert_eq!(results["context"]["status"], "blocked");
    assert!(results["context"]["by_office"]
        .as_array()
        .unwrap()
        .is_empty());
    assert_eq!(results["votes"]["status"], "approved");
    assert_eq!(results["votes"]["total"], "4");
}

#[test]
fn duplicata_repetida_e_conflito_sao_distintos() {
    let (_dir, outcome, _results, quality) = run("mt-duplicate-exact.csv");
    assert!(!outcome.approved);
    assert_eq!(quality["keys"]["duplicate_keys"], 1);
    assert_eq!(quality["keys"]["repeated_occurrences"], 1);
    assert_eq!(quality["keys"]["conflicts"], 0);
    assert_eq!(
        quality["keys"]["evidence"][0]["kind"],
        "repeated_occurrence"
    );
    assert_eq!(quality["uses"][0]["status"], "blocked");

    let (_dir, outcome, _results, quality) = run("mt-duplicate-conflict.csv");
    assert!(!outcome.approved);
    assert_eq!(quality["keys"]["duplicate_keys"], 1);
    assert_eq!(quality["keys"]["repeated_occurrences"], 0);
    assert_eq!(quality["keys"]["conflicts"], 1);
    assert_eq!(quality["keys"]["evidence"][0]["kind"], "conflict");
}

#[test]
fn categoria_desconhecida_entra_na_cobertura_e_bloqueia_interpretacao() {
    let (_dir, outcome, results, quality) = run("mt-unknown-category.csv");
    assert!(outcome.approved);
    assert_eq!(results["votes"]["status"], "approved");
    assert_eq!(results["votes"]["total"], "1");
    let unknown = find_row(
        &results["votes"]["by_office_category"],
        &[("categoria_codigo", "9")],
    );
    assert_eq!(unknown["categoria_status"], "unconfirmed");
    assert_eq!(unknown["votos"], "1");
    let category = find_row(&quality["coverage"]["categories"], &[("code", "9")]);
    assert_eq!(category["status"], "unconfirmed");
    assert_eq!(category["votes"], "1");
    assert_eq!(quality["uses"][2]["status"], "blocked");
    assert_eq!(
        quality["checks"]
            .as_array()
            .unwrap()
            .iter()
            .find(|check| check["id"] == "category_domain")
            .unwrap()["status"],
        "blocked"
    );
}

#[test]
fn overflow_de_votos_reprova() {
    let (_dir, outcome, results, quality) = run("mt-overflow.csv");
    assert!(!outcome.approved);
    assert_eq!(results["votes"]["status"], "blocked");
    let check = quality["checks"]
        .as_array()
        .unwrap()
        .iter()
        .find(|check| check["id"] == "numeric_votes")
        .unwrap();
    assert_eq!(check["status"], "fail");
}

#[test]
fn fora_do_escopo_bloqueia_votos_e_contexto() {
    let (_dir, outcome, results, quality) = run("mt-out-of-scope.csv");
    assert!(!outcome.approved);
    assert_eq!(results["votes"]["status"], "blocked");
    assert_eq!(results["context"]["status"], "blocked");
    assert!(quality["unexpected_values"]
        .as_array()
        .unwrap()
        .iter()
        .any(|value| value["column"] == "NR_TURNO" && value["status"] == "out_of_scope"));
}

#[test]
fn truncada_e_cabecalho_divergente_nao_aprovam() {
    let (_dir, outcome, _results, quality) = run("mt-truncated.csv");
    assert!(!outcome.approved);
    assert_eq!(quality["source"]["verification"], "not_completed");
    let (_dir, outcome, _results, quality) = run("header-bad.csv");
    assert!(!outcome.approved);
    let header = quality["checks"]
        .as_array()
        .unwrap()
        .iter()
        .find(|check| check["id"] == "header")
        .unwrap();
    assert_eq!(header["status"], "fail");
    let fingerprint = quality["checks"]
        .as_array()
        .unwrap()
        .iter()
        .find(|check| check["id"] == "header_fingerprint")
        .unwrap();
    assert_eq!(fingerprint["status"], "not_executed");
    assert_eq!(quality["source"]["verification"], "not_completed");
}

#[test]
fn hash_divergente_reprova_sem_aprovar() {
    let dir = tempfile::tempdir().unwrap();
    let input = fixture("mt-valid.csv");
    let output = dir.path().join("out");
    let mut profile = profile_for(&input);
    profile.expected_source_sha256 = Some("0".repeat(64));
    let outcome = analyze::run(&input, &output, &profile).unwrap();
    assert!(!outcome.approved);
    let quality: Value =
        serde_json::from_slice(&fs::read(output.join("quality.json")).unwrap()).unwrap();
    assert_eq!(quality["source"]["verification"], "mismatch");
    assert_eq!(quality["uses"][0]["status"], "blocked");
}

#[test]
fn secoes_agregadas_bloqueiam_contagem_fisica_sem_falhar_o_resto() {
    let (_dir, outcome, results, quality) = run("mt-agregadas.csv");
    assert!(outcome.approved);
    assert_eq!(quality["ds_secoes_agregadas"]["status"], "blocked");
    assert_eq!(
        quality["ds_secoes_agregadas"]["context_groups_with_non_sentinel"],
        1
    );
    assert_eq!(results["context"]["status"], "approved");
    let physical = quality["uses"]
        .as_array()
        .unwrap()
        .iter()
        .find(|usage| usage["id"] == "physical_section_count")
        .unwrap();
    assert_eq!(physical["status"], "blocked");
}

#[test]
fn view_verifica_payload_sha_membro_e_ordinal() {
    let dir = tempfile::tempdir().unwrap();
    let source = fixture("mt-valid.csv");
    let view = dir.path().join("view");
    fs::create_dir(&view).unwrap();
    let payload = view.join("payload.encoded");
    let measurement = tsepack::codec::compress(&source, &payload, "zstd-3", None).unwrap();
    let bytes = fs::read(&source).unwrap();
    let descriptor = serde_json::json!({
        "artifact_kind": "bweb_storage_view",
        "format_version": 1,
        "guarantee": "exact-csv-member-bytes",
        "kind": "csv-codec",
        "source": {
            "bytes": bytes.len(),
            "sha256": tsepack::hash::sha256_bytes(&bytes),
            "records": records(&bytes),
            "zip_path": "t1/MT/sintetico.zip",
            "zip_sha256": tsepack::hash::sha256_bytes(b"zip sintetico"),
            "member_name": "mt-valid.csv",
            "member_ordinal": 0
        },
        "encoded": {
            "file": "payload.encoded",
            "bytes": measurement.output_bytes,
            "sha256": measurement.encoded_sha256
        },
        "codec": "zstd-3",
        "dictionary": null,
        "pack_manifest": null,
        "decoded_stream": null
    });
    fs::write(
        view.join("view.json"),
        serde_json::to_vec_pretty(&descriptor).unwrap(),
    )
    .unwrap();
    let output = dir.path().join("out");
    let mut profile = profile_for(&source);
    profile.expected_zip_sha256 = Some(tsepack::hash::sha256_bytes(b"zip sintetico"));
    profile.expected_member_name = Some("mt-valid.csv".into());
    profile.expected_member_ordinal = Some(0);
    let outcome = analyze::run(&view, &output, &profile).unwrap();
    assert!(outcome.approved);
    let quality: Value =
        serde_json::from_slice(&fs::read(output.join("quality.json")).unwrap()).unwrap();
    assert_eq!(quality["source"]["kind"], "view");
    assert_eq!(quality["source"]["member_ordinal"], 0);
    assert_eq!(
        quality["source"]["view_sha256"],
        tsepack::hash::sha256_bytes(&fs::read(view.join("view.json")).unwrap())
    );
    assert_eq!(quality["source"]["verification"], "verified");
    assert_eq!(quality["source"]["expected_records"], 8);
}

#[test]
fn view_com_payload_adulterado_reprova() {
    let dir = tempfile::tempdir().unwrap();
    let source = fixture("mt-valid.csv");
    let view = dir.path().join("view");
    fs::create_dir(&view).unwrap();
    let payload = view.join("payload.encoded");
    let measurement = tsepack::codec::compress(&source, &payload, "zstd-3", None).unwrap();
    let bytes = fs::read(&source).unwrap();
    let descriptor = serde_json::json!({
        "artifact_kind": "bweb_storage_view",
        "format_version": 1,
        "guarantee": "exact-csv-member-bytes",
        "kind": "csv-codec",
        "source": {
            "bytes": bytes.len(),
            "sha256": tsepack::hash::sha256_bytes(&bytes),
            "records": records(&bytes),
            "zip_path": "t1/MT/sintetico.zip",
            "zip_sha256": tsepack::hash::sha256_bytes(b"zip sintetico"),
            "member_name": "mt-valid.csv",
            "member_ordinal": 0
        },
        "encoded": {
            "file": "payload.encoded",
            "bytes": measurement.output_bytes,
            "sha256": measurement.encoded_sha256
        },
        "codec": "zstd-3",
        "dictionary": null,
        "pack_manifest": null,
        "decoded_stream": null
    });
    fs::write(
        view.join("view.json"),
        serde_json::to_vec_pretty(&descriptor).unwrap(),
    )
    .unwrap();
    let mut payload_bytes = fs::read(&payload).unwrap();
    payload_bytes[0] ^= 0xff;
    fs::write(&payload, payload_bytes).unwrap();
    let output = dir.path().join("out");
    let mut profile = profile_for(&source);
    profile.expected_zip_sha256 = Some(tsepack::hash::sha256_bytes(b"zip sintetico"));
    profile.expected_member_name = Some("mt-valid.csv".into());
    profile.expected_member_ordinal = Some(0);
    assert!(analyze::run(&view, &output, &profile).is_err());
    assert!(output.join("run.json").is_file());
    assert!(!output.join("results.json").exists());
}

#[test]
fn segunda_execucao_reproduz_resultados_e_qualidade() {
    let dir = tempfile::tempdir().unwrap();
    let input = fixture("mt-valid.csv");
    let profile = profile_for(&input);
    let first = dir.path().join("first");
    let second = dir.path().join("second");
    assert!(analyze::run(&input, &first, &profile).unwrap().approved);
    assert!(analyze::run(&input, &second, &profile).unwrap().approved);
    for name in [
        "results.json",
        "quality.json",
        "votes_by_office.csv",
        "votes_by_office_municipality.csv",
        "context_by_office.csv",
        "context_by_office_municipality.csv",
        "context_by_office_zone.csv",
        "REPORT.md",
    ] {
        assert_eq!(
            fs::read(first.join(name)).unwrap(),
            fs::read(second.join(name)).unwrap(),
            "{name}"
        );
    }
}

#[test]
fn perfil_desconhecido_e_rejeitado_sem_inferencia() {
    assert!(analyze::profile_for_id("mt-2026-t1-bweb-v1").is_some());
    assert!(analyze::profile_for_id("desconhecido").is_none());
}

#[test]
fn view_com_membro_divergente_reprova_com_mismatch() {
    let dir = tempfile::tempdir().unwrap();
    let source = fixture("mt-valid.csv");
    let view = dir.path().join("view");
    fs::create_dir(&view).unwrap();
    let payload = view.join("payload.encoded");
    let measurement = tsepack::codec::compress(&source, &payload, "zstd-3", None).unwrap();
    let bytes = fs::read(&source).unwrap();
    let descriptor = serde_json::json!({
        "artifact_kind": "bweb_storage_view",
        "format_version": 1,
        "guarantee": "exact-csv-member-bytes",
        "kind": "csv-codec",
        "source": {
            "bytes": bytes.len(),
            "sha256": tsepack::hash::sha256_bytes(&bytes),
            "records": 8,
            "zip_path": "t1/MT/sintetico.zip",
            "zip_sha256": tsepack::hash::sha256_bytes(b"zip sintetico"),
            "member_name": "outro.csv",
            "member_ordinal": 1
        },
        "encoded": {
            "file": "payload.encoded",
            "bytes": measurement.output_bytes,
            "sha256": measurement.encoded_sha256
        },
        "codec": "zstd-3",
        "dictionary": null,
        "pack_manifest": null,
        "decoded_stream": null
    });
    fs::write(
        view.join("view.json"),
        serde_json::to_vec_pretty(&descriptor).unwrap(),
    )
    .unwrap();
    let output = dir.path().join("out");
    let mut profile = profile_for(&source);
    profile.expected_zip_sha256 = Some(tsepack::hash::sha256_bytes(b"zip sintetico"));
    profile.expected_member_name = Some("mt-valid.csv".into());
    profile.expected_member_ordinal = Some(0);
    let outcome = analyze::run(&view, &output, &profile).unwrap();
    assert!(!outcome.approved);
    let quality: Value =
        serde_json::from_slice(&fs::read(output.join("quality.json")).unwrap()).unwrap();
    assert_eq!(quality["source"]["verification"], "mismatch");
}

#[test]
fn saida_existente_ou_sobreposta_e_recusada_sem_residuo() {
    let dir = tempfile::tempdir().unwrap();
    let input = fixture("mt-valid.csv");
    let profile = profile_for(&input);
    let output = dir.path().join("out");
    fs::create_dir(&output).unwrap();
    assert!(analyze::run(&input, &output, &profile).is_err());
    assert!(!output.join("results.json").exists());
    let overlap = dir.path().join("overlap.csv");
    fs::copy(&input, &overlap).unwrap();
    assert!(analyze::run(&overlap, &overlap, &profile).is_err());
}

fn read_byte_records(path: &Path) -> Vec<csv::ByteRecord> {
    let mut reader = csv::ReaderBuilder::new()
        .has_headers(false)
        .flexible(false)
        .delimiter(b';')
        .from_path(path)
        .unwrap();
    reader
        .byte_records()
        .map(|record| record.unwrap())
        .collect()
}

fn write_byte_records(path: &Path, records: &[csv::ByteRecord]) {
    let mut writer = csv::WriterBuilder::new()
        .has_headers(false)
        .delimiter(b';')
        .terminator(csv::Terminator::CRLF)
        .from_path(path)
        .unwrap();
    for record in records {
        writer.write_byte_record(record).unwrap();
    }
    writer.flush().unwrap();
}

fn column_index(records: &[csv::ByteRecord], name: &str) -> usize {
    records[0]
        .iter()
        .position(|field| field == name.as_bytes())
        .unwrap()
}

#[test]
fn campo_excessivo_falha_explicitamente() {
    let dir = tempfile::tempdir().unwrap();
    let original = read_byte_records(&fixture("mt-valid.csv"));
    let nm_pos = column_index(&original, "NM_VOTAVEL");
    let huge = vec![b'X'; 300_000];
    let mut replaced = csv::ByteRecord::new();
    for (index, field) in original[1].iter().enumerate() {
        if index == nm_pos {
            replaced.push_field(&huge);
        } else {
            replaced.push_field(field);
        }
    }
    let mut out_records = vec![original[0].clone(), replaced];
    out_records.extend_from_slice(&original[2..]);
    let csv = dir.path().join("huge.csv");
    write_byte_records(&csv, &out_records);
    let profile = profile_for(&csv);
    let output = dir.path().join("out");
    let outcome = analyze::run(&csv, &output, &profile).unwrap();
    assert!(!outcome.approved);
    let quality: Value =
        serde_json::from_slice(&fs::read(output.join("quality.json")).unwrap()).unwrap();
    let lexical = quality["checks"]
        .as_array()
        .unwrap()
        .iter()
        .find(|check| check["id"] == "lexical_fields")
        .unwrap();
    assert_eq!(lexical["status"], "fail");
}

#[test]
fn data_invalida_reprova_lexico() {
    let dir = tempfile::tempdir().unwrap();
    let source = fs::read(fixture("mt-valid.csv")).unwrap();
    // Substituição em bytes (Latin-1): ambas as datas são ASCII.
    let needle = b"05/10/2026";
    let replacement = b"99/99/9999";
    let position = source
        .windows(needle.len())
        .position(|window| window == needle)
        .expect("data do fixture");
    let mut bad = source;
    bad.splice(
        position..position + needle.len(),
        replacement.iter().cloned(),
    );
    let csv = dir.path().join("bad-date.csv");
    fs::write(&csv, bad).unwrap();
    let profile = profile_for(&csv);
    let output = dir.path().join("out");
    let outcome = analyze::run(&csv, &output, &profile).unwrap();
    assert!(!outcome.approved);
    let quality: Value =
        serde_json::from_slice(&fs::read(output.join("quality.json")).unwrap()).unwrap();
    let lexical = quality["checks"]
        .as_array()
        .unwrap()
        .iter()
        .find(|check| check["id"] == "lexical_fields")
        .unwrap();
    assert_eq!(lexical["status"], "fail");
}

#[test]
fn conflito_de_nome_municipal_bloqueia_cobertura_territorial() {
    let dir = tempfile::tempdir().unwrap();
    let original = read_byte_records(&fixture("mt-valid.csv"));
    let nm_pos = column_index(&original, "NM_MUNICIPIO");
    let nr_pos = column_index(&original, "NR_VOTAVEL");
    let qt_pos = column_index(&original, "QT_VOTOS");
    // ByteRecord não tem set direto; reconstrói o registro.
    let mut rebuilt = csv::ByteRecord::new();
    for (index, field) in original[1].iter().enumerate() {
        if index == nm_pos {
            rebuilt.push_field(b"OUTRO NOME");
        } else if index == nr_pos {
            rebuilt.push_field(b"9999");
        } else if index == qt_pos {
            rebuilt.push_field(b"0");
        } else {
            rebuilt.push_field(field);
        }
    }
    let mut out_records = original.clone();
    out_records.push(rebuilt);
    let csv = dir.path().join("conflict-name.csv");
    write_byte_records(&csv, &out_records);
    let profile = profile_for(&csv);
    let output = dir.path().join("out");
    let outcome = analyze::run(&csv, &output, &profile).unwrap();
    assert!(outcome.approved);
    let quality: Value =
        serde_json::from_slice(&fs::read(output.join("quality.json")).unwrap()).unwrap();
    assert_eq!(quality["coverage"]["municipality_name_conflicts"], 1);
    let territorial = quality["uses"]
        .as_array()
        .unwrap()
        .iter()
        .find(|use_status| use_status["id"] == "territorial_coverage_observed")
        .unwrap();
    assert_eq!(territorial["status"], "blocked");
}

#[test]
fn recibo_de_falha_tem_schema_unificado() {
    let dir = tempfile::tempdir().unwrap();
    let input = fixture("mt-valid.csv");
    let output = dir.path().join("out");
    let mut profile = profile_for(&input);
    profile.expected_source_sha256 = Some("0".repeat(64));
    let outcome = analyze::run(&input, &output, &profile).unwrap();
    assert!(!outcome.approved);
    let run: Value = serde_json::from_slice(&fs::read(output.join("run.json")).unwrap()).unwrap();
    assert_eq!(run["approved"], false);
    assert!(run.get("peak_rss_kib").is_some());
    assert!(run.get("parameters").is_some());
    assert!(run.get("outputs").is_some());
}

#[test]
fn cli_retorna_exit_nao_zero_quando_controle_obrigatorio_reprova() {
    let dir = tempfile::tempdir().unwrap();
    let binary = env!("CARGO_BIN_EXE_tsepack");
    let invalid = dir.path().join("invalid");
    let status = std::process::Command::new(binary)
        .args([
            "analyze",
            "--input",
            fixture("mt-out-of-scope.csv").to_str().unwrap(),
            "--output",
            invalid.to_str().unwrap(),
        ])
        .status()
        .unwrap();
    assert!(!status.success());
    assert!(invalid.join("quality.json").is_file());
}

#[test]
fn verificador_independente_confere_fixture_sintetica() {
    let dir = tempfile::tempdir().unwrap();
    let input = fixture("mt-valid.csv");
    let output = dir.path().join("out");
    let profile = profile_for(&input);
    assert!(analyze::run(&input, &output, &profile).unwrap().approved);
    let status = std::process::Command::new("python3")
        .args([
            "scripts/analyze_check.py",
            "--csv",
            input.to_str().unwrap(),
            "--results",
            output.join("results.json").to_str().unwrap(),
            "--quality",
            output.join("quality.json").to_str().unwrap(),
        ])
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .status()
        .unwrap();
    assert!(status.success());
}
