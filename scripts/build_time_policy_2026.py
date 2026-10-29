#!/usr/bin/env python3
"""Materializa política de relógio nominal a partir do índice municipal oficial.

Deslocamentos documentados pelas páginas TSE/TRE de 2026. Não prova ajuste
físico de relógio de cada urna. Nomes servem só para resolver códigos oficiais.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import unicodedata

from acquire_2026 import write_json
from prepare_audit_2026 import UFS

AM_ACRE = {"AMATURA", "ATALAIA DO NORTE", "BENJAMIN CONSTANT", "EIRUNEPE", "ENVIRA",
           "GUAJARA", "IPIXUNA", "ITAMARATI", "JUTAI", "SAO PAULO DE OLIVENCA", "TABATINGA"}
SOURCES = [
    "https://www.tre-am.jus.br/comunicacao/noticias/2026/Setembro/eleitorado-do-amazonas-deve-ficar-atento-aos-horarios-de-votacao-nas-eleicoes-2026",
    "https://www.tre-pe.jus.br/comunicacao/noticias/2026/Setembro/faltam-26-dias-votacao-comeca-e-termina-no-mesmo-horario-em-todo-o-pais",
    "https://www.tse.jus.br/legislacao/compilada/res/2026/resolucao-no-23-751-de-26-de-fevereiro-de-2026",
]


def normalize(value):
    return "".join(c for c in unicodedata.normalize("NFKD", value.upper()) if not unicodedata.combining(c))


def build(index):
    if {a["cd"].upper() for a in index["abr"]} != UFS:
        raise ValueError("índice municipal com cobertura diferente da esperada")
    shifts = {uf: 0 for uf in UFS if uf != "ZZ"}
    shifts.update({uf: 3600 for uf in ("AM", "MT", "MS", "RO", "RR")})
    shifts["AC"] = 7200
    shifts["ZZ"] = None
    overrides, found, noronha = {}, set(), []
    for state in index["abr"]:
        uf = state["cd"].upper()
        for municipality in state["mu"]:
            name = normalize(municipality["nm"])
            identity = f"{uf}/{int(municipality['cd']):05d}"
            if identity in overrides:
                raise ValueError("código municipal repetido na política")
            if uf == "AM" and name in AM_ACRE:
                overrides[identity] = 7200
                found.add(name)
            if uf == "PE" and name == "FERNANDO DE NORONHA":
                overrides[identity] = -3600
                noronha.append(identity)
    if found != AM_ACRE or len(noronha) != 1:
        raise ValueError(f"exceções municipais incompletas: AM faltantes={sorted(AM_ACRE-found)}, Noronha={noronha}")
    return {"format_version": 1,
            "scope": "2026, horário civil nominal convertido para Brasília; exterior não integra contagem BRT",
            "brt_shift_seconds_by_uf": shifts, "municipality_overrides": overrides,
            "sources": SOURCES,
            "assumption": "timestamp do log corresponde ao relógio local nominal da seção; não atesta sincronização física. Ajustes/erros de relógio requerem evidência própria.",
            "outside_brazil": "ZZ: sem deslocamento nacional BRT; métricas de horário BRT excluem essa abrangência explicitamente"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--municipalities", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    raw = args.municipalities.read_bytes()
    result = build(json.loads(raw))
    result["municipalities_index_sha256"] = hashlib.sha256(raw).hexdigest()
    write_json(args.output, result)
    print("política nominal: códigos municipais resolvidos a partir do índice oficial, exceções conferidas")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"política reprovada: {exc}", file=sys.stderr)
        sys.exit(1)
