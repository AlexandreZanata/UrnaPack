//! Determinismo: duas construções sobre o mesmo conteúdo
//! geram manifestos byte a byte idênticos.

use tsepack::manifest::Manifest;

#[test]
fn manifesto_e_deterministico() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("b.csv"), "2").unwrap();
    std::fs::write(dir.path().join("a.csv"), "1").unwrap();

    let m1 = Manifest::build_from_dir(dir.path(), "fonte").unwrap();
    let m2 = Manifest::build_from_dir(dir.path(), "fonte").unwrap();

    let j1 = serde_json::to_string_pretty(&m1).unwrap();
    let j2 = serde_json::to_string_pretty(&m2).unwrap();
    assert_eq!(j1, j2);
    // Ordenado por caminho:
    assert!(j1.find("a.csv").unwrap() < j1.find("b.csv").unwrap());
}

#[test]
fn benchmark_round_trip_zstd() {
    let dir = tempfile::tempdir().unwrap();
    let p = dir.path().join("amostra.log");
    std::fs::write(&p, "urna evento voto\n".repeat(1000)).unwrap();
    let rep = tsepack::benchmark::run_on_file(&p, "quick").unwrap();
    for c in &rep.cases {
        assert!(c.round_trip_ok, "round-trip falhou em {}", c.method);
    }
    // Dado repetitivo deve comprimir (razão > 1) em algum nível ZSTD.
    assert!(rep
        .cases
        .iter()
        .any(|c| c.method != "stored" && c.ratio.is_some_and(|r| r > 1.0)));
}
