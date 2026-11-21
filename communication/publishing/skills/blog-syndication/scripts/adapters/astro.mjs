// astro adapter — targets an Astro content-collection ("post") on your own site,
// the canonical copy. This is THE one platform-specific schema in the toolkit
// (a specific site's content-collection shape): to target a different site, fork
// this file. Nothing in the generic core depends on it; it loads only when
// `astro` is a target.
import {
  rewriteBody,
  canonicalFor,
  platformTags,
  assetUrl,
  yamlFront,
  asDate,
  splitFrontmatter,
  isDate,
  isAbsUrl,
} from "../lib.mjs";

// The site's maturity taxonomy — this adapter's convention, not the core's.
const STATUS = ["idea", "prototype", "deep-dive"];

function emit(data, body, config) {
  const fm = {
    publishDate: asDate(data.publishDate) || data.publishDate,
    updateDate: data.updateDate
      ? asDate(data.updateDate) || data.updateDate
      : undefined,
    draft: data.draft ?? true,
    title: data.title,
    excerpt: data.excerpt?.trim(),
    image: data.coverImage
      ? assetUrl(data.coverImage.replace(/^img:/, ""), data.slug, config, {
          absolute: false,
        })
      : undefined,
    category: data.category,
    tags: platformTags(data, "astro", config),
    author: data.author || config.site.author,
    status: data.status,
    metadata: {
      canonical: canonicalFor(data, config),
      description: data.excerpt?.trim(),
    },
  };
  return (
    yamlFront(fm) +
    "\n" +
    rewriteBody(body, {
      platform: "astro",
      absolute: false,
      slug: data.slug,
      config,
    })
  );
}

// Source-side rule: status must be in the site taxonomy (was in core validateAll).
function sourceValidate(data) {
  const errors = [];
  if (data.status !== undefined && !STATUS.includes(data.status))
    errors.push(`status "${data.status}" not one of ${STATUS.join("|")}`);
  return { errors };
}

// Generated-document rule: a faithful replica of the site's Astro `post` zod schema, so
// we can validate the astro output without Astro's toolchain installed.
function validate(raw, { config }) {
  const errors = [];
  const { data, body, hadFrontmatter } = splitFrontmatter(raw);
  if (!hadFrontmatter) {
    errors.push("astro: missing frontmatter");
    return errors;
  }
  if (typeof data.title !== "string" || !data.title)
    errors.push("astro: title must be a non-empty string");
  if (!isDate(data.publishDate))
    errors.push(
      "astro: publishDate must be a YAML date (z.date()), got " +
        typeof data.publishDate,
    );
  if (data.updateDate !== undefined && !isDate(data.updateDate))
    errors.push("astro: updateDate must be a date");
  if (data.draft !== undefined && typeof data.draft !== "boolean")
    errors.push("astro: draft must be boolean");
  if (data.status !== undefined && !STATUS.includes(data.status))
    errors.push(`astro: status must be ${STATUS.join("|")}`);
  if (
    data.tags !== undefined &&
    (!Array.isArray(data.tags) || data.tags.some((t) => typeof t !== "string"))
  )
    errors.push("astro: tags must be string[]");
  if (data.excerpt !== undefined && typeof data.excerpt !== "string")
    errors.push("astro: excerpt must be a string");
  if (
    data.image !== undefined &&
    !String(data.image).startsWith(config.site.assetsPath)
  )
    errors.push(
      `astro: image should be root-relative under ${config.site.assetsPath}`,
    );
  const canonical = data.metadata && data.metadata.canonical;
  if (!isAbsUrl(canonical))
    errors.push("astro: metadata.canonical must be an absolute URL");
  const labsPath = safePath(config.site.labsBaseUrl);
  // On-site cross-links must be root-relative to the site's base, not absolute.
  const esc = labsPath.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const absLink = new RegExp(`\\]\\((https?://[^)]*${esc}/[^)]+)\\)`, "g");
  for (const m of body.matchAll(absLink))
    errors.push(
      `astro: cross-link should be root-relative (${labsPath}/…), found absolute ${m[1]}`,
    );
  return errors;
}

function safePath(url) {
  try {
    return new URL(url).pathname.replace(/\/$/, "");
  } catch {
    return url;
  }
}

export default { id: "astro", emit, sourceValidate, validate };
