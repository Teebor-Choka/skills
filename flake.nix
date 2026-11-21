{
  description = "Public AI agent skills — github.com/Teebor-Choka/skills";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    treefmt-nix = {
      url = "github:numtide/treefmt-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    flake-utils.url = "github:numtide/flake-utils";
    git-hooks = {
      url = "github:cachix/git-hooks.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    # Only its pure lib is used (hook manifest renderer), so no flake inputs of its own.
    # Pinned until the renderer lands on main.
    agent-env = {
      url = "git+https://github.com/Teebor-Choka/agent-env.git?ref=main&rev=a8de73ea2944b95598fe217e9ff085c8303fadd9";
      flake = false;
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      treefmt-nix,
      flake-utils,
      git-hooks,
      agent-env,
    }:
    flake-utils.lib.eachSystem [ "aarch64-darwin" "aarch64-linux" "x86_64-linux" ] (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        # The baseline the skills promise; pinned so a nixpkgs bump cannot move it.
        python = pkgs.python313;
        py = python.withPackages (ps: [
          ps.pyyaml
          ps.pytest
        ]);
        # The pytest suites run on the systems they ran on while the code-quality suite (tools with no
        # aarch64-linux build) shared this check.
        testsSupportedSystem = builtins.elem system [
          "aarch64-darwin"
          "x86_64-linux"
        ];

        treefmtEval = treefmt-nix.lib.evalModule pkgs {
          projectRootFile = "flake.nix";
          programs.nixfmt = {
            enable = true;
            package = pkgs.nixfmt-rfc-style;
          };
          programs.prettier = {
            enable = true;
            # Preserve prose wrapping so SKILL.md instruction text is not reflowed.
            settings.proseWrap = "preserve";
          };
          programs.shfmt = {
            enable = true;
            indent_size = 2;
          };
          # Exclude auto-generated lock files from all formatters.
          settings.global.excludes = [
            "flake.lock"
            "**/package-lock.json"
            "**/node_modules/**"
            # render_docs.py output is byte-compared by --check, so no formatter may touch it.
            "**/docs/generated/**"
          ];
        };

        # Commit-time parity with CI: the same treefmt and skills validator that
        # `nix flake check` runs, plus the workflow/shell linters. Entering the
        # dev shell installs the hook and a .pre-commit-config.yaml symlink.
        preCommit = git-hooks.lib.${system}.run {
          src = ./.;
          hooks = {
            treefmt = {
              enable = true;
              packageOverrides.treefmt = treefmtEval.config.build.wrapper;
            };
            skills-validate = {
              enable = true;
              name = "skills-validate";
              entry = "${py}/bin/python3 scripts/validate-skills.py .";
              files = "(^|/)SKILL\\.md$|^scripts/validate-skills\\.py$|^scripts/skill-size-allow\\.txt$";
              pass_filenames = false;
            };
            shellcheck = {
              enable = true;
              # `use flake` has no shebang, which shellcheck rejects (SC2148).
              excludes = [ "^\\.envrc$" ];
            };
            actionlint = {
              enable = true;
              extraPackages = [ pkgs.shellcheck ];
            };
            zizmor.enable = true;
          };
        };
      in
      {
        formatter = treefmtEval.config.build.wrapper;

        checks = {
          formatting = treefmtEval.config.build.check self;

          # The git workflow scripts (babysit, pr-landed, pr-state) against stub forge CLIs.
          git-workflow =
            pkgs.runCommand "git-workflow-tests"
              {
                nativeBuildInputs = [
                  pkgs.bats
                  pkgs.jq
                  pkgs.git
                  python
                  pkgs.coreutils
                  pkgs.gnugrep
                  pkgs.gnused
                  pkgs.gawk
                ];
              }
              ''
                export HOME=$TMPDIR
                cp -r ${self}/engineering/tools/git/skills/workflow/scripts scripts
                chmod -R u+w scripts
                patchShebangs scripts
                bats scripts
                touch $out
              '';

          # Node suites of presentation (deck-io, the patterns linter, the registry check) and
          # publishing. Dependencies come from each package-lock.json, so the sandbox needs no network.
          presentation =
            let
              mods =
                dir:
                pkgs.importNpmLock.buildNodeModules {
                  npmRoot = self + "/communication/presentation/${dir}";
                  nodejs = pkgs.nodejs;
                };
            in
            pkgs.runCommand "presentation-tests"
              {
                nativeBuildInputs = [
                  pkgs.nodejs
                  python
                ];
              }
              ''
                export HOME=$TMPDIR
                cp -r ${self}/communication/presentation plugin
                chmod -R u+w plugin
                ln -s ${mods "deck-io/scripts"}/node_modules plugin/deck-io/scripts/node_modules
                ln -s ${mods "skills/patterns/scripts"}/node_modules plugin/skills/patterns/scripts/node_modules
                (cd plugin/deck-io/scripts && node --test test.mjs)
                (cd plugin/skills/patterns/scripts && node --test test.mjs)
                python3 plugin/skills/patterns/scripts/verify.py
                touch $out
              '';

          publishing =
            let
              dir = "communication/publishing/skills/blog-syndication/scripts";
              mods = pkgs.importNpmLock.buildNodeModules {
                npmRoot = self + "/${dir}";
                nodejs = pkgs.nodejs;
              };
            in
            pkgs.runCommand "publishing-tests" { nativeBuildInputs = [ pkgs.nodejs ]; } ''
              export HOME=$TMPDIR
              cp -r ${self}/${dir} scripts
              chmod -R u+w scripts
              ln -s ${mods}/node_modules scripts/node_modules
              cd scripts
              node --test test.mjs
              touch $out
            '';

          # The yubikey rehearsals: the ceremony and step scripts against a stub ykman and ssh-keygen and a
          # software keyring, no card. b4 needs a pty: util-linux `script` on Linux, the system one on darwin.
          yubikey =
            pkgs.runCommand "yubikey-tests"
              {
                nativeBuildInputs = [
                  pkgs.gnupg
                  pkgs.openssh
                  pkgs.coreutils
                  pkgs.findutils
                  pkgs.diffutils
                  pkgs.gawk
                  pkgs.gnugrep
                  pkgs.gnused
                  pkgs.gnutar
                ]
                ++ pkgs.lib.optional pkgs.stdenv.isLinux pkgs.util-linux;
              }
              ''
                export HOME=$TMPDIR
                ${pkgs.lib.optionalString pkgs.stdenv.isDarwin "export PATH=$PATH:/usr/bin # BSD script(1): nixpkgs ships none for darwin"}
                cp -r ${self}/engineering/tools/security/yubikey/skills/yubikey skill
                chmod -R u+w skill
                patchShebangs skill
                sh skill/tests/rehearse-ceremony.sh
                sh skill/tests/rehearse-steps.sh
                touch $out
              '';

          skills-validate =
            pkgs.runCommand "skills-validate"
              {
                nativeBuildInputs = [ py ];
              }
              ''
                python3 ${self}/scripts/validate-skills.py ${self}
                touch $out
              '';

          concurrency-refs =
            pkgs.runCommand "concurrency-refs"
              {
                nativeBuildInputs = [ py ];
              }
              ''
                python3 ${self}/scripts/check-concurrency-refs.py ${self}
                touch $out
              '';

          marketplace-json =
            pkgs.runCommand "marketplace-json"
              {
                nativeBuildInputs = [
                  python
                  pkgs.jq
                ];
              }
              ''
                jq empty < ${self}/.claude-plugin/marketplace.json
                python3 ${self}/scripts/check-marketplace.py ${self}
                touch $out
              '';

          # Every plugin that ships hooks/manifest.json: its committed hooks/hooks.json must equal the
          # rendered one (agent-env's renderClaudeHooks). A new plugin is covered by adding the manifest.
          hooks-manifest =
            let
              l = import "${agent-env}/modules/home/agent-plugins-lib.nix" { inherit (pkgs) lib; };
              withHooks = builtins.filter (p: p.hooks != null) (l.normalize { src = self; });
              one =
                p:
                let
                  rendered = pkgs.writeText "${p.name}.hooks.json" (builtins.toJSON (l.renderClaudeHooks p.hooks));
                in
                ''
                  echo "${p.name}"
                  diff <(jq -S . ${rendered}) <(jq -S . ${p.root}/hooks/hooks.json)
                '';
            in
            pkgs.runCommand "hooks-manifest" { nativeBuildInputs = [ pkgs.jq ]; } ''
              ${pkgs.lib.concatMapStrings one withHooks}
              touch $out
            '';

          # Every plugin normalizes through agent-env, including hooks-only ones with no skills/ dir:
          # forcing skillNames and the root of each would throw if one did not.
          plugins-normalize =
            let
              l = import "${agent-env}/modules/home/agent-plugins-lib.nix" { inherit (pkgs) lib; };
              plugins = l.normalize { src = self; };
              line = p: "${p.name}: ${toString (builtins.length p.skillNames)} skill(s)\n";
            in
            pkgs.runCommand "plugins-normalize" { } ''
              printf '%s' ${pkgs.lib.escapeShellArg (pkgs.lib.concatMapStrings line plugins)}
              touch $out
            '';

          shellcheck =
            pkgs.runCommand "shellcheck"
              {
                nativeBuildInputs = [
                  pkgs.shellcheck
                  pkgs.findutils
                ];
              }
              ''
                files=$(find ${self} -name "*.sh" -not -path "*/node_modules/*")
                if [ -n "$files" ]; then
                  echo "$files" | xargs shellcheck
                fi
                touch $out
              '';
        }
        // pkgs.lib.optionalAttrs testsSupportedSystem {
          # Single target for every pytest suite in the repo: it discovers each
          # `tests/` directory and runs them in one invocation. The suites need only
          # python/pytest/git (plus jq and prettier for a few cases).
          tests =
            pkgs.runCommand "tests"
              {
                nativeBuildInputs = [
                  pkgs.git
                  pkgs.jq
                  pkgs.prettier # project-docs AT-18 skips without it
                  (python.withPackages (ps: [
                    ps.pytest
                    ps.pytest-cov
                    ps.pyyaml # scripts/tests run validate-skills.py, which imports yaml
                  ]))
                ];
              }
              ''
                export HOME="$TMPDIR"

                # Some suites' assets/*.sh use `#!/usr/bin/env bash` shebangs,
                # fine on a normal system but unresolvable as-is on Linux's Nix
                # sandbox -- unlike Darwin's sandbox-exec profile (which
                # allowlists a small set of host paths, /bin/bash among them),
                # the Linux sandbox is a full container with nothing from the
                # host filesystem, so `/usr/bin/env` itself doesn't exist there.
                # `${self}` is also read-only, so the whole tree is copied and
                # shebang-patched on a writable copy.
                cp -r ${self} "$TMPDIR/repo"
                chmod -R u+w "$TMPDIR/repo"
                patchShebangs "$TMPDIR/repo"
                cd "$TMPDIR/repo"

                mapfile -t testdirs < <(
                  find . -type d -name tests \
                    -not -path '*/node_modules/*' -not -path '*/.claude/*' | sort
                )
                python3 -m pytest "''${testdirs[@]}" -v -p no:cacheprovider
                touch $out
              '';
        };

        devShells.default = pkgs.mkShell {
          inherit (preCommit) shellHook;
          buildInputs = preCommit.enabledPackages;
          nativeBuildInputs = with pkgs; [
            nodejs
            bats
            py
            treefmt
            nixfmt-rfc-style
            prettier
            shfmt
            shellcheck
            jq
          ];
        };
      }
    );
}
