import type { Metadata } from "next"
import Link from "next/link"
import { notFound } from "next/navigation"
import { ArrowLeft, ArrowRight, Clock, Mail } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Footer } from "@/components/marketing/footer"
import { Header } from "@/components/marketing/header"
import { SITE_URL, SITE_NAME } from "@/lib/seo/site"
import { getLivePosts, getPostBySlug, type PostBlock } from "@/lib/blog/posts"

// Only live posts (status: "live" + a body) are emitted as routes; any other
// slug 404s. This is what keeps unwritten "forthcoming" posts from ever
// shipping as thin, index-diluting pages.
export const dynamicParams = false

export function generateStaticParams() {
  return getLivePosts().map((p) => ({ slug: p.slug }))
}

type Params = { params: Promise<{ slug: string }> }

const DEFAULT_AUTHOR = `${SITE_NAME} research team`

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params
  const post = getPostBySlug(slug)
  if (!post || post.status !== "live") return {}
  const description = post.metaDescription ?? post.dek
  const url = `${SITE_URL}/blog/${post.slug}`
  // The PNG twin, never the SVG: no major social platform renders an SVG
  // preview, so pointing og:image at the .svg would silently produce a
  // link with no card at all. Absolute URL because scrapers do not resolve
  // relative ones. Posts without artwork fall through to the site-wide
  // opengraph-image card, which is the existing behaviour.
  const heroPng = post.heroImage ? `${SITE_URL}${post.heroImage}.png` : undefined
  const images = heroPng
    ? [{ url: heroPng, width: 1200, height: 630, alt: post.heroImageAlt ?? post.title }]
    : undefined
  return {
    title: `${post.title} · Field notes`,
    description,
    alternates: { canonical: `/blog/${post.slug}` },
    openGraph: {
      type: "article",
      title: post.title,
      description,
      url,
      publishedTime: post.date,
      modifiedTime: post.date,
      authors: [post.author ?? DEFAULT_AUTHOR],
      section: post.topicLabel,
      ...(images ? { images } : {}),
    },
    twitter: {
      card: "summary_large_image",
      title: post.title,
      description,
      ...(heroPng ? { images: [heroPng] } : {}),
    },
  }
}

/** Minimal, dependency-free inline formatter: `code`, **bold**, *italic*.
 *  No dangerouslySetInnerHTML — every token becomes a real React element. */
function renderInline(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = []
  const regex = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g
  let lastIndex = 0
  let key = 0
  let m: RegExpExecArray | null
  while ((m = regex.exec(text)) !== null) {
    if (m.index > lastIndex) nodes.push(text.slice(lastIndex, m.index))
    const tok = m[0]
    if (tok.startsWith("`")) {
      nodes.push(
        <code
          key={key++}
          className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.85em] text-foreground"
        >
          {tok.slice(1, -1)}
        </code>,
      )
    } else if (tok.startsWith("**")) {
      nodes.push(
        <strong key={key++} className="font-semibold text-foreground">
          {tok.slice(2, -2)}
        </strong>,
      )
    } else {
      nodes.push(<em key={key++}>{tok.slice(1, -1)}</em>)
    }
    lastIndex = regex.lastIndex
  }
  if (lastIndex < text.length) nodes.push(text.slice(lastIndex))
  return nodes
}

function Block({ block }: { block: PostBlock }) {
  switch (block.type) {
    case "h2":
      return (
        <h2 className="mt-12 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
          {block.text}
        </h2>
      )
    case "quote":
      return (
        <blockquote
          className="my-8 border-l-4 pl-6 text-lg font-medium italic leading-relaxed text-foreground/85"
          style={{ borderColor: "var(--mt-teal)" }}
        >
          {renderInline(block.text)}
        </blockquote>
      )
    case "list":
      return (
        <ul className="my-6 list-disc space-y-2 pl-6 text-lg leading-relaxed text-muted-foreground">
          {block.items.map((item, i) => (
            <li key={i}>{renderInline(item)}</li>
          ))}
        </ul>
      )
    case "p":
    default:
      return (
        <p className="mt-6 text-lg leading-relaxed text-muted-foreground">
          {renderInline(block.text)}
        </p>
      )
  }
}

export default async function BlogPostPage({ params }: Params) {
  const { slug } = await params
  const post = getPostBySlug(slug)
  if (!post || post.status !== "live" || !post.body?.length) notFound()

  const url = `${SITE_URL}/blog/${post.slug}`
  const author = post.author ?? DEFAULT_AUTHOR
  const description = post.metaDescription ?? post.dek

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "BlogPosting",
    headline: post.title,
    description,
    datePublished: post.date,
    dateModified: post.date,
    author: { "@type": "Organization", name: author, url: SITE_URL },
    publisher: {
      "@type": "Organization",
      name: SITE_NAME,
      logo: {
        "@type": "ImageObject",
        url: `${SITE_URL}/icons/icon-512.png`,
        width: 512,
        height: 512,
      },
    },
    mainEntityOfPage: { "@type": "WebPage", "@id": url },
    // The post's own artwork when it has some, so a rich result shows the
    // essay rather than the generic site card. PNG, not SVG: Google's
    // structured-data image guidance requires a raster format.
    image: post.heroImage ? `${SITE_URL}${post.heroImage}.png` : `${SITE_URL}/opengraph-image`,
    url,
    articleSection: post.topicLabel,
    inLanguage: "en-US",
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main>
        <article className="mx-auto max-w-3xl px-5 py-16 sm:px-6 lg:py-24">
          <script
            type="application/ld+json"
            // Developer-authored static content — safe.
            dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
          />

          <Link
            href="/blog"
            className="inline-flex items-center gap-1.5 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden />
            Field notes
          </Link>

          <div className="mt-6 flex items-center gap-2">
            <span className="inline-flex items-center rounded-full border bg-violet-50 px-2.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-violet-700 dark:border-violet-900 dark:bg-violet-950/40 dark:text-violet-300">
              {post.topicLabel}
            </span>
          </div>

          <h1 className="mt-5 text-3xl font-semibold leading-[1.1] tracking-tight text-foreground sm:text-4xl lg:text-5xl">
            {post.title}
          </h1>
          <p className="mt-5 text-xl font-medium leading-relaxed text-foreground/85">
            {post.dek}
          </p>

          <div className="mt-6 flex flex-wrap items-center gap-4 border-b pb-8 text-sm text-muted-foreground">
            <span className="font-mono tabular-nums">{post.date}</span>
            <span aria-hidden>·</span>
            <span className="inline-flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" aria-hidden />
              {post.readingMinutes} min read
            </span>
            <span aria-hidden>·</span>
            <span>{author}</span>
          </div>

          {/* Hero artwork. The SVG rather than the PNG twin — it stays crisp on
              any display and costs a fraction as much; the PNG exists only for
              social scrapers, which cannot read SVG. Width/height reserve the
              space so the essay text below does not shift as it loads. */}
          {post.heroImage ? (
            <figure className="mt-10">
              <img
                src={`${post.heroImage}.svg`}
                alt={post.heroImageAlt ?? ""}
                width={1200}
                height={630}
                className="w-full rounded-2xl border"
                decoding="async"
              />
            </figure>
          ) : null}

          <div className="mt-2">
            {post.body.map((block, i) => (
              <Block key={i} block={block} />
            ))}
          </div>

          {/* End-of-post CTA */}
          <div className="mt-16 rounded-2xl border bg-muted/20 p-8 text-center">
            <h2 className="text-xl font-semibold tracking-tight">
              Get each essay as it ships.
            </h2>
            <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">
              Methodology essays land on shipping milestones, not a content calendar. No marketing
              email, no upsell — just the writing.
            </p>
            <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
              <Button asChild className="gap-2">
                <Link href="/contact?reason=Subscribe%20to%20Field%20notes">
                  Subscribe by email
                  <Mail className="h-4 w-4" />
                </Link>
              </Button>
              <Button asChild variant="outline" className="gap-2">
                <Link href="/blog">
                  More field notes
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
            </div>
          </div>
        </article>
      </main>
      <Footer />
    </div>
  )
}
