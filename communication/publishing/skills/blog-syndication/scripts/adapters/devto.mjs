// dev.to / Forem adapter. Frontmatter with an absolute canonical_url; tags are
// lowercase-alphanumeric and truncated. Loads only when `devto` is a target.
import {
  rewriteBody,
  canonicalFor,
  platformTags,
  assetUrl,
  yamlFront,
  splitFrontmatter,
  isAbsUrl,
} from "../lib.mjs";

function emit(data, body, config) {
  const fm = {
    title: data.title,
    published: data.draft === false,
    description: data.excerpt?.trim(),
    tags: platformTags(data, "devto", config).join(", "),
    canonical_url: canonicalFor(data, config),
    cover_image: data.coverImage
      ? assetUrl(data.coverImage.replace(/^img:/, ""), data.slug, config, {
          absolute: true,
        })
      : undefined,
    series: data.series,
  };
  return (
    yamlFront(fm) +
    "\n" +
    rewriteBody(body, {
      platform: "devto",
      absolute: true,
      slug: data.slug,
      config,
    })
  );
}

function validate(raw, { config }) {
  const errors = [];
  const { data, body, hadFrontmatter } = splitFrontmatter(raw);
  if (!hadFrontmatter) {
    errors.push("devto: missing frontmatter");
    return errors;
  }
  if (typeof data.title !== "string" || !data.title)
    errors.push("devto: title required");
  if (typeof data.published !== "boolean")
    errors.push("devto: published must be boolean");
  if (!isAbsUrl(data.canonical_url))
    errors.push("devto: canonical_url must be absolute URL");
  if (data.cover_image !== undefined && !isAbsUrl(data.cover_image))
    errors.push("devto: cover_image must be absolute URL");
  const tags =
    typeof data.tags === "string"
      ? data.tags
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean)
      : [];
  const max = (config.devto && config.devto.maxTags) ?? 4;
  if (tags.length > max) errors.push(`devto: ${tags.length} tags (max ${max})`);
  for (const t of tags)
    if (!/^[a-z0-9]+$/.test(t))
      errors.push(`devto: tag "${t}" must be lowercase-alphanumeric`);
  if (!body.trim()) errors.push("devto: empty body");
  return errors;
}

export default { id: "devto", emit, validate };
