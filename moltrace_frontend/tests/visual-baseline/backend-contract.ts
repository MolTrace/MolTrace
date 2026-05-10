#!/usr/bin/env -S pnpm tsx
/**
 * MolTrace UI design system — frontend/backend contract audit.
 *
 * Scans frontend source files for backend API calls, compares them against the
 * backend OpenAPI document, and writes JSON + Markdown reports beside the
 * visual baseline reports. This complements visual screenshots: when a new
 * surface or control is added, the audit catches missing backend routes before
 * the UI silently degrades.
 *
 * Prereq: backend running on http://localhost:8000, or set BACKEND_OPENAPI_URL.
 *
 * Run via: pnpm visual:backend-contract
 */

import ts from "typescript"
import { readdir, readFile, writeFile } from "node:fs/promises"
import { dirname, extname, join, relative, sep } from "node:path"
import { fileURLToPath } from "node:url"
import { ROUTES } from "./routes"

const __dirname = dirname(fileURLToPath(import.meta.url))
const FRONTEND_ROOT = join(__dirname, "../..")
const REPORT_JSON_PATH = join(__dirname, "backend-contract-report.json")
const REPORT_MD_PATH = join(__dirname, "backend-contract-report.md")
const OPENAPI_URL = process.env.BACKEND_OPENAPI_URL ?? "http://localhost:8000/openapi.json"
const STRICT_UNRESOLVED = process.env.BACKEND_CONTRACT_STRICT_UNRESOLVED === "1"

const SCAN_ROOTS = ["app", "components", "src", "lib", "hooks"]
const SOURCE_EXTENSIONS = new Set([".ts", ".tsx"])
const TEST_FILE_RE = /(?:^|[./\\])(?:__tests__|tests)(?:[./\\])|(?:\.test|\.spec)\.[tj]sx?$/
const GENERATED_FILE_RE = /(?:^|[./\\])schema\.d\.ts$/
const API_CLIENT_IMPLEMENTATION_FILES = new Set(["lib/api/client.ts", "src/lib/api/client.ts"])

type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | "OPTIONS" | "HEAD" | "ANY"

type ApiCall = {
  method: HttpMethod
  path: string
  rawPath: string
  file: string
  line: number
  column: number
  source: "apiFetch" | "fetch(buildApiPath)" | "fetch(/api/backend)"
}

type UnresolvedCall = {
  file: string
  line: number
  column: number
  source: string
  reason: string
}

type OpenApiOperation = {
  method: Exclude<HttpMethod, "ANY">
  path: string
}

type OpenApiDocument = {
  paths?: Record<string, Record<string, unknown>>
}

type VariablePathDeclaration = {
  name: string
  initializer: ts.Expression
  scope: ts.Node
  start: number
}

type PathResolver = (name: string, atNode: ts.Node, seen: Set<string>) => string | null

function isSourceFile(path: string) {
  if (!SOURCE_EXTENSIONS.has(extname(path))) return false
  const rel = relative(FRONTEND_ROOT, path)
  if (TEST_FILE_RE.test(rel) || GENERATED_FILE_RE.test(rel)) return false
  return !rel.split(sep).some((part) => part === "node_modules" || part === ".next")
}

async function walk(dir: string): Promise<string[]> {
  const entries = await readdir(dir, { withFileTypes: true })
  const files: string[] = []
  for (const entry of entries) {
    if (entry.name === "node_modules" || entry.name === ".next") continue
    const path = join(dir, entry.name)
    if (entry.isDirectory()) {
      files.push(...(await walk(path)))
    } else if (entry.isFile() && isSourceFile(path)) {
      files.push(path)
    }
  }
  return files
}

function lineAndColumn(sourceFile: ts.SourceFile, node: ts.Node) {
  const pos = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile))
  return { line: pos.line + 1, column: pos.character + 1 }
}

function propertyNameText(name: ts.PropertyName): string | null {
  if (ts.isIdentifier(name) || ts.isStringLiteral(name) || ts.isNumericLiteral(name)) return name.text
  return null
}

function methodFromOptions(options: ts.Expression | undefined): HttpMethod {
  if (!options || !ts.isObjectLiteralExpression(options)) return "GET"
  for (const prop of options.properties) {
    if (!ts.isPropertyAssignment(prop)) continue
    const name = propertyNameText(prop.name)
    if (name !== "method") continue
    const value = prop.initializer
    if (ts.isStringLiteralLike(value)) {
      const method = value.text.toUpperCase()
      if (["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"].includes(method)) {
        return method as HttpMethod
      }
    }
  }
  return "ANY"
}

function expressionToPath(expr: ts.Expression, resolvePath: PathResolver, seen = new Set<string>()): string | null {
  if (ts.isStringLiteralLike(expr)) return expr.text

  if (ts.isIdentifier(expr)) return resolvePath(expr.text, expr, seen)

  if (ts.isAsExpression(expr) || ts.isSatisfiesExpression(expr) || ts.isNonNullExpression(expr)) {
    return expressionToPath(expr.expression, resolvePath, seen)
  }

  if (ts.isParenthesizedExpression(expr)) return expressionToPath(expr.expression, resolvePath, seen)

  if (ts.isTemplateExpression(expr)) {
    let value = expr.head.text
    for (const span of expr.templateSpans) {
      const nested = expressionToPath(span.expression, resolvePath, seen)
      value += nested ?? "{param}"
      value += span.literal.text
    }
    return value
  }

  if (ts.isBinaryExpression(expr) && expr.operatorToken.kind === ts.SyntaxKind.PlusToken) {
    const left = expressionToPath(expr.left, resolvePath, seen)
    const right = expressionToPath(expr.right, resolvePath, seen)
    if (left != null && right != null) return `${left}${right}`
  }

  if (ts.isCallExpression(expr)) {
    const callee = expr.expression
    if (ts.isIdentifier(callee) && callee.text === "buildApiPath" && expr.arguments[0]) {
      return expressionToPath(expr.arguments[0], resolvePath, seen)
    }
  }

  return null
}

function nearestScope(node: ts.Node): ts.Node {
  let current: ts.Node | undefined = node.parent
  while (current) {
    if (ts.isSourceFile(current) || ts.isBlock(current) || ts.isFunctionLike(current)) return current
    current = current.parent
  }
  return node.getSourceFile()
}

function scopeDepth(node: ts.Node) {
  let depth = 0
  let current: ts.Node | undefined = node
  while (current) {
    depth++
    current = current.parent
  }
  return depth
}

function scopeContains(scope: ts.Node, node: ts.Node, sourceFile: ts.SourceFile) {
  return scope.getStart(sourceFile) <= node.getStart(sourceFile) && node.getEnd() <= scope.getEnd()
}

function collectVariablePathDeclarations(sourceFile: ts.SourceFile): VariablePathDeclaration[] {
  const declarations: VariablePathDeclaration[] = []
  const visit = (node: ts.Node) => {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer) {
      declarations.push({
        name: node.name.text,
        initializer: node.initializer,
        scope: nearestScope(node),
        start: node.getStart(sourceFile),
      })
    }
    ts.forEachChild(node, visit)
  }
  visit(sourceFile)
  return declarations
}

function createPathResolver(sourceFile: ts.SourceFile, declarations: VariablePathDeclaration[]): PathResolver {
  const resolver: PathResolver = (name, atNode, seen) => {
    const at = atNode.getStart(sourceFile)
    const candidates = declarations
      .filter((decl) => decl.name === name && decl.start < at && scopeContains(decl.scope, atNode, sourceFile))
      .sort((a, b) => scopeDepth(b.scope) - scopeDepth(a.scope) || b.start - a.start)

    for (const decl of candidates) {
      const key = `${decl.name}:${decl.start}`
      if (seen.has(key)) continue
      const nextSeen = new Set(seen)
      nextSeen.add(key)
      const value = expressionToPath(decl.initializer, resolver, nextSeen)
      if (value != null) return value
    }
    return null
  }
  return resolver
}

function normalizeFrontendPath(path: string): string | null {
  let value = path.trim()
  if (!value) return null
  if (value.startsWith("/api/backend")) value = value.slice("/api/backend".length) || "/"
  if (!value.startsWith("/")) return null
  value = value.split("#", 1)[0] ?? value
  value = value.split("?", 1)[0] ?? value
  value = value.replace(/\$\{[^}]+\}/g, "{param}")
  value = value.replace(/\/+/g, "/")
  value = value.replace(/(?<!\/)\{param\}$/g, "")
  if (value.length > 1) value = value.replace(/\/$/g, "")
  return value || "/"
}

function scanSourceFile(path: string, text: string): { calls: ApiCall[]; unresolved: UnresolvedCall[] } {
  const sourceFile = ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  const variableDeclarations = collectVariablePathDeclarations(sourceFile)
  const resolvePath = createPathResolver(sourceFile, variableDeclarations)
  const calls: ApiCall[] = []
  const unresolved: UnresolvedCall[] = []
  const file = relative(FRONTEND_ROOT, path)
  if (API_CLIENT_IMPLEMENTATION_FILES.has(file)) return { calls, unresolved }

  function addCall(node: ts.CallExpression, pathExpr: ts.Expression, method: HttpMethod, source: ApiCall["source"]) {
    const rawPath = expressionToPath(pathExpr, resolvePath)
    const loc = lineAndColumn(sourceFile, node)
    if (rawPath == null) {
      unresolved.push({
        file,
        line: loc.line,
        column: loc.column,
        source,
        reason: "Could not statically resolve backend path expression.",
      })
      return
    }
    const normalized = normalizeFrontendPath(rawPath)
    if (!normalized) {
      unresolved.push({
        file,
        line: loc.line,
        column: loc.column,
        source,
        reason: `Resolved path is not a backend-relative path: ${rawPath}`,
      })
      return
    }
    calls.push({ method, path: normalized, rawPath, file, line: loc.line, column: loc.column, source })
  }

  const visit = (node: ts.Node) => {
    if (ts.isCallExpression(node)) {
      const callee = node.expression
      if (ts.isIdentifier(callee) && callee.text === "apiFetch" && node.arguments[0]) {
        addCall(node, node.arguments[0], methodFromOptions(node.arguments[1]), "apiFetch")
      } else if (ts.isIdentifier(callee) && callee.text === "fetch" && node.arguments[0]) {
        const first = node.arguments[0]
        if (ts.isCallExpression(first) && ts.isIdentifier(first.expression) && first.expression.text === "buildApiPath" && first.arguments[0]) {
          addCall(node, first.arguments[0], methodFromOptions(node.arguments[1]), "fetch(buildApiPath)")
        } else {
          const rawPath = expressionToPath(first, resolvePath)
          if (rawPath?.startsWith("/api/backend")) {
            addCall(node, first, methodFromOptions(node.arguments[1]), "fetch(/api/backend)")
          }
        }
      }
    }
    ts.forEachChild(node, visit)
  }

  visit(sourceFile)
  return { calls, unresolved }
}

function openApiOperations(openapi: OpenApiDocument): OpenApiOperation[] {
  const operations: OpenApiOperation[] = []
  for (const [path, operationMap] of Object.entries(openapi.paths ?? {})) {
    for (const method of Object.keys(operationMap)) {
      const upper = method.toUpperCase()
      if (["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"].includes(upper)) {
        operations.push({ method: upper as OpenApiOperation["method"], path })
      }
    }
  }
  operations.push({ method: "GET", path: "/openapi.json" })
  return operations
}

function segmentIsParam(segment: string) {
  return /^\{[^/{}]+\}$/.test(segment)
}

function pathsMatch(frontendPath: string, backendPath: string) {
  const front = frontendPath.split("/").filter(Boolean)
  const back = backendPath.split("/").filter(Boolean)
  if (front.length !== back.length) return false
  return front.every((segment, index) => {
    const other = back[index]!
    return segment === other || segmentIsParam(segment) || segmentIsParam(other)
  })
}

function callHasOperation(call: ApiCall, operations: OpenApiOperation[]) {
  return operations.some((operation) => {
    const methodMatches = call.method === "ANY" || call.method === operation.method
    return methodMatches && pathsMatch(call.path, operation.path)
  })
}

function staticAppRoutes(files: string[]) {
  return files
    .filter((file) => file.startsWith(join(FRONTEND_ROOT, "app")) && file.endsWith(`${sep}page.tsx`))
    .map((file) => {
      const rel = relative(join(FRONTEND_ROOT, "app"), file).replace(/\\/g, "/")
      const route = `/${rel.replace(/\/page\.tsx$/, "").replace(/^page\.tsx$/, "")}`
      return route === "/" ? "/" : route.replace(/\/$/, "")
    })
    .filter((route) => !route.includes("["))
    .sort()
}

function markdownTable(rows: string[][], headers: string[]) {
  if (rows.length === 0) return "_None._"
  return [
    `| ${headers.join(" | ")} |`,
    `| ${headers.map(() => "---").join(" | ")} |`,
    ...rows.map((row) => `| ${row.map((value) => value.replace(/\|/g, "\\|")).join(" | ")} |`),
  ].join("\n")
}

async function main() {
  const files = (await Promise.all(SCAN_ROOTS.map((root) => walk(join(FRONTEND_ROOT, root))))).flat().sort()
  const scanned = await Promise.all(
    files.map(async (file) => {
      const text = await readFile(file, "utf-8")
      return scanSourceFile(file, text)
    }),
  )
  const calls = scanned.flatMap((result) => result.calls)
  const unresolved = scanned.flatMap((result) => result.unresolved)

  const openapiResponse = await fetch(OPENAPI_URL)
  if (!openapiResponse.ok) {
    throw new Error(`Could not fetch OpenAPI from ${OPENAPI_URL}: ${openapiResponse.status} ${openapiResponse.statusText}`)
  }
  const openapi = (await openapiResponse.json()) as OpenApiDocument
  const operations = openApiOperations(openapi)
  const missing = calls.filter((call) => !callHasOperation(call, operations))

  const routes = staticAppRoutes(files)
  const baselineRouteSet = new Set(ROUTES.map((route) => route.path))
  const staticRoutesNotInBaseline = routes.filter((route) => !baselineRouteSet.has(route))

  const report = {
    capturedAt: new Date().toISOString(),
    openapiUrl: OPENAPI_URL,
    scannedFiles: files.length,
    visualBaselineRoutes: ROUTES.length,
    staticAppRoutes: routes.length,
    staticRoutesNotInBaseline,
    backendOperations: operations.length,
    frontendApiCalls: calls.length,
    missingCount: missing.length,
    unresolvedCount: unresolved.length,
    missing,
    unresolved,
  }

  await writeFile(REPORT_JSON_PATH, JSON.stringify(report, null, 2) + "\n", "utf-8")

  const missingRows = missing.map((call) => [
    call.method,
    call.path,
    `${call.file}:${call.line}`,
    call.source,
  ])
  const unresolvedRows = unresolved.slice(0, 50).map((call) => [
    call.source,
    `${call.file}:${call.line}`,
    call.reason,
  ])
  const uncoveredRows = staticRoutesNotInBaseline.slice(0, 75).map((route) => [route])

  const md = [
    `# MolTrace frontend/backend contract audit — ${report.capturedAt}`,
    "",
    `- OpenAPI URL: ${OPENAPI_URL}`,
    `- Scanned source files: ${report.scannedFiles}`,
    `- Visual baseline routes: ${report.visualBaselineRoutes}`,
    `- Static app routes: ${report.staticAppRoutes}`,
    `- Backend OpenAPI operations: ${report.backendOperations}`,
    `- Frontend backend API calls: ${report.frontendApiCalls}`,
    `- Missing backend operations: ${report.missingCount}`,
    `- Unresolved static path expressions: ${report.unresolvedCount}`,
    "",
    "## Missing Backend Operations",
    "",
    markdownTable(missingRows, ["Method", "Path", "Caller", "Source"]),
    "",
    "## Unresolved Static Path Expressions",
    "",
    markdownTable(unresolvedRows, ["Source", "Caller", "Reason"]),
    "",
    "## Static App Routes Not In Visual Baseline",
    "",
    "These are informational. Dynamic routes, mobile-only/PWA utility pages, and intentionally excluded variants may be normal.",
    "",
    markdownTable(uncoveredRows, ["Route"]),
    "",
  ].join("\n")
  await writeFile(REPORT_MD_PATH, md, "utf-8")

  console.log(`MolTrace frontend/backend contract audit`)
  console.log(`  Frontend calls : ${report.frontendApiCalls}`)
  console.log(`  Backend ops    : ${report.backendOperations}`)
  console.log(`  Missing        : ${report.missingCount}`)
  console.log(`  Unresolved     : ${report.unresolvedCount}`)
  console.log(`  JSON           : ${relative(__dirname, REPORT_JSON_PATH)}`)
  console.log(`  MD             : ${relative(__dirname, REPORT_MD_PATH)}`)

  if (missing.length > 0 || (STRICT_UNRESOLVED && unresolved.length > 0)) process.exit(1)
}

main().catch((err) => {
  console.error("Fatal error:", err)
  process.exit(1)
})
