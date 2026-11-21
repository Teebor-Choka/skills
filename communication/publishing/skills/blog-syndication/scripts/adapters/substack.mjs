// Substack adapter (paste platform). Same shape as Medium, but syndicate:
// only/except blocks filter on the substack id. Loads only when targeted.
import { buildDoc, sidecar, validate } from "./_paste.mjs";

export default {
  id: "substack",
  emit: (data, body, config) => buildDoc(data, body, config, "substack"),
  sidecar: (data, config) => sidecar(data, config, "substack"),
  validate: (raw, ctx) => validate(raw, ctx, "substack"),
};
