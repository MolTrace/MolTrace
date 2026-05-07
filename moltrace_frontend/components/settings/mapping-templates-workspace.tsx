"use client"

import { useCallback, useEffect, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { trackExternalObjectLinkCreated, trackMappingTemplateCreated } from "@/src/lib/analytics/analytics-client"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

type Row = Record<string, unknown>

type MappingTemplateRow = {
  template_id: string
  connector: string
  name: string
  source_type: string
  target_type: string
  field_map_json: string
  raw: Row
}

type ExternalRecordRow = {
  external_record_id: string
  connector: string
  source_type: string
  external_key: string
  status: string
  raw: Row
}

type ExternalObjectLinkRow = {
  external_object_link_id: string
  external_record_id: string
  target_type: string
  target_id: string
  status: string
  raw: Row
}

const SOURCE_TYPE_OPTIONS = [
  "eln_experiment",
  "lims_sample",
  "instrument_file",
  "regulatory_document",
  "reaction_table",
  "ctd_package",
  "other",
] as const

const TARGET_TYPE_OPTIONS = [
  "spectracheck_session",
  "regulatory_dossier",
  "reaction_experiment",
  "compound_batch",
  "file_record",
  "action_item",
  "other",
] as const

function isRecord(v: unknown): v is Row {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readStr(v: unknown): string {
  if (typeof v === "string") return v.trim()
  if (typeof v === "number" && Number.isFinite(v)) return String(v)
  return ""
}

function asRows(payload: unknown): Row[] {
  if (Array.isArray(payload)) return payload.filter(isRecord)
  if (!isRecord(payload)) return []
  if (Array.isArray(payload.items)) return payload.items.filter(isRecord)
  if (Array.isArray(payload.results)) return payload.results.filter(isRecord)
  if (Array.isArray(payload.mapping_templates)) return payload.mapping_templates.filter(isRecord)
  if (Array.isArray(payload.external_records)) return payload.external_records.filter(isRecord)
  if (Array.isArray(payload.external_object_links)) return payload.external_object_links.filter(isRecord)
  return []
}

function parseMappingTemplateRow(row: Row): MappingTemplateRow | null {
  const templateId = readStr(row.template_id ?? row.id)
  if (!templateId) return null
  return {
    template_id: templateId,
    connector: readStr(row.connector) || "—",
    name: readStr(row.name) || "—",
    source_type: readStr(row.source_type) || "—",
    target_type: readStr(row.target_type) || "—",
    field_map_json: typeof row.field_map_json === "string" ? row.field_map_json : JSON.stringify(row.field_map_json ?? {}, null, 2),
    raw: row,
  }
}

function parseExternalRecordRow(row: Row): ExternalRecordRow | null {
  const externalRecordId = readStr(row.external_record_id ?? row.id)
  if (!externalRecordId) return null
  return {
    external_record_id: externalRecordId,
    connector: readStr(row.connector) || "—",
    source_type: readStr(row.source_type) || "—",
    external_key: readStr(row.external_key) || "—",
    status: readStr(row.status) || "—",
    raw: row,
  }
}

function parseExternalObjectLinkRow(row: Row): ExternalObjectLinkRow | null {
  const externalObjectLinkId = readStr(row.external_object_link_id ?? row.id)
  if (!externalObjectLinkId) return null
  return {
    external_object_link_id: externalObjectLinkId,
    external_record_id: readStr(row.external_record_id) || "—",
    target_type: readStr(row.target_type) || "—",
    target_id: readStr(row.target_id) || "—",
    status: readStr(row.status) || "—",
    raw: row,
  }
}

export function MappingTemplatesWorkspace() {
  const [loadingTemplates, setLoadingTemplates] = useState(true)
  const [loadingExternalRecords, setLoadingExternalRecords] = useState(true)
  const [loadingExternalLinks, setLoadingExternalLinks] = useState(true)
  const [error, setError] = useState("")

  const [mappingTemplates, setMappingTemplates] = useState<MappingTemplateRow[]>([])
  const [externalRecords, setExternalRecords] = useState<ExternalRecordRow[]>([])
  const [externalObjectLinks, setExternalObjectLinks] = useState<ExternalObjectLinkRow[]>([])

  const [connector, setConnector] = useState("")
  const [name, setName] = useState("")
  const [sourceType, setSourceType] = useState<(typeof SOURCE_TYPE_OPTIONS)[number]>("eln_experiment")
  const [targetType, setTargetType] = useState<(typeof TARGET_TYPE_OPTIONS)[number]>("spectracheck_session")
  const [fieldMapJson, setFieldMapJson] = useState("{\n  \"external_field\": \"moltrace_field\"\n}")
  const [createTemplateBusy, setCreateTemplateBusy] = useState(false)
  const [updateTemplateBusy, setUpdateTemplateBusy] = useState(false)

  const [externalRecordConnector, setExternalRecordConnector] = useState("")
  const [externalRecordSourceType, setExternalRecordSourceType] =
    useState<(typeof SOURCE_TYPE_OPTIONS)[number]>("eln_experiment")
  const [externalRecordExternalKey, setExternalRecordExternalKey] = useState("")
  const [createExternalRecordBusy, setCreateExternalRecordBusy] = useState(false)

  const [externalLinkExternalRecordId, setExternalLinkExternalRecordId] = useState("")
  const [externalLinkTargetType, setExternalLinkTargetType] =
    useState<(typeof TARGET_TYPE_OPTIONS)[number]>("spectracheck_session")
  const [externalLinkTargetId, setExternalLinkTargetId] = useState("")
  const [createExternalLinkBusy, setCreateExternalLinkBusy] = useState(false)

  const [selectedTemplateId, setSelectedTemplateId] = useState("")
  const [selectedExternalRecordId, setSelectedExternalRecordId] = useState("")

  const loadTemplates = useCallback(async () => {
    setLoadingTemplates(true)
    setError("")
    try {
      const payload = await apiFetch<unknown>("/mapping-templates", { method: "GET" })
      const rows = asRows(payload).map(parseMappingTemplateRow).filter((row): row is MappingTemplateRow => row != null)
      setMappingTemplates(rows)
      if (!selectedTemplateId && rows.length > 0) setSelectedTemplateId(rows[0]!.template_id)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load mapping templates.")
      setMappingTemplates([])
    } finally {
      setLoadingTemplates(false)
    }
  }, [selectedTemplateId])

  const loadExternalRecords = useCallback(async () => {
    setLoadingExternalRecords(true)
    setError("")
    try {
      const payload = await apiFetch<unknown>("/external-records", { method: "GET" })
      const rows = asRows(payload).map(parseExternalRecordRow).filter((row): row is ExternalRecordRow => row != null)
      setExternalRecords(rows)
      if (!selectedExternalRecordId && rows.length > 0) {
        setSelectedExternalRecordId(rows[0]!.external_record_id)
        setExternalLinkExternalRecordId(rows[0]!.external_record_id)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load external records.")
      setExternalRecords([])
    } finally {
      setLoadingExternalRecords(false)
    }
  }, [selectedExternalRecordId])

  const loadExternalObjectLinks = useCallback(async () => {
    setLoadingExternalLinks(true)
    setError("")
    try {
      const payload = await apiFetch<unknown>("/external-object-links", { method: "GET" })
      const rows = asRows(payload)
        .map(parseExternalObjectLinkRow)
        .filter((row): row is ExternalObjectLinkRow => row != null)
      setExternalObjectLinks(rows)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load external object links.")
      setExternalObjectLinks([])
    } finally {
      setLoadingExternalLinks(false)
    }
  }, [])

  useEffect(() => {
    void Promise.all([loadTemplates(), loadExternalRecords(), loadExternalObjectLinks()])
  }, [loadTemplates, loadExternalRecords, loadExternalObjectLinks])

  useEffect(() => {
    async function loadTemplateDetail() {
      if (!selectedTemplateId) return
      try {
        const payload = await apiFetch<unknown>(`/mapping-templates/${selectedTemplateId}`, { method: "GET" })
        if (!isRecord(payload)) return
        const row = parseMappingTemplateRow(payload)
        if (!row) return
        setConnector(row.connector === "—" ? "" : row.connector)
        setName(row.name === "—" ? "" : row.name)
        if (SOURCE_TYPE_OPTIONS.includes(row.source_type as (typeof SOURCE_TYPE_OPTIONS)[number])) {
          setSourceType(row.source_type as (typeof SOURCE_TYPE_OPTIONS)[number])
        }
        if (TARGET_TYPE_OPTIONS.includes(row.target_type as (typeof TARGET_TYPE_OPTIONS)[number])) {
          setTargetType(row.target_type as (typeof TARGET_TYPE_OPTIONS)[number])
        }
        setFieldMapJson(row.field_map_json)
      } catch {
        // keep current form state when detail fails
      }
    }
    void loadTemplateDetail()
  }, [selectedTemplateId])

  useEffect(() => {
    async function loadExternalRecordDetail() {
      if (!selectedExternalRecordId) return
      try {
        await apiFetch(`/external-records/${selectedExternalRecordId}`, { method: "GET" })
      } catch {
        // keep table data if detail load fails
      }
    }
    void loadExternalRecordDetail()
  }, [selectedExternalRecordId])

  async function createMappingTemplate() {
    setCreateTemplateBusy(true)
    setError("")
    try {
      const parsed = JSON.parse(fieldMapJson)
      await apiFetch("/mapping-templates", {
        method: "POST",
        body: {
          connector: connector.trim(),
          name: name.trim(),
          source_type: sourceType,
          target_type: targetType,
          field_map_json: parsed,
        },
      })
      trackMappingTemplateCreated({
        connector_type: connector.trim(),
        target_program: targetType,
        status: "created",
        source_format: sourceType,
        target_format: targetType,
      })
      await loadTemplates()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create mapping template.")
    } finally {
      setCreateTemplateBusy(false)
    }
  }

  async function updateMappingTemplate() {
    if (!selectedTemplateId) return
    setUpdateTemplateBusy(true)
    setError("")
    try {
      const parsed = JSON.parse(fieldMapJson)
      await apiFetch(`/mapping-templates/${selectedTemplateId}`, {
        method: "PATCH",
        body: {
          connector: connector.trim(),
          name: name.trim(),
          source_type: sourceType,
          target_type: targetType,
          field_map_json: parsed,
        },
      })
      await loadTemplates()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update mapping template.")
    } finally {
      setUpdateTemplateBusy(false)
    }
  }

  async function createExternalRecord() {
    setCreateExternalRecordBusy(true)
    setError("")
    try {
      await apiFetch("/external-records", {
        method: "POST",
        body: {
          connector: externalRecordConnector.trim(),
          source_type: externalRecordSourceType,
          external_key: externalRecordExternalKey.trim(),
        },
      })
      setExternalRecordExternalKey("")
      await loadExternalRecords()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create external record.")
    } finally {
      setCreateExternalRecordBusy(false)
    }
  }

  async function createExternalObjectLink() {
    setCreateExternalLinkBusy(true)
    setError("")
    try {
      await apiFetch("/external-object-links", {
        method: "POST",
        body: {
          external_record_id: externalLinkExternalRecordId.trim(),
          target_type: externalLinkTargetType,
          target_id: externalLinkTargetId.trim(),
        },
      })
      trackExternalObjectLinkCreated({
        target_program: externalLinkTargetType,
        status: "created",
      })
      setExternalLinkTargetId("")
      await loadExternalObjectLinks()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create external object link.")
    } finally {
      setCreateExternalLinkBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">External Object Links and Mapping Templates</h1>
        <p className="text-muted-foreground">
          Configure mapping templates and external object links for connector-driven data flow.
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          <span
            className="cursor-help underline decoration-dotted underline-offset-2"
            title="Mapping templates define how fields from external systems become MolTrace projects, samples, sessions, dossiers, experiments, files, or action items."
          >
            Mapping templates define how fields from external systems become MolTrace projects, samples, sessions,
            dossiers, experiments, files, or action items.
          </span>
        </p>
      </div>

      {error ? <p className="text-xs text-destructive">{error}</p> : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Mapping template form</CardTitle>
          <CardDescription>
            <code className="text-xs">POST /mapping-templates</code>,{" "}
            <code className="text-xs">GET /mapping-templates</code>,{" "}
            <code className="text-xs">GET /mapping-templates/{"{template_id}"}</code>,{" "}
            <code className="text-xs">PATCH /mapping-templates/{"{template_id}"}</code>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="mapping-connector">connector</Label>
              <Input id="mapping-connector" value={connector} onChange={(e) => setConnector(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="mapping-name">name</Label>
              <Input id="mapping-name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="mapping-source-type">source type</Label>
              <select
                id="mapping-source-type"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
                value={sourceType}
                onChange={(e) => setSourceType(e.target.value as (typeof SOURCE_TYPE_OPTIONS)[number])}
              >
                {SOURCE_TYPE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="mapping-target-type">target type</Label>
              <select
                id="mapping-target-type"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
                value={targetType}
                onChange={(e) => setTargetType(e.target.value as (typeof TARGET_TYPE_OPTIONS)[number])}
              >
                {TARGET_TYPE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1 sm:col-span-2">
              <Label htmlFor="mapping-field-map-json">field map JSON</Label>
              <Textarea
                id="mapping-field-map-json"
                rows={8}
                value={fieldMapJson}
                onChange={(e) => setFieldMapJson(e.target.value)}
              />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" disabled={createTemplateBusy} onClick={() => void createMappingTemplate()}>
              {createTemplateBusy ? "Creating…" : "Create mapping template"}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={updateTemplateBusy || !selectedTemplateId}
              onClick={() => void updateMappingTemplate()}
            >
              {updateTemplateBusy ? "Saving…" : "Save selected template"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Mapping template table</CardTitle>
        </CardHeader>
        <CardContent>
          {loadingTemplates ? <p className="text-sm text-muted-foreground">Loading mapping templates…</p> : null}
          {!loadingTemplates ? (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>template ID</TableHead>
                    <TableHead>connector</TableHead>
                    <TableHead>name</TableHead>
                    <TableHead>source type</TableHead>
                    <TableHead>target type</TableHead>
                    <TableHead>field map JSON</TableHead>
                    <TableHead>open</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {mappingTemplates.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-xs text-muted-foreground">
                        No mapping templates returned.
                      </TableCell>
                    </TableRow>
                  ) : (
                    mappingTemplates.map((row) => (
                      <TableRow key={row.template_id}>
                        <TableCell className="font-mono text-[10px]">{row.template_id}</TableCell>
                        <TableCell className="text-xs">{row.connector}</TableCell>
                        <TableCell className="text-xs">{row.name}</TableCell>
                        <TableCell className="text-xs">{row.source_type}</TableCell>
                        <TableCell className="text-xs">{row.target_type}</TableCell>
                        <TableCell className="max-w-[20rem] text-xs">{row.field_map_json}</TableCell>
                        <TableCell>
                          <Button
                            type="button"
                            size="sm"
                            variant={selectedTemplateId === row.template_id ? "secondary" : "outline"}
                            onClick={() => setSelectedTemplateId(row.template_id)}
                          >
                            Open
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Create external record</CardTitle>
          <CardDescription>
            <code className="text-xs">POST /external-records</code>,{" "}
            <code className="text-xs">GET /external-records</code>,{" "}
            <code className="text-xs">GET /external-records/{"{external_record_id}"}</code>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1">
              <Label htmlFor="external-record-connector">connector</Label>
              <Input
                id="external-record-connector"
                value={externalRecordConnector}
                onChange={(e) => setExternalRecordConnector(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="external-record-source-type">source type</Label>
              <select
                id="external-record-source-type"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
                value={externalRecordSourceType}
                onChange={(e) => setExternalRecordSourceType(e.target.value as (typeof SOURCE_TYPE_OPTIONS)[number])}
              >
                {SOURCE_TYPE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="external-record-key">external key</Label>
              <Input
                id="external-record-key"
                value={externalRecordExternalKey}
                onChange={(e) => setExternalRecordExternalKey(e.target.value)}
              />
            </div>
          </div>
          <Button type="button" disabled={createExternalRecordBusy} onClick={() => void createExternalRecord()}>
            {createExternalRecordBusy ? "Creating…" : "Create external record"}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">External record table</CardTitle>
        </CardHeader>
        <CardContent>
          {loadingExternalRecords ? <p className="text-sm text-muted-foreground">Loading external records…</p> : null}
          {!loadingExternalRecords ? (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>external record ID</TableHead>
                    <TableHead>connector</TableHead>
                    <TableHead>source type</TableHead>
                    <TableHead>external key</TableHead>
                    <TableHead>status</TableHead>
                    <TableHead>open</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {externalRecords.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6} className="text-xs text-muted-foreground">
                        No external records returned.
                      </TableCell>
                    </TableRow>
                  ) : (
                    externalRecords.map((row) => (
                      <TableRow key={row.external_record_id}>
                        <TableCell className="font-mono text-[10px]">{row.external_record_id}</TableCell>
                        <TableCell className="text-xs">{row.connector}</TableCell>
                        <TableCell className="text-xs">{row.source_type}</TableCell>
                        <TableCell className="text-xs">{row.external_key}</TableCell>
                        <TableCell className="text-xs">{row.status}</TableCell>
                        <TableCell>
                          <Button
                            type="button"
                            size="sm"
                            variant={selectedExternalRecordId === row.external_record_id ? "secondary" : "outline"}
                            onClick={() => {
                              setSelectedExternalRecordId(row.external_record_id)
                              setExternalLinkExternalRecordId(row.external_record_id)
                            }}
                          >
                            Open
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Create external link</CardTitle>
          <CardDescription>
            <code className="text-xs">POST /external-object-links</code>,{" "}
            <code className="text-xs">GET /external-object-links</code>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1">
              <Label htmlFor="external-link-record-id">external record ID</Label>
              <Input
                id="external-link-record-id"
                value={externalLinkExternalRecordId}
                onChange={(e) => setExternalLinkExternalRecordId(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="external-link-target-type">target type</Label>
              <select
                id="external-link-target-type"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
                value={externalLinkTargetType}
                onChange={(e) => setExternalLinkTargetType(e.target.value as (typeof TARGET_TYPE_OPTIONS)[number])}
              >
                {TARGET_TYPE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="external-link-target-id">target ID</Label>
              <Input
                id="external-link-target-id"
                value={externalLinkTargetId}
                onChange={(e) => setExternalLinkTargetId(e.target.value)}
              />
            </div>
          </div>
          <Button type="button" disabled={createExternalLinkBusy} onClick={() => void createExternalObjectLink()}>
            {createExternalLinkBusy ? "Creating…" : "Create external object link"}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">External object link table</CardTitle>
        </CardHeader>
        <CardContent>
          {loadingExternalLinks ? <p className="text-sm text-muted-foreground">Loading external object links…</p> : null}
          {!loadingExternalLinks ? (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>external object link ID</TableHead>
                    <TableHead>external record ID</TableHead>
                    <TableHead>target type</TableHead>
                    <TableHead>target ID</TableHead>
                    <TableHead>status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {externalObjectLinks.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className="text-xs text-muted-foreground">
                        No external object links returned.
                      </TableCell>
                    </TableRow>
                  ) : (
                    externalObjectLinks.map((row) => (
                      <TableRow key={row.external_object_link_id}>
                        <TableCell className="font-mono text-[10px]">{row.external_object_link_id}</TableCell>
                        <TableCell className="font-mono text-[10px]">{row.external_record_id}</TableCell>
                        <TableCell className="text-xs">{row.target_type}</TableCell>
                        <TableCell className="text-xs">{row.target_id}</TableCell>
                        <TableCell className="text-xs">{row.status}</TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}
