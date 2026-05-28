"use client"

import { useId, useMemo, useState } from "react"
import { ArrowRight, CheckCircle2, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"

/**
 * Contact form — client component.
 *
 * UX:
 *  - Real-time required-field validation (HTML5 + a small derived flag so
 *    the submit button only enables when the form is meaningfully filled).
 *  - "Reason" select biases the receiving inbox (sales@ vs support@ etc.)
 *    so the mailto: handoff lands in the right team's queue.
 *  - Submit composes a structured mailto: with the form fields as the
 *    message body. This is intentionally the lowest-friction path that
 *    doesn't need a backend endpoint — the user's mail client opens with
 *    everything prefilled and they hit Send. On success the form flips to
 *    a confirmation state so users know it worked.
 *  - Privacy consent is required (GDPR / pharma-tenant expectation).
 */

const REASONS = [
  { value: "demo", label: "Request a demo", inbox: "sales@moltrace.com" },
  { value: "sales", label: "Sales question", inbox: "sales@moltrace.com" },
  { value: "support", label: "Customer support", inbox: "support@moltrace.com" },
  { value: "partnership", label: "Partnership / Integration", inbox: "partnerships@moltrace.com" },
  { value: "press", label: "Press / Analyst inquiry", inbox: "press@moltrace.com" },
  { value: "security", label: "Security / Vulnerability report", inbox: "security@moltrace.com" },
  { value: "other", label: "Other", inbox: "hello@moltrace.com" },
] as const
type ReasonValue = (typeof REASONS)[number]["value"]

type FormState = {
  name: string
  email: string
  company: string
  role: string
  reason: ReasonValue
  message: string
  consent: boolean
}

const INITIAL: FormState = {
  name: "",
  email: "",
  company: "",
  role: "",
  reason: "demo",
  message: "",
  consent: false,
}

function buildMailto(state: FormState): string {
  const reason = REASONS.find((r) => r.value === state.reason) ?? REASONS[0]
  const subject = `[MolTrace · ${reason.label}] Inquiry from ${state.name || "(no name)"}`
  const lines = [
    `Name: ${state.name}`,
    `Email: ${state.email}`,
    state.company ? `Company: ${state.company}` : null,
    state.role ? `Role: ${state.role}` : null,
    `Reason: ${reason.label}`,
    "",
    "Message:",
    state.message,
    "",
    "—",
    "Sent via the MolTrace contact form.",
  ].filter(Boolean) as string[]
  const body = lines.join("\n")
  return `mailto:${reason.inbox}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`
}

export function ContactForm() {
  const [state, setState] = useState<FormState>(INITIAL)
  const [submitting, setSubmitting] = useState(false)
  const [sent, setSent] = useState(false)
  const nameId = useId()
  const emailId = useId()
  const companyId = useId()
  const roleId = useId()
  const reasonId = useId()
  const messageId = useId()
  const consentId = useId()

  // Required-field readiness — gates the submit button so a click never
  // produces an empty mailto.
  const canSubmit = useMemo(() => {
    const ok =
      state.name.trim().length >= 2 &&
      /.+@.+\..+/.test(state.email.trim()) &&
      state.message.trim().length >= 10 &&
      state.consent
    return ok
  }, [state])

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setState((prev) => ({ ...prev, [key]: value }))

  const handleSubmit: React.FormEventHandler<HTMLFormElement> = (event) => {
    event.preventDefault()
    if (!canSubmit) return
    setSubmitting(true)
    // Hand off to the OS mail client. We use window.location.href instead
    // of <a target="_blank"> so the user's existing tab is reused and the
    // mailto: doesn't get blocked as a popup. Wrap in a short delay so
    // the loading spinner is perceptible.
    const href = buildMailto(state)
    window.setTimeout(() => {
      try {
        window.location.href = href
      } catch {
        // Browsers without a registered mail handler will quietly no-op.
      }
      setSent(true)
      setSubmitting(false)
    }, 350)
  }

  if (sent) {
    return (
      <div
        data-testid="contact-form-success"
        className="rounded-2xl border bg-card p-8 shadow-sm"
        style={{ borderTop: "3px solid var(--mt-teal)" }}
      >
        <CheckCircle2 className="h-10 w-10" style={{ color: "var(--mt-teal)" }} aria-hidden />
        <h3 className="mt-4 text-lg font-semibold">Thanks — your message is on its way.</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          Your mail client should have opened with everything prefilled. If it didn't, you can write
          us directly at{" "}
          <a
            href={`mailto:${REASONS.find((r) => r.value === state.reason)?.inbox ?? "hello@moltrace.com"}`}
            className="font-medium text-foreground underline-offset-4 hover:underline"
          >
            {REASONS.find((r) => r.value === state.reason)?.inbox ?? "hello@moltrace.com"}
          </a>
          .
        </p>
        <p className="mt-4 text-xs text-muted-foreground">
          We typically respond within one business day. Customer-support tickets follow your
          enterprise SLA.
        </p>
        <Button
          type="button"
          variant="outline"
          className="mt-6"
          onClick={() => {
            setSent(false)
            setState(INITIAL)
          }}
        >
          Send another message
        </Button>
      </div>
    )
  }

  return (
    <form
      onSubmit={handleSubmit}
      data-testid="contact-form"
      className="rounded-2xl border bg-card p-6 shadow-sm sm:p-8"
      style={{ borderTop: "3px solid var(--mt-teal)" }}
      noValidate
    >
      <div className="grid gap-5 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor={nameId}>
            Full name <span className="text-rose-500">*</span>
          </Label>
          <Input
            id={nameId}
            type="text"
            autoComplete="name"
            value={state.name}
            onChange={(e) => update("name", e.target.value)}
            placeholder="Dr. Jane Chen"
            required
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={emailId}>
            Work email <span className="text-rose-500">*</span>
          </Label>
          <Input
            id={emailId}
            type="email"
            autoComplete="email"
            value={state.email}
            onChange={(e) => update("email", e.target.value)}
            placeholder="jane.chen@pharmaco.com"
            required
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={companyId}>Company / organization</Label>
          <Input
            id={companyId}
            type="text"
            autoComplete="organization"
            value={state.company}
            onChange={(e) => update("company", e.target.value)}
            placeholder="PharmaCo Research"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={roleId}>Role <span className="text-muted-foreground">(optional)</span></Label>
          <Input
            id={roleId}
            type="text"
            autoComplete="organization-title"
            value={state.role}
            onChange={(e) => update("role", e.target.value)}
            placeholder="Director, Analytical R&D"
          />
        </div>
      </div>

      <div className="mt-5 space-y-1.5">
        <Label htmlFor={reasonId}>
          Reason for getting in touch <span className="text-rose-500">*</span>
        </Label>
        <select
          id={reasonId}
          value={state.reason}
          onChange={(e) => update("reason", e.target.value as ReasonValue)}
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-[color,box-shadow] outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
        >
          {REASONS.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
        <p className="text-xs text-muted-foreground">
          Routes your message to the right team —{" "}
          <span className="font-mono">{REASONS.find((r) => r.value === state.reason)?.inbox}</span>.
        </p>
      </div>

      <div className="mt-5 space-y-1.5">
        <Label htmlFor={messageId}>
          Message <span className="text-rose-500">*</span>
        </Label>
        <Textarea
          id={messageId}
          value={state.message}
          onChange={(e) => update("message", e.target.value)}
          placeholder="Tell us a bit about your workflow, instruments, regulatory context, or the question you have."
          rows={6}
          required
        />
        <p className="text-xs text-muted-foreground">
          {state.message.trim().length < 10
            ? "10 characters minimum."
            : `${state.message.trim().length} characters.`}
        </p>
      </div>

      <div className="mt-5 flex items-start gap-2">
        <input
          id={consentId}
          type="checkbox"
          checked={state.consent}
          onChange={(e) => update("consent", e.target.checked)}
          className="mt-0.5 h-4 w-4 shrink-0 cursor-pointer rounded border-input"
          required
        />
        <Label htmlFor={consentId} className="cursor-pointer text-xs leading-snug font-normal text-muted-foreground">
          I agree to MolTrace contacting me about my inquiry. We never share your information with
          third parties. See our{" "}
          <a
            href="https://moltrace-docs.vercel.app/guides/legal/privacy-policy/"
            target="_blank"
            rel="noopener noreferrer"
            className="text-foreground underline-offset-4 hover:underline"
          >
            privacy policy
          </a>
          .
        </Label>
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t pt-5">
        <p className="text-xs text-muted-foreground">
          <span className="font-mono uppercase tracking-[0.12em]">Response time</span> · typically 1 business day
        </p>
        <Button
          type="submit"
          size="lg"
          disabled={!canSubmit || submitting}
          className={cn("min-w-[180px] gap-2", !canSubmit && "cursor-not-allowed opacity-60")}
        >
          {submitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              Opening mail client…
            </>
          ) : (
            <>
              Send message
              <ArrowRight className="h-4 w-4" aria-hidden />
            </>
          )}
        </Button>
      </div>
    </form>
  )
}
