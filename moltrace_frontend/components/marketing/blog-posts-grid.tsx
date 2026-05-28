"use client"

import { useMemo, useState } from "react"
import { ArrowRight, Clock, Tag } from "lucide-react"
import { cn } from "@/lib/utils"

/**
 * Topic-filtered post grid (client component).
 *
 * Each "post" here is a curated essay summary — title + dek + the
 * actual claim spelled out — so the page is valuable as an editorial
 * index even before posts are live. Filter pills give the page real
 * interactivity rather than a static list.
 *
 * Topics map onto the three editorial streams: Science / Engineering /
 * Methodology. "All" shows everything. Filter state is local; no URL
 * sync (keeps it dependency-light; can be added later).
 */

export type BlogTopic =
  | "all"
  | "science"
  | "engineering"
  | "methodology"
  | "regulatory"
  | "company"

export type BlogPost = {
  slug: string
  title: string
  dek: string
  claim: string
  topic: Exclude<BlogTopic, "all">
  topicLabel: string
  date: string
  readingMinutes: number
  status: "live" | "forthcoming"
  href?: string
}

type Props = {
  posts: BlogPost[]
}

const TOPIC_PILLS: { value: BlogTopic; label: string }[] = [
  { value: "all", label: "All" },
  { value: "science", label: "Science" },
  { value: "engineering", label: "Engineering" },
  { value: "methodology", label: "Methodology" },
  { value: "regulatory", label: "Regulatory" },
  { value: "company", label: "Company" },
]

const TOPIC_CHIP_STYLE: Record<Exclude<BlogTopic, "all">, string> = {
  science: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-900",
  engineering: "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950/40 dark:text-sky-300 dark:border-sky-900",
  methodology: "bg-violet-50 text-violet-700 border-violet-200 dark:bg-violet-950/40 dark:text-violet-300 dark:border-violet-900",
  regulatory: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-900",
  company: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-900",
}

export function BlogPostsGrid({ posts }: Props) {
  const [topic, setTopic] = useState<BlogTopic>("all")
  const counts = useMemo(() => {
    const acc: Record<BlogTopic, number> = {
      all: posts.length,
      science: 0,
      engineering: 0,
      methodology: 0,
      regulatory: 0,
      company: 0,
    }
    for (const p of posts) acc[p.topic]++
    return acc
  }, [posts])
  const filtered = useMemo(
    () => (topic === "all" ? posts : posts.filter((p) => p.topic === topic)),
    [topic, posts],
  )

  return (
    <>
      {/* Filter pills */}
      <div
        role="radiogroup"
        aria-label="Filter posts by topic"
        className="flex flex-wrap items-center gap-2"
      >
        {TOPIC_PILLS.map((pill) => {
          const active = topic === pill.value
          const count = counts[pill.value]
          return (
            <button
              key={pill.value}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => setTopic(pill.value)}
              className={cn(
                "inline-flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-sm font-medium transition-all",
                active
                  ? "border-foreground bg-foreground text-background"
                  : "border-border bg-card text-muted-foreground hover:border-[color:var(--mt-teal)]/40 hover:text-foreground",
              )}
            >
              {pill.label}
              <span
                className={cn(
                  "rounded-full px-1.5 font-mono text-[10px] tabular-nums",
                  active
                    ? "bg-background/15 text-background"
                    : "bg-muted text-muted-foreground",
                )}
              >
                {count}
              </span>
            </button>
          )
        })}
      </div>

      {/* Posts grid */}
      <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {filtered.map((post) => {
          const chip = TOPIC_CHIP_STYLE[post.topic]
          const Wrapper = post.href ? "a" : "div"
          const wrapperProps = post.href
            ? {
                href: post.href,
                target: "_blank" as const,
                rel: "noopener noreferrer" as const,
              }
            : {}
          return (
            <Wrapper
              key={post.slug}
              {...wrapperProps}
              className={cn(
                "group flex flex-col rounded-2xl border bg-card p-6 shadow-sm transition-all",
                post.href ? "cursor-pointer hover:-translate-y-0.5 hover:shadow-md" : "",
              )}
              style={{ borderTop: "3px solid var(--mt-teal)" }}
            >
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.14em]",
                    chip,
                  )}
                >
                  <Tag className="h-3 w-3" aria-hidden />
                  {post.topicLabel}
                </span>
                {post.status === "forthcoming" ? (
                  <span className="inline-flex items-center rounded-full border border-dashed px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                    Forthcoming
                  </span>
                ) : null}
              </div>
              <h3 className="mt-4 text-lg font-semibold leading-tight tracking-tight">
                {post.title}
              </h3>
              <p className="mt-2 text-sm font-medium leading-relaxed text-foreground/80">
                {post.dek}
              </p>
              <p className="mt-3 flex-1 text-sm leading-relaxed text-muted-foreground">
                {post.claim}
              </p>
              <div className="mt-5 flex items-center justify-between gap-3 border-t pt-4">
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <span className="font-mono tabular-nums">{post.date}</span>
                  <span aria-hidden>·</span>
                  <span className="inline-flex items-center gap-1">
                    <Clock className="h-3 w-3" aria-hidden />
                    {post.readingMinutes} min read
                  </span>
                </div>
                {post.href ? (
                  <span
                    className="inline-flex items-center gap-1 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] transition-transform group-hover:translate-x-0.5"
                    style={{ color: "var(--mt-teal)" }}
                  >
                    Read
                    <ArrowRight className="h-3 w-3" aria-hidden />
                  </span>
                ) : (
                  <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                    Subscribe for drop
                  </span>
                )}
              </div>
            </Wrapper>
          )
        })}
      </div>

      {filtered.length === 0 ? (
        <div className="mt-12 rounded-2xl border border-dashed bg-muted/20 px-6 py-12 text-center">
          <p className="text-sm text-muted-foreground">
            No posts in this topic yet. Subscribe below and we'll send you the first one when it
            ships.
          </p>
        </div>
      ) : null}
    </>
  )
}
