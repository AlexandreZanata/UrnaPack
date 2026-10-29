#!/usr/bin/env bash
# Pipeline completo do catálogo preservado. Nunca sobrescreve um run anterior.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $# -ne 2 ]]; then
  echo "uso: bash scripts/reproduce_audit_2026.sh DIRETORIO_FONTES NOVO_DIRETORIO_EXECUCAO" >&2
  exit 2
fi
source_root=$(realpath -m "$1")
run_root=$(realpath -m "$2")
if [[ -e "$run_root" ]]; then
  echo "diretório de execução já existe; escolha outro para preservar evidência" >&2
  exit 1
fi
mkdir -p "$run_root"
catalog=auditoria/2026/catalogo-fixado.json
official=auditoria/2026/evidencias/totalizacao-presidente-2t.json
python3 scripts/acquire_2026.py fetch --catalog "$catalog" --root "$source_root" \
  --receipt "$run_root/acquisition.json" --transport curl
python3 scripts/acquire_2026.py verify --catalog "$catalog" --root "$source_root" \
  --receipt "$run_root/verification.json"
python3 scripts/prepare_audit_2026.py --catalog "$catalog" --root "$source_root" \
  --destination "$run_root/csv" --evidence "$run_root/preparation" --manifest "$run_root/bu-input.json"
python3 scripts/build_time_policy_2026.py \
  --municipalities auditoria/2026/evidencias/municipios-2t.json --output "$run_root/time-policy.json"
cargo build --locked --release --bin audit_2026 --bin audit_logs_2026
target/release/audit_2026 --manifest "$run_root/bu-input.json" \
  --time-policy "$run_root/time-policy.json" --output "$run_root/president.json" \
  --sections-output "$run_root/sections.csv"
python3 scripts/check_audit_2026.py --report "$run_root/president.json" \
  --official "$official" --output "$run_root/comparison.json"
python3 - "$run_root" <<'PY'
import sys,json,hashlib,pathlib,subprocess
root=pathlib.Path(sys.argv[1]); path=root/'sections.csv'; data=path.read_bytes()
receipt={'format_version':1,'path':str(path),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
         'scope':'Projeção semântica; não é restauração byte a byte do BU original.'}
(root/'sections-export.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
env={'format_version':1,'git_revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
     'git_status':subprocess.check_output(['git','status','--porcelain'],text=True),
     'rustc':subprocess.check_output(['rustc','--version','--verbose'],text=True),'python':sys.version,
     'curl':subprocess.check_output(['curl','--version'],text=True),
     'binary_sha256':{n:hashlib.sha256(pathlib.Path('target/release',n).read_bytes()).hexdigest()
                      for n in ['audit_2026','audit_logs_2026']}}
(root/'environment.json').write_text(json.dumps(env,sort_keys=True,indent=2)+'\n')
PY
python3 scripts/reconcile_coverage_2026.py --sections "$run_root/sections.csv" \
  --export-receipt "$run_root/sections-export.json" --source-manifest "$run_root/bu-input.json" \
  --report "$run_root/president.json" --official "$official" --output "$run_root/coverage.json"
# Código diferente de zero continua explícito. Diagnóstico científico é
# preservado; falha de estrutura/fluxo será reprovada também pelo coletor.
logs_code=0
python3 scripts/run_logs_2026.py --root "$source_root" --catalog "$catalog" \
  --sections "$run_root/sections.csv" --export-receipt "$run_root/sections-export.json" \
  --policy "$run_root/time-policy.json" \
  --zero-sections auditoria/2026/evidencias/registros-exterior-sem-cargo.json \
  --out-root "$run_root/logs" || logs_code=$?
python3 scripts/collect_logs_2026.py --directories "$run_root"/logs/?? \
  --official "$official" --output "$run_root/log-input.json"
aggregate_code=0
target/release/audit_logs_2026 --aggregate-manifest "$run_root/log-input.json" \
  --output "$run_root/log-national.json" || aggregate_code=$?
python3 - "$run_root" "$logs_code" "$aggregate_code" <<'PY'
import sys,json,pathlib
sys.path.insert(0,'scripts')
from acquire_2026 import hashes,limits_at
root=pathlib.Path(sys.argv[1]); files={}
buffer=limits_at('scripts/limits.env')['IO_BUFFER_BYTES']
for path in sorted(root.rglob('*')):
 if path.is_file():
  measured=hashes(path,buffer)
  files[str(path.relative_to(root))]={key:measured[key] for key in ['bytes','sha256']}
(root/'artifacts.json').write_text(json.dumps({'format_version':1,'logs_exit_code':int(sys.argv[2]),
  'aggregate_exit_code':int(sys.argv[3]),'files':files},sort_keys=True,indent=2)+'\n')
PY
if [[ "$logs_code" -ne 0 || "$aggregate_code" -ne 0 ]]; then
  echo "Artefatos gerados com diagnóstico de logs; sem conciliação integral. Consulte log-national.json." >&2
  exit 1
fi
echo "Aquisição, integridade, BU e logs conciliados. Artefatos em $run_root"
