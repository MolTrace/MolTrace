"use client"

import { statusLabel } from "@/lib/ui/status"
import { useCallback, useEffect, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { trackExternalObjectLinkCreated, trackMappingTemplateCreated } from "@/src/lib/analytics/analytics-client"
import { Button } from "@/components/ui/button"
import { ModuleCard } from "@/components/dashboard/module-card"
import { ExternalLink, FileBox, FileSpreadsheet, Link2, Plus, Tags } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { JsonObjectField } from "@/components/ui/json-object-field"
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
  connector_id: string
  external_system: string
  external_object_type: string
  external_object_id: string
  status: string
  raw: Row
}

type ExternalObjectLinkRow = {
  external_object_link_id: string
  external_record_id: string
  moltrace_resource_type: string
  moltrace_resource_id: string
  relation_type: string
  raw: Row
}

type ConnectorOption = {
  id: string
  label: string
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

// Enums below mirror the backend create models (extra="forbid"); the option value is
// the wire token and must stay verbatim — only the displayed label is humanized.

// ExternalSystemRecordCreate.external_object_type
const EXTERNAL_OBJECT_TYPE_OPTIONS = [
  "project",
  "sample",
  "experiment",
  "batch",
  "report",
  "document",
  "result",
  "file",
  "action_item",
  "other",
] as const

// ExternalObjectLinkCreate.moltrace_resource_type
const MOLTRACE_RESOURCE_TYPE_OPTIONS = [
  "project",
  "sample",
  "spectracheck_session",
  "regulatory_dossier",
  "reaction_project",
  "reaction_experiment",
  "compound",
  "batch",
  "report",
  "file",
  "artifact",
  "action_item",
  "other",
] as const

// ExternalObjectLinkCreate.relation_type
const RELATION_TYPE_OPTIONS = [
  "source_of",
  "exported_to",
  "linked_to",
  "synchronized_with",
  "derived_from",
  "evidence_for",
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
  const externalRecordId = readStr(row.id ?? row.external_record_id)
  if (!externalRecordId) return null
  return {
    external_record_id: externalRecordId,
    connector_id: readStr(row.connector_id),
    external_system: readStr(row.external_system) || "—",
    external_object_type: readStr(row.external_object_type) || "—",
    external_object_id: readStr(row.external_object_id) || "—",
    status: readStr(row.status) || "—",
    raw: row,
  }
}

function parseExternalObjectLinkRow(row: Row): ExternalObjectLinkRow | null {
  const externalObjectLinkId = readStr(row.id ?? row.external_object_link_id)
  if (!externalObjectLinkId) return null
  return {
    external_object_link_id: externalObjectLinkId,
    external_record_id: readStr(row.external_record_id) || "—",
    moltrace_resource_type: readStr(row.moltrace_resource_type) || "—",
    moltrace_resource_id: readStr(row.moltrace_resource_id) || "—",
    relation_type: readStr(row.relation_type) || "—",
    raw: row,
  }
}

function parseConnectorOption(row: Row): ConnectorOption | null {
  const id = readStr(row.id ?? row.connector_id)
  if (!id) return null
  const label = readStr(row.display_name) || readStr(row.connector_key) || `Connector #${id}`
  return { id, label }
}

export function MappingTemplatesWorkspace() {
  const [loadingTemplates, setLoadingTemplates] = useState(true)
  const [loadingExternalRecords, setLoadingExternalRecords] = useState(true)
  const [loadingExternalLinks, setLoadingExternalLinks] = useState(true)
  const [error, setError] = useState("")

  const [mappingTemplates, setMappingTemplates] = useState<MappingTemplateRow[]>([])
  const [externalRecords, setExternalRecords] = useState<ExternalRecordRow[]>([])
  const [externalObjectLinks, setExternalObjectLinks] = useState<ExternalObjectLinkRow[]>([])
  const [connectors, setConnectors] = useState<ConnectorOption[]>([])

  const [connector, setConnector] = useState("")
  const [name, setName] = useState("")
  const [sourceType, setSourceType] = useState<(typeof SOURCE_TYPE_OPTIONS)[number]>("eln_experiment")
  const [targetType, setTargetType] = useState<(typeof TARGET_TYPE_OPTIONS)[number]>("spectracheck_session")
  const [fieldMap, setFieldMap] = useState<Record<string, unknown>>({ external_field: "moltrace_field" })
  const [fieldMapFormKey, setFieldMapFormKey] = useState(0)
  const [createTemplateBusy, setCreateTemplateBusy] = useState(false)
  const [updateTemplateBusy, setUpdateTemplateBusy] = useState(false)

  const [externalRecordConnectorId, setExternalRecordConnectorId] = useState("")
  const [externalRecordExternalSystem, setExternalRecordExternalSystem] = useState("")
  const [externalRecordObjectType, setExternalRecordObjectType] =
    useState<(typeof EXTERNAL_OBJECT_TYPE_OPTIONS)[number]>("project")
  const [externalRecordObjectId, setExternalRecordObjectId] = useState("")
  const [createExternalRecordBusy, setCreateExternalRecordBusy] = useState(false)

  const [externalLinkExternalRecordId, setExternalLinkExternalRecordId] = useState("")
  const [externalLinkResourceType, setExternalLinkResourceType] =
    useState<(typeof MOLTRACE_RESOURCE_TYPE_OPTIONS)[number]>("project")
  const [externalLinkResourceId, setExternalLinkResourceId] = useState("")
  const [externalLinkRelationType, setExternalLinkRelationType] =
    useState<(typeof RELATION_TYPE_OPTIONS)[number]>("linked_to")
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

  const loadConnectors = useCallback(async () => {
    try {
      const payload = await apiFetch<unknown>("/connectors", { method: "GET" })
      const rows = asRows(payload)
        .map(parseConnectorOption)
        .filter((row): row is ConnectorOption => row != null)
      setConnectors(rows)
    } catch {
      // A connector list failure should not blank the whole workspace; the record
      // form simply shows its empty state until connectors load.
      setConnectors([])
    }
  }, [])

  useEffect(() => {
    void Promise.all([loadTemplates(), loadExternalRecords(), loadExternalObjectLinks(), loadConnectors()])
  }, [loadTemplates, loadExternalRecords, loadExternalObjectLinks, loadConnectors])

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
        try {
          const parsedMap = JSON.parse(row.field_map_json)
          setFieldMap(isRecord(parsedMap) ? parsedMap : {})
        } catch {
          setFieldMap({})
        }
        setFieldMapFormKey((k) => k + 1)
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
      await apiFetch("/mapping-templates", {
        method: "POST",
        body: {
          // MappingTemplateCreate/Update (extra="forbid") has no free-text `connector`;
          // it wants connector_id (int). Preserve the typed name in metadata_json
          // (non-lossy) until a numeric connector picker exists.
          name: name.trim(),
          source_type: sourceType,
          target_type: targetType,
          field_map_json: fieldMap,
          metadata_json: { connector: connector.trim() },
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
      await apiFetch(`/mapping-templates/${selectedTemplateId}`, {
        method: "PATCH",
        body: {
          // MappingTemplateCreate/Update (extra="forbid") has no free-text `connector`;
          // it wants connector_id (int). Preserve the typed name in metadata_json
          // (non-lossy) until a numeric connector picker exists.
          name: name.trim(),
          source_type: sourceType,
          target_type: targetType,
          field_map_json: fieldMap,
          metadata_json: { connector: connector.trim() },
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
    const connectorId = Number(externalRecordConnectorId)
    if (!Number.isInteger(connectorId) || connectorId <= 0) {
      setError("Choose a connector before creating an external record.")
      return
    }
    setCreateExternalRecordBusy(true)
    setError("")
    try {
      await apiFetch("/external-records", {
        method: "POST",
        // ExternalSystemRecordCreate (extra="forbid"): connector_id (int),
        // external_system (str), external_object_type (enum), external_object_id (str).
        body: {
          connector_id: connectorId,
          external_system: externalRecordExternalSystem.trim(),
          external_object_type: externalRecordObjectType,
          external_object_id: externalRecordObjectId.trim(),
        },
      })
      setExternalRecordExternalSystem("")
      setExternalRecordObjectId("")
      await loadExternalRecords()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create external record.")
    } finally {
      setCreateExternalRecordBusy(false)
    }
  }

  async function createExternalObjectLink() {
    const externalRecordId = Number(externalLinkExternalRecordId)
    const resourceId = Number(externalLinkResourceId)
    if (!Number.isInteger(externalRecordId) || externalRecordId <= 0) {
      setError("Choose an external record to link.")
      return
    }
    if (!Number.isInteger(resourceId) || resourceId <= 0) {
      setError("Enter the MolTrace resource ID to link to.")
      return
    }
    setCreateExternalLinkBusy(true)
    setError("")
    try {
      await apiFetch("/external-object-links", {
        method: "POST",
        // ExternalObjectLinkCreate (extra="forbid"): external_record_id (int),
        // moltrace_resource_type (enum), moltrace_resource_id (int), relation_type (enum).
        body: {
          external_record_id: externalRecordId,
          moltrace_resource_type: externalLinkResourceType,
          moltrace_resource_id: resourceId,
          relation_type: externalLinkRelationType,
        },
      })
      trackExternalObjectLinkCreated({
        target_program: externalLinkResourceType,
        status: "created",
      })
      setExternalLinkResourceId("")
      await loadExternalObjectLinks()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create external object link.")
    } finally {
      setCreateExternalLinkBusy(false)
    }
  }

  function connectorLabelById(connectorId: string): string {
    if (!connectorId) return "—"
    return connectors.find((option) => option.id === connectorId)?.label ?? `#${connectorId}`
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <p
          className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
          style={{ color: "var(--mt-slate)" }}
        >
          MolTrace · Settings · Mapping Templates
        </p>
        <h1 className="font-mono text-2xl font-bold tracking-tight">External Object Links and Mapping Templates</h1>
        <p className="text-sm text-muted-foreground">
          Configure mapping templates and external object links for connector-driven data flow.
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          <span>
            Mapping templates define how fields from external systems become MolTrace projects, samples, sessions,
            dossiers, experiments, files, or action items.
          </span>
        </p>
      </div>

      {error ? <p className="text-xs text-destructive">{error}</p> : null}

      <ModuleCard
        accent="slate"
        eyebrow="Form"
        title="Mapping template form"
        icon={Plus}
        description="Define how raw connector or instrument fields map to MolTrace entities. Templates can be created, browsed, and updated."
      >
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="mapping-connector">Connector</Label>
              <Input id="mapping-connector" value={connector} onChange={(e) => setConnector(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="mapping-name">Name</Label>
              <Input id="mapping-name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="mapping-source-type">Source type</Label>
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
              <Label htmlFor="mapping-target-type">Target type</Label>
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
              <JsonObjectField
                key={`field-map-${fieldMapFormKey}`}
                idPrefix="mapping-field-map-json"
                label="Field map"
                initialValue={fieldMap}
                onChange={setFieldMap}
                description="External field name → MolTrace field name. Add a row per mapping; use raw JSON for anything nested."
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
        </div>
      </ModuleCard>

      <ModuleCard
        accent="slate"
        eyebrow="Templates"
        title="Mapping template table"
        icon={Tags}
      >
        <div>
          {loadingTemplates ? <p className="text-sm text-muted-foreground">Loading mapping templates…</p> : null}
          {!loadingTemplates ? (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Template ID</TableHead>
                    <TableHead>Connector</TableHead>
                    <TableHead>Name</TableHead>
                    <TableHead>Source type</TableHead>
                    <TableHead>Target type</TableHead>
                    <TableHead>Field map</TableHead>
                    <TableHead>Open</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {mappingTemplates.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-xs text-muted-foreground">
                        No mapping templates found.
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
        </div>
      </ModuleCard>

      <ModuleCard
        accent="slate"
        eyebrow="Create"
        title="Create external record"
        icon={FileBox}
        description="Register a record from an external system (LIMS, ELN, etc.) for cross-referencing within MolTrace."
      >
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="external-record-connector">Connector</Label>
              <select
                id="external-record-connector"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none disabled:opacity-60"
                value={externalRecordConnectorId}
                onChange={(e) => setExternalRecordConnectorId(e.target.value)}
                disabled={connectors.length === 0}
              >
                <option value="">
                  {connectors.length === 0 ? "No connectors registered yet" : "Select a connector"}
                </option>
                {connectors.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="external-record-system">External system</Label>
              <Input
                id="external-record-system"
                value={externalRecordExternalSystem}
                onChange={(e) => setExternalRecordExternalSystem(e.target.value)}
                placeholder="e.g. Benchling, LabWare"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="external-record-object-type">Object type</Label>
              <select
                id="external-record-object-type"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
                value={externalRecordObjectType}
                onChange={(e) =>
                  setExternalRecordObjectType(e.target.value as (typeof EXTERNAL_OBJECT_TYPE_OPTIONS)[number])
                }
              >
                {EXTERNAL_OBJECT_TYPE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {statusLabel(option)}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="external-record-object-id">Object ID</Label>
              <Input
                id="external-record-object-id"
                value={externalRecordObjectId}
                onChange={(e) => setExternalRecordObjectId(e.target.value)}
                placeholder="ID of the record in that system"
              />
            </div>
          </div>
          {connectors.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              Register a connector first before creating an external record.
            </p>
          ) : null}
          <Button
            type="button"
            disabled={
              createExternalRecordBusy ||
              !externalRecordConnectorId ||
              !externalRecordExternalSystem.trim() ||
              !externalRecordObjectId.trim()
            }
            onClick={() => void createExternalRecord()}
          >
            {createExternalRecordBusy ? "Creating…" : "Create external record"}
          </Button>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="slate"
        eyebrow="Records"
        title="External record table"
        icon={FileSpreadsheet}
      >
        <div>
          {loadingExternalRecords ? <p className="text-sm text-muted-foreground">Loading external records…</p> : null}
          {!loadingExternalRecords ? (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>External record ID</TableHead>
                    <TableHead>Connector</TableHead>
                    <TableHead>External system</TableHead>
                    <TableHead>Object type</TableHead>
                    <TableHead>Object ID</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Open</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {externalRecords.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-xs text-muted-foreground">
                        No external records found.
                      </TableCell>
                    </TableRow>
                  ) : (
                    externalRecords.map((row) => (
                      <TableRow key={row.external_record_id}>
                        <TableCell className="font-mono text-[10px]">{row.external_record_id}</TableCell>
                        <TableCell className="text-xs">{connectorLabelById(row.connector_id)}</TableCell>
                        <TableCell className="text-xs">{row.external_system}</TableCell>
                        <TableCell className="text-xs">{statusLabel(row.external_object_type)}</TableCell>
                        <TableCell className="text-xs">{row.external_object_id}</TableCell>
                        <TableCell className="text-xs">{statusLabel(row.status)}</TableCell>
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
        </div>
      </ModuleCard>

      <ModuleCard
        accent="slate"
        eyebrow="Link"
        title="Create external link"
        icon={Link2}
        description="Link an external record to a MolTrace object (project, sample, compound, batch) for traceability."
      >
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="external-link-record-id">External record</Label>
              <select
                id="external-link-record-id"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none disabled:opacity-60"
                value={externalLinkExternalRecordId}
                onChange={(e) => setExternalLinkExternalRecordId(e.target.value)}
                disabled={externalRecords.length === 0}
              >
                <option value="">
                  {externalRecords.length === 0 ? "No external records yet" : "Select an external record"}
                </option>
                {externalRecords.map((record) => (
                  <option key={record.external_record_id} value={record.external_record_id}>
                    {`#${record.external_record_id} · ${record.external_object_id}`}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="external-link-resource-type">Resource type</Label>
              <select
                id="external-link-resource-type"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
                value={externalLinkResourceType}
                onChange={(e) =>
                  setExternalLinkResourceType(e.target.value as (typeof MOLTRACE_RESOURCE_TYPE_OPTIONS)[number])
                }
              >
                {MOLTRACE_RESOURCE_TYPE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {statusLabel(option)}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="external-link-resource-id">Resource ID</Label>
              <Input
                id="external-link-resource-id"
                type="number"
                min={1}
                value={externalLinkResourceId}
                onChange={(e) => setExternalLinkResourceId(e.target.value)}
                placeholder="MolTrace resource ID"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="external-link-relation-type">Relation type</Label>
              <select
                id="external-link-relation-type"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
                value={externalLinkRelationType}
                onChange={(e) =>
                  setExternalLinkRelationType(e.target.value as (typeof RELATION_TYPE_OPTIONS)[number])
                }
              >
                {RELATION_TYPE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {statusLabel(option)}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {externalRecords.length === 0 ? (
            <p className="text-xs text-muted-foreground">Create an external record above before linking it.</p>
          ) : null}
          <Button
            type="button"
            disabled={createExternalLinkBusy || !externalLinkExternalRecordId || !externalLinkResourceId.trim()}
            onClick={() => void createExternalObjectLink()}
          >
            {createExternalLinkBusy ? "Creating…" : "Create external object link"}
          </Button>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="slate"
        eyebrow="Links"
        title="External object link table"
        icon={ExternalLink}
      >
        <div>
          {loadingExternalLinks ? <p className="text-sm text-muted-foreground">Loading external object links…</p> : null}
          {!loadingExternalLinks ? (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>External object link ID</TableHead>
                    <TableHead>External record ID</TableHead>
                    <TableHead>Resource type</TableHead>
                    <TableHead>Resource ID</TableHead>
                    <TableHead>Relation type</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {externalObjectLinks.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className="text-xs text-muted-foreground">
                        No external object links found.
                      </TableCell>
                    </TableRow>
                  ) : (
                    externalObjectLinks.map((row) => (
                      <TableRow key={row.external_object_link_id}>
                        <TableCell className="font-mono text-[10px]">{row.external_object_link_id}</TableCell>
                        <TableCell className="font-mono text-[10px]">{row.external_record_id}</TableCell>
                        <TableCell className="text-xs">{statusLabel(row.moltrace_resource_type)}</TableCell>
                        <TableCell className="text-xs">{row.moltrace_resource_id}</TableCell>
                        <TableCell className="text-xs">{statusLabel(row.relation_type)}</TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          ) : null}
        </div>
      </ModuleCard>
    </div>
  )
}
