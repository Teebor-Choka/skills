{
  description = "Public AI agent skills — github.com/Teebor-Choka/skills";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    treefmt-nix = {
      url = "github:numtide/treefmt-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      treefmt-nix,
      flake-utils,
    }:
    flake-utils.lib.eachSystem [ "aarch64-darwin" "aarch64-linux" "x86_64-linux" ] (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        py = pkgs.python3.withPackages (ps: [ ps.pyyaml ]);
        codeQualityTools = import ./nix/code-quality-tools.nix { inherit pkgs; };
        codeQualitySupportedSystem = builtins.elem system [
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
          ];
        };
      in
      {
        formatter = treefmtEval.config.build.wrapper;

        checks = {
          formatting = treefmtEval.config.build.check self;

          skills-validate =
            pkgs.runCommand "skills-validate"
              {
                nativeBuildInputs = [ py ];
              }
              ''
                python3 ${self}/scripts/validate-skills.py ${self}
                touch $out
              '';

          marketplace-json =
            pkgs.runCommand "marketplace-json"
              {
                nativeBuildInputs = [
                  pkgs.python3
                  pkgs.jq
                ];
              }
              ''
                jq empty < ${self}/.claude-plugin/marketplace.json
                python3 ${self}/scripts/check-marketplace.py ${self}
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
        // pkgs.lib.optionalAttrs codeQualitySupportedSystem {
          # Runs engineering/swe/code-quality/tests/ for real, against real
          # tool binaries -- every tool that skill's scripts shell out to is
          # provisioned here, either from nixpkgs directly (cargo-llvm-cov,
          # rust-code-analysis, llvm) or from ./nix/code-quality-tools.nix
          # (everything nixpkgs doesn't package). CARGO_NET_OFFLINE guards
          # against this actually needing network during the build -- the
          # fixtures declare zero dependencies so it shouldn't, verified
          # directly, but this makes a regression fail loudly instead of
          # silently passing on a machine whose own Nix builds aren't
          # sandboxed (this flake's own dev machine, notably).
          code-quality-tests =
            pkgs.runCommand "code-quality-tests"
              {
                nativeBuildInputs = [
                  pkgs.cargo
                  pkgs.rustc
                  # `cargo build` alone never needs a C linker (a library
                  # target's final output is an internal .rlib), but `cargo
                  # test`/`cargo llvm-cov` link a real executable and do --
                  # without this, that step fails with "linker `cc` not
                  # found" (and, before that, a red herring about `xcrun`
                  # failing to locate the SDK, which is actually just cc's
                  # own absence surfacing first). Found by isolating this
                  # exact case in a minimal reproduction.
                  pkgs.stdenv.cc
                  pkgs.cargo-llvm-cov
                  pkgs.llvm
                  pkgs.rust-code-analysis
                  pkgs.git
                  pkgs.jq
                  codeQualityTools.cargo-crap
                  codeQualityTools.cargo-iceberg4rust
                  codeQualityTools.jscpd
                  (pkgs.python3.withPackages (ps: [
                    ps.pytest
                    ps.pytest-cov
                    codeQualityTools.crap4py
                    codeQualityTools.complexipy
                    codeQualityTools.pyscn
                  ]))
                ];
                CARGO_NET_OFFLINE = "true";
              }
              ''
                export HOME="$TMPDIR"
                export CARGO_HOME="$TMPDIR/cargo-home"
                export LLVM_COV="${pkgs.llvm}/bin/llvm-cov"
                export LLVM_PROFDATA="${pkgs.llvm}/bin/llvm-profdata"
                cd ${self}/engineering/swe/code-quality
                python3 -m pytest tests/ -v -p no:cacheprovider
                touch $out
              '';
        };

        devShells.default = pkgs.mkShell {
          nativeBuildInputs = with pkgs; [
            nodejs
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
