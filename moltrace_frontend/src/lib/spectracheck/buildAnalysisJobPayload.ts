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
    input_file_ids: args.inputFileIds,
    parameters: args.parameters,
  }
}
