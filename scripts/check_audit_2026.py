#!/usr/bin/env python3
"""Confere saída Rust contra totalização oficial e afirmações transcritas.

Discordância com imagem é resultado da auditoria, não falha de execução.
Divergência BU x totalização ou inconsistência interna reprova com exit != 0.
"""
import argparse
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import sys

from acquire_2026 import write_json
from prepare_audit_2026 import UFS


def percent(votes, candidate="13"):
    total = votes.get("13", 0) + votes.get("22", 0)
    if not total:
        return None
    return str((Decimal(votes.get(candidate, 0)) * 100 / Decimal(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def check(report, official):
    if report["format_version"] != 1 or official["ele"] != "6258" or official["t"] != "2":
        raise ValueError("versão/eleição/turno divergente")
    if set(report["by_uf"]) != UFS:
        raise ValueError("cobertura de UFs incompleta")
    observed = report["presidential"]
    candidates = {}
    for cargo in official["carg"]:
        if cargo["cd"] != "1":
            continue
        for group in cargo["agr"]:
            for party in group["par"]:
                for candidate in party["cand"]:
                    number = candidate["n"]
                    if number in candidates:
                        raise ValueError("candidato duplicado no JSON de totalização")
                    candidates[number] = int(candidate["vap"])
    expected = dict(candidates, **{"95": int(official["v"]["vb"]), "96": int(official["v"]["tvn"])})
    if observed["votes"] != expected or observed["turnout"] != int(official["e"]["c"]):
        raise ValueError("BU x totalização: votos/comparecimento divergentes")
    if sum(observed["votes"].values()) != observed["turnout"]:
        raise ValueError("soma de categorias != comparecimento")
    if sum(item["sections"] for item in report["raw_minute_windows"].values()) + report["closing_missing"] != observed["sections"]:
        raise ValueError("partição temporal perde ou duplica seções")
    assertions = []

    def exact(identifier, page, text, claimed, value, method):
        assertions.append({"id": identifier, "page": page, "claim": text, "claimed": claimed,
                           "observed": value, "status": "reproduzido" if claimed == value else "não reproduzido nesta definição",
                           "method": method})

    exact("N01", 1, "Seções processadas", 499205, observed["sections"], "chave completa de seção/cargo/eleição; não linhas CSV")
    exact("N02", 1, "Votos apurados", 128236074, observed["turnout"], "soma dos votos de todos os tipos presidenciais; confronto com JSON nacional")
    minute = report["raw_minute_windows"]
    early = minute["ate_17h00m59s"]
    exact("N03", 2, "Flávio com 52,39% até 17h00", "52.39", percent(early["votes"], "22"), "inclui o minuto inteiro, até 17:00:59; sem ajuste de fuso")
    for identifier, key, claimed_sections, claimed_turnout, claimed_share in [
        ("N04", "17h01m00s_ate_17h15m59s", 339593, 88071750, "53.46"),
        ("N05", "17h16m00s_ate_18h59m59s", 2472, 674799, "57.16"),
    ]:
        window = minute[key]
        exact(identifier + "a", 3, key + ": seções", claimed_sections, window["sections"], "horário lexical, fronteiras explícitas")
        exact(identifier + "b", 3, key + ": eleitores", claimed_turnout, window["turnout"], "comparecimento somado uma vez por seção presidencial")
        exact(identifier + "c", 3, key + ": % Lula", claimed_share, percent(window["votes"]), "votos 13 / (13+22), arredondado a duas casas")
    late = minute["desde_19h00m00s"]
    exact("N06a", 3, "Após 19h: seções (corte >=19:00:00)", 6333, late["sections"], ">=19:00:00; cenário >19:00:00 também publicado no relatório Rust")
    exact("N06b", 3, "Após 19h: eleitores (corte >=19:00:00)", 1856306, late["turnout"], "comparecimento de todas as seções nesse corte")
    for uf, claimed_sections, share in [("BA", 936, "72.31"), ("PE", 657, "65.70"), ("MA", None, "83.31"), ("SP", 1571, "57.46")]:
        value = report["raw_after_19_by_uf"][uf]
        if claimed_sections is not None:
            exact("N07-" + uf + "a", 3, uf + ": seções desde 19h", claimed_sections, value["sections"], ">=19:00:00 lexical")
        exact("N07-" + uf + "b", 3, uf + ": % Lula", share, percent(value["votes"]), "votos válidos, não comparecimento total")
    exact("N08", 3, "Eleitores com biometria não habilitados por ela", 8632488, observed["biometric_not_enabled"], "QT_ELEI_BIOM_SEM_HABILITACAO uma vez por seção presidencial")
    exact("N09", 3, "6,73% do comparecimento", "6.73", str((Decimal(observed["biometric_not_enabled"]) * 100 / Decimal(observed["turnout"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)), "eleitores / comparecimento, não votos de candidato")
    margin = observed["votes"]["13"] - observed["votes"]["22"]
    exact("N10", 3, "Margem final", 4430191, margin, "votos nominais 13 menos votos nominais 22")
    for number in ("13", "22"):
        exact("N11-" + number, 4, "100% válidos, candidato " + number, 106 if number == "13" else 4,
              report["extremes"]["unanimity_" + number], "válidos >0 e votos do candidato == válidos")
        exact("N12-" + number, 4, "Mais de 90%, candidato " + number, 6899 if number == "13" else 384,
              report["extremes"]["above_90_" + number], "desigualdade estrita: 10*votos > 9*válidos; >=90% publicado separadamente")
    return {"format_version": 1, "bu_vs_totalization": "matched_votes_and_turnout",
            "section_count_note": {"BU_presidential_keys": observed["sections"], "official_s_object": official["s"],
                                   "status": "universo presidencial; conciliação geográfica ampliada documentada em cobertura-secoes.json"},
            "numeric_assertions": assertions,
            "derived": {"early_flavio_margin_through_17_00_59": early["votes"]["22"]-early["votes"]["13"],
                        "lula_margin_after_17_00_59_known_closing": sum(v["votes"].get("13",0)-v["votes"].get("22",0) for k,v in minute.items() if k != "ate_17h00m59s"),
                        "biometric_to_margin_ratio": str(Decimal(observed["biometric_not_enabled"])/Decimal(margin)),
                        "turnout_without_closing_time": observed["turnout"]-sum(v["turnout"] for v in minute.values()),
                        "turnout_since_17_16": minute["17h16m00s_ate_18h59m59s"]["turnout"] + late["turnout"]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--official", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = check(json.loads(args.report.read_text()), json.loads(args.official.read_text()))
    result["inputs_sha256"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.report, args.official)}
    write_json(args.output, result)
    print("BU x totalização: votos e comparecimento coincidem; afirmações comparadas individualmente")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"conferência reprovada: {exc}", file=sys.stderr)
        sys.exit(1)
