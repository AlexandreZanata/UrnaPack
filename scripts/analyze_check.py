#!/usr/bin/env python3
"""Verificação independente da análise descritiva da BU web (Etapa 5A).

Lê o CSV restaurado com csv/collections da stdlib e recalcula os agregados do
`tsepack analyze` sem chamar funções Rust. Também recalcula Q1/Q2 e compara com
uma referência anterior, quando fornecida.
"""

import argparse
import collections
import csv
import hashlib
import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
U64_MAX = (1 << 64) - 1
OCCURRENCE_FIELDS = (
    "ANO_ELEICAO", "CD_PLEITO", "CD_ELEICAO", "NR_TURNO", "SG_UF",
    "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "CD_CARGO_PERGUNTA", "NR_VOTAVEL",
)
CONTEXT_FIELDS = (
    "ANO_ELEICAO", "CD_PLEITO", "CD_ELEICAO", "NR_TURNO", "SG_UF",
    "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "CD_CARGO_PERGUNTA",
)
CONTEXT_EQUALITY_FIELDS = (
    "DT_BU_RECEBIDO", "QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES",
    "CD_TIPO_URNA", "DS_TIPO_URNA", "NR_LOCAL_VOTACAO", "NR_URNA_EFETIVADA",
    "CD_CARGA_1_URNA_EFETIVADA", "CD_CARGA_2_URNA_EFETIVADA",
    "CD_FLASHCARD_URNA_EFETIVADA", "DT_CARGA_URNA_EFETIVADA",
    "DS_CARGO_PERGUNTA_SECAO", "DS_SECOES_AGREGADAS", "DT_ABERTURA",
    "DT_ENCERRAMENTO", "QT_ELEI_BIOM_SEM_HABILITACAO", "DT_EMISSAO_BU",
    "NR_JUNTA_APURADORA", "NR_TURMA_APURADORA",
)
SENTINELS = {"#NULO", "#NULO#", "#NE", "#NE#", "-1", "-3", ""}


def load_limits():
    path = Path(os.environ.get("URNAPACK_LIMITS_FILE", ROOT / "scripts/limits.env"))
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def ratio(numerator, denominator):
    if denominator == 0:
        return None, "denominator_zero"
    scaled = (numerator * 1_000_000 + denominator // 2) // denominator
    return f"{scaled // 1_000_000}.{scaled % 1_000_000:06d}", None


def add_checked(target, value):
    total = target + value
    if total > U64_MAX:
        return None
    return total


class Checker:
    def __init__(self, limits):
        self.limits = limits
        self.errors = []
        self.records = 0
        self.votes_office = collections.defaultdict(int)
        self.votes_office_category = collections.defaultdict(int)
        self.votes_office_municipality_category = collections.defaultdict(int)
        self.occurrences = {}
        self.q1 = collections.defaultdict(int)
        self.duplicates = 0
        self.repeated = 0
        self.conflicts = 0
        self.contexts = {}
        self.context_divergences = 0
        self.context_divergence_rows = 0
        self.zero_denominator_groups = 0
        self.arithmetic_checked = 0
        self.arithmetic_failures = 0
        self.sentinels = collections.defaultdict(collections.Counter)
        self.municipality_names = {}
        self.municipality_name_conflicts = 0
        self.zones = set()
        self.municipalities = set()
        self.parties = set()
        self.columns = {}
        self.parse_errors = 0
        self.votes_overflow = False

    def fail(self, detail):
        self.errors.append(detail)

    def accept(self, row, index, columns):
        self.records += 1
        max_records = int(self.limits["MAX_CSV_RECORDS"])
        if self.records > max_records:
            self.fail(f"MAX_CSV_RECORDS excedido no registro {self.records}")
        for name in columns["header"]:
            if len(row[columns[name]]) > int(self.limits["MAX_FIELD_BYTES"]):
                self.fail(f"MAX_FIELD_BYTES excedido no registro {self.records}")
        for name, position in columns.items():
            if name == "header":
                continue
            value = row[position]
            if value in SENTINELS:
                self.sentinels[name][value] += 1

        def value(name):
            return row[columns[name]]

        try:
            aptos = int(value("QT_APTOS"))
            comparecimento = int(value("QT_COMPARECIMENTO"))
            abstencoes = int(value("QT_ABSTENCOES"))
            votes = int(value("QT_VOTOS"))
        except ValueError:
            self.parse_errors += 1
            self.fail(f"inteiro inválido no registro {self.records}")
            return
        if any(item < 0 or item > U64_MAX for item in (aptos, comparecimento, abstencoes, votes)):
            self.parse_errors += 1
            self.fail(f"inteiro fora de u64 no registro {self.records}")
            return

        self.arithmetic_checked += 1
        if comparecimento + abstencoes != aptos:
            self.arithmetic_failures += 1
            self.fail(f"aritmética divergente no registro {self.records}")

        occurrence_key = tuple(value(name) for name in OCCURRENCE_FIELDS)
        digest = hashlib.sha256()
        for item in row:
            encoded = item.encode("latin-1")
            digest.update(len(encoded).to_bytes(4, "little"))
            digest.update(encoded)
        digest = digest.digest()
        if occurrence_key in self.occurrences:
            self.duplicates += 1
            if self.occurrences[occurrence_key] == digest:
                self.repeated += 1
            else:
                self.conflicts += 1
        else:
            if len(self.occurrences) >= int(self.limits["MAX_BWEB_OCCURRENCE_KEYS"]):
                self.fail("MAX_BWEB_OCCURRENCE_KEYS excedido")
            self.occurrences[occurrence_key] = digest

        context_key = tuple(value(name) for name in CONTEXT_FIELDS)
        equality = tuple(value(name) for name in CONTEXT_EQUALITY_FIELDS)
        if context_key in self.contexts:
            first = self.contexts[context_key]
            if not first["divergent"] and first["equality"] != equality:
                first["divergent"] = True
                self.context_divergences += 1
                self.context_divergence_rows += 1
        else:
            if len(self.contexts) >= int(self.limits["MAX_BWEB_OCCURRENCE_KEYS"]):
                self.fail("limite de contextos excedido")
            self.contexts[context_key] = {
                "first_record": self.records,
                "equality": equality,
                "aptos": aptos,
                "comparecimento": comparecimento,
                "abstencoes": abstencoes,
                "divergent": False,
            }
            if aptos == 0:
                self.zero_denominator_groups += 1

        cargo = value("CD_CARGO_PERGUNTA")
        municipality = value("CD_MUNICIPIO")
        municipality_name = value("NM_MUNICIPIO")
        if municipality in self.municipality_names:
            if self.municipality_names[municipality] != municipality_name:
                self.municipality_name_conflicts += 1
        else:
            self.municipality_names[municipality] = municipality_name
        self.municipalities.add(municipality)
        self.zones.add((municipality, value("NR_ZONA")))
        self.q1[(cargo, value("SG_UF"), municipality)] += votes
        party = value("NR_PARTIDO")
        if party not in SENTINELS:
            self.parties.add(party)
        category_code = value("CD_TIPO_VOTAVEL")
        category_name = value("DS_TIPO_VOTAVEL")
        if add_checked(self.votes_office[cargo], votes) is None:
            self.votes_overflow = True
            self.fail(f"overflow de votos no registro {self.records}")
        else:
            self.votes_office[cargo] += votes
        office_category = (cargo, category_code, category_name)
        if add_checked(self.votes_office_category[office_category], votes) is None:
            self.votes_overflow = True
            self.fail(f"overflow de votos por categoria no registro {self.records}")
        else:
            self.votes_office_category[office_category] += votes
        office_municipality = (cargo, municipality, category_code, category_name)
        if add_checked(
            self.votes_office_municipality_category[office_municipality], votes
        ) is None:
            self.votes_overflow = True
            self.fail(f"overflow de votos por município no registro {self.records}")
        else:
            self.votes_office_municipality_category[office_municipality] += votes


def parse_csv(path, limits):
    checker = Checker(limits)
    with open(path, "rb") as raw:
        reader = csv.reader(
            io.TextIOWrapper(raw, encoding="latin-1", newline=""),
            delimiter=";",
            quotechar='"',
            doublequote=True,
            strict=True,
        )
        header = next(reader)
        if len(header) != 45:
            raise SystemExit(f"cabeçalho com {len(header)} campos, esperado 45")
        columns = {name: position for position, name in enumerate(header)}
        columns["header"] = header
        checker.columns = columns
        for index, row in enumerate(reader, start=1):
            if len(row) != 45:
                raise SystemExit(f"registro {index} com {len(row)} campos")
            checker.accept(row, index, columns)
    return header, columns, checker


def compare_rows(label, expected, actual, key_fields, checks):
    expected_map = {}
    for row in expected:
        key = tuple(row[field] for field in key_fields)
        if key in expected_map:
            checks.append({"check": f"{label}_duplicate_key", "ok": False, "detail": str(key)})
        expected_map[key] = row
    actual_map = {}
    for row in actual:
        key = tuple(row[field] for field in key_fields)
        actual_map[key] = row
    if set(expected_map) != set(actual_map):
        missing = sorted(set(expected_map) - set(actual_map))[:5]
        extra = sorted(set(actual_map) - set(expected_map))[:5]
        checks.append(
            {
                "check": label,
                "ok": False,
                "detail": f"chaves divergentes; faltando={missing} extras={extra}",
            }
        )
        return
    for key, expected_row in expected_map.items():
        actual_row = actual_map[key]
        if expected_row != actual_row:
            checks.append(
                {
                    "check": label,
                    "ok": False,
                    "detail": f"linha {key}: esperado={expected_row} obtido={actual_row}",
                }
            )
            return
    checks.append({"check": label, "ok": True, "detail": f"{len(expected_map)} linhas"})


def context_aggregate(checker):
    offices = collections.defaultdict(lambda: [0, 0, 0, 0])
    municipalities = collections.defaultdict(lambda: [0, 0, 0, 0])
    zones = collections.defaultdict(lambda: [0, 0, 0, 0])
    for key, entry in checker.contexts.items():
        cargo, municipality, zone = key[8], key[5], key[6]
        for target in (
            offices[cargo],
            municipalities[(cargo, municipality)],
            zones[(cargo, municipality, zone)],
        ):
            target[0] += 1
            target[1] += entry["aptos"]
            target[2] += entry["comparecimento"]
            target[3] += entry["abstencoes"]
    rows = []
    for (cargo,), values in sorted(offices.items()):
        rows.append(context_row(cargo, "", "", values))
    for (cargo, municipality), values in sorted(municipalities.items()):
        rows.append(
            context_row(
                cargo,
                municipality,
                checker.municipality_names.get(municipality, ""),
                values,
            )
        )
    for (cargo, municipality, zone), values in sorted(zones.items()):
        rows.append(
            context_row(
                cargo,
                municipality,
                checker.municipality_names.get(municipality, ""),
                values,
                zone=zone,
            )
        )
    return rows


def context_row(cargo, municipality, municipality_name, values, zone=""):
    groups, aptos, comparecimento, abstencoes = values
    rate, reason = ratio(comparecimento, aptos)
    abst_rate, abst_reason = ratio(abstencoes, aptos)
    return {
        "cargo": cargo,
        "municipio": municipality or None,
        "municipio_nome": municipality_name or None,
        "zona": zone or None,
        "grupos_contexto": groups,
        "aptos": str(aptos),
        "comparecimento": str(comparecimento),
        "abstencoes": str(abstencoes),
        "comparecimento_por_aptos": rate,
        "comparecimento_por_aptos_motivo": reason,
        "abstencao_por_aptos": abst_rate,
        "abstencao_por_aptos_motivo": abst_reason,
    }


def verify_reference_queries(checker, reference, checks):
    q1_map = checker.q1
    q1 = [
        {"key": [cargo, uf, municipality], "votes": str(votes)}
        for (cargo, uf, municipality), votes in sorted(q1_map.items())
    ]
    expected_q1 = [
        {"key": item["key"], "votes": item["votes"]} for item in reference["q1"]
    ]
    checks.append(
        {
            "check": "reference_q1",
            "ok": q1 == expected_q1,
            "detail": f"{len(q1)} grupos",
        }
    )
    q2_map = collections.defaultdict(
        lambda: {"sections": 0, "aptos": 0, "comparecimento": 0, "abstencoes": 0}
    )
    for key, entry in checker.contexts.items():
        if key[8] != "1":
            continue
        q2_key = (key[4], key[5], key[6])
        target = q2_map[q2_key]
        target["sections"] += 1
        target["aptos"] += entry["aptos"]
        target["comparecimento"] += entry["comparecimento"]
        target["abstencoes"] += entry["abstencoes"]
    q2 = [
        {
            "key": [uf, municipality, zone],
            "sections": entry["sections"],
            "aptos": str(entry["aptos"]),
            "comparecimento": str(entry["comparecimento"]),
            "abstencoes": str(entry["abstencoes"]),
        }
        for (uf, municipality, zone), entry in sorted(q2_map.items())
    ]
    expected_q2 = [
        {
            "key": item["key"],
            "sections": item["sections"],
            "aptos": item["aptos"],
            "comparecimento": item["comparecimento"],
            "abstencoes": item["abstencoes"],
        }
        for item in reference["q2_presidente"]
    ]
    checks.append(
        {
            "check": "reference_q2_presidente",
            "ok": q2 == expected_q2,
            "detail": f"{len(q2)} zonas",
        }
    )

def main(argv=None):
    parser = argparse.ArgumentParser(description="Verificação independente da análise MT t1.")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--quality", required=True)
    parser.add_argument("--reference", default=None)
    parser.add_argument("--expected-sha256", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)
    limits = load_limits()
    checks = []
    observed_sha = sha256_file(args.csv)
    checks.append(
        {
            "check": "csv_sha256",
            "ok": args.expected_sha256 is None or observed_sha == args.expected_sha256,
            "detail": observed_sha,
        }
    )
    header, _columns, checker = parse_csv(args.csv, limits)
    results = json.loads(Path(args.results).read_text(encoding="utf-8"))
    quality = json.loads(Path(args.quality).read_text(encoding="utf-8"))
    checks.append(
        {
            "check": "records",
            "ok": checker.records == results["source"]["records"] == quality["source"]["records"],
            "detail": str(checker.records),
        }
    )
    checks.append(
        {
            "check": "source_hash",
            "ok": results["source"]["csv_sha256"] == observed_sha,
            "detail": observed_sha,
        }
    )
    checks.append(
        {
            "check": "header",
            "ok": header
            == [
                "DT_GERACAO", "HH_GERACAO", "ANO_ELEICAO", "CD_TIPO_ELEICAO",
                "NM_TIPO_ELEICAO", "CD_PLEITO", "DT_PLEITO", "NR_TURNO",
                "CD_ELEICAO", "DS_ELEICAO", "SG_UF", "CD_MUNICIPIO",
                "NM_MUNICIPIO", "NR_ZONA", "NR_SECAO", "NR_LOCAL_VOTACAO",
                "CD_CARGO_PERGUNTA", "DS_CARGO_PERGUNTA", "NR_PARTIDO",
                "SG_PARTIDO", "NM_PARTIDO", "DT_BU_RECEBIDO", "QT_APTOS",
                "QT_COMPARECIMENTO", "QT_ABSTENCOES", "CD_TIPO_URNA",
                "DS_TIPO_URNA", "CD_TIPO_VOTAVEL", "DS_TIPO_VOTAVEL",
                "NR_VOTAVEL", "NM_VOTAVEL", "QT_VOTOS", "NR_URNA_EFETIVADA",
                "CD_CARGA_1_URNA_EFETIVADA", "CD_CARGA_2_URNA_EFETIVADA",
                "CD_FLASHCARD_URNA_EFETIVADA", "DT_CARGA_URNA_EFETIVADA",
                "DS_CARGO_PERGUNTA_SECAO", "DS_SECOES_AGREGADAS", "DT_ABERTURA",
                "DT_ENCERRAMENTO", "QT_ELEI_BIOM_SEM_HABILITACAO",
                "DT_EMISSAO_BU", "NR_JUNTA_APURADORA", "NR_TURMA_APURADORA",
            ],
            "detail": f"{len(header)} campos",
        }
    )
    expected_office = [
        {"cargo": cargo, "votos": str(votes)}
        for cargo, votes in sorted(checker.votes_office.items())
    ]
    actual_office = [
        {"cargo": row["cargo"], "votos": row["votos"]}
        for row in results["votes"]["by_office"]
    ]
    checks.append(
        {
            "check": "votes_by_office",
            "ok": expected_office == actual_office,
            "detail": f"{len(expected_office)} cargos",
        }
    )
    expected_category = [
        {
            "cargo": cargo,
            "categoria_codigo": code,
            "categoria": description,
            "votos": str(votes),
        }
        for (cargo, code, description), votes in sorted(
            checker.votes_office_category.items()
        )
    ]
    actual_category = [
        {
            "cargo": row["cargo"],
            "categoria_codigo": row["categoria_codigo"],
            "categoria": row["categoria"],
            "votos": row["votos"],
        }
        for row in results["votes"]["by_office_category"]
    ]
    checks.append(
        {
            "check": "votes_by_office_category",
            "ok": expected_category == actual_category,
            "detail": f"{len(expected_category)} grupos",
        }
    )
    municipality_totals = collections.defaultdict(int)
    for (cargo, municipality, _code, _description), votes in (
        checker.votes_office_municipality_category.items()
    ):
        municipality_totals[(cargo, municipality)] += votes
    expected_municipality = []
    for (cargo, municipality, code, description), votes in sorted(
        checker.votes_office_municipality_category.items()
    ):
        total = municipality_totals[(cargo, municipality)]
        fraction, reason = ratio(votes, total)
        expected_municipality.append(
            {
                "cargo": cargo,
                "municipio": municipality,
                "categoria_codigo": code,
                "categoria": description,
                "votos": str(votes),
                "total_cargo_municipio": str(total),
                "fracao": fraction,
                "fracao_motivo": reason,
            }
        )
    actual_municipality = [
        {
            "cargo": row["cargo"],
            "municipio": row["municipio"],
            "categoria_codigo": row["categoria_codigo"],
            "categoria": row["categoria"],
            "votos": row["votos"],
            "total_cargo_municipio": row["total_cargo_municipio"],
            "fracao": row["fracao"],
            "fracao_motivo": row["fracao_motivo"],
        }
        for row in results["votes"]["by_office_municipality"]
    ]
    checks.append(
        {
            "check": "votes_by_office_municipality",
            "ok": expected_municipality == actual_municipality,
            "detail": f"{len(expected_municipality)} grupos",
        }
    )
    context_rows = context_aggregate(checker)
    expected_office_context = [
        row
        for row in context_rows
        if row["municipio"] is None
    ]
    actual_office_context = [
        {
            "cargo": row["cargo"],
            "municipio": row["municipio"],
            "municipio_nome": row["municipio_nome"],
            "zona": row["zona"],
            "grupos_contexto": row["grupos_contexto"],
            "aptos": row["aptos"],
            "comparecimento": row["comparecimento"],
            "abstencoes": row["abstencoes"],
            "comparecimento_por_aptos": row["comparecimento_por_aptos"],
            "comparecimento_por_aptos_motivo": row["comparecimento_por_aptos_motivo"],
            "abstencao_por_aptos": row["abstencao_por_aptos"],
            "abstencao_por_aptos_motivo": row["abstencao_por_aptos_motivo"],
        }
        for row in results["context"]["by_office"]
    ]
    checks.append(
        {
            "check": "context_by_office",
            "ok": expected_office_context == actual_office_context,
            "detail": f"{len(expected_office_context)} cargos",
        }
    )
    expected_context_municipality = [
        row for row in context_rows if row["municipio"] is not None and row["zona"] is None
    ]
    actual_context_municipality = [
        {
            key: row[key]
            for key in [
                "cargo", "municipio", "municipio_nome", "zona", "grupos_contexto",
                "aptos", "comparecimento", "abstencoes", "comparecimento_por_aptos",
                "comparecimento_por_aptos_motivo", "abstencao_por_aptos",
                "abstencao_por_aptos_motivo",
            ]
        }
        for row in results["context"]["by_office_municipality"]
    ]
    checks.append(
        {
            "check": "context_by_office_municipality",
            "ok": expected_context_municipality == actual_context_municipality,
            "detail": f"{len(expected_context_municipality)} grupos",
        }
    )
    expected_context_zone = [row for row in context_rows if row["zona"] is not None]
    actual_context_zone = [
        {
            key: row[key]
            for key in [
                "cargo", "municipio", "municipio_nome", "zona", "grupos_contexto",
                "aptos", "comparecimento", "abstencoes", "comparecimento_por_aptos",
                "comparecimento_por_aptos_motivo", "abstencao_por_aptos",
                "abstencao_por_aptos_motivo",
            ]
        }
        for row in results["context"]["by_office_zone"]
    ]
    checks.append(
        {
            "check": "context_by_office_zone",
            "ok": expected_context_zone == actual_context_zone,
            "detail": f"{len(expected_context_zone)} grupos",
        }
    )
    checks.append(
        {
            "check": "keys",
            "ok": (
                quality["keys"]["duplicate_keys"] == checker.duplicates
                and quality["keys"]["repeated_occurrences"] == checker.repeated
                and quality["keys"]["conflicts"] == checker.conflicts
                and quality["keys"]["distinct_occurrences"] == len(checker.occurrences)
            ),
            "detail": f"duplicatas={checker.duplicates}",
        }
    )
    checks.append(
        {
            "check": "context",
            "ok": (
                quality["context"]["groups"] == len(checker.contexts)
                and quality["context"]["divergent_groups"] == checker.context_divergences
                and quality["context"]["zero_denominator_groups"]
                == checker.zero_denominator_groups
                and quality["context"]["arithmetic_checked"] == checker.arithmetic_checked
                and quality["context"]["arithmetic_failures"] == checker.arithmetic_failures
            ),
            "detail": f"grupos={len(checker.contexts)}",
        }
    )
    checks.append(
        {
            "check": "coverage",
            "ok": (
                quality["coverage"]["municipalities"] == len(checker.municipalities)
                and quality["coverage"]["zones"] == len(checker.zones)
                and quality["coverage"]["context_groups"] == len(checker.contexts)
                and quality["coverage"]["parties"] == len(checker.parties)
                and quality["coverage"].get("municipality_name_conflicts", 0)
                == checker.municipality_name_conflicts
            ),
            "detail": (
                f"municípios={len(checker.municipalities)} zonas={len(checker.zones)} "
                f"contextos={len(checker.contexts)} conflitos_nome={checker.municipality_name_conflicts}"
            ),
        }
    )
    sentinels = {
        column: dict(sorted(values.items()))
        for column, values in sorted(checker.sentinels.items())
    }
    checks.append(
        {
            "check": "sentinels",
            "ok": sentinels == quality["sentinels"],
            "detail": f"{len(sentinels)} colunas",
        }
    )
    aggregated = collections.Counter(
        entry["equality"][13] for entry in checker.contexts.values()
    )
    limit = int(checker.limits.get("MAX_ANALYZE_DISTINCT_VALUES", "2000"))
    distinct = len(aggregated)
    overflow = max(0, distinct - limit)
    expected_aggregated = [
        {"code": value, "name": value, "count": count}
        for value, count in sorted(aggregated.items())[:limit]
    ]
    ds_quality = quality["ds_secoes_agregadas"]
    checks.append(
        {
            "check": "ds_secoes_agregadas",
            "ok": (
                ds_quality["distinct_values"] == distinct
                and ds_quality.get("values_overflow", 0) == overflow
                and ds_quality["values"] == expected_aggregated
            ),
            "detail": f"{distinct} valores, overflow={overflow}",
        }
    )
    if args.reference:
        reference = json.loads(Path(args.reference).read_text(encoding="utf-8"))
        verify_reference_queries(checker, reference, checks)
    success = all(check["ok"] for check in checks)
    report = {
        "artifact_kind": "bweb_independent_check",
        "format_version": 1,
        "csv": str(args.csv),
        "csv_sha256": observed_sha,
        "records": checker.records,
        "success": success,
        "checks": checks,
        "errors": checker.errors,
    }
    output = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    if not success:
        print("analyze_check: divergência entre análise e recálculo independente", file=sys.stderr)
        return 1
    print(f"analyze_check: OK ({checker.records} registros, {len(checks)} verificações)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
