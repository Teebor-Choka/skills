// Dispatch a deck file to the right (lazily-loaded) format adapter.
import path from "node:path";
import { loadAdapter } from "./loader.mjs";

export async function ingest(file) {
  const ext = path.extname(file).toLowerCase().slice(1);
  const fmt = ext === "pptx" ? "pptx" : ext === "pdf" ? "pdf" : null;
  if (!fmt)
    throw new Error(
      `unsupported deck format: ${file} (expected .pptx or .pdf)`,
    );
  const adapter = await loadAdapter(fmt);
  return adapter.ingest(file);
}
