//! Round-trip: manifesto salvo e recarregado é idêntico;
//! verificação aprova o diretório intacto.

use std::path::Path;
use tsepack::manifest::Manifest;
use tsepack::verify::verify;

#[test]
fn manifest_round_trip_e_verify_ok() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("bu_001.csv"), "a,b,c\n1,2,3\n").unwrap();
    std::fs::write(dir.path().join("log.txt"), "evento repetido\n".repeat(100)).unwrap();

    let m = Manifest::build_from_dir(dir.path(), "teste").unwrap();
    assert_eq!(m.files.len(), 2);

    let mpath = dir.path().join("manifest.json");
    m.save(&mpath).unwrap();
    let m2 = Manifest::load(&mpath).unwrap();
    assert_eq!(m, m2);

    let rep = verify(&mpath, dir.path()).unwrap();
    assert!(rep.approved, "esperava aprovação: {rep:?}");
    assert_eq!(rep.failed, 0);
}

#[test]
fn corrupcao_e_detectada() {
    let dir = tempfile::tempdir().unwrap();
    let f = dir.path().join("dado.csv");
    std::fs::write(&f, "original").unwrap();

    let m = Manifest::build_from_dir(dir.path(), "teste").unwrap();
    let mpath = dir.path().join("manifest.json");
    m.save(&mpath).unwrap();

    // Corrompe (trunca/altera) o arquivo após o manifesto.
    std::fs::write(&f, "adulterado!").unwrap();

    let rep = verify(&mpath, dir.path()).unwrap();
    assert!(!rep.approved);
    assert_eq!(rep.failed, 1);
}

#[test]
fn arquivo_ausente_e_detectado() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("x.bin"), b"0123456789").unwrap();
    let m = Manifest::build_from_dir(dir.path(), "teste").unwrap();
    let mpath = Path::new(dir.path()).join("manifest.json");
    m.save(&mpath).unwrap();

    std::fs::remove_file(dir.path().join("x.bin")).unwrap();
    let rep = verify(&mpath, dir.path()).unwrap();
    assert!(!rep.approved);
}
