import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"

/**
 * PredictionRequest is `extra="forbid"`, so a key the server does not declare is a 422 for the
 * WHOLE request — not an ignored field. The old body sent five such keys and every "Run
 * prediction" click failed. Validated directly against the Pydantic model, the old shape reports:
 *
 *   target_module, task_key, input_summary_json, artifact_id, experimental_mode
 *     -> all extra_forbidden
 *
 * These two call sites are the only POSTers of /ai/predictions, and nothing type-checks their
 * body (it goes out as a plain object through apiFetch<unknown>), so tsc cannot catch a
 * regression here. This test is the guard instead.
 */

/** The POST body literal in each file, keyed by the statement that opens it. */
const FILES: { path: string; opener: string }[] = [
  { path: "components/ai/ai-predictions-workspace.tsx", opener: "const body: Record<string, unknown> = {" },
  { path: "components/ai/ai-module-prediction-augmentation.tsx", opener: "body: {" },
]

/** Keys the server rejects outright. Their presence in the BODY is the bug returning. */
const FORBIDDEN_KEYS = ["target_module", "task_key", "input_summary_json", "experimental_mode"]

const REQUIRED_KEYS = [
  "service_key",
  "model_artifact_id",
  "request_json",
  "experimental",
  "evidence_item_id",
  "compound_id",
  "session_id",
  "notes",
]

/**
 * Extract exactly the body object literal by brace-matching from its opener.
 *
 * A fixed-size slice is not good enough: both files also call trackAiPredictionRunStarted with
 * target_module/task_key, which are legitimate analytics labels sitting a few lines from the
 * body. A naive window catches those and reports a bug that is not there — it did, on the first
 * run of this test.
 */
function bodySource(file: { path: string; opener: string }): string {
  const text = readFileSync(resolve(process.cwd(), file.path), "utf8")
  const at = text.indexOf(file.opener)
  expect(at, `${file.path} should contain ${file.opener}`).toBeGreaterThan(-1)
  const from = text.indexOf("{", at + file.opener.length - 1)
  let depth = 0
  for (let i = from; i < text.length; i += 1) {
    if (text[i] === "{") depth += 1
    else if (text[i] === "}") {
      depth -= 1
      if (depth === 0) return text.slice(from, i + 1)
    }
  }
  throw new Error(`unbalanced braces in ${file.path}`)
}

/** Top-level keys of the body literal, ignoring anything nested inside it. */
function bodyKeys(src: string): string[] {
  const keys: string[] = []
  let depth = 0
  for (const line of src.split("\n")) {
    const m = /^\s*([a-z_][a-z0-9_]*)\s*:/i.exec(line)
    if (depth === 1 && m) keys.push(m[1]!)
    for (const ch of line) {
      if (ch === "{" || ch === "[") depth += 1
      else if (ch === "}" || ch === "]") depth -= 1
    }
  }
  return keys
}

describe("/ai/predictions request body", () => {
  for (const file of FILES) {
    describe(file.path, () => {
      const keys = bodyKeys(bodySource(file))

      it("sends every field the server declares, and nothing else", () => {
        expect([...keys].sort()).toEqual([...REQUIRED_KEYS].sort())
      })

      for (const key of FORBIDDEN_KEYS) {
        it(`never sends ${key} — extra="forbid" makes it a 422`, () => {
          expect(keys).not.toContain(key)
        })
      }

      it("uses model_artifact_id, not the bare artifact_id the server rejects", () => {
        expect(keys).not.toContain("artifact_id")
        expect(keys).toContain("model_artifact_id")
      })

      it("omits non-positive ids rather than sending 0 — the server requires ge=1", () => {
        const src = bodySource(file)
        for (const key of ["evidence_item_id", "compound_id", "session_id"]) {
          expect(src, `${file.path}:${key}`).toMatch(new RegExp(`${key}:[^,]*> 0 \\? [a-z]+ : null`))
        }
      })
    })
  }
})
