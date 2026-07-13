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
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        py = pkgs.python3.withPackages (ps: [ ps.pyyaml ]);

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
