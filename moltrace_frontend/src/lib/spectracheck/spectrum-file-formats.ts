export const SPECTRACHECK_TEXT_SPECTRUM_ACCEPT = [
  ".csv",
  ".tsv",
  ".txt",
  ".json",
  ".jcamp",
  ".jdx",
  ".dx",
  ".xy",
  ".asc",
  ".dat",
].join(",")

export const SPECTRACHECK_PROCESSED_NMR_SPECTRUM_ACCEPT = SPECTRACHECK_TEXT_SPECTRUM_ACCEPT

export const SPECTRACHECK_RAW_FID_ARCHIVE_ACCEPT = [
  ".zip",
  ".tar.gz",
  ".tgz",
  "application/zip",
  "application/gzip",
  "application/x-gzip",
].join(",")

export const SPECTRACHECK_VENDOR_NMR_SPECTRUM_ACCEPT = [
  ".fid",
  ".ser",
  ".1r",
  ".1i",
  ".2rr",
  ".2ri",
].join(",")

export const SPECTRACHECK_NMR_SPECTRUM_ACCEPT = [
  SPECTRACHECK_TEXT_SPECTRUM_ACCEPT,
  SPECTRACHECK_RAW_FID_ARCHIVE_ACCEPT,
  SPECTRACHECK_VENDOR_NMR_SPECTRUM_ACCEPT,
].join(",")

export const SPECTRACHECK_RAW_FID_ACCEPT = SPECTRACHECK_RAW_FID_ARCHIVE_ACCEPT

export const SPECTRACHECK_MS_SPECTRUM_ACCEPT = [
  ".mzML",
  ".mzXML",
  ".mzData",
  ".imzML",
  ".mgf",
  ".cdf",
  ".netcdf",
  ".raw",
  ".wiff",
  ".wiff2",
  ".d",
  ".yep",
  ".baf",
  ".tdf",
  ".tsf",
  ".xml",
  SPECTRACHECK_TEXT_SPECTRUM_ACCEPT,
].join(",")

export const SPECTRACHECK_ALL_SPECTRUM_ACCEPT = [
  SPECTRACHECK_NMR_SPECTRUM_ACCEPT,
  SPECTRACHECK_MS_SPECTRUM_ACCEPT,
].join(",")

const TEXT_SPECTRUM_RE = /\.(csv|tsv|txt|json|jcamp|jdx|dx|xy|asc|dat)$/i
const RAW_FID_ARCHIVE_RE = /\.(zip|tar\.gz|tgz)$/i
const RAW_FID_RE = /\.(zip|tar\.gz|tgz|fid|ser|1r|1i|2rr|2ri)$/i
const MS_SPECTRUM_RE = /\.(mzml|mzxml|mzdata|imzml|mgf|cdf|netcdf|raw|wiff2?|d|yep|baf|tdf|tsf|xml)$/i

export function isTextSpectrumFilename(filename: string) {
  return TEXT_SPECTRUM_RE.test(filename)
}

export function isRawFidLikeFilename(filename: string) {
  return RAW_FID_RE.test(filename)
}

export function isRawFidArchiveFilename(filename: string) {
  return RAW_FID_ARCHIVE_RE.test(filename)
}

export function isMsSpectrumFilename(filename: string) {
  return MS_SPECTRUM_RE.test(filename) || isTextSpectrumFilename(filename)
}

export function isSpectraCheckSpectrumFilename(filename: string) {
  return isTextSpectrumFilename(filename) || isRawFidLikeFilename(filename) || isMsSpectrumFilename(filename)
}
