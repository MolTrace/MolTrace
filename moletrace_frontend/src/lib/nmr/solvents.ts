/** Sentinel value for the “Other / custom” dropdown row (not sent to the API). */
export const NMR_SOLVENT_OTHER_VALUE = "__spectracheck_nmr_solvent_other__"

export type NmrSolventOption = {
  value: string
  label: string
  aliases?: string[]
}

export const NMR_SOLVENT_OPTIONS: NmrSolventOption[] = [
  { value: "CDCl3", label: "CDCl3", aliases: ["deuteriochloroform"] },
  { value: "D2O", label: "D2O", aliases: ["heavy water"] },
  { value: "DMSO-d6", label: "DMSO-d6", aliases: ["dimethyl sulfoxide-d6"] },
  { value: "Acetone-d6", label: "Acetone-d6" },
  { value: "Acetonitrile-d3", label: "Acetonitrile-d3" },
  { value: "Methanol-d4", label: "Methanol-d4" },
  { value: "Ethanol-d6", label: "Ethanol-d6" },
  { value: "Benzene-d6", label: "Benzene-d6" },
  { value: "Toluene-d8", label: "Toluene-d8" },
  { value: "THF-d8", label: "THF-d8" },
  { value: "Pyridine-d5", label: "Pyridine-d5" },
  { value: "DMF-d7", label: "DMF-d7" },
  { value: "Chloroform-d", label: "Chloroform-d" },
  { value: "Dichloromethane-d2", label: "Dichloromethane-d2" },
  { value: "CD2Cl2", label: "CD2Cl2" },
  { value: "Carbon tetrachloride", label: "Carbon tetrachloride" },
  { value: "CCl4", label: "CCl4" },
  { value: "C6D6", label: "C6D6" },
  { value: "CD3CN", label: "CD3CN" },
  { value: "CD3OD", label: "CD3OD" },
  { value: "CD3COCD3", label: "CD3COCD3" },
  { value: "(CD3)2CO", label: "(CD3)2CO" },
  { value: "(CD3)2SO", label: "(CD3)2SO" },
  { value: NMR_SOLVENT_OTHER_VALUE, label: "Other / custom" },
]

export function getNmrSolventForApi(selectedValue: string, customSolvent: string): string {
  if (selectedValue === NMR_SOLVENT_OTHER_VALUE) {
    return customSolvent.trim()
  }
  return selectedValue
}
