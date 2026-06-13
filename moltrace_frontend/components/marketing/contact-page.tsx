import Link from "next/link"
import {
  Briefcase,
  Building2,
  Globe2,
  HeadphonesIcon,
  Lock,
  Mail,
  MapPin,
  Newspaper,
  ShieldCheck,
  Sparkles,
} from "lucide-react"
import { ContactForm } from "@/components/marketing/contact-form"
import { Footer } from "@/components/marketing/footer"
import { Header } from "@/components/marketing/header"

/**
 * Contact page — full marketing-shell route at /contact.
 *
 * Layout (modern B2B SaaS standard):
 *   - Hero: eyebrow + H1 + one-line subtitle
 *   - Channel cards: 4 inbox-routed contact options with response-time SLA
 *   - Two-column body: form (2/3) + sidebar (1/3) with offices and trust signals
 *   - Trust band: GDPR + SOC 2 + encryption reassurance
 *
 * The form (client component) hands off to mailto: with prefilled fields
 * routed to the right inbox per the user's "Reason" selection. No backend
 * endpoint required.
 */

type Channel = {
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>
  eyebrow: string
  title: string
  description: string
  email: string
  responseTime: string
}

const CHANNELS: Channel[] = [
  {
    icon: Sparkles,
    eyebrow: "Sales · Demos",
    title: "See MolTrace in action",
    description: "Walk through SpectraCheck, the Regentry, and Repho with our solutions team.",
    email: "sales@moltrace.com",
    responseTime: "Within 1 business day",
  },
  {
    icon: HeadphonesIcon,
    eyebrow: "Customer support",
    title: "Open a support ticket",
    description: "Existing customers — we'll route your message into your enterprise SLA queue.",
    email: "support@moltrace.com",
    responseTime: "24/5 enterprise SLA",
  },
  {
    icon: ShieldCheck,
    eyebrow: "Security · Compliance",
    title: "Report a vulnerability",
    description: "Coordinated disclosure encouraged. PGP key on request. Same-day acknowledgement.",
    email: "security@moltrace.com",
    responseTime: "Same business day",
  },
  {
    icon: Newspaper,
    eyebrow: "Press · Analysts",
    title: "Media inquiries",
    description: "For analyst briefings, regulatory commentary, and customer-story interviews.",
    email: "press@moltrace.com",
    responseTime: "Within 2 business days",
  },
]

type Office = {
  city: string
  region: string
  address: string
  hours: string
}

const OFFICES: Office[] = [
  {
    city: "Boston, MA",
    region: "Headquarters · Americas",
    address: "245 Main Street, Cambridge, MA 02142, USA",
    hours: "Mon–Fri · 09:00–18:00 ET",
  },
  {
    city: "London, UK",
    region: "EMEA · Regulatory liaison",
    address: "1 Finsbury Avenue, London EC2M 2PF, United Kingdom",
    hours: "Mon–Fri · 09:00–18:00 GMT",
  },
  {
    city: "Singapore",
    region: "APAC",
    address: "8 Marina View, Asia Square Tower 1, Singapore 018960",
    hours: "Mon–Fri · 09:00–18:00 SGT",
  },
]

const TRUST_SIGNALS = [
  { icon: ShieldCheck, label: "SOC 2 Type II" },
  { icon: Lock, label: "GDPR-compliant intake" },
  { icon: Globe2, label: "Encrypted in transit (TLS 1.3)" },
]

export function ContactPage() {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main>
        {/* ── Hero ────────────────────────────────────────────────────────── */}
        <section className="relative overflow-hidden border-b">
          <div
            aria-hidden
            className="absolute inset-x-0 top-0 h-px"
            style={{
              background:
                "linear-gradient(90deg, transparent 0%, var(--mt-teal) 25%, var(--mt-teal) 75%, transparent 100%)",
              opacity: 0.5,
            }}
          />
          <div
            aria-hidden
            className="scientific-grid-subtle absolute inset-0 opacity-30"
          />
          <div className="relative mx-auto max-w-7xl px-5 py-20 sm:px-6 lg:px-8 lg:py-24">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-teal)" }}
            >
              Get in touch
            </p>
            <h1 className="mt-3 max-w-3xl text-4xl font-semibold tracking-tight sm:text-5xl">
              Let's talk about your science.
            </h1>
            <p className="mt-5 max-w-2xl text-lg leading-relaxed text-muted-foreground">
              Demo requests, support tickets, partnership ideas, and security disclosures all start
              here. Your message is routed to the right team based on your reason for getting in
              touch — most inquiries get a reply within one business day.
            </p>
          </div>
        </section>

        {/* ── Channel cards ───────────────────────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-12 sm:px-6 lg:px-8 lg:py-16">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {CHANNELS.map((channel) => {
                const Icon = channel.icon
                return (
                  <div
                    key={channel.email}
                    className="group flex flex-col rounded-2xl border bg-card p-6 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md"
                    style={{ borderTop: "3px solid var(--mt-teal)" }}
                  >
                    <span
                      className="inline-flex h-10 w-10 items-center justify-center rounded-xl"
                      style={{
                        backgroundColor: "var(--mt-teal-soft)",
                        color: "var(--mt-teal)",
                      }}
                    >
                      <Icon className="h-5 w-5" aria-hidden />
                    </span>
                    <p
                      className="mt-4 font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                      style={{ color: "var(--mt-teal)" }}
                    >
                      {channel.eyebrow}
                    </p>
                    <h2 className="mt-1.5 text-base font-semibold tracking-tight">{channel.title}</h2>
                    <p className="mt-2 flex-1 text-sm leading-relaxed text-muted-foreground">
                      {channel.description}
                    </p>
                    <a
                      href={`mailto:${channel.email}`}
                      className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-foreground transition-colors hover:text-[color:var(--mt-teal)]"
                    >
                      <Mail className="h-3.5 w-3.5" aria-hidden />
                      {channel.email}
                    </a>
                    <p className="mt-1 text-xs text-muted-foreground">{channel.responseTime}</p>
                  </div>
                )
              })}
            </div>
          </div>
        </section>

        {/* ── Form + sidebar ──────────────────────────────────────────────── */}
        <section className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-20">
          <div className="grid gap-10 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Send us a message
              </p>
              <h2 className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl">
                Tell us what you're working on.
              </h2>
              <p className="mt-3 max-w-xl text-sm text-muted-foreground">
                The more context you share — instruments, regulatory framework, scale — the faster
                we can match you with the right specialist.
              </p>
              <div className="mt-8">
                <ContactForm />
              </div>
            </div>

            <aside className="space-y-8 lg:pt-12">
              {/* Offices */}
              <div>
                <p
                  className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                  style={{ color: "var(--mt-teal)" }}
                >
                  Offices
                </p>
                <ul className="mt-4 space-y-5">
                  {OFFICES.map((office) => (
                    <li key={office.city} className="flex gap-3">
                      <MapPin
                        className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground"
                        aria-hidden
                      />
                      <div className="text-sm">
                        <p className="font-semibold tracking-tight">{office.city}</p>
                        <p className="text-xs uppercase tracking-[0.12em] text-muted-foreground">
                          {office.region}
                        </p>
                        <p className="mt-1.5 leading-snug text-muted-foreground">{office.address}</p>
                        <p className="mt-1 text-xs text-muted-foreground">{office.hours}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Trust signals */}
              <div className="rounded-2xl border bg-card p-5">
                <p
                  className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                  style={{ color: "var(--mt-teal)" }}
                >
                  Privacy &amp; security
                </p>
                <ul className="mt-4 space-y-3">
                  {TRUST_SIGNALS.map(({ icon: Icon, label }) => (
                    <li key={label} className="flex items-center gap-2.5 text-sm">
                      <Icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                      <span>{label}</span>
                    </li>
                  ))}
                </ul>
                <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
                  We never share contact-form data with third parties. See our{" "}
                  <Link
                    href="https://docs.moltrace.co/guides/legal/privacy-policy/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-foreground underline-offset-4 hover:underline"
                  >
                    privacy policy
                  </Link>{" "}
                  for the full retention and processing notice.
                </p>
              </div>

              {/* Other ways to reach us */}
              <div className="rounded-2xl border bg-muted/30 p-5">
                <p
                  className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                  style={{ color: "var(--mt-teal)" }}
                >
                  Other ways
                </p>
                <ul className="mt-4 space-y-3 text-sm">
                  <li className="flex items-center gap-2.5">
                    <Briefcase className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                    <Link
                      href="https://docs.moltrace.co/guides/company/careers/"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-foreground transition-colors hover:text-[color:var(--mt-teal)]"
                    >
                      Open roles &amp; careers
                    </Link>
                  </li>
                  <li className="flex items-center gap-2.5">
                    <Building2 className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                    <Link
                      href="https://docs.moltrace.co/guides/company/about/"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-foreground transition-colors hover:text-[color:var(--mt-teal)]"
                    >
                      About MolTrace
                    </Link>
                  </li>
                  <li className="flex items-center gap-2.5">
                    <Globe2 className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                    <Link
                      href="https://docs.moltrace.co/"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-foreground transition-colors hover:text-[color:var(--mt-teal)]"
                    >
                      Documentation
                    </Link>
                  </li>
                </ul>
              </div>
            </aside>
          </div>
        </section>
      </main>
      <Footer />
    </div>
  )
}
