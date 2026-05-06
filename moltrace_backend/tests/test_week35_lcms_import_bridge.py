import base64
import hashlib
import struct

from nmrcheck.lcms_import import import_lcms_bridge
from nmrcheck.models import LCMSImportBridgeRequest


def _b64_f64(values):
    return base64.b64encode(struct.pack("<" + "d" * len(values), *values)).decode()


def test_processed_lcms_peak_table_extracts_ms1_and_msms_lists():
    text = """scan_id,ms_level,rt_min,mz,intensity,precursor_mz
ms1_001,1,0.50,47.04914,100,
ms1_001,1,0.50,48.05249,2.3,
ms2_001,2,0.51,47.04914,10,47.04914
ms2_001,2,0.51,29.03858,100,47.04914
ms2_001,2,0.51,31.01839,25,47.04914
"""
    result = import_lcms_bridge(LCMSImportBridgeRequest(filename="ethanol_lcms.csv", source_text=text))
    assert result.source_format == "processed_peak_table"
    assert result.label == "ready_for_downstream_ms"
    assert result.scan_count == 2
    assert result.ms1_scan_count == 1
    assert result.ms2_scan_count == 1
    assert abs(result.primary_ms1_mz - 47.04914) < 0.00001
    assert result.selected_msms_precursor_mz == 47.04914
    assert "47.049140" in result.extracted_ms1_peak_list_text
    assert "29.038580" in result.extracted_msms_peak_list_text
    assert result.immutable_raw_data is True
    assert result.file_sha256 == hashlib.sha256(text.encode()).hexdigest()


def test_mzml_import_decodes_simple_uncompressed_binary_arrays():
    mz1 = _b64_f64([47.04914, 48.05249])
    in1 = _b64_f64([100.0, 2.3])
    mz2 = _b64_f64([47.04914, 29.03858, 31.01839])
    in2 = _b64_f64([10.0, 100.0, 25.0])
    xml = f'''<mzML><run><spectrumList count="2">
      <spectrum id="scan=1" defaultArrayLength="2">
        <cvParam accession="MS:1000511" name="ms level" value="1"/>
        <cvParam accession="MS:1000285" name="total ion current" value="102.3"/>
        <cvParam accession="MS:1000504" name="base peak m/z" value="47.04914"/>
        <cvParam accession="MS:1000505" name="base peak intensity" value="100"/>
        <scanList><scan><cvParam accession="MS:1000016" name="scan start time" value="0.50" unitName="minute"/></scan></scanList>
        <binaryDataArrayList count="2">
          <binaryDataArray><cvParam accession="MS:1000514" name="m/z array"/><cvParam accession="MS:1000523" name="64-bit float"/><binary>{mz1}</binary></binaryDataArray>
          <binaryDataArray><cvParam accession="MS:1000515" name="intensity array"/><cvParam accession="MS:1000523" name="64-bit float"/><binary>{in1}</binary></binaryDataArray>
        </binaryDataArrayList>
      </spectrum>
      <spectrum id="scan=2" defaultArrayLength="3">
        <cvParam accession="MS:1000511" name="ms level" value="2"/>
        <scanList><scan><cvParam accession="MS:1000016" name="scan start time" value="0.51" unitName="minute"/></scan></scanList>
        <precursorList><precursor><selectedIonList><selectedIon><cvParam accession="MS:1000744" name="selected ion m/z" value="47.04914"/></selectedIon></selectedIonList></precursor></precursorList>
        <binaryDataArrayList count="2">
          <binaryDataArray><cvParam accession="MS:1000514" name="m/z array"/><cvParam accession="MS:1000523" name="64-bit float"/><binary>{mz2}</binary></binaryDataArray>
          <binaryDataArray><cvParam accession="MS:1000515" name="intensity array"/><cvParam accession="MS:1000523" name="64-bit float"/><binary>{in2}</binary></binaryDataArray>
        </binaryDataArrayList>
      </spectrum>
    </spectrumList></run></mzML>'''
    result = import_lcms_bridge(LCMSImportBridgeRequest(filename="sample.mzML", source_text=xml))
    assert result.source_format == "mzML"
    assert result.ms1_scan_count == 1
    assert result.ms2_scan_count == 1
    assert result.chromatogram[0].retention_time_min == 0.5
    assert result.extracted_precursors[0].precursor_mz == 47.04914
    assert "31.018390" in result.extracted_msms_peak_list_text


def test_mzxml_import_decodes_interleaved_peak_pairs():
    values = [47.04914, 100.0, 48.05249, 2.3]
    peaks = base64.b64encode(struct.pack(">" + "f" * len(values), *values)).decode()
    text = f'''<mzXML><msRun scanCount="1">
      <scan num="1" msLevel="1" retentionTime="PT30S" basePeakMz="47.04914" basePeakIntensity="100" totIonCurrent="102.3">
        <peaks precision="32" byteOrder="network" compressionType="none">{peaks}</peaks>
      </scan>
    </msRun></mzXML>'''
    result = import_lcms_bridge(LCMSImportBridgeRequest(filename="sample.mzXML", source_text=text))
    assert result.source_format == "mzXML"
    assert result.scan_count == 1
    assert result.chromatogram[0].retention_time_min == 0.5
    assert abs(result.primary_ms1_mz - 47.04914) < 0.00001


def test_unsupported_vendor_format_returns_provenance_warning_without_crashing():
    result = import_lcms_bridge(
        LCMSImportBridgeRequest(filename="sample.raw", source_format="unsupported_vendor", source_text="vendor bytes placeholder")
    )
    assert result.label == "unsupported_vendor_format"
    assert result.source_format == "unsupported_vendor"
    assert result.scan_count == 0
    assert result.immutable_raw_data is True
    assert any("Convert" in item for item in result.recommended_next_actions)
