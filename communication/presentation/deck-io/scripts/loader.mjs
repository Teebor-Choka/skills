// Lazy format-adapter loader (mirrors blog-syndication/loader.mjs). Adapter ids
// are known statically; a module imports only when that format is ingested — so
// a pptx run never loads the pdf adapter (or pdfjs).
export const FORMATS = ["pptx", "pdf"];

export async function loadAdapter(fmt) {
  if (!FORMATS.includes(fmt)) throw new Error(`unknown deck format "${fmt}"`);
  const mod = await import(`./adapters/${fmt}.mjs`);
  return mod.default;
}
