# MolTrace frontend/backend contract audit — 2026-05-10T14:01:46.121Z

- OpenAPI URL: http://localhost:8000/openapi.json
- Scanned source files: 504
- Visual baseline routes: 71
- Static app routes: 81
- Backend OpenAPI operations: 781
- Frontend backend API calls: 669
- Missing backend operations: 0
- Unresolved static path expressions: 18

## Missing Backend Operations

_None._

## Unresolved Static Path Expressions

| Source | Caller | Reason |
| --- | --- | --- |
| apiFetch | components/admin/mobile-tenant-summary-workspace.tsx:162 | Could not statically resolve backend path expression. |
| apiFetch | components/admin/system-status-workspace.tsx:125 | Could not statically resolve backend path expression. |
| apiFetch | components/admin/tenant-detail-workspace.tsx:2795 | Could not statically resolve backend path expression. |
| apiFetch | components/compounds/compound-detail-workspace.tsx:213 | Resolved path is not a backend-relative path: {param} |
| apiFetch | components/compounds/compound-detail-workspace.tsx:214 | Resolved path is not a backend-relative path: {param}/structures |
| apiFetch | components/compounds/compound-detail-workspace.tsx:215 | Resolved path is not a backend-relative path: {param}/aliases |
| apiFetch | components/compounds/compound-detail-workspace.tsx:216 | Resolved path is not a backend-relative path: {param}/relationships |
| apiFetch | components/compounds/compound-detail-workspace.tsx:217 | Resolved path is not a backend-relative path: {param}/evidence-links |
| apiFetch | components/compounds/compound-detail-workspace.tsx:267 | Resolved path is not a backend-relative path: {param}/aliases |
| apiFetch | components/compounds/compound-detail-workspace.tsx:294 | Resolved path is not a backend-relative path: {param}/relationships |
| apiFetch | components/knowledge/knowledge-extraction-records-workspace.tsx:135 | Could not statically resolve backend path expression. |
| apiFetch | components/ml/ml-model-factory-dashboard.tsx:188 | Could not statically resolve backend path expression. |
| apiFetch | components/ml/ml-training-run-launcher.tsx:146 | Could not statically resolve backend path expression. |
| apiFetch | components/settings/method-registry-workspace.tsx:143 | Could not statically resolve backend path expression. |
| apiFetch | components/validation/validation-dashboard-workspace.tsx:241 | Could not statically resolve backend path expression. |
| apiFetch | src/components/mobile/MobileCommandCenter.tsx:156 | Could not statically resolve backend path expression. |
| apiFetch | src/components/mobile/MobileRegulatoryQueue.tsx:159 | Could not statically resolve backend path expression. |
| apiFetch | src/lib/dashboard/dashboard-cross-module-command-center.ts:114 | Could not statically resolve backend path expression. |

## Static App Routes Not In Visual Baseline

These are informational. Dynamic routes, mobile-only/PWA utility pages, and intentionally excluded variants may be normal.

| Route |
| --- |
| /api-test |
| /dashboard/projects |
| /dashboard/reactions |
| /dashboard/regulatory |
| /dashboard/reports |
| /dashboard/roi |
| /dashboard/settings |
| /dashboard/spectroscopy |
| /mobile |
| /offline |
