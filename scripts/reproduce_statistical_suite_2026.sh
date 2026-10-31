#!/usr/bin/env bash
# Fontes pequenas já tratadas: sections.csv, politica-relogio-nominal-2026.json,
# logs-nacional.json. Tamanhos/hashes continuam fixados no protocolo versionado.
set -euo pipefail
if [[ $# -ne 2 ]]; then
  echo 'Uso: bash scripts/reproduce_statistical_suite_2026.sh FONTES_TRATADAS SAIDA_NOVA' >&2
  exit 2
fi
stats_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
stats_sources=$(realpath -- "$1")
stats_output=$(realpath -m -- "$2")
cd -- "$stats_root"
if [[ -e "$stats_output" ]]; then
  echo 'Saída existente; preservar tentativas anteriores.' >&2
  exit 2
fi
if [[ -n $(git status --porcelain) ]]; then
  echo 'Checkout com alterações; fixe uma revisão limpa antes de registrar a reprodução.' >&2
  exit 2
fi
mkdir -p -- "$stats_output"
stats_target=${CARGO_TARGET_DIR:-"$stats_output/build"}
git rev-parse HEAD > "$stats_output/source-git.txt"
rustc --version > "$stats_output/rustc.txt"
cargo --version > "$stats_output/cargo.txt"
python3 --version > "$stats_output/python.txt"
CARGO_TARGET_DIR="$stats_target" cargo build --release --locked --bin statistical_suite_2026 > "$stats_output/build.log" 2>&1
sha256sum "$stats_target/release/statistical_suite_2026" > "$stats_output/binary.sha256"
"$stats_target/release/statistical_suite_2026" \
  --protocol "$stats_root/auditoria/2026/suite/protocolo.json" \
  --sections "$stats_sources/sections.csv" \
  --time-policy "$stats_sources/politica-relogio-nominal-2026.json" \
  --log-report "$stats_sources/logs-nacional.json" \
  --output "$stats_output/results" > "$stats_output/stdout.log" 2> "$stats_output/stderr.log"
python3 scripts/check_statistical_suite_2026.py \
  --protocol auditoria/2026/suite/protocolo.json --sections "$stats_sources/sections.csv" \
  --result "$stats_output/results" --output "$stats_output/independent-check.json" > "$stats_output/check.log" 2>&1
python3 scripts/render_statistical_suite_2026.py --result "$stats_output/results" --output "$stats_output/RELATORIO.md"
python3 - "$stats_output" "$stats_target" <<'PY'
from pathlib import Path
import hashlib,json,subprocess,sys
root=Path.cwd();out=Path(sys.argv[1]);target=Path(sys.argv[2]).resolve()
sys.path.insert(0,str(root/'scripts'))
from validate import load_limits
buffer=load_limits(root)['IO_BUFFER_BYTES']
def measure(path):
    h=hashlib.sha256();n=0
    with path.open('rb') as stream:
        while chunk:=stream.read(buffer):h.update(chunk);n+=len(chunk)
    return {'bytes':n,'sha256':h.hexdigest()}
paths=[p for p in out.rglob('*') if p.is_file() and not p.resolve().is_relative_to(target)]
sources=subprocess.check_output(['git','ls-files','src','scripts','Cargo.toml','Cargo.lock','auditoria/2026/suite/protocolo.json'],text=True).splitlines()
report={'format_version':1,'execution_success':True,'scope':'Artefatos da bateria e hashes das fontes versionadas. O cache de compilação não é artefato científico.','git_revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'files':{p.relative_to(out).as_posix():measure(p) for p in sorted(paths)},'source_files':{name:measure(root/name) for name in sources}}
with (out/'artifacts.json').open('x',encoding='utf-8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
PY
