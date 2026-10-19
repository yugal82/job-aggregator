import DOMPurify from "isomorphic-dompurify";

const BLOCK_TAG_RE = /<\/?(p|div|ul|ol|li|br|h[1-6]|table|section|article|header|footer|blockquote|pre)\b/i;

export type SanitizedDescription =
  | { kind: "html"; html: string }
  | { kind: "text"; text: string };

export function sanitizeDescription(raw: string): SanitizedDescription {
  if (BLOCK_TAG_RE.test(raw)) {
    return { kind: "html", html: DOMPurify.sanitize(raw) };
  }
  return { kind: "text", text: raw };
}
