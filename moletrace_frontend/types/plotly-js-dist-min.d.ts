declare module "plotly.js-dist-min" {
  const Plotly: {
    downloadImage: (
      root: HTMLElement,
      opts: { format: string; filename: string; scale?: number }
    ) => Promise<string | undefined>
  }
  export default Plotly
}
