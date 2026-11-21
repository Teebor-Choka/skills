// Lazy adapter loader. Adapter ids are known statically (cheap); each module is
// import()-ed only when its platform is actually targeted — so a `--platforms
// devto` run never loads the astro adapter (or its schema).
import { PLATFORMS } from "./lib.mjs";

export { PLATFORMS };

export async function loadAdapter(id) {
  if (!PLATFORMS.includes(id)) throw new Error(`unknown platform "${id}"`);
  const mod = await import(`./adapters/${id}.mjs`);
  return mod.default;
}

export async function loadAdapters(ids) {
  const out = {};
  for (const id of ids) out[id] = await loadAdapter(id);
  return out;
}
