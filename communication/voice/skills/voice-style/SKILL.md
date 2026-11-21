---
name: voice-style
description: Apply the plain-voice output style on a harness that has no output styles, and set its depth and length for a session. Use when a harness other than Claude Code needs the voice rules, or when asked how the unslop style and its mode command are installed.
license: MIT
compatibility: any
---

# Voice style

The `voice` plugin ships the plain-voice rules as an output style (`output-styles/unslop.md`) and a
command (`commands/unslop-mode.md`) that sets two axes for one session: de-slop depth (off, light,
default, strict) and length (terse, normal, full).

## Claude Code

Enable the plugin. The style appears as `voice:unslop` and the command as `/voice:unslop-mode`.

## Other harnesses

They have no output styles. Append the body of `output-styles/unslop.md` to the system prompt or the
always-on instructions file (`AGENTS.md`, `APPEND_SYSTEM.md`, or the agent's `developer_instructions`).
Run the mode command's steps by hand: state the depth and the length once, then follow them.

## A persona profile

The `mimic` skill writes a validated `profile.md` for one person in its state dir
(`~/.config/agents/state/voice/<persona>/`). For text drafted as that person, load the profile
after the style. Its measured habits (casing, punctuation, emoji, dashes, length, signature
phrases) win over the style's surface rules, as the style's own precedence puts the author's voice
above any anti-slop rule. The floor still holds: facts, code, exact strings and security warnings
stay intact. The profile applies to that draft only, never to your own replies.
