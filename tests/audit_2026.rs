//! Integração executa o binário real sobre fixture explicitamente sintética.
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::path::Path;
use std::process::Command;

fn run_case(bytes: &[u8], correct_sha: bool) -> (bool, Option<Value>, String) {
    let temp = tempfile::tempdir().unwrap();
    let input = temp.path().join("synthetic.csv");
    std::fs::write(&input, bytes).unwrap();
    let hash = if correct_sha {
        hex::encode(Sha256::digest(bytes))
    } else {
        hex::encode(Sha256::digest(b"outros bytes sinteticos"))
    };
    let manifest = temp.path().join("manifest.json");
    std::fs::write(
        &manifest,
        serde_json::to_vec(&json!({"format_version":1,"inputs":[{
            "path":input,"bytes":bytes.len(),"sha256":hash,"uf":"MT",
            "zip_sha256":hex::encode(Sha256::digest(bytes)),
            "zip_url":"synthetic:test-fixture-not-TSE","member":"synthetic.csv"
        }]}))
        .unwrap(),
    )
    .unwrap();
    let output = temp.path().join("report.json");
    let result = Command::new(env!("CARGO_BIN_EXE_audit_2026"))
        .args([
            "--manifest",
            manifest.to_str().unwrap(),
            "--output",
            output.to_str().unwrap(),
        ])
        .output()
        .unwrap();
    let report = output
        .exists()
        .then(|| serde_json::from_slice(&std::fs::read(output).unwrap()).unwrap());
    (
        result.status.success(),
        report,
        String::from_utf8_lossy(&result.stderr).into_owned(),
    )
}

fn fixture() -> Vec<u8> {
    std::fs::read(
        Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/audit-2026/synthetic.csv"),
    )
    .unwrap()
}

#[test]
fn sums_context_once_and_checks_exact_percent_boundary() {
    let (ok, report, error) = run_case(&fixture(), true);
    assert!(ok, "{error}");
    let report = report.unwrap();
    assert_eq!(report["presidential"]["sections"], 2);
    assert_eq!(report["presidential"]["turnout"], 103);
    assert_eq!(report["presidential"]["biometric_not_enabled"], 3);
    assert_eq!(report["extremes"]["above_90_13"], 1);
    assert_eq!(report["extremes"]["at_least_90_13"], 2);
    assert_eq!(report["raw_clock_windows"]["ate_17h00m00s"]["sections"], 1);
    assert_eq!(report["raw_strict_after_19"]["sections"], 0);
}

#[test]
fn wrong_hash_exits_nonzero_without_report() {
    let (ok, report, error) = run_case(&fixture(), false);
    assert!(!ok);
    assert!(report.is_none());
    assert!(error.contains("SHA-256 divergente"));
}

#[test]
fn duplicate_occurrence_is_not_silently_removed() {
    let mut bytes = fixture();
    let text = String::from_utf8(bytes.clone()).unwrap();
    bytes.extend_from_slice(text.lines().nth(1).unwrap().as_bytes());
    bytes.extend_from_slice(b"\r\n");
    let (ok, report, error) = run_case(&bytes, true);
    assert!(!ok);
    assert!(report.is_none());
    assert!(error.contains("ocorrência duplicada"));
}

#[test]
fn changed_repeated_context_fails() {
    let text = String::from_utf8(fixture()).unwrap();
    let mut rows: Vec<_> = text.lines().map(str::to_owned).collect();
    // Alteração de uma das duas linhas da seção, preservando sintaxe e soma aptos.
    rows[2] = rows[2].replace("2026-10-25 17:00:00", "2026-10-25 17:00:01");
    let (ok, report, error) = run_case(rows.join("\n").as_bytes(), true);
    assert!(!ok);
    assert!(report.is_none());
    assert!(error.contains("contexto repetido divergente"));
}
