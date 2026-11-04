# Same toolset the scripts request through `nix shell nixpkgs#...`, for an interactive
# `nix-shell scripts/shell.nix` session. Needs <nixpkgs> on NIX_PATH.
{
  pkgs ? import <nixpkgs> { },
}:
pkgs.mkShell {
  packages = with pkgs; [
    yt-dlp
    ffmpeg
    jq
    whisper-cpp
    python3
  ];
}
