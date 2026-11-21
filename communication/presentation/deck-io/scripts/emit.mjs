// Apply safe-fix ops to a deck and write a *.fixed copy (never edits in place).
// pptx only — a pdf is not editable, so review reports pdf fixes rather than
// applying them.
import fs from "node:fs";
import path from "node:path";
import { loadAdapter } from "./loader.mjs";

export async function emit(file, ops, outFile) {
  const ext = path.extname(file).toLowerCase().slice(1);
  if (ext !== "pptx")
    throw new Error(`safe-fix supports pptx only (got .${ext})`);
  const adapter = await loadAdapter("pptx");
  if (typeof adapter.emit !== "function")
    throw new Error("pptx adapter has no emit");
  const out = outFile || file.replace(/\.pptx$/i, ".fixed.pptx");
  fs.writeFileSync(out, adapter.emit(file, ops));
  return out;
}
