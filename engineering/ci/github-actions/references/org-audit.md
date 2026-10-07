# Read-only audit of GitHub repo protection and security updates

Answers "which repos do not opt into policy X" and "are security updates on for our repos" without
changing anything. Needs `gh` authenticated with admin or security-manager rights on the repos
(without it `security_and_analysis` is absent and the checks below read as "disabled").
Endpoints: [repos REST API](https://docs.github.com/en/rest/repos/repos),
[rules API](https://docs.github.com/en/rest/repos/rules).

```bash
OWNER=my-org                  # an org or a user
POLICY="main-protection"      # name of the ruleset every repo should be under
gh repo list "$OWNER" --no-archived --source -L 1000 \
  --json name,defaultBranchRef --jq '.[] | [.name, .defaultBranchRef.name] | @tsv' |
while IFS=$'\t' read -r repo branch; do
  # Active rulesets that apply to the repo, inherited org rulesets included.
  rs=$(gh api "repos/$OWNER/$repo/rulesets" --jq '[.[] | select(.enforcement=="active") | .name] | join(",")' 2>/dev/null) || rs=unavailable
  # Classic branch protection on the default branch; 404 means none.
  bp=$(gh api "repos/$OWNER/$repo/branches/$branch/protection" --silent 2>/dev/null && echo yes || echo no)
  # Dependabot alerts (204 = on) and security updates ({enabled,paused}; 404 = off).
  va=$(gh api "repos/$OWNER/$repo/vulnerability-alerts" --silent 2>/dev/null && echo on || echo off)
  su=$(gh api "repos/$OWNER/$repo/automated-security-fixes" --jq '.enabled' 2>/dev/null || echo off)
  printf '%s\trulesets=%s\tclassic=%s\talerts=%s\tsecurity_updates=%s\n' "$repo" "$rs" "$bp" "$va" "$su"
done | tee audit.tsv
grep -v -F "$POLICY" audit.tsv                       # repos not under the policy
awk -F'\t' '$5!="security_updates=true"' audit.tsv   # repos without security updates
```

- Org-level rulesets and their repo targeting: `gh api orgs/$OWNER/rulesets`, then
  `gh api orgs/$OWNER/rulesets/<id>` and read `conditions.repository_name`.
- Run it for each owner, personal accounts included: `OWNER=<username>`.
- `--source` skips forks; drop it to audit them. Archived repos are skipped on purpose.
- `rulesets=unavailable` means the API refused (private repos on a free plan return 403); treat it as
  unknown, not as compliant.
- A repo can show both a ruleset and classic protection. Report both; do not count classic
  protection as satisfying a ruleset policy.

## Fixing drift

Fix in the Terraform that owns the repo, not by hand, so the next apply does not revert it. Provider
docs ([integrations/github](https://github.com/integrations/terraform-provider-github/tree/main/docs/resources)):
`repository_ruleset` and `organization_ruleset` for rulesets, `repository_vulnerability_alerts` and
`repository_dependabot_security_updates` for the security toggles, `branch_protection` for classic
rules. The `vulnerability_alerts` argument on `github_repository` is deprecated in favour of the
standalone resource.
