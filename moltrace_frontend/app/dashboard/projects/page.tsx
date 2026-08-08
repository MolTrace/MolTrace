import { redirect } from "next/navigation"

/**
 * `/dashboard/projects` was a v0 prototype, and the fourth of its kind — the
 * companion to `/dashboard/regulatory`, `/dashboard/spectroscopy` and
 * `/dashboard/reactions`, which were retired in b2ff354. That sweep missed this
 * one: it does not carry a person's name, so a grep for the invented reviewers
 * did not reach it.
 *
 * It listed three projects with invented names, completion percentages, team
 * sizes, analysis counts and "2 hours ago" timestamps, across 117 lines with
 * **zero** data fetching of any kind. Nothing in the product linked to it; the
 * only reference was a visual-baseline script whose match signal pinned the
 * fabricated content itself.
 *
 * A mockup route cannot be made honest while remaining a mockup: there is no
 * live source behind it to fall back from. It redirects to `/projects`, the real
 * surface, so the URL keeps working and lands on data that exists.
 */
export default function Page() {
  redirect("/projects")
}
