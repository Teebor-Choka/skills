#!/usr/bin/env bash
# Rehearse the OpenBao path of references/runbook.md against a throwaway dev server on localhost.
# Needs bao, sops, jq and curl on PATH. Nothing leaves the machine. The dev server speaks plain HTTP,
# so this does not test TLS; real use needs an https VAULT_ADDR.
# Usage: bash tests/openbao.sh
set -u
here="$(cd "$(dirname "$0")" && pwd)"
runbook="$here/../references/runbook.md"
for t in bao sops jq curl; do command -v "$t" >/dev/null || {
  echo "missing $t" >&2
  exit 2
}; done
tmp="$(mktemp -d "${TMPDIR:-/tmp}/sops-openbao.XXXXXX")"
srv=""
# shellcheck disable=SC2329 # runs through the EXIT trap below
cleanup() {
  [ -n "$srv" ] && kill "$srv" 2>/dev/null
  rm -rf "$tmp"
}
trap cleanup EXIT
fail=0
ok() { if [ "$2" = "$3" ]; then echo "  ok: $1"; else
  echo "  FAIL: $1: expected '$2', got '$3'"
  fail=1
fi; }
has() { if grep -qF -- "$2" "$runbook"; then echo "  ok: $1"; else
  echo "  FAIL: $1: runbook lacks: $2"
  fail=1
fi; }

echo "runbook carries the commands this test runs"
has "transit mount" 'bao secrets enable -path=sops transit'
has "transit key" 'bao write -f sops/keys/secrets'
has "policy path encrypt" 'path "sops/encrypt/secrets"'
has "policy path decrypt" 'path "sops/decrypt/secrets"'
has "sops key type" 'hc_vault_transit_uri'
has "token without storing it" 'bao login -method=<method> -no-store -token-only'
has "revoke" 'bao token revoke -self'

port=$((18200 + RANDOM % 500))
export VAULT_ADDR="http://127.0.0.1:$port" BAO_ADDR="http://127.0.0.1:$port"
bao server -dev -dev-root-token-id=root -dev-listen-address="127.0.0.1:$port" >"$tmp/server.log" 2>&1 &
srv=$!
n=0
until BAO_TOKEN=root bao status >/dev/null 2>&1; do
  n=$((n + 1))
  [ "$n" -gt 50 ] && {
    echo "dev server did not start"
    tail -5 "$tmp/server.log"
    exit 1
  }
  sleep 0.2
done
export BAO_TOKEN=root VAULT_TOKEN=root
bao secrets enable -path=sops transit >/dev/null
bao write -f sops/keys/secrets >/dev/null
bao write -f sops/keys/secrets2 >/dev/null
bao policy write sops-user - >/dev/null <<'EOF'
path "sops/encrypt/secrets" { capabilities = ["update"] }
path "sops/decrypt/secrets" { capabilities = ["update"] }
EOF
ok "bao list shows both keys" "secrets secrets2" "$(bao list -format=json sops/keys | jq -r 'join(" ")')"
bao auth enable userpass >/dev/null
bao write auth/userpass/users/alice password=throwaway-test-password policies=sops-user >/dev/null

# bao reads BAO_TOKEN before VAULT_TOKEN, sops reads only VAULT_*: act as the user with BAO_TOKEN unset.
login() { env -u BAO_TOKEN -u VAULT_TOKEN bao login -method=userpass -no-store -token-only username=alice password=throwaway-test-password; }
user_token="$(login)"

cd "$tmp" && mkdir secrets
cat >.sops.yaml <<EOF
creation_rules:
  - path_regex: ^secrets/.*\.ya?ml$
    hc_vault_transit_uri: "$VAULT_ADDR/v1/sops/keys/secrets"
EOF

echo "encrypt and decrypt as the policy user"
printf 'name: value-that-must-not-appear\n' >plain.yaml
# --filename-override only names the file for the creation rule; sops does not read it.
# shellcheck disable=SC2094
VAULT_TOKEN="$user_token" sops --encrypt --input-type yaml --output-type yaml \
  --filename-override secrets/prod.yaml plain.yaml >secrets/prod.yaml
ok "no cleartext value in the file" 0 "$(grep -c 'value-that-must-not-appear' secrets/prod.yaml)"
ok "the value is ENC[...]" 1 "$(grep -c '^name: ENC\[' secrets/prod.yaml)"
ok "the metadata names the transit key" 1 "$(grep -c '^ *key_name: secrets$' secrets/prod.yaml)"
ok "the policy user can decrypt" "name: value-that-must-not-appear" \
  "$(VAULT_TOKEN="$user_token" sops --decrypt secrets/prod.yaml)"
rm -f plain.yaml

echo "least privilege: the policy user cannot read or rotate the key"
env -u BAO_TOKEN VAULT_TOKEN="$user_token" bao read sops/keys/secrets >/dev/null 2>&1
rc=$?
ok "the policy user cannot read the key" 1 "$([ "$rc" -ne 0 ] && echo 1 || echo 0)"
env -u BAO_TOKEN VAULT_TOKEN="$user_token" bao write -f sops/keys/secrets/rotate >/dev/null 2>&1
rc=$?
ok "the policy user cannot rotate the key" 1 "$([ "$rc" -ne 0 ] && echo 1 || echo 0)"

echo "denial: a token without the policy, and a revoked token"
bare="$(bao token create -policy=default -field=token)"
out="$(VAULT_TOKEN="$bare" sops --decrypt secrets/prod.yaml 2>&1 >/dev/null)"
rc=$?
ok "a token without the policy cannot decrypt" 1 "$([ "$rc" -ne 0 ] && echo 1 || echo 0)"
ok "the error is a permission error" 1 "$([ "$(printf '%s' "$out" | grep -ci 'permission denied')" -ge 1 ] && echo 1 || echo 0)"
env -u BAO_TOKEN VAULT_TOKEN="$user_token" bao token revoke -self >/dev/null
VAULT_TOKEN="$user_token" sops --decrypt secrets/prod.yaml >/dev/null 2>&1
rc=$?
ok "a revoked token cannot decrypt" 1 "$([ "$rc" -ne 0 ] && echo 1 || echo 0)"

echo "add a second key, then updatekeys"
cat >.sops.yaml <<EOF
creation_rules:
  - path_regex: ^secrets/.*\.ya?ml$
    hc_vault_transit_uri: "$VAULT_ADDR/v1/sops/keys/secrets,$VAULT_ADDR/v1/sops/keys/secrets2"
EOF
sops updatekeys -y secrets/prod.yaml >/dev/null 2>&1
ok "both keys are in the metadata" 2 "$(grep -c '^ *key_name: ' secrets/prod.yaml)"
bao policy write only-secrets2 - >/dev/null <<'EOF'
path "sops/decrypt/secrets2" { capabilities = ["update"] }
EOF
only2="$(bao token create -policy=only-secrets2 -field=token)"
only1="$(bao token create -policy=sops-user -field=token)"
ok "a token for the second key alone can decrypt" "name: value-that-must-not-appear" \
  "$(VAULT_TOKEN="$only2" sops --decrypt secrets/prod.yaml)"
ok "a token for the first key alone can decrypt" "name: value-that-must-not-appear" \
  "$(VAULT_TOKEN="$only1" sops --decrypt secrets/prod.yaml)"
ok "the root token still decrypts" "name: value-that-must-not-appear" "$(sops --decrypt secrets/prod.yaml)"

[ "$fail" = 0 ] && echo "PASS" || echo "FAIL"
exit "$fail"
