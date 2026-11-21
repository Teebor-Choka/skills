// Shared logic for "paste" platforms (Medium, Substack): no frontmatter, an H1
// title, absolute links, and metadata carried in a <slug>.meta.json sidecar
// (those editors have no frontmatter, so title/subtitle/canonical are pasted by
// hand). Imported transitively only when a paste adapter loads.
import fs from "node:fs";
import path from "node:path";
import {
  rewriteBody,
  canonicalFor,
  platformTags,
  assetUrl,
  isAbsUrl,
} from "../lib.mjs";

export function buildDoc(data, body, config, platform) {
  const parts = [`# ${data.title}`, ""];
  if (data.subtitle) parts.push(`_${data.subtitle}_`, "");
  if (data.coverImage)
    parts.push(
      `![${data.coverImageAlt || data.title}](${assetUrl(
        data.coverImage.replace(/^img:/, ""),
        data.slug,
        config,
        { absolute: true },
      )})`,
      "",
    );
  parts.push(
    rewriteBody(body, { platform, absolute: true, slug: data.slug, config }),
  );
  return parts.join("\n");
}

export function sidecar(data, config, platform) {
  return {
    platform,
    title: data.title,
    subtitle: data.subtitle,
    tags: platformTags(data, "medium", config), // paste platforms follow Medium's tag rules
    canonicalUrl: canonicalFor(data, config),
    instructions:
      platform === "medium"
        ? 'Paste the .md into Medium. Then Story settings → Advanced → set canonical to canonicalUrl. (Or use Medium\'s "Import a story" on the live canonical URL to auto-set it.)'
        : "Paste the .md into Substack. Set the title and subtitle above, then Post settings → set canonical URL to canonicalUrl.",
  };
}

export function validate(raw, { slug, dir, config }, platform) {
  const errors = [];
  if (/^---\r?\n/.test(raw))
    errors.push(`${platform}: must NOT have frontmatter (paste-ready)`);
  const firstLine = raw.split("\n").find((l) => l.trim());
  if (!firstLine || !firstLine.startsWith("# "))
    errors.push(`${platform}: must start with an H1 "# title"`);
  // External copies must use absolute URLs (readers are off-site).
  for (const m of raw.matchAll(/\]\((\/[^)]+)\)/g))
    errors.push(
      `${platform}: root-relative link "${m[1]}" — external output must be absolute`,
    );
  const meta = path.join(dir, `${slug}.meta.json`);
  if (!fs.existsSync(meta))
    errors.push(`${platform}: missing sidecar ${slug}.meta.json`);
  else {
    try {
      const j = JSON.parse(fs.readFileSync(meta, "utf8"));
      if (!j.title) errors.push(`${platform}: sidecar missing title`);
      if (!isAbsUrl(j.canonicalUrl))
        errors.push(`${platform}: sidecar canonicalUrl must be absolute`);
    } catch (e) {
      errors.push(`${platform}: sidecar not valid JSON — ${e.message}`);
    }
  }
  return errors;
}
