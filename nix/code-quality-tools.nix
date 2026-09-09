# Custom packages for engineering/swe/code-quality's integration test --
# tools required by that skill's own scripts that aren't in nixpkgs, pinned
# to the exact versions verified against them. See engineering/swe/
# code-quality/references/{rust,python}.md for what each tool is used for.
#
# Only aarch64-darwin and x86_64-linux are supported (this flake's local
# dev machine and its actual CI platform, respectively) -- complexipy and
# pyscn ship no aarch64-linux wheel upstream, so that system throws rather
# than silently picking the wrong binary.
{ pkgs }:
rec {
  cargo-crap = pkgs.rustPlatform.buildRustPackage {
    pname = "cargo-crap";
    version = "0.5.0";
    src = pkgs.fetchCrate {
      pname = "cargo-crap";
      version = "0.5.0";
      hash = "sha256-5RhRFUh1w5/yItkmc3Vk1B6oyrmzKKl6EEZ3v0aBLwk=";
    };
    cargoHash = "sha256-vPdzZIeXsjICz5icPrr2LQ4GrcMSZe2nRa65iyzLH7Q=";
    doCheck = false;
  };

  cargo-iceberg4rust = pkgs.rustPlatform.buildRustPackage {
    pname = "cargo-iceberg4rust";
    version = "0.3.0";
    src = pkgs.fetchCrate {
      pname = "cargo-iceberg4rust";
      version = "0.3.0";
      hash = "sha256-1T5L6qNRT5pczwPRcLw/38mc13s5P/W8VKbuP1IwETM=";
    };
    cargoHash = "sha256-ksZYzvbfoAkKL0TUx2YU+GZg5q3iX5Nm712xyzfC5wU=";
    doCheck = false;
  };

  # jscpd's own crates.io release currently needs rustc 1.96, one version
  # ahead of this flake's nixpkgs pin -- but npm's optionalDependencies
  # resolve to a prebuilt per-platform binary package with zero further
  # deps, so fetching that binary directly sidesteps the toolchain gap
  # entirely rather than waiting on nixpkgs to catch up.
  jscpd =
    let
      byPlatform = {
        "aarch64-darwin" = {
          url = "https://registry.npmjs.org/jscpd-darwin-arm64/-/jscpd-darwin-arm64-5.2.0.tgz";
          hash = "sha512-QnEDfTH2MymizVHiEQpqfYEj63k1DW7QC0QBZoevh+o/iHQrHxKlgrakMysUIwIJlnmvqPB6iP/G3dBpFmnmeQ==";
        };
        "x86_64-linux" = {
          url = "https://registry.npmjs.org/jscpd-linux-x64-gnu/-/jscpd-linux-x64-gnu-5.2.0.tgz";
          hash = "sha512-p88BpA5QzyZzyF8uYeVCz9ZBoZYg8s6AwcDc3NkIDNTbrrF0sKqgGjclGWAoJvYAiGExiFNqV768pVHsE//l0Q==";
        };
      };
      info =
        byPlatform.${pkgs.stdenv.hostPlatform.system}
          or (throw "jscpd: no prebuilt binary pinned for ${pkgs.stdenv.hostPlatform.system}");
    in
    pkgs.stdenvNoCC.mkDerivation {
      pname = "jscpd";
      version = "5.2.0";
      src = pkgs.fetchurl { inherit (info) url hash; };
      sourceRoot = ".";
      unpackCmd = "tar xzf $curSrc";
      dontBuild = true;
      installPhase = ''
        mkdir -p $out/bin
        install -m755 package/bin/jscpd $out/bin/jscpd
      '';
    };

  crap4py = pkgs.python3Packages.buildPythonPackage {
    pname = "crap4py";
    version = "0.1.1";
    format = "wheel";
    src = pkgs.fetchurl {
      url = "https://files.pythonhosted.org/packages/03/c6/eda37aa64d84a3e22a5c9242e5696a83750c7737dc99d43bce97dfc53e53/crap4py-0.1.1-py3-none-any.whl";
      hash = "sha256-LNryjcz8iDE8lfG6zfmf4Zo5776YVdmBNSuwKnoXqQw=";
    };
    doCheck = false;
    pythonImportsCheck = [ "crap4py" ];
  };

  # PyO3-based, ships platform+CPython-version-specific binary wheels --
  # pinned to this flake's nixpkgs python3 version (3.14, confirmed by
  # testing directly -- the global `nixpkgs` flake registry entry used
  # while researching this resolved to 3.13, a DIFFERENT revision than
  # this flake's own pinned input). Bump both together if either changes;
  # a version mismatch fails loudly (ModuleNotFoundError on the compiled
  # extension, not a silent wrong-ABI load) rather than corrupting results.
  complexipy =
    let
      byPlatform = {
        "aarch64-darwin" = {
          url = "https://files.pythonhosted.org/packages/88/1c/1c2ae1b4984e9c0c51bd0eb7c1434abf77c6e5b77c023bbf41bc6546da31/complexipy-8.0.1-cp314-cp314-macosx_11_0_arm64.whl";
          hash = "sha256-THdotJ3w2cGCeD0vYpETn6FS7XsS9K1txuLATtbieNg=";
        };
        "x86_64-linux" = {
          url = "https://files.pythonhosted.org/packages/0d/fb/03e028bbcfe318d6ffa9bf9e62db6ae1d2cac020bf62c0ba4e90bdf5b454/complexipy-8.0.1-cp314-cp314-manylinux_2_17_x86_64.manylinux2014_x86_64.whl";
          hash = "sha256-TY9MwceFGBW3wOYuZJmCMOloPoWAEAXNwk7YBL0+Bmk=";
        };
      };
      info =
        byPlatform.${pkgs.stdenv.hostPlatform.system}
          or (throw "complexipy: no wheel pinned for ${pkgs.stdenv.hostPlatform.system}");
    in
    pkgs.python3Packages.buildPythonPackage {
      pname = "complexipy";
      version = "8.0.1";
      format = "wheel";
      src = pkgs.fetchurl { inherit (info) url hash; };
      doCheck = false;
      pythonImportsCheck = [ "complexipy" ];
    };

  # Ships a precompiled binary wrapped as a "py3-none" (CPython-version-
  # agnostic) but platform-specific wheel -- no Linux aarch64 wheel exists
  # upstream.
  pyscn =
    let
      byPlatform = {
        "aarch64-darwin" = {
          url = "https://files.pythonhosted.org/packages/a8/39/186499a9762738038a02d86b8c3c68b3a152b39f80a7418c90ada7d530da/pyscn-1.31.0-py3-none-macosx_11_0_arm64.whl";
          hash = "sha256-GUgWMdaE90dStD6ADs4a06t1mdeaGmEjJBzhdc3ESQU=";
        };
        "x86_64-linux" = {
          url = "https://files.pythonhosted.org/packages/3f/7a/22517439cb71118090ba7fc43115e436f0c87b2d6d84a0e81fb9ba0de078/pyscn-1.31.0-py3-none-manylinux_2_17_x86_64.whl";
          hash = "sha256-OlnleMV1niQqOOyRhlWMiWZEPLJLligW0/7HpyLqeps=";
        };
      };
      info =
        byPlatform.${pkgs.stdenv.hostPlatform.system}
          or (throw "pyscn: no wheel pinned for ${pkgs.stdenv.hostPlatform.system}");
    in
    pkgs.python3Packages.buildPythonPackage {
      pname = "pyscn";
      version = "1.31.0";
      format = "wheel";
      src = pkgs.fetchurl { inherit (info) url hash; };
      doCheck = false;
      # The wheel bundles a standalone prebuilt pyscn-linux-amd64 executable
      # (invoked directly via subprocess, unlike complexipy's dlopen()'d .so
      # extension above) -- its ELF PT_INTERP header hardcodes a glibc
      # loader path (e.g. /lib64/ld-linux-x86-64.so.2) that doesn't exist in
      # Nix's store, so the kernel's execve() returns ENOENT for the
      # binary's own path, confusingly identical to the binary being
      # missing entirely. autoPatchelfHook rewrites that header to Nix's
      # own dynamic linker. Found by diagnosing directly in CI: the binary
      # was confirmed present with correct permissions right before pytest
      # invoked it and still got ENOENT from pyscn's own subprocess call.
      nativeBuildInputs = pkgs.lib.optionals pkgs.stdenv.hostPlatform.isLinux [
        pkgs.autoPatchelfHook
      ];
    };
}
