// React DevTools Standalone connector. Renders a render-blocking <script>
// tag that connects the in-page React renderer to a DevTools server listening
// on localhost:8097. The connection is invaluable in local development, but
// in production builds the script 404s and stalls HTML parsing — which can
// add hundreds of ms (or more) to LCP. NODE_ENV is set to 'production' by
// `next build` on both Render and Vercel, so this gate is platform-neutral.
export function DevToolsBridge() {
  if (process.env.NODE_ENV === "production") return null
  return <script src="http://localhost:8097" />
}
