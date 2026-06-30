/**
 * Registry of supported embedding models.
 *
 * Each entry maps an accepted model name (or short alias) to its metadata:
 *   - xenovaId:  model ID used with @xenova/transformers pipeline
 *   - dim:       output vector dimension (dense)
 *   - sparse:    true if the model also produces lexical sparse weights (BGE-M3)
 *   - prefix:    instruction prefix strategy ("e5" | "none")
 *   - isDefault: true when this entry matches the active EMBEDDING_MODEL env var
 *                (computed at call time by resolveModel / getDefaultModel)
 *
 * Supported values for the EMBEDDING_MODEL env var:
 *   Xenova/multilingual-e5-small  (default)
 *   multilingual-e5-small
 *   multilingual-e5-base
 *   multilingual-e5-large
 *   BAAI/bge-m3
 *   Xenova/all-MiniLM-L6-v2
 */

const DEFAULT_MODEL = "Xenova/multilingual-e5-small";

const REGISTRY = {
  // ── E5 small (default) ────────────────────────────────────────────────────
  "Xenova/multilingual-e5-small": {
    xenovaId: "Xenova/multilingual-e5-small",
    dim: 384,
    sparse: false,
    prefix: "e5",
  },
  "multilingual-e5-small": {
    xenovaId: "Xenova/multilingual-e5-small",
    dim: 384,
    sparse: false,
    prefix: "e5",
  },

  // ── E5 base ───────────────────────────────────────────────────────────────
  "Xenova/multilingual-e5-base": {
    xenovaId: "Xenova/multilingual-e5-base",
    dim: 768,
    sparse: false,
    prefix: "e5",
  },
  "multilingual-e5-base": {
    xenovaId: "Xenova/multilingual-e5-base",
    dim: 768,
    sparse: false,
    prefix: "e5",
  },

  // ── E5 large ──────────────────────────────────────────────────────────────
  "Xenova/multilingual-e5-large": {
    xenovaId: "Xenova/multilingual-e5-large",
    dim: 1024,
    sparse: false,
    prefix: "e5",
  },
  "multilingual-e5-large": {
    xenovaId: "Xenova/multilingual-e5-large",
    dim: 1024,
    sparse: false,
    prefix: "e5",
  },

  // ── BGE-M3 (dense + sparse) ───────────────────────────────────────────────
  "BAAI/bge-m3": {
    xenovaId: "Xenova/bge-m3",
    dim: 1024,
    sparse: true,
    prefix: "none",
  },
  "Xenova/bge-m3": {
    xenovaId: "Xenova/bge-m3",
    dim: 1024,
    sparse: true,
    prefix: "none",
  },

  // ── MiniLM (legacy alias from .env.example) ───────────────────────────────
  "Xenova/all-MiniLM-L6-v2": {
    xenovaId: "Xenova/all-MiniLM-L6-v2",
    dim: 384,
    sparse: false,
    prefix: "none",
  },
  "all-MiniLM-L6-v2": {
    xenovaId: "Xenova/all-MiniLM-L6-v2",
    dim: 384,
    sparse: false,
    prefix: "none",
  },
};

/**
 * Canonical model list for the Compare tab model selector.
 * Each entry has an id (accepted by the search API) and a display label.
 */
export const CANONICAL_MODELS = [
  { id: "Xenova/multilingual-e5-small", label: "E5 Small" },
  { id: "Xenova/multilingual-e5-base",  label: "E5 Base" },
  { id: "Xenova/multilingual-e5-large", label: "E5 Large" },
  { id: "BAAI/bge-m3",                  label: "BGE-M3" },
  { id: "Xenova/all-MiniLM-L6-v2",      label: "MiniLM L6" },
];

/**
 * Return the currently configured default model name (from EMBEDDING_MODEL env).
 * @returns {string}
 */
export function getDefaultModel() {
  return process.env.EMBEDDING_MODEL ?? DEFAULT_MODEL;
}

/**
 * Resolve a model name to its registry entry.
 * Throws a descriptive error for unknown models.
 * The returned entry includes an `isDefault` boolean indicating whether
 * this model is the currently configured default (per EMBEDDING_MODEL env var).
 *
 * @param {string} name  Value from EMBEDDING_MODEL env var (or alias)
 * @returns {{ xenovaId: string, dim: number, sparse: boolean, prefix: string, isDefault: boolean }}
 */
export function resolveModel(name) {
  const entry = REGISTRY[name];
  if (!entry) {
    const known = Object.keys(REGISTRY)
      .filter((k) => !k.startsWith("Xenova/") && !k.startsWith("BAAI/"))
      .join(", ");
    throw new Error(
      `Unknown EMBEDDING_MODEL: "${name}". Supported values: ${known}. ` +
        "Check SCHEMA.md for the full list and migration instructions."
    );
  }
  const defaultName = getDefaultModel();
  const isDefault =
    name === defaultName || entry.xenovaId === REGISTRY[defaultName]?.xenovaId;
  return { ...entry, isDefault };
}

/**
 * Return the dense vector dimension for a model name.
 * @param {string} name
 * @returns {number}
 */
export function getModelDim(name) {
  return resolveModel(name).dim;
}
