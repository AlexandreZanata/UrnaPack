#!/usr/bin/env bash
# Aplica (idempotente) os rulesets de .github/rulesets/main.json via gh api.
# Requer autenticação com permissão de administração no repositório.
# Uso: ./scripts/apply_rulesets.sh [owner/repo]  (padrão: origin do git)
set -euo pipefail

REPO="${1:-$(git remote get-url origin | sed -E 's#.*github.com[:/]([^/]+/[^/]+?)(\.git)?$#\1#')}"
FILE=".github/rulesets/main.json"

command -v gh >/dev/null || { echo "gh CLI necessário"; exit 1; }
command -v python3 >/dev/null || { echo "python3 necessário"; exit 1; }

echo "repositório-alvo: $REPO"
NAMES=$(python3 -c "import json; print('\n'.join(r['name'] for r in json.load(open('$FILE'))))")

# Regras em JSON não se aplicam sozinhas: a aplicação exige esta chamada à API.
for name in $NAMES; do
  id=$(gh api "repos/$REPO/rulesets" --jq ".[] | select(.name==\"$name\") | .id" || true)
  body=$(python3 -c "import json; print(json.dumps([r for r in json.load(open('$FILE')) if r['name']==\"$name\"][0]))")
  if [ -z "$id" ]; then
    echo "criando ruleset '$name'..."
    echo "$body" | gh api "repos/$REPO/rulesets" --method POST --input - --jq '{name, id}' 
  else
    echo "atualizando ruleset '$name' (id $id)..."
    echo "$body" | gh api "repos/$REPO/rulesets/$id" --method PUT --input - --jq '{name, id}'
  fi
done
echo "OK: rulesets aplicados. Confira em: https://github.com/$REPO/settings/rules"
