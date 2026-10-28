#!/usr/bin/env python3
"""Regressões da Etapa 1 para o mapeador estrutural (stdlib, sem rede).

Fixtures sintéticas em tests/fixtures/map/ (identificadas, hashes calculados
dos bytes). Contêineres temporários são criados a partir delas; nenhum dado
real do TSE é versionado aqui.
"""

import csv
import copy
import hashlib
import io
import json
import os
from pathlib import Path
from unittest import mock

import map_raw_data as M
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "map_raw_data.py")
FIXTURE_CSV = os.path.join(ROOT, "tests", "fixtures", "map", "csec-amostra.csv")

# Cabeçalho esperado da fixture (ordem documental da família csec).
EXPECTED_HEADER = [
    "DT_GERACAO", "HH_GERACAO", "AA_ELEICAO", "CD_PLEITO",
    "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA",
    "NR_SECAO", "NR_LOCAL_VOTACAO", "NR_URNA_ESPERADA",
    "CD_CARGA_URNA_ESPERADA", "CD_FLASHCARD_URNA_ESPERADA",
    "DT_CARGA_URNA_ESPERADA", "ST_CORRESP_ALTERADA",
    "NM_MAQUINA_GERACAO_MIDIA", "NR_SRI_TPM_GERACAO_MIDIA",
    "NR_SRI_INSTAL_GERACAO_MIDIA", "NM_MAQUINA_TRANSM_CORRESP",
    "NR_SRI_TPM_TRANSM_CORRESP", "NR_SRI_INSTAL_TRANSM_CORRESP",
]


def run_mapper(source, year, scope, output, limits_file=None):
    env = dict(os.environ)
    if limits_file:
        env["URNAPACK_LIMITS_FILE"] = limits_file
    return subprocess.run(
        [sys.executable, SCRIPT, "--source", source,
         "--year", str(year), "--scope", scope, "--output", output],
        capture_output=True, text=True, env=env,
    )


def fixture_bytes():
    with open(FIXTURE_CSV, "rb") as f:
        return f.read()


class TestMapaValido(unittest.TestCase):
    def test_csv_valido_acentos_quoting_sentinelas(self):
        raw = fixture_bytes()
        # Hash real dos bytes (nunca fictício); prova que a fixture foi lida.
        sha = hashlib.sha256(raw).hexdigest()
        self.assertEqual(len(sha), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in sha))
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src")
            out = os.path.join(tmp, "out")
            os.makedirs(src)
            zpath = os.path.join(src, "amostra.zip")
            with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("csec-amostra.csv", raw)
                z.writestr("doc.pdf", b"%PDF-1.4 fake\n")
            r = run_mapper(src, 2026, "MT", out)
            self.assertEqual(r.returncode, 0, msg=r.stderr)
            m = json.loads(Path(out, "map.json").read_text(encoding="utf-8"))
            self.assertEqual(m["artifact_kind"], "raw_structure_map")
            self.assertEqual(m["format_version"], 1)
            self.assertEqual(m["status"], "complete")
            self.assertEqual(m["params"]["source"], src)
            self.assertEqual(len(m["csv_profiles"]), 1)
            prof = m["csv_profiles"][0]
            self.assertEqual(prof["header"], EXPECTED_HEADER)
            self.assertEqual(prof["family"], "csec")
            self.assertEqual(prof["records"], 3)
            self.assertEqual(prof["field_divergence_count"], 0)
            self.assertEqual(prof["read_level"], "fully_read")
            # SHA do membro calculado dos bytes completos, separado do fingerprint.
            self.assertEqual(prof["member_sha256"], sha)
            fp = hashlib.sha256(
                json.dumps(EXPECTED_HEADER, ensure_ascii=False,
                           separators=(",", ":")).encode("utf-8")).hexdigest()
            self.assertEqual(prof["header_fingerprint"], fp)
            self.assertNotEqual(prof["member_sha256"], prof["header_fingerprint"])
            # Sentinelas lexicais preservadas por coluna (sem normalização).
            sent = prof["sentinels"]
            self.assertEqual(sent.get("NR_URNA_ESPERADA", {}).get("#NULO"), 1)
            self.assertEqual(sent.get("CD_CARGA_URNA_ESPERADA", {}).get("-1"), 1)
            self.assertEqual(sent.get("CD_FLASHCARD_URNA_ESPERADA", {}).get("#NE"), 1)
            # Campo vazio preservado como "" (distinto de zero/nulo).
            self.assertIn("", sent.get("NR_SECAO", {}))
            # Opaco amostrado sem hash completo.
            members = [json.loads(line) for line in
                       Path(out, "members.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(members), 2)
            pdf = [x for x in members if x["name"] == "doc.pdf"][0]
            self.assertIsNone(pdf["member_sha256"])
            self.assertEqual(pdf["read_level"], "sampled")


class TestMapaFalhas(unittest.TestCase):
    def _zip_case(self, tmp, name, members):
        src = os.path.join(tmp, "src")
        os.makedirs(src, exist_ok=True)
        zpath = os.path.join(src, name)
        with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for arc, data in members:
                z.writestr(arc, data)
        return src

    def test_cabecalho_desconhecido_reprova(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = self._zip_case(tmp, "u.zip", [("x.csv", b'"A";"B"\r\n"1";"2"\r\n')])
            out = os.path.join(tmp, "out")
            r = run_mapper(src, 2026, "MT", out)
            self.assertNotEqual(r.returncode, 0)
            diag = json.loads(Path(out, "diagnostic.partial.json").read_text(encoding="utf-8"))
            self.assertEqual(diag["status"], "incomplete")
            self.assertTrue(any("desconhecido" in e for e in diag["errors"]))
            self.assertFalse(os.path.exists(os.path.join(out, "map.json")))

    def test_cabecalho_duplicado_reprova(self):
        dup = EXPECTED_HEADER.copy()
        dup[1] = dup[0]
        buf = io.StringIO(newline="")
        w = csv.writer(buf, delimiter=";", quotechar='"', doublequote=True, lineterminator="\r\n")
        w.writerow(dup)
        w.writerow(["x"] * len(dup))
        with tempfile.TemporaryDirectory() as tmp:
            src = self._zip_case(tmp, "d.zip", [("csec.csv", buf.getvalue().encode("latin-1"))])
            out = os.path.join(tmp, "out")
            r = run_mapper(src, 2026, "MT", out)
            self.assertNotEqual(r.returncode, 0)
            diag = json.loads(Path(out, "diagnostic.partial.json").read_text(encoding="utf-8"))
            self.assertTrue(any("duplicado" in e for e in diag["errors"]))

    def test_linha_divergente_reprova_com_ordinal(self):
        buf = io.StringIO(newline="")
        w = csv.writer(buf, delimiter=";", quotechar='"', doublequote=True, lineterminator="\r\n")
        w.writerow(EXPECTED_HEADER)
        w.writerow(["x"] * (len(EXPECTED_HEADER) - 1))
        with tempfile.TemporaryDirectory() as tmp:
            src = self._zip_case(tmp, "c.zip", [("csec.csv", buf.getvalue().encode("latin-1"))])
            out = os.path.join(tmp, "out")
            r = run_mapper(src, 2026, "MT", out)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("registro 1", r.stderr)

    def test_zip_invalido_reprova(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src")
            os.makedirs(src)
            Path(src, "q.zip").write_bytes(b"isto nao e um zip")
            out = os.path.join(tmp, "out")
            r = run_mapper(src, 2026, "MT", out)
            self.assertNotEqual(r.returncode, 0)

    def test_zip_truncado_reprova(self):
        raw = fixture_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src")
            os.makedirs(src)
            zpath = os.path.join(src, "t.zip")
            with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("csec.csv", raw)
            # Trunca o arquivo físico.
            size = os.path.getsize(zpath)
            with open(zpath, "r+b") as f:
                f.truncate(size // 2)
            out = os.path.join(tmp, "out")
            r = run_mapper(src, 2026, "MT", out)
            self.assertNotEqual(r.returncode, 0)

    def test_nomes_repetidos_reprovam_sem_escolher(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src")
            os.makedirs(src)
            zpath = os.path.join(src, "d.zip")
            with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("a.txt", b"primeira")
                z.writestr("a.txt", b"segunda")
            out = os.path.join(tmp, "out")
            r = run_mapper(src, 2026, "MT", out)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("duplicado", r.stderr)

    def test_path_traversal_reprova(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src")
            os.makedirs(src)
            zpath = os.path.join(src, "t.zip")
            with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("../evil.txt", b"x")
            out = os.path.join(tmp, "out")
            r = run_mapper(src, 2026, "MT", out)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("inseguro", r.stderr)

    def test_saida_dentro_da_fonte_recusada(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src")
            os.makedirs(src)
            Path(src, "a.txt").write_text("oi", encoding="utf-8")
            r = run_mapper(src, 2026, "MT", os.path.join(src, "out"))
            self.assertNotEqual(r.returncode, 0)

    def test_limite_aplicado_reprova(self):
        with open(os.path.join(ROOT, "scripts", "limits.env"), encoding="utf-8") as f:
            base = f.read()
        with tempfile.TemporaryDirectory() as tmp:
            custom = os.path.join(tmp, "limits.env")
            Path(custom).write_text(base.replace("MAX_CSV_FIELDS=100", "MAX_CSV_FIELDS=4"))
            src = os.path.join(tmp, "src")
            os.makedirs(src)
            with zipfile.ZipFile(os.path.join(src, "l.zip"), "w",
                                 compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("x.csv", b'"A";"B";"C";"D";"E"\r\n"1";"2";"3";"4";"5"\r\n')
            out = os.path.join(tmp, "out")
            r = run_mapper(src, 2026, "MT", out, limits_file=custom)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("MAX_CSV_FIELDS", r.stderr)

    def test_limite_desconhecido_reprova(self):
        with tempfile.TemporaryDirectory() as tmp:
            custom = os.path.join(tmp, "limits.env")
            Path(custom).write_text("MAX_GIT_FILE_BYTES=1\n")
            src = os.path.join(tmp, "src")
            os.makedirs(src)
            Path(src, "a.txt").write_text("oi", encoding="utf-8")
            out = os.path.join(tmp, "out")
            # Carga de limites ausentes deve falhar com exit != 0.
            proc = subprocess.run(
                [sys.executable, "-c",
                 "import sys; sys.path.insert(0, 'scripts'); "
                 "import map_raw_data; map_raw_data.load_limits(%r)" % custom],
                capture_output=True, text=True, cwd=ROOT)
            self.assertNotEqual(proc.returncode, 0)

    def test_raiz_link_legitimo_ok_e_interno_reprovado(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = os.path.join(tmp, "real")
            os.makedirs(real)
            Path(real, "a.txt").write_text("dados", encoding="utf-8")
            link = os.path.join(tmp, "ligacao")
            os.symlink(real, link)
            out = os.path.join(tmp, "out1")
            r = run_mapper(link, 2026, "MT", out)
            self.assertEqual(r.returncode, 0, msg=r.stderr)
            # Link interno reprova.
            src2 = os.path.join(tmp, "src2")
            os.makedirs(src2)
            Path(src2, "real.txt").write_text("dados", encoding="utf-8")
            os.symlink(os.path.join(src2, "real.txt"), os.path.join(src2, "atalho.txt"))
            out2 = os.path.join(tmp, "out2")
            r2 = run_mapper(src2, 2026, "MT", out2)
            self.assertNotEqual(r2.returncode, 0)
            self.assertIn("symlink", r2.stderr)


class TestMetadadoVsBytes(unittest.TestCase):
    def test_bytes_completos_conferidos_e_amostra_sem_hash(self):
        raw = fixture_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src")
            os.makedirs(src)
            zpath = os.path.join(src, "a.zip")
            with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("csec.csv", raw)
                z.writestr("blob.dat", b"\x00\x01\x02\x03" * 100)
            out = os.path.join(tmp, "out")
            r = run_mapper(src, 2026, "MT", out)
            self.assertEqual(r.returncode, 0, msg=r.stderr)
            members = [json.loads(line) for line in
                       Path(out, "members.jsonl").read_text(encoding="utf-8").splitlines()]
            by_name = {m["name"]: m for m in members}
            csv_m = by_name["csec.csv"]
            # Metadado declarado preservado, hash calculado dos bytes completos.
            self.assertEqual(csv_m["declared_size"], len(raw))
            self.assertEqual(members[0]["member_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(csv_m["member_sha256"], hashlib.sha256(raw).hexdigest())
            dat_m = by_name["blob.dat"]
            # Leitura parcial/amostra não gera hash completo.
            self.assertIsNone(dat_m["member_sha256"])
            self.assertIn(dat_m["read_level"], ("sampled", "metadata_only"))


class TestDeterminismo(unittest.TestCase):
    def test_repeticao_byte_a_byte(self):
        raw = fixture_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src")
            os.makedirs(src)
            with zipfile.ZipFile(os.path.join(src, "a.zip"), "w",
                                 compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("csec.csv", raw)
            out1 = os.path.join(tmp, "out1")
            out2 = os.path.join(tmp, "out2")
            self.assertEqual(run_mapper(src, 2026, "MT", out1).returncode, 0)
            self.assertEqual(run_mapper(src, 2026, "MT", out2).returncode, 0)
            for fn in ("map.json", "members.jsonl"):
                h1 = hashlib.sha256(Path(out1, fn).read_bytes()).hexdigest()
                h2 = hashlib.sha256(Path(out2, fn).read_bytes()).hexdigest()
                self.assertEqual(h1, h2, msg=f"{fn} diverge entre execuções")



class TestRevisaoIntegridade(unittest.TestCase):
    def make_source(self, root, filename="a.zip", raw=None):
        source = Path(root) / "src"
        source.mkdir()
        with zipfile.ZipFile(source / filename, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("csec.csv", fixture_bytes() if raw is None else raw)
        return source

    def test_erro_de_travessia_nao_pode_virar_mapa_completo(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.make_source(tmp)
            restricted = source / "restrito"
            restricted.mkdir()
            (restricted / "dado.txt").write_bytes(fixture_bytes())
            restricted.chmod(0)
            try:
                result = run_mapper(str(source), 2026, "MT", str(Path(tmp) / "out"))
            finally:
                restricted.chmod(0o700)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertFalse((Path(tmp) / "out/map.json").exists())

    def test_saida_por_alias_na_fonte_e_recusada_antes_de_escrever(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.make_source(tmp)
            alias = Path(tmp) / "alias"
            alias.symlink_to(source, target_is_directory=True)
            result = run_mapper(str(source), 2026, "MT", str(alias / "reports"))
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((source / "reports").exists())

    def test_falha_em_reexecucao_retira_marcador_completo_anterior(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.make_source(tmp)
            out = Path(tmp) / "out"
            self.assertEqual(run_mapper(str(source), 2026, "MT", str(out)).returncode, 0)
            (source / "invalido.zip").write_bytes(fixture_bytes())
            result = run_mapper(str(source), 2026, "MT", str(out))
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((out / "map.json").exists())
            self.assertEqual(json.loads((out / "run.json").read_text())["success"], False)

    def test_zip_identificado_por_assinatura_sem_extensao_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.make_source(tmp, filename="arquivo.bin")
            out = Path(tmp) / "out"
            result = run_mapper(str(source), 2026, "MT", str(out))
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads((out / "map.json").read_text())
            self.assertEqual(data["coverage"]["csv_members"], 1)
            self.assertFalse(any("logd.dat" in item for item in data["limitations"]))

    def test_frequencias_de_escopo_sao_contadas_dos_registros(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.make_source(tmp)
            out = Path(tmp) / "out"
            result = run_mapper(str(source), 2026, "MT", str(out))
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads((out / "map.json").read_text())
            scopes = data["csv_profiles"][0]["scopes"]
            self.assertEqual(scopes["SG_UF"]["counts"], {"MT": 3})

    def test_campo_valido_acima_do_limite_padrao_do_python(self):
        rows = list(csv.reader(io.StringIO(fixture_bytes().decode("latin-1")), delimiter=";"))
        rows[1][EXPECTED_HEADER.index("NM_MUNICIPIO")] = "a" * 150000
        data = io.StringIO(newline="")
        writer = csv.writer(data, delimiter=";", lineterminator="\r\n")
        writer.writerows(rows)
        with tempfile.TemporaryDirectory() as tmp:
            source = self.make_source(tmp, raw=data.getvalue().encode("latin-1"))
            result = run_mapper(str(source), 2026, "MT", str(Path(tmp) / "out"))
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_caminhos_zip_ambiguos_e_absolutos_reprovam(self):
        for name in ("C:/csec.csv", "C:csec.csv", "./csec.csv", "sub//csec.csv"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp) / "src"
                source.mkdir()
                with zipfile.ZipFile(source / "a.zip", "w") as z:
                    z.writestr(name, fixture_bytes())
                result = run_mapper(str(source), 2026, "MT", str(Path(tmp) / "out"))
                self.assertNotEqual(result.returncode, 0)

    def test_falha_ao_gravar_recibo_nao_publica_sucesso(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self.make_source(tmp)
            out = Path(tmp) / "out"
            with mock.patch.object(M, "write_run", side_effect=OSError("falha injetada")):
                result = M.main(["--source", str(source), "--year", "2026", "--scope", "MT", "--output", str(out)])
            self.assertNotEqual(result, 0)
            self.assertFalse((out / "map.json").exists())



class TestLimitesEPublicacao(unittest.TestCase):
    def limits_file(self, root, **changes):
        lines = Path(ROOT, "scripts/limits.env").read_text().splitlines()
        text = "\n".join(line.split("=", 1)[0] + "=" + str(changes[line.split("=", 1)[0]])
                         if "=" in line and line.split("=", 1)[0] in changes else line
                         for line in lines) + "\n"
        path = Path(root) / "limits.env"
        path.write_text(text)
        return str(path)

    def make_source(self, root):
        source = Path(root) / "src"
        source.mkdir()
        path = source / "a.zip"
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as z:
            z.writestr("csec.csv", fixture_bytes())
        return source, path

    def test_falha_na_publicacao_preserva_geracao_anterior(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, _ = self.make_source(tmp)
            out = Path(tmp) / "out"
            self.assertEqual(run_mapper(str(source), 2026, "MT", str(out)).returncode, 0)
            original_map = (out / "map.json").read_bytes()
            original_members = (out / "members.jsonl").read_bytes()
            replace = os.replace
            def fail_report(src, dest):
                if Path(dest) == out / "report.md":
                    raise OSError("falha de publicação injetada")
                return replace(src, dest)
            with mock.patch.object(M.os, "replace", side_effect=fail_report):
                result = M.main(["--source", str(source), "--year", "2026", "--scope", "MT", "--output", str(out)])
            self.assertNotEqual(result, 0)
            self.assertFalse((out / "map.json").exists())
            previous = next(out.glob(".previous-*"))
            self.assertEqual((previous / "map.json").read_bytes(), original_map)
            self.assertEqual((previous / "members.jsonl").read_bytes(), original_members)
            self.assertFalse(json.loads((out / "run.json").read_text())["success"])
            self.assertEqual(list(out.glob(".staging-*")), [])

    def test_limite_registros_interrompe_e_nao_publica_contagem_parcial(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, _ = self.make_source(tmp)
            out = Path(tmp) / "out"
            config = self.limits_file(tmp, MAX_CSV_RECORDS=1)
            result = run_mapper(str(source), 2026, "MT", str(out), limits_file=config)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("MAX_CSV_RECORDS", result.stderr)
            self.assertFalse((out / "map.json").exists())

    def test_limite_considera_bytes_lexicais_e_newlines_em_campo(self):
        raw = fixture_bytes()
        rows = list(csv.reader(io.StringIO(raw.decode("latin-1")), delimiter=";"))
        values = sum(len(value) for value in rows[0]) + len(rows[0])
        with tempfile.TemporaryDirectory() as tmp:
            source, _ = self.make_source(tmp)
            config = self.limits_file(tmp, MAX_RECORD_BYTES=values)
            result = run_mapper(str(source), 2026, "MT", str(Path(tmp) / "out"), limits_file=config)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("MAX_RECORD_BYTES", result.stderr)

    def test_limite_de_bytes_retidos_de_escopo_e_aplicado(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, _ = self.make_source(tmp)
            config = self.limits_file(tmp, MAX_PROFILE_VALUE_BYTES=1)
            result = run_mapper(str(source), 2026, "MT", str(Path(tmp) / "out"), limits_file=config)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("MAX_PROFILE_VALUE_BYTES", result.stderr)

    def test_limite_expansao_sem_arredondar_para_baixo(self):
        raw = fixture_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            source.mkdir()
            path = source / "a.zip"
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("csec.csv", raw)
            comment_size = len(raw) - path.stat().st_size - 1
            self.assertGreater(comment_size, 0)
            with zipfile.ZipFile(path, "a") as z:
                z.comment = b"p" * comment_size
            self.assertGreater(len(raw), path.stat().st_size)
            self.assertLess(len(raw), path.stat().st_size * 2)
            config = self.limits_file(tmp, MAX_ZIP_EXPANSION_RATIO=1)
            result = run_mapper(str(source), 2026, "MT", str(Path(tmp) / "out"), limits_file=config)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("expansão", result.stderr)

    def test_csv_com_crc_corrompido_nao_recebe_hash_integral(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, path = self.make_source(tmp)
            blob = path.read_bytes()
            offset = blob.index(fixture_bytes())
            changed = bytearray(blob)
            changed[offset] ^= 1
            path.write_bytes(changed)
            out = Path(tmp) / "out"
            result = run_mapper(str(source), 2026, "MT", str(out))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CRC", result.stderr)
            self.assertFalse((out / "map.json").exists())

    def test_nome_zip_com_nul_nao_e_truncado_silenciosamente(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            source.mkdir()
            path = source / "a.zip"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("abcX.csv", fixture_bytes())
            path.write_bytes(path.read_bytes().replace(b"abcX.csv", b"abc\x00.csv"))
            result = run_mapper(str(source), 2026, "MT", str(Path(tmp) / "out"))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("truncado", result.stderr)

    def test_contagem_de_bytes_e_finais_de_linha_conferida(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, _ = self.make_source(tmp)
            out = Path(tmp) / "out"
            result = run_mapper(str(source), 2026, "MT", str(out))
            self.assertEqual(result.returncode, 0, result.stderr)
            profile = json.loads((out / "map.json").read_text())["csv_profiles"][0]
            raw = fixture_bytes()
            self.assertEqual(profile["member_bytes_read"], len(raw))
            self.assertEqual(profile["line_endings"]["CRLF"], raw.count(b"\r\n"))
            self.assertEqual(profile["line_endings"]["LF"], raw.count(b"\n") - raw.count(b"\r\n"))



class TestFidelidadeDoInventario(unittest.TestCase):
    def test_tamanho_declarado_falso_nao_recebe_fully_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.zip"
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("csec.csv", fixture_bytes())
            limits = M.load_limits(M.DEFAULT_LIMITS)
            with zipfile.ZipFile(path) as z:
                wrong = copy.copy(z.infolist()[0])
                wrong.file_size += 1
                with self.assertRaisesRegex(M.MappingError, "tamanho lido diverge"):
                    M.profile_csv_member(z, wrong, 0, path.name,
                                         hashlib.sha256(path.read_bytes()).hexdigest(), limits, [])

    def test_diretorio_vazio_com_nome_nao_utf8_reprova(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            source.mkdir()
            os.mkdir(os.fsencode(source) + b"/\xff")
            result = run_mapper(str(source), 2026, "MT", str(Path(tmp) / "out"))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("sem perda", result.stderr)

    def test_link_em_destino_de_artefato_nao_altera_fonte(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src"
            source.mkdir()
            original = source / "dados.txt"
            raw = fixture_bytes()
            original.write_bytes(raw)
            out = Path(tmp) / "out"
            out.mkdir()
            (out / "run.json").symlink_to(original)
            result = run_mapper(str(source), 2026, "MT", str(out))
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(original.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
