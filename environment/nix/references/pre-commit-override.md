# Lightweight pre-commit override

The nixpkgs `pre-commit` package pulls heavyweight test-only deps (dotnet-sdk, nodejs, go,
coursier, cabal-install, cargo) via `nativeCheckInputs`. Even with `doCheck = false`,
`doInstallCheck = true` plus string interpolation in `preCheck` forces those to build from
source. Strip them with an override in the `let` block before the `pre-commit-check`:

```nix
pre-commit-lightweight = pkgs.pre-commit.overridePythonAttrs {
  nativeCheckInputs = [ ];
  doCheck = false;
  doInstallCheck = false;
  dontUsePytestCheck = true;
  preCheck = "";
  postCheck = "";
};
```

Then pass `package = pre-commit-lightweight;` to `pre-commit.lib.${system}.run { ... }` and
drop `tools = pkgs;` (unnecessary). The `run` function in `cachix/git-hooks.nix` accepts
`package` as a module option.
