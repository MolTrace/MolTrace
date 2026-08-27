import { render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { RegulatoryDossierWorkspace } from "@/components/regulatory-hub/regulatory-dossier-workspace"

const mockApiFetch = vi.hoisted(() => vi.fn<(path: string, init?: unknown) => Promise<unknown>>())

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  apiFetch: (path: string, init?: unknown) => mockApiFetch(path, init),
}))

vi.mock("next/navigation", async (orig) => ({
  ...(await orig<typeof import("next/navigation")>()),
  useParams: () => ({ dossierId: "4" }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/regulatory/dossiers/4",
}))

const DOSSIER = {
  id: 4,
  title: "Test dossier",
  jurisdiction_id: 1,
  status: "draft",
  max_daily_dose_g: 1.0,
}

// One Q3D assessment: a Class 1 element over its limit, and one element ICH Q3D gives no
// PDE for by this route -- an absent limit, which must never read as a permissive one.
const ELEMENTAL_ASSESSMENT = {
  id: 11,
  elemental_summary_json: {
    route: "oral",
    action_required: true,
    assessed_elements: [
      {
        input_element: "Pb",
        element: "Pb",
        element_class: "1",
        pde_ug_per_day: 5.0,
        route_data_available: true,
        permitted_concentration_ppm: 5.0,
        control_threshold_ppm: 1.5,
        observed_concentration: 7.25,
        threshold_triggered: true,
        review_required: true,
        source: "ich_q3d_engine",
        regulatory_basis: "ICH Q3D(R2)",
        rule_set_version: "sha256:abc",
      },
      {
        input_element: "Ni",
        element: "Ni",
        element_class: "3",
        pde_ug_per_day: null,
        route_data_available: false,
        observed_concentration: 2.0,
        threshold_triggered: false,
        review_required: false,
        source: "ich_q3d_engine",
        regulatory_basis: "ICH Q3D(R2)",
      },
    ],
  },
  warnings: [],
}

function routeMock(path: string): unknown {
  if (path === `/regulatory/dossiers/4`) return DOSSIER
  if (path.endsWith("/elemental-impurity-assessment")) return [ELEMENTAL_ASSESSMENT]
  if (path === "/regulatory/jurisdictions") return [{ id: 1, name: "US", code: "US" }]
  return []
}

describe("RegulatoryDossierWorkspace — elemental impurities (ICH Q3D)", () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
    mockApiFetch.mockImplementation((path: string) => Promise.resolve(routeMock(path)))
  })

  it("loads the dossier's Q3D assessment so action-queue items have somewhere to open", async () => {
    render(<RegulatoryDossierWorkspace />)

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/regulatory/dossiers/4/elemental-impurity-assessment",
        expect.objectContaining({ method: "GET" }),
      ),
    )
  })

  it("renders each element's limit, and does not present an absent limit as a permissive one", async () => {
    const { default: userEvent } = await import("@testing-library/user-event")
    const user = userEvent.setup()
    render(<RegulatoryDossierWorkspace />)
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalled())

    // Sections live under their stage group.
    await user.click(await screen.findByText("Impurity & Safety"))
    await user.click(await screen.findByText("Elemental Impurities"))

    // Pb: 7.25 ppm measured against a 5 ppm permitted concentration.
    expect(await screen.findByText("Pb")).toBeInTheDocument()
    expect(screen.getByText(/7.25 ppm/)).toBeInTheDocument()
    expect(screen.getByText(/control threshold 1\.5 ppm/)).toBeInTheDocument()
    expect(screen.getByText(/5 µg\/day/)).toBeInTheDocument()
    expect(screen.getByText("at or above limit")).toBeInTheDocument()

    // Ni: ICH Q3D gives no PDE for this route. That is an ABSENT limit, and the row must say
    // so rather than leaving a blank cell that reads as "nothing to meet".
    expect(screen.getByText("Ni")).toBeInTheDocument()
    expect(screen.getByText(/no Q3D limit for this route/)).toBeInTheDocument()
    // It measured 2.0 ppm against no limit, so it is not a pass.
    expect(screen.queryByText("within limit")).not.toBeInTheDocument()
  })
})
