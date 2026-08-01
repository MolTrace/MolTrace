/**
 * POST /jobs — preserve backend field names exactly.
 */
export function buildAnalysisJobPayload(args: {
  sessionId: string | null | undefined
  sampleId: string
  jobType: string
  inputFileIds: string[]
  parameters: Record<string, unknown>
}) {
  return {
    session_id: args.sessionId ?? null,
    sample_id: args.sampleId.trim() ? args.sampleId.trim() : null,
    job_type: args.jobType,
    // AnalysisJobCreate (extra="forbid") fields are *_json-suffixed.
    input_file_ids_json: args.inputFileIds,
    parameters_json: args.parameters,
  }
}
