import type { Metadata } from "next"
import { BlogPage } from "@/components/marketing/blog-page"

export const metadata: Metadata = {
  title: "Field notes · MolTrace",
  description:
    "Methodology essays, architecture decisions, and validation deep-dives from the MolTrace team. The work, written down as we ship it.",
  alternates: { canonical: "/blog" },
  openGraph: {
    title: "Field notes · MolTrace",
    description:
      "Field notes from MolTrace: methodology, engineering, regulatory context. Written for analysts, engineers, and reviewers who want the actual reasoning.",
    type: "website",
  },
}

export default function BlogRoute() {
  return <BlogPage />
}
