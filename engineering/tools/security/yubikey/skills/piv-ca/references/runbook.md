# Runbook: CA root key on two YubiKeys

Replace `example.com` with the zone the intermediate may sign for. Replace `<STICK>` with the name of the plain USB
stick (`ls /Volumes` on macOS, `ls /media/amnesia` on Tails). `ykman` prompts for every PIN and PUK: type them there.

The `openssl` commands ran on OpenSSL 3.6.3: the root has one `basicConstraints`, the name constraints print as shown
and the chain verifies. The `ykman` options were read from `ykman` 5.9.1 `--help` and were not run on a card.
Step 2 checks the options on the Tails `ykman`. The Tails OpenSSL version is unchecked.

## Contents

- Needs
- 1. Laptop, online
- 2. Tails, offline: network and tool check
- 3. Tails: root key, root certificate, signed intermediate
- 4. Tails: set up and load the first YubiKey
- 5. Tails: the second YubiKey
- 6. Tails: take out the public files, destroy the key
- 7. Laptop: verify and ship
- Done when
- Failures

## Needs

- Two YubiKeys, firmware 5.7.4 or later, checked genuine: https://www.yubico.com/genuine/
- Two YubiKeys whose PIV application is empty, or holds nothing you need: `ykman piv reset` and step 4 do not
  keep other PIV slots.
- A Tails stick with Persistent Storage, Additional Software on, and `yubikey-manager` and `pcscd` kept:
  `sudo apt update && sudo apt install yubikey-manager pcscd` (online, once).
- A plain USB stick for public files.
- The intermediate's CSR as `int.csr`. Check it: `openssl req -in int.csr -noout -verify -subject` prints
  `verify OK` and the subject you expect.

If `ykman` fails with an `ImportError` for `cryptography`, a stray `PYTHONPATH` loads packages of another Python
version. Run `env -u PYTHONPATH -u PYTHONHOME ykman ...`.

## 1. Laptop, online

1. Copy the CSR to the plain stick: `cp int.csr "/Volumes/<STICK>/"`. Eject it.
2. Boot Tails from its stick, unlock Persistent Storage, set an Administration Password under Additional Settings.
3. On the Welcome Screen choose Offline Mode, Disable all networking.

## 2. Tails, offline: network and tool check

Open Terminal. Check the network is off before the key exists:

```
ip -4 route show default
```

Expect no output. Stop if it prints a route: restart Tails and choose Offline Mode.

```
ykman --version
ykman piv keys import --help | grep -e --pin-policy -e --touch-policy
ykman piv certificates import --help | grep -e --verify
openssl version
```

Expect `ykman` 5.x and all three options. Stop if `--verify` is missing. Without it the key cannot be proven to work
before the key file is destroyed, so use a Tails release with a newer `ykman`.

## 3. Tails: root key, root certificate, signed intermediate

Work in RAM only. Every later step runs in `/tmp/ca`: run `cd /tmp/ca` and `umask 077` again in any new terminal.

```
umask 077
mkdir -p /tmp/ca && cd /tmp/ca
openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-384 -out root.key
openssl req -x509 -new -key root.key -sha384 -days 3650 -subj "/CN=Example Root CA" -out root.crt \
  -addext "basicConstraints=critical,CA:TRUE,pathlen:1" \
  -addext "keyUsage=critical,keyCertSign,cRLSign"
openssl x509 -in root.crt -noout -subject -dates -ext basicConstraints,keyUsage
```

Expect the subject, ten years, `CA:TRUE, pathlen:1` and `Certificate Sign, CRL Sign`. The root allows one
intermediate below it (`pathlen:1`).

Plug the plain stick in, copy the CSR and check it:

```
cp "/media/amnesia/<STICK>/int.csr" .
openssl req -in int.csr -noout -verify -subject
```

Expect `verify OK` and the subject you chose for the intermediate. Stop if either differs.

**Confirm before signing.** The root signs whatever the CSR asks to be. Read the subject, then confirm it is the
CSR you made. The name constraint below limits what the intermediate may sign for, and it excludes IP addresses:

```
cat > int.ext <<'EOF'
basicConstraints=critical,CA:TRUE,pathlen:0
keyUsage=critical,keyCertSign,cRLSign
nameConstraints=critical,permitted;DNS:example.com,excluded;IP:0.0.0.0/0.0.0.0,excluded;IP:0:0:0:0:0:0:0:0/0:0:0:0:0:0:0:0
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid
EOF
openssl x509 -req -in int.csr -CA root.crt -CAkey root.key -CAcreateserial -days 730 -sha384 -extfile int.ext -out int.crt
openssl verify -CAfile root.crt int.crt
openssl x509 -in int.crt -noout -ext nameConstraints,basicConstraints
cat int.crt root.crt > chain.pem
```

Expect `int.crt: OK` and this output:

```
X509v3 Basic Constraints: critical
    CA:TRUE, pathlen:0
X509v3 Name Constraints: critical
    Permitted:
      DNS:example.com
    Excluded:
      IP:0.0.0.0/0.0.0.0
      IP:0:0:0:0:0:0:0:0/0:0:0:0:0:0:0:0
```

`pathlen:0` stops the intermediate from creating further CAs. The name constraint holds only against verifiers
that enforce it. Email and URI names are not constrained: the issuing CA must not issue them. Leaves with IP
addresses or `localhost` as names fail verification: use DNS names under `example.com` only.

## 4. Tails: set up and load the first YubiKey

Plug only this YubiKey in.

```
ykman list --serials
ykman info
ykman piv info
```

Expect one serial, firmware 5.7.4 or later and nothing in slot 9C. Stop if 9C is used. Write the serial on paper.

The factory PIN is `123456` and the factory PUK is `12345678`. Choose a new PIN and a new PUK, each 6 to 8
characters. Each command asks for the current value and then the new one:

```
ykman piv access change-pin
ykman piv access change-puk
ykman piv access change-management-key --generate --protect
```

The last command stores a random management key on the YubiKey, unlocked by the PIN. If it asks for the current
management key, press Enter for the factory default. Read back:

```
ykman piv info
```

Expect no default-credential warning for the PIN, the PUK or the management key.

**Confirm before the import.** Load the key and certificate:

```
ykman piv keys import --pin-policy always --touch-policy always 9c root.key
ykman piv certificates import --verify 9c root.crt
ykman piv info
```

`--verify` signs with the key in the slot and checks it against the certificate, so a pass proves the key works. It
asks for the PIN and a touch. Expect slot 9C, algorithm `ECCP384` and the root subject. A wrong import is undone
with `ykman piv keys delete 9c`, which also removes the only YubiKey copy of the key: do it only while
`root.key` is still in `/tmp/ca`. Unplug the YubiKey.

## 5. Tails: the second YubiKey

Plug only the second YubiKey in. Run `cd /tmp/ca` first, then repeat step 4 with a PIN and PUK of your choice.
Record both. `root.key` is still in `/tmp/ca`.

## 6. Tails: take out the public files, destroy the key

Do not continue until `--verify` passed on both YubiKeys. Plug the plain stick in. Copy public files only, never
`root.key`, and check the copy:

```
sha256sum root.crt int.crt chain.pem > SHA256SUMS
cp root.crt int.crt chain.pem SHA256SUMS "/media/amnesia/<STICK>/"
sync
( cd "/media/amnesia/<STICK>" && sha256sum -c SHA256SUMS )
```

Expect `OK` for all three files. The root certificate can also be read back from a YubiKey later
(`ykman piv certificates export 9c root.crt`), but a lost `int.crt` cannot be signed again without a PKCS#11 path.

**Confirm before the delete.** Destroy the key:

```
shred -u /tmp/ca/root.key
ls /tmp/ca
```

Expect no `root.key`. Eject the stick, then power off Tails. Tails also erases RAM at shutdown.

## 7. Laptop: verify and ship

```
cp "/Volumes/<STICK>/root.crt" "/Volumes/<STICK>/int.crt" "/Volumes/<STICK>/chain.pem" .
openssl verify -CAfile root.crt int.crt
```

Publish `root.crt` where clients can trust it. Load `chain.pem` (intermediate then root) into the issuing CA as its
signed certificate. Issue one leaf from the issuing CA, save it as `leaf.crt`, and verify it:

```
openssl verify -CAfile root.crt -untrusted int.crt leaf.crt
```

Expect `leaf.crt: OK`.

Store the two YubiKeys in separate places. Record both PINs and PUKs in a password manager, never the key.

## Done when

- `ykman piv info` on each YubiKey shows slot 9C, `ECCP384` and the root subject.
- `ykman piv certificates import --verify` passed on each YubiKey in the session.
- `openssl verify -CAfile root.crt int.crt` printed `OK` and the intermediate shows the name constraint.
- `sha256sum -c SHA256SUMS` passed on the stick, and `root.key` exists nowhere after the session.
- PIN and PUK of both YubiKeys are changed and recorded.
- A leaf from the issuing CA verifies against `root.crt`.
- The loss rule is written down: losing both YubiKeys means a new root and re-trusting every client.

## Failures

- `ykman piv info` shows 9C already in use: stop. Do not import over it. Find out what is there first.
- `--verify` fails: the certificate does not match the key. Do not continue to the second YubiKey. Check that
  `root.key` and `root.crt` are from the same step 3.
- A PIN counter dropped: stop and find out which prompt was answered. `ykman piv info` shows the retries left.
- The PIN is blocked after three wrong tries: `ykman piv access unblock-pin` resets it with the PUK. The key is
  unaffected.
- The PUK is blocked and the PIN works: the key works. Only the PUK recovery path is lost. Do not reset.
- Both are blocked: only `ykman piv reset` remains. It wipes every PIV slot on that YubiKey, including the root key.
  The other YubiKey then holds the only copy.
- The session ended after the first YubiKey was loaded and before the second: `root.key` is gone with the RAM, and
  the first YubiKey holds the only copy. Do not reset it. Either accept a one-YubiKey root and record the risk, or
  start again at step 3 with a new root and distrust the first one.
- A YubiKey that you must reuse for a new root: only after the old root is out of every trust store, run
  `ykman piv reset`. It wipes every PIV slot.
