#!/bin/sh
# Shared helpers. POSIX sh. Source this file; do not run it.
# State holds no secrets: device labels, serials, firmware, fingerprints, phase markers.

YKHK_STATE=${YKHK_STATE:-${XDG_STATE_HOME:-$HOME/.local/state}/yubikey-hw-keys}
YKHK_TTY=${YKHK_TTY:-/dev/tty} # prompts read here; tests point it at a file
YKHK_MIN_FW=5.7.4              # read by key-read.sh
export YKHK_MIN_FW
export YKHK_STATE
mkdir -p "$YKHK_STATE"
chmod 700 "$YKHK_STATE" 2>/dev/null # the state holds the plan, handles and the staged backup bundle

say() { printf '%s\n' "$*"; }
die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}
# Open the prompt input once, on first use, so read-only scripts need no terminal.
_tty() { [ -n "${_TTY_OPEN-}" ] || {
  (exec 3<"$YKHK_TTY") 2>/dev/null || die "no terminal for prompts. Run this in your own terminal window, not through the agent."
  exec 3<"$YKHK_TTY"
  _TTY_OPEN=1
}; }

ask() { # ask "question" [default] -> $REPLY
  _tty
  if [ -n "${2-}" ]; then printf '%s [%s] ' "$1" "$2"; else printf '%s ' "$1"; fi
  IFS= read -r REPLY <&3 || die "no input"
  [ -n "$REPLY" ] || REPLY=${2-}
}
confirm() { # confirm "question": returns 0 only on y/yes
  _tty
  printf '%s [y/N] ' "$1"
  IFS= read -r ans <&3 || die "no input"
  case $ans in y | Y | yes | YES) return 0 ;; *) return 1 ;; esac
}
pause() {
  _tty
  printf '%s (press Enter) ' "$1"
  IFS= read -r _ <&3 || die "no input"
}

# run_tool CMD NIXPKG ARGS...: use CMD from PATH, else nix, else stop.
run_tool() {
  cmd=$1
  pkg=$2
  shift 2
  if command -v "$cmd" >/dev/null 2>&1; then
    "$cmd" "$@"
  elif command -v nix >/dev/null 2>&1; then
    bin=$(nix_bin "$cmd" "$pkg") || die "could not resolve $pkg with nix"
    "$bin" "$@"
  else die "$cmd not found and nix is not available"; fi
}
# nix_bin CMD PKG: path of CMD in nixpkgs#PKG. `nix run` re-evaluates on every call (seconds), so the store
# path is resolved once and kept in the state dir. Only a /nix/store/*/bin/CMD path is used or cached; a
# garbage-collected path is resolved again. Delete $YKHK_STATE/nixbin.CMD to pick up a newer nixpkgs.
# nix keeps its own error output visible.
nix_bin() {
  cache="$YKHK_STATE/nixbin.$1"
  p=$(cat "$cache" 2>/dev/null)
  case $p in
  /nix/store/*/bin/"$1") [ -x "$p" ] && {
    printf '%s\n' "$p"
    return 0
  } ;;
  esac
  for p in $(nix --extra-experimental-features 'nix-command flakes' build --no-link --print-out-paths "nixpkgs#$2"); do
    case $p in /nix/store/*) ;; *) continue ;; esac
    if [ -x "$p/bin/$1" ]; then
      printf '%s\n' "$p/bin/$1" | tee "$cache"
      return 0
    fi
  done
  return 1
}
yk() { run_tool ykman yubikey-manager "$@"; }

# ver_ge A B: true when version A >= B
ver_ge() { [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -n1)" = "$2" ]; }

# need_init: the device plan must exist. On Tails it travels next to the scripts and is seeded from there.
need_init() {
  [ -s "$YKHK_STATE/devices.tsv" ] || { [ -f "$(dirname "$0")/devices.tsv" ] && cp "$(dirname "$0")/devices.tsv" "$YKHK_STATE/devices.tsv"; }
  [ -s "$YKHK_STATE/devices.tsv" ] || die "no device list. Run init-plan.sh COUNT, or copy devices.tsv next to the scripts."
}
mark_done() { : >"$YKHK_STATE/done.$1"; }

phase_list() {
  cat <<'LIST'
A1|Verify keys
A2|Tails stick
A3|Format sticks
B|Ceremony
C|Daily machine
D|SOPS and KMS
E|Recovery
LIST
}
progress() {
  phase_list | {
    here=0
    while IFS='|' read -r id name; do
      if [ -f "$YKHK_STATE/done.$id" ]; then
        bar='▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓'
        tag=''
      elif [ "$here" -eq 0 ]; then
        bar='▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░'
        tag='  <- you are here'
        here=1
      else
        bar='░░░░░░░░░░░░░░░░░░░░'
        tag=''
      fi
      printf '%-3s %s  %s%s\n' "$id" "$bar" "$name" "$tag"
    done
  }
}

# --- ceremony helpers (Tails) ---
# YKHK_GPG_EXTRA: extra gpg options, for rehearsal tests only (loopback passphrase).
# shellcheck disable=SC2086 # extra options are separate words
g() { gpg ${YKHK_GPG_EXTRA-} "$@"; }
gh() { (
  GNUPGHOME=$1
  export GNUPGHOME
  shift
  g "$@"
); } # gpg in another home
use_gnupghome() {
  [ -s "$YKHK_STATE/gnupghome" ] || die "no ceremony keyring. Run b0-start.sh first."
  GNUPGHOME=$(cat "$YKHK_STATE/gnupghome")
  export GNUPGHOME
}
need_fpr() {
  [ -s "$YKHK_STATE/primary.fpr" ] || die "no primary key yet. Run b2-primary.sh first."
  KEYFPR=$(cat "$YKHK_STATE/primary.fpr")
}
need_done() { [ -f "$YKHK_STATE/done.$1" ] || die "step $1 is not done yet."; }
# fprs HOME: sorted primary and subkey fingerprints of the secret keys in HOME
fprs() { gh "$1" --batch --with-colons --list-secret-keys --with-subkey-fingerprints | awk -F: '/^fpr:/ {print $10}' | sort; }

# --- device and step helpers (ceremony on Tails, checks on the Mac) ---
# devices.tsv columns: idx role label serial firmware verified
label_field() { awk -F'\t' -v l="$1" -v c="$2" '$3==l {print $c}' "$YKHK_STATE/devices.tsv"; }
label_serial() { label_field "$1" 4; }
label_role() { label_field "$1" 2; }
all_labels() { awk -F'\t' '{print $3}' "$YKHK_STATE/devices.tsv"; }
daily_labels() { awk -F'\t' '$2=="daily" {print $3}' "$YKHK_STATE/devices.tsv"; }
root_label() { awk -F'\t' '$2=="root" {print $3}' "$YKHK_STATE/devices.tsv"; }

# unverified_labels: labels whose genuineness was not confirmed in phase A (column 6 is not "yes").
unverified_labels() { awk -F'\t' '$6!="yes" {print $3}' "$YKHK_STATE/devices.tsv"; }
# reset_label LABEL: forget the serial and the verification of one key (a rejected or replaced key).
reset_label() {
  tmp=$(mktemp)
  awk -F'\t' -v OFS='\t' -v l="$1" '$3==l {$4="-"; $5="-"; $6="no"} 1' "$YKHK_STATE/devices.tsv" >"$tmp" && mv "$tmp" "$YKHK_STATE/devices.tsv"
  rm -f "$YKHK_STATE/done.A1"
}

# ask_card LABEL: loop until exactly that key (by recorded serial) is the only one plugged in.
# A key whose genuineness was not confirmed in phase A is refused: no PIN, subkey or primary key goes onto it.
ask_card() {
  want=$(label_serial "$1")
  [ -n "$want" ] && [ "$want" != - ] || die "unknown label or no serial recorded: $1"
  [ "$(label_field "$1" 6)" = yes ] || die "$1 was not confirmed genuine (phase A). Run key-genuine.sh $1 first."
  while :; do
    pause "Unplug all YubiKeys, then plug in ONLY the $1 key (serial $want)"
    got=$(yk list --serials 2>/dev/null </dev/null)
    [ "$got" = "$want" ] && return 0
    say "Found: ${got:-none}. Need exactly $want."
    confirm "Try again?" || die "stopped"
  done
}

# read_secret PROMPT: no-echo read from the prompt terminal into $SECRET. Caller must unset it.
read_secret() {
  _tty
  printf '%s' "$1"
  if [ -t 3 ]; then stty -echo <&3; fi
  # shellcheck disable=SC2034 # result variable, read by the caller
  IFS= read -r SECRET <&3 || die "no input"
  if [ -t 3 ]; then stty echo <&3; fi
  printf '\n'
}

# card_fprs: the three subkey fingerprints (sign, encrypt, authenticate) held by the plugged-in card.
# YKHK_CARD_FPRS overrides it, for rehearsal tests only.
card_fprs() {
  if [ -n "${YKHK_CARD_FPRS-}" ]; then
    # shellcheck disable=SC2086 # test hook: space-separated fingerprints
    printf '%s\n' $YKHK_CARD_FPRS
    return
  fi
  gpg --card-status --with-colons 2>/dev/null |
    awk -F: '/^fpr:/ {for (i = 2; i <= 4; i++) if ($i != "") print $i; exit}'
}

# Ceremony steps in order: "script args|description|done marker".
steps_all() {
  echo "b0-start.sh|Start the offline session|B0"
  for l in $(all_labels); do echo "b1-pins.sh $l|Set PINs on the $l key|B1.$l"; done
  echo "b2-primary.sh|Generate the primary key|B2"
  for l in $(daily_labels); do echo "b3-subkeys.sh $l|Put subkeys on the $l key|B3.$l"; done
  echo "b4-backup.sh|Export, encrypt and stage the backup|B4a"
  echo "b4-copy.sh backup|Copy the backup to the BACKUP stick|B4.backup"
  echo "b4-copy.sh public|Copy the public key to the PUBLIC stick|B4.public"
  echo "b5-verify-backup.sh|Restore test of both backups (blocking)|B5"
  echo "b6-keytocard.sh|Move the primary key to the root card|B6"
  for l in $(all_labels); do echo "b7-touch.sh $l|Set touch policy on the $l key|B7.$l"; done
  for l in $(daily_labels); do echo "b8-ssh.sh $l|Create the SSH key on the $l key|B8.$l"; done
  echo "b9-end.sh|Save SSH handles and end the ceremony|B9"
}
next_step() {
  steps_all | while IFS='|' read -r cmd desc mark; do
    [ -f "$YKHK_STATE/done.$mark" ] || {
      printf '%s|%s|%s\n' "$cmd" "$desc" "$mark"
      return
    }
  done
}
ceremony_bar() {
  total=0
  n=0
  for m in $(steps_all | cut -d'|' -f3); do
    total=$((total + 1))
    [ -f "$YKHK_STATE/done.$m" ] && n=$((n + 1))
  done
  [ "$total" -gt 0 ] || return 0
  fill=$((n * 20 / total))
  bar=''
  i=0
  while [ "$i" -lt 20 ]; do
    if [ "$i" -lt "$fill" ]; then bar="$bar▓"; else bar="$bar░"; fi
    i=$((i + 1))
  done
  printf 'Ceremony %s  %s of %s steps\n' "$bar" "$n" "$total"
}

# subkeys_without_expiry: count of secret subkeys in the ceremony keyring with no expiry date.
subkeys_without_expiry() {
  g --batch --with-colons --list-secret-keys "$KEYFPR" | awk -F: '/^ssb:/ && $7=="" {n++} END {print n+0}'
}

# subkey_table: "FPR EXPIRY" for each secret subkey in the ceremony keyring, EXPIRY empty when it never expires.
subkey_table() {
  g --batch --with-colons --list-secret-keys --with-subkey-fingerprints "$KEYFPR" |
    awk -F: '/^ssb:/ {e=$7; s=1; next} /^fpr:/ && s {print $10, e; s=0}'
}

# --- B4, shared by b4-backup.sh and b4-backup-all.sh ---
# b4_gate: all YKHK_SUBKEYS (default 6) subkeys exist and each has an expiry.
b4_gate() {
  gate_want=${YKHK_SUBKEYS:-6}
  gate_have=$(g --batch --with-colons --list-secret-keys "$KEYFPR" | grep -c '^ssb:')
  [ "$gate_have" -eq "$gate_want" ] || die "found $gate_have subkeys, expected $gate_want. Finish B3 first."
  gate_noexp=$(subkeys_without_expiry)
  [ "$gate_noexp" -eq 0 ] || die "$gate_noexp subkeys have no expiry. Run subkey-expiry.sh PERIOD FPR... first (subkey-expiry.sh lists them)."
}
# b4_bundle DIR: write public.asc and the encrypted identity-backup.tar.gpg into DIR (a 0700 temp dir).
# The plaintext secret export and the revocation certificate stay in DIR, so the caller removes DIR.
b4_bundle() {
  g --armor --export "$KEYFPR" >"$1/public.asc" || die "public export failed"
  g --armor --export-secret-keys "$KEYFPR" >"$1/primary-secret.asc" || die "secret export failed"
  # --gen-revoke refuses batch mode, so it asks four questions on the terminal.
  say "Revocation certificate: answer  y  then  0  then press Enter (empty description) then  y."
  g --output "$1/revoke.asc" --gen-revoke "$KEYFPR" || die "revocation certificate failed"
  [ -s "$1/primary-secret.asc" ] && [ -s "$1/revoke.asc" ] || die "an export file is empty"
  tar -C "$1" -cf - primary-secret.asc revoke.asc |
    g --symmetric --cipher-algo AES256 --output "$1/identity-backup.tar.gpg" || die "encryption failed"
  [ -s "$1/identity-backup.tar.gpg" ] || die "encrypted bundle is empty"
}
# b4_record FILE: the ceremony record (read by c-import.sh and c-check.sh): fingerprints, card map, devices.
b4_record() {
  {
    echo "primary: $KEYFPR"
    g --batch --with-colons --list-secret-keys --with-subkey-fingerprints "$KEYFPR" |
      awk -F: '/^ssb:/ {use=$12} /^fpr:/ && use {print "subkey(" use "): " $10; use=""}'
    for c in "$YKHK_STATE"/card.*; do [ -f "$c" ] && echo "card(${c##*.}): $(cat "$c")"; done
    echo "devices:"
    cat "$YKHK_STATE/devices.tsv" 2>/dev/null
  } >"$1"
}

# valid_period PERIOD: an expiry period or date for a subkey: 1y, 18m, 90d, 2w or YYYY-MM-DD. Zero, "never" and anything
# else are refused: a subkey that never expires cannot be retired if its revocation misses a verifier.
valid_period() { printf '%s' "$1" | grep -Eq '^[1-9][0-9]*[dwmy]$|^[0-9]{4}-[0-9]{2}-[0-9]{2}$'; }

# sha FILE...: SHA-256 lines in the sha256sum format, with whichever tool the machine has.
sha() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"; else shasum -a 256 "$@"; fi; }
# check_pubkey_digest FILE DIGEST: refuse a public.asc that is not the copy last written down on paper. Fingerprints cannot
# catch a stale genuine copy (one without a later revocation), because they are unchanged; only a digest kept off the stick can.
check_pubkey_digest() {
  if [ -z "${2-}" ]; then
    say "WARNING: no public.asc digest given. A stale copy of the key, without a later revocation, would not be detected."
    return 0
  fi
  want=$(printf '%s' "$2" | tr -d ' ' | tr '[:upper:]' '[:lower:]')
  got=$(sha "$1" | cut -d' ' -f1)
  [ "$got" = "$want" ] || die "public.asc digest is $got, not $want from your paper. It is not the copy you last wrote down. Do not continue."
}
