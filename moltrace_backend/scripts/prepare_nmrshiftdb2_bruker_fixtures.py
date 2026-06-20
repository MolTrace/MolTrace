from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import ssl
import sys
import urllib.request
import zipfile
from pathlib import Path

import defusedxml.ElementTree as ET  # XXE-safe parser (defense-in-depth; dev fixture script)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "nmrshiftdb2"
SOURCE_INDEX = FIXTURE_ROOT / "source" / "nmrshiftdb2rawdata.nmredata.sd"
RAW_DIR = FIXTURE_ROOT / "raw"
EXTRACTED_DIR = RAW_DIR / "extracted"
EXPECTED_DIR = FIXTURE_ROOT / "expected"
MANIFEST = EXPECTED_DIR / "nmrshiftdb2_bruker_20.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download and prepare 20 1D Bruker NMRShiftDB2 FID fixtures."
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument(
        "--verify-tls",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Verify TLS certificates while downloading (default: on). Pass --no-verify-tls only "
            "for the legacy NMRShiftDB2 raw-data endpoint, which can present an incomplete chain."
        ),
    )
    args = parser.parse_args()
    # TLS is verified by DEFAULT (secure-by-default); this unverified context is built ONLY on an
    # explicit --no-verify-tls opt-out for the legacy NMRShiftDB2 endpoint (incomplete cert chain).
    # Dev-only fixture-download CLI; never imported by the application.
    # nosemgrep: python.lang.security.unverified-ssl-context.unverified-ssl-context
    ssl_context = None if args.verify_tls else ssl._create_unverified_context()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    EXPECTED_DIR.mkdir(parents=True, exist_ok=True)

    fixtures: list[dict[str, object]] = []
    seen: set[str] = set()
    for candidate in _candidate_urls()[args.start :]:
        spectrum_id = candidate["spectrum_id"]
        if spectrum_id in seen:
            continue
        seen.add(spectrum_id)
        archive = RAW_DIR / f"nmrshiftdb2_{spectrum_id}_{candidate['nucleus'].lower()}.zip"
        extracted = EXTRACTED_DIR / f"{archive.stem}_bruker"
        try:
            if not archive.exists():
                _download(
                    candidate["source_url"], archive, timeout=args.timeout, context=ssl_context
                )
            if not zipfile.is_zipfile(archive):
                archive.unlink(missing_ok=True)
                continue
            if not extracted.exists():
                _extract_zip(archive, extracted)
            dataset_root = _find_bruker_dataset(extracted)
            if dataset_root is None:
                shutil.rmtree(extracted, ignore_errors=True)
                continue
            peaklist = dataset_root / "pdata" / "1" / "peaklist.xml"
            if not peaklist.exists():
                continue
            expected_peaks = _reference_peaks_from_peaklist(peaklist, candidate["nucleus"])
            if not expected_peaks:
                continue
            fixtures.append(
                {
                    "source": "NMRShiftDB2",
                    "source_url": candidate["source_url"],
                    "spectrum_id": spectrum_id,
                    "vendor": "Bruker",
                    "nucleus": candidate["nucleus"],
                    "archive": str(archive.relative_to(FIXTURE_ROOT)),
                    "archive_sha256": _sha256(archive),
                    "extracted_path": str(dataset_root.relative_to(FIXTURE_ROOT)),
                    "reference_peak_ppm": expected_peaks,
                    "reference_peak_count": len(expected_peaks),
                    "ppm_tolerance": 0.01,
                    "peak_count_tolerance": 2,
                }
            )
            print(f"prepared {len(fixtures):02d}/{args.limit}: {archive.name}")
            if len(fixtures) >= args.limit:
                break
        except Exception as exc:  # pragma: no cover - helper script diagnostics.
            print(f"skipping {candidate['source_url']}: {exc}", file=sys.stderr)

    if len(fixtures) < args.limit:
        raise SystemExit(f"Only prepared {len(fixtures)} fixtures; requested {args.limit}.")

    manifest = {
        "source_index": str(SOURCE_INDEX.relative_to(FIXTURE_ROOT)),
        "source_index_sha256": _sha256(SOURCE_INDEX),
        "fixture_count": len(fixtures),
        "fixtures": fixtures,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {MANIFEST.relative_to(ROOT)}")
    return 0


def _candidate_urls() -> list[dict[str, str]]:
    text = SOURCE_INDEX.read_text(encoding="utf-8", errors="replace")
    candidates: list[dict[str, str]] = []
    for match in re.finditer(r"https?://[^\s<>]+?_(?:1H|13C)\.zip", text):
        base_url = match.group(0)
        spectrum_id_match = re.search(r"/(\d+)_(1H|13C)\.zip$", base_url)
        if not spectrum_id_match:
            continue
        spectrum_id, nucleus = spectrum_id_match.groups()
        source_url = (
            f"{base_url}?spectrumid={spectrum_id}"
            "&nmrshiftdbaction=exportspec&format=rawdata"
        )
        candidates.append(
            {
                "source_url": source_url,
                "spectrum_id": spectrum_id,
                "nucleus": nucleus,
            }
        )
    return candidates


def _download(url: str, target: Path, *, timeout: int, context: ssl.SSLContext | None) -> None:
    with urllib.request.urlopen(url, timeout=timeout, context=context) as response:
        target.write_bytes(response.read())


def _extract_zip(archive: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        root = target.resolve()
        for member in zf.infolist():
            member_target = (target / member.filename).resolve()
            if root not in member_target.parents and member_target != root:
                raise RuntimeError(f"Unsafe archive member: {member.filename}")
        zf.extractall(target)


def _find_bruker_dataset(root: Path) -> Path | None:
    datasets = [
        fid.parent
        for fid in root.rglob("fid")
        if fid.is_file() and (fid.parent / "acqus").is_file()
    ]
    if not datasets:
        return None
    datasets.sort(key=lambda path: (len(path.relative_to(root).parts), str(path).lower()))
    return datasets[0]


def _reference_peaks_from_peaklist(peaklist: Path, nucleus: str) -> list[float]:
    root = ET.parse(peaklist).getroot()
    peaks: list[float] = []
    if nucleus == "13C":
        for peak in root.findall(".//Peak1D"):
            try:
                ppm = float(peak.attrib["F1"])
            except (KeyError, ValueError):
                continue
            if not _is_common_13c_solvent_peak(ppm):
                peaks.append(ppm)
    else:
        for block in root.findall(".//PeakList1D"):
            block_peaks: list[tuple[float, float]] = []
            for peak in block.findall("Peak1D"):
                try:
                    block_peaks.append(
                        (float(peak.attrib["F1"]), float(peak.attrib.get("intensity", "0")))
                    )
                except ValueError:
                    continue
            if block_peaks:
                peaks.append(max(block_peaks, key=lambda item: item[1])[0])

    return _cluster_ppm(peaks, tolerance=0.08 if nucleus == "1H" else 0.18)


def _cluster_ppm(peaks: list[float], *, tolerance: float) -> list[float]:
    if not peaks:
        return []
    ordered = sorted(float(peak) for peak in peaks)
    clusters: list[list[float]] = []
    for peak in ordered:
        if not clusters or abs(peak - clusters[-1][-1]) > tolerance:
            clusters.append([peak])
        else:
            clusters[-1].append(peak)
    return [round(sum(cluster) / len(cluster), 6) for cluster in clusters]


def _is_common_13c_solvent_peak(ppm: float) -> bool:
    return (
        76.4 <= ppm <= 77.8  # CDCl3 triplet
        or 38.7 <= ppm <= 40.2  # DMSO-d6 / methanol-d4 region
        or 48.2 <= ppm <= 50.3  # CD3OD
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
