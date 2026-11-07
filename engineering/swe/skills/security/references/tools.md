# Tool reference

Commands run from the target root. Tools not on `PATH` run as `nix run nixpkgs#<attr> -- <args>`
(attrs: `gitleaks`, `trufflehog`, `osv-scanner`, `semgrep`, `zizmor`, `nuclei`). SkillSpector,
garak, and strix are Python tools: run them with `uvx`, `uv tool install`, or their Docker image.
Check each tool with `--help` first. Flags below were taken from the project READMEs.

Exit codes: gitleaks, trufflehog, and osv-scanner exit 1 when they find something. Read the
result file, not just the exit code.

## 1. Secrets

**gitleaks** (history and tree)

```
gitleaks git --redact --report-format sarif --report-path - .    # git history
gitleaks dir --redact --report-format sarif --report-path - .    # plain directory
```

Its built-in rules skip obvious placeholders such as `AKIAIOSFODNN7EXAMPLE`, so test with a
random fake token, not a documentation one.

**trufflehog** (second engine, with verification)

```
trufflehog git file://$PWD --json --no-verification
trufflehog filesystem . --json --no-verification
```

`--no-verification` is the default here. Verification (`--results=verified,unknown`) sends the
candidate secret to the provider, so it needs user approval. A verified hit is a live credential:
report it as rotate-now, never print the value.

Run both: they use different detectors, and a hit from both is high confidence.

## 2. Dependencies

**osv-scanner** (v2 syntax)

```
osv-scanner scan source -r --format sarif .
```

Reads lockfiles and manifests. It reports a known advisory, not reachability: before rating a
finding, check that the vulnerable function is used and that the input is attacker-reachable.
Prefer the fixed version the advisory names.

## 3. SAST

**semgrep**

```
semgrep scan --config p/default --config p/security-audit --metrics=off --sarif --quiet .
```

`--config auto` cannot run with `--metrics=off`. The registry packs download rules over the
network but upload no source with metrics off. Add language packs (`p/python`, `p/typescript`,
`p/golang`, `p/rust`) when the repo needs them. For Rust, semgrep coverage is thin: lean on
`cargo audit` or `cargo deny` through the language skill.

## 4. GitHub Actions

**zizmor**

```
zizmor --format sarif --no-progress .
```

Runs offline by default and skips the audits that need the GitHub API (impostor commits, known
vulnerable actions). Set `GITHUB_TOKEN` or pass `--gh-token` to enable them. Fix by SHA-pinning
actions, scoping `permissions:` per job, and moving `${{ }}` expressions out of `run:` into
`env:`.

## 5. Agent supply chain

**SkillSpector** (NVIDIA)

```
skillspector scan ./skill-dir --no-llm --format json --output report.json
skillspector scan ./skills --recursive --no-llm --format sarif --output report.sarif
```

`--no-llm` is the static pass and sends nothing out. Without it, SkillSpector calls a model
provider (configured by env vars) and spends quota: ask first. Use `--fail-on-incomplete` when a
partial scan must not pass. Point it at skills and MCP configs in the target and at any skill
about to be installed. Run `skillspector --help` for the install and gating options.

## 7. LLM endpoint (ask first)

**garak** (NVIDIA)

```
garak --list_probes
python3 -m garak --target_type <family> --target_name <model> --spec probes.promptinject
```

Probes a model or an HTTP-served LLM app for jailbreaks, prompt injection, encoding bypasses,
data leakage. It sends many requests to the target, so run it only against an endpoint the user
owns, and agree the probe set and budget first. Only relevant when the repo ships or calls an
LLM. Garak results are model-behavior findings: report them separately from code findings.

## 8. Dynamic (authorized targets only)

**nuclei** (ProjectDiscovery)

```
nuclei -u https://staging.example.test -severity high,critical -rate-limit 10 -jsonl -o nuclei.jsonl
```

Sends live requests from community templates. Run it against a target the user owns, at a
limited rate, never production without explicit approval. Update templates before use
(`nuclei -update-templates`).

**strix** (autonomous pentest agents)

```
export STRIX_LLM=<provider/model> LLM_API_KEY=<key>
strix --target ./app-directory
strix --target https://staging.example.test --instruction "<scope and test accounts>"
```

Needs Docker and an LLM key. It runs the target code and attacks it in a sandbox, then
writes results to `strix_runs/<run-name>`. Use it for a local build or staging copy the user
owns. Give it the scope and test accounts in `--instruction`, and check results with
`strix view`. A strix finding with a working PoC is strong evidence; still keep the proof
minimal and local.
