// Medium adapter (paste platform). Loads only when `medium` is a target.
import { buildDoc, sidecar, validate } from "./_paste.mjs";

export default {
  id: "medium",
  emit: (data, body, config) => buildDoc(data, body, config, "medium"),
  sidecar: (data, config) => sidecar(data, config, "medium"),
  validate: (raw, ctx) => validate(raw, ctx, "medium"),
};
