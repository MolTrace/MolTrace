// React DevTools Standalone connector. Renders a render-blocking <script>
// tag that connects the in-page React renderer to a DevTools server listening
// on localhost:8097.
//
// Gated behind NEXT_PUBLIC_ENABLE_REACT_DEVTOOLS_BRIDGE because:
//   - In production it 404s and stalls HTML parsing (LCP regression).
//   - In local dev without `npx react-devtools` running, every page load
//     spams the console with ERR_CONNECTION_REFUSED on localhost:8097.
// Default off; opt in with NEXT_PUBLIC_ENABLE_REACT_DEVTOOLS_BRIDGE=1 once
// the standalone DevTools window is open.
export function DevToolsBridge() {
  if (process.env.NODE_ENV === "production") return null
  if (process.env.NEXT_PUBLIC_ENABLE_REACT_DEVTOOLS_BRIDGE !== "1") return null
  return <script src="http://localhost:8097" />
}
