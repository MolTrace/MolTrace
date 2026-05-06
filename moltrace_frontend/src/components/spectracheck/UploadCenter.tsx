"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useOptionalSpectraCheckWorkspaceSession } from "@/components/spectracheck/spectracheck-workspace-session-context"
import { QualityAssessmentCard } from "@/src/components/spectracheck/QualityAssessmentCard"
import { QualityFindingsTable } from "@/src/components/spectracheck/QualityFindingsTable"
import { QualityStatusBadge } from "@/src/components/spectracheck/QualityStatusBadge"
import { ApiError, apiFetch } from "@/src/lib/api/client"
import { parseQualityControlPayload } from "@/src/lib/spectracheck/quality-control-assessment"
import { trackFileUploaded, trackQcCompleted } from "@/src/lib/analytics/analytics-client"
import {
  normalizeSessionFileRecord,
  normalizeSessionFileRecordList,
  type SessionFileRecord,
} from "@/src/lib/spectracheck/session-file-record"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

const FILE_KIND_OPTIONS = [
  "processed_nmr",
  "raw_fid",
  "ms_peak_table",
  "lcms_mzml",
  "lcms_mzxml",
  "lcms_peak_table",
  "report",
  "other",
] as const

const SESSION_ROLE_OPTIONS = [
  "processed_1h",
  "processed_13c",
  "raw_fid_1h",
  "raw_fid_13c",
  "ms1",
  "msms",
  "lcms",
  "report_source",
  "other",
] as const

type FileKind = (typeof FILE_KIND_OPTIONS)[number]
type SessionRole = (typeof SESSION_ROLE_OPTIONS)[number]

type FileRecord = SessionFileRecord

type Props = {
  sessionId?: string | null
  onUseFile?: (args: { role: SessionRole; file: FileRecord }) => void
}

function formatBytes(size: number | null): string {
  if (size == null || !Number.isFinite(size) || size < 0) return "—"
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(iso: string | null): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString()
}

function errorText(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message || fallback
  if (err instanceof Error) return err.message || fallback
  return fallback
}

export function UploadCenter({ sessionId = null, onUseFile }: Props) {
  const workspaceSession = useOptionalSpectraCheckWorkspaceSession()
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [fileKind, setFileKind] = useState<FileKind>("processed_nmr")
  const [sessionRole, setSessionRole] = useState<SessionRole>("processed_1h")

  const [uploadBusy, setUploadBusy] = useState(false)
  const [attachBusy, setAttachBusy] = useState(false)
  const [listBusy, setListBusy] = useState(false)
  const [error, setError] = useState("")

  const [uploadedFileRecord, setUploadedFileRecord] = useState<FileRecord | null>(null)
  const [localSessionFiles, setLocalSessionFiles] = useState<FileRecord[]>([])
  const [activeRoleFile, setActiveRoleFile] = useState<Partial<Record<SessionRole, string>>>({})

  const [fileQcById, setFileQcById] = useState<Record<string, unknown>>({})
  const [qcAssessFileId, setQcAssessFileId] = useState<string | null>(null)
  const [qcViewFileId, setQcViewFileId] = useState<string | null>(null)
  const qcFindingsRef = useRef<HTMLDivElement | null>(null)

  const hasSession = Boolean(sessionId && sessionId.trim())
  const canUpload = Boolean(selectedFile) && !uploadBusy
  const canAttach = hasSession && uploadedFileRecord != null && !attachBusy

  const sessionFiles = workspaceSession?.sessionFiles ?? localSessionFiles

  async function loadSessionFiles(currentSessionId: string) {
    setListBusy(true)
    try {
      const data = await apiFetch<unknown>(`/spectracheck/sessions/${encodeURIComponent(currentSessionId)}/files`, {
        method: "GET",
      })
      setLocalSessionFiles(normalizeSessionFileRecordList(data))
    } catch (err) {
      setError(errorText(err, "Could not load session files."))
      setLocalSessionFiles([])
    } finally {
      setListBusy(false)
    }
  }

  useEffect(() => {
    if (workspaceSession) {
      return
    }
    if (!hasSession || !sessionId) {
      setLocalSessionFiles([])
      return
    }
    void loadSessionFiles(sessionId.trim())
  }, [hasSession, sessionId, workspaceSession])

  async function onUploadFile() {
    if (!selectedFile) return
    setUploadBusy(true)
    setError("")
    try {
      const fd = new FormData()
      fd.append("file", selectedFile)
      fd.append("file_kind", fileKind)
      const data = await apiFetch<unknown>("/files/upload", {
        method: "POST",
        body: fd,
      })
      const rec = normalizeSessionFileRecord(data)
      if (!rec) {
        throw new Error("Upload succeeded but file record was not returned.")
      }
      setUploadedFileRecord(rec)
      trackFileUploaded({
        session_id: sessionId?.trim() || undefined,
        metadata: {
          file_kind: fileKind,
          file_size_bytes: selectedFile.size,
          has_sha256: Boolean(rec.sha256),
        },
      })
    } catch (err) {
      setError(errorText(err, "Upload failed."))
    } finally {
      setUploadBusy(false)
    }
  }

  async function onAttachToSession() {
    if (!hasSession || !sessionId || !uploadedFileRecord) return
    setAttachBusy(true)
    setError("")
    try {
      await apiFetch(`/spectracheck/sessions/${encodeURIComponent(sessionId.trim())}/files`, {
        method: "POST",
        body: {
          file_id: uploadedFileRecord.file_id,
          file_kind: fileKind,
          session_role: sessionRole,
        },
      })
      if (workspaceSession) {
        await workspaceSession.refreshSessionFiles()
      } else {
        await loadSessionFiles(sessionId.trim())
      }
    } catch (err) {
      setError(errorText(err, "Could not attach file to session."))
    } finally {
      setAttachBusy(false)
    }
  }

  function clearSelectedFile() {
    setSelectedFile(null)
    setUploadedFileRecord(null)
    setError("")
  }

  const tableRows = useMemo(() => sessionFiles, [sessionFiles])

  function setRoleSelection(role: SessionRole, file: FileRecord) {
    setActiveRoleFile((prev) => ({ ...prev, [role]: file.file_id }))
    onUseFile?.({ role, file })
  }

  const runFileQcAssess = useCallback(async (fileId: string) => {
    const fid = fileId.trim()
    if (!fid) return
    setQcAssessFileId(fid)
    try {
      const res = await apiFetch<unknown>(`/quality-control/files/${encodeURIComponent(fid)}/assess`, {
        method: "POST",
        body: {},
      })
      setFileQcById((prev) => ({ ...prev, [fid]: res }))
      try {
        const parsed = parseQualityControlPayload(res, {
          targetType: "spectracheck_session_file",
          modality: "spectracheck_upload",
        })
        trackQcCompleted({
          metadata: {
            qc_status: parsed.qcStatus,
            readiness_status: parsed.readinessLabel,
            target_type: parsed.targetType,
          },
        })
      } catch {
        /* optional parse */
      }
    } catch {
      try {
        const g = await apiFetch<unknown>(`/quality-control/files/${encodeURIComponent(fid)}`, { method: "GET" })
        setFileQcById((prev) => ({ ...prev, [fid]: g }))
      } catch {
        // Leave prior cache; user can still use files without QC.
      }
    } finally {
      setQcAssessFileId(null)
    }
  }, [])

  const loadFileQcOnly = useCallback(async (fileId: string) => {
    const fid = fileId.trim()
    if (!fid) return
    setQcAssessFileId(fid)
    try {
      const g = await apiFetch<unknown>(`/quality-control/files/${encodeURIComponent(fid)}`, { method: "GET" })
      setFileQcById((prev) => ({ ...prev, [fid]: g }))
    } catch {
      // optional GET failure — View stays disabled until assessment exists
    } finally {
      setQcAssessFileId(null)
    }
  }, [])

  const qcViewPayload = qcViewFileId ? fileQcById[qcViewFileId] : undefined
  const qcViewParsed = useMemo(
    () =>
      qcViewPayload !== undefined
        ? parseQualityControlPayload(qcViewPayload, { targetType: "file", modality: "spectracheck_upload" })
        : null,
    [qcViewPayload],
  )

  function renderFileQcCell(fileId: string) {
    const raw = fileQcById[fileId]
    const parsed =
      raw !== undefined
        ? parseQualityControlPayload(raw, { targetType: "file", modality: "spectracheck_session_file" })
        : null
    const busy = qcAssessFileId === fileId
    const hasAssessment = raw !== undefined
    return (
      <div className="flex min-w-[200px] max-w-[280px] flex-col gap-1.5">
        <QualityStatusBadge status={parsed?.qcStatus ?? "not_assessed"} />
        <div className="flex flex-wrap gap-1">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="h-8"
            disabled={busy}
            onClick={() => void runFileQcAssess(fileId)}
          >
            {busy ? "Running…" : "Run QC"}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8"
            disabled={!hasAssessment}
            onClick={() => setQcViewFileId(fileId)}
          >
            View QC
          </Button>
        </div>
      </div>
    )
  }

  return (
    <Card className="min-w-0">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2">
          Upload Center
          <InfoTooltip
            content="Upload raw or processed scientific files, preserve hashes, and attach files to the current SpectraCheck session."
            label="Upload Center information"
          />
        </CardTitle>
        <CardDescription>
          Upload and attach scientific files to the current session. Uploaded file bytes are not persisted in localStorage.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-3">
          <div className="space-y-2">
            <Label htmlFor="upload-center-file">file upload</Label>
            <Input
              id="upload-center-file"
              type="file"
              onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="upload-center-kind">file kind dropdown</Label>
            <select
              id="upload-center-kind"
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
              value={fileKind}
              onChange={(e) => setFileKind(e.target.value as FileKind)}
            >
              {FILE_KIND_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="upload-center-role">session role dropdown</Label>
            <select
              id="upload-center-role"
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
              value={sessionRole}
              onChange={(e) => setSessionRole(e.target.value as SessionRole)}
            >
              {SESSION_ROLE_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button type="button" onClick={() => void onUploadFile()} disabled={!canUpload}>
            {uploadBusy ? "Uploading..." : "Upload file"}
          </Button>
          <Button type="button" variant="secondary" onClick={() => void onAttachToSession()} disabled={!canAttach}>
            {attachBusy ? "Attaching..." : "Attach to session"}
          </Button>
          <Button type="button" variant="outline" onClick={clearSelectedFile}>
            Clear selected file
          </Button>
        </div>

        {!hasSession ? (
          <p className="text-xs text-muted-foreground">Attach to session is available when a sessionId exists.</p>
        ) : null}
        {error ? <p className="text-sm text-destructive">{error}</p> : null}

        {uploadedFileRecord ? (
          <Card className="border-muted">
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Uploaded FileRecord</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-2 text-sm sm:grid-cols-2">
              <p>
                <span className="text-muted-foreground">filename:</span> {uploadedFileRecord.filename}
              </p>
              <p>
                <span className="text-muted-foreground">file size:</span> {formatBytes(uploadedFileRecord.file_size)}
              </p>
              <p className="sm:col-span-2">
                <span className="text-muted-foreground">SHA-256:</span> {uploadedFileRecord.sha256 ?? "—"}
              </p>
              <p>
                <span className="text-muted-foreground">file kind:</span> {uploadedFileRecord.file_kind}
              </p>
              <p>
                <span className="text-muted-foreground">created date:</span> {formatDate(uploadedFileRecord.created_at)}
              </p>
              <div className="sm:col-span-2 border-t pt-3">
                <p className="mb-2 text-xs font-medium text-muted-foreground">Quality control</p>
                {renderFileQcCell(uploadedFileRecord.file_id)}
              </div>
            </CardContent>
          </Card>
        ) : null}

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium">Session file table</h3>
            <Badge variant="outline">{tableRows.length}</Badge>
          </div>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>filename</TableHead>
                  <TableHead>file size</TableHead>
                  <TableHead>SHA-256</TableHead>
                  <TableHead>file kind</TableHead>
                  <TableHead>created date</TableHead>
                  <TableHead>session use</TableHead>
                  <TableHead>quality control</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {listBusy ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-sm text-muted-foreground">
                      Loading session files...
                    </TableCell>
                  </TableRow>
                ) : null}
                {!listBusy && tableRows.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-sm text-muted-foreground">
                      No session files found.
                    </TableCell>
                  </TableRow>
                ) : null}
                {!listBusy &&
                  tableRows.map((f) => (
                    <TableRow key={f.file_id}>
                      <TableCell className="max-w-[220px] truncate">{f.filename}</TableCell>
                      <TableCell>{formatBytes(f.file_size)}</TableCell>
                      <TableCell className="max-w-[240px] truncate font-mono text-xs">{f.sha256 ?? "—"}</TableCell>
                      <TableCell>{f.file_kind}</TableCell>
                      <TableCell>{formatDate(f.created_at)}</TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          <Button type="button" variant="outline" size="sm" onClick={() => setRoleSelection("processed_1h", f)}>
                            use in processed 1H
                          </Button>
                          <Button type="button" variant="outline" size="sm" onClick={() => setRoleSelection("processed_13c", f)}>
                            use in processed 13C
                          </Button>
                          <Button type="button" variant="outline" size="sm" onClick={() => setRoleSelection("raw_fid_1h", f)}>
                            use in raw FID
                          </Button>
                          <Button type="button" variant="outline" size="sm" onClick={() => setRoleSelection("msms", f)}>
                            use in MS/MS
                          </Button>
                          <Button type="button" variant="outline" size="sm" onClick={() => setRoleSelection("lcms", f)}>
                            use in LC-MS
                          </Button>
                        </div>
                      </TableCell>
                      <TableCell className="align-top">{renderFileQcCell(f.file_id)}</TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </div>
        </div>

        {Object.keys(activeRoleFile).length > 0 ? (
          <div className="flex flex-wrap gap-1 text-xs">
            {Object.entries(activeRoleFile).map(([role, fileId]) => (
              <Badge key={role} variant="secondary">
                {role}: {fileId}
              </Badge>
            ))}
          </div>
        ) : null}
      </CardContent>

      <Dialog open={qcViewFileId != null} onOpenChange={(o) => !o && setQcViewFileId(null)}>
        <DialogContent className="max-h-[min(90vh,880px)] max-w-3xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>File quality assessment</DialogTitle>
            <DialogDescription className="font-mono text-xs">
              {qcViewFileId ? (
                <>
                  <span className="text-muted-foreground">file id:</span> {qcViewFileId}
                </>
              ) : null}
            </DialogDescription>
          </DialogHeader>
          {qcViewFileId && qcViewParsed && qcViewPayload !== undefined ? (
            <div className="space-y-4">
              <QualityAssessmentCard
                qcStatus={qcViewParsed.qcStatus}
                readinessLabel={qcViewParsed.readinessLabel}
                qualityScore={qcViewParsed.qualityScore}
                targetType={qcViewParsed.targetType}
                modality={qcViewParsed.modality}
                warningsCount={qcViewParsed.warningsCount}
                findingsCount={qcViewParsed.findingsCount}
                recommendedActions={qcViewParsed.recommendedActions}
                showOverride={qcViewParsed.showOverride}
                developerJson={qcViewPayload}
                runQcBusy={qcAssessFileId === qcViewFileId}
                onRunQc={() => void runFileQcAssess(qcViewFileId)}
                onViewFindings={() => qcFindingsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
              />
              <div ref={qcFindingsRef}>
                <p className="mb-2 text-xs font-medium text-muted-foreground">Findings</p>
                <QualityFindingsTable findings={qcViewParsed.findings} />
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => qcViewFileId && void loadFileQcOnly(qcViewFileId)}
                disabled={qcAssessFileId === qcViewFileId}
              >
                Refresh from server
              </Button>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </Card>
  )
}
