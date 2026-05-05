"use client"

import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { FileText, Upload, Clock, Check } from "lucide-react"

const files = [
  { name: "1H_NMR_500MHz.dx", type: "1H NMR", size: "2.4 MB", status: "processed" },
  { name: "13C_NMR_125MHz.dx", type: "13C NMR", size: "1.8 MB", status: "processed" },
  { name: "MSMS_ESI_pos.mzML", type: "MS/MS", size: "12.1 MB", status: "processed" },
  { name: "LCMS_gradient.raw", type: "LC-MS", size: "45.2 MB", status: "processing" },
]

const metadata = {
  instrument: "Bruker AVANCE III 500",
  solvent: "CDCl3",
  temperature: "298 K",
  pulseSequence: "zg30",
  relaxationDelay: "1.0 s",
  acquisitionTime: "3.28 s",
  spectralWidth: "10000 Hz",
}

const runHistory = [
  { version: "v3", time: "2 min ago", status: "current" },
  { version: "v2", time: "15 min ago", status: "completed" },
  { version: "v1", time: "1 hr ago", status: "completed" },
]

export function FilePanel() {
  return (
    <div className="flex h-full flex-col">
      <div className="border-b px-4 py-3">
        <h3 className="font-semibold">Files & Data</h3>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-3">
          <Accordion type="multiple" defaultValue={["files", "metadata"]} className="space-y-2">
            {/* Uploaded Files */}
            <AccordionItem value="files" className="rounded-lg border px-3">
              <AccordionTrigger className="py-3 text-sm hover:no-underline">
                <div className="flex items-center gap-2">
                  <Upload className="h-4 w-4" />
                  Uploaded Files ({files.length})
                </div>
              </AccordionTrigger>
              <AccordionContent className="pb-3">
                <div className="space-y-2">
                  {files.map((file, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-2 rounded bg-muted/50 px-2 py-1.5"
                    >
                      <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-xs font-medium">{file.name}</div>
                        <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                          <span>{file.type}</span>
                          <span>·</span>
                          <span>{file.size}</span>
                        </div>
                      </div>
                      {file.status === "processed" ? (
                        <Check className="h-3.5 w-3.5 text-success" />
                      ) : (
                        <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
                      )}
                    </div>
                  ))}
                </div>
                <Button variant="outline" size="sm" className="mt-3 w-full gap-1 text-xs">
                  <Upload className="h-3 w-3" />
                  Add File
                </Button>
              </AccordionContent>
            </AccordionItem>

            {/* Acquisition Metadata */}
            <AccordionItem value="metadata" className="rounded-lg border px-3">
              <AccordionTrigger className="py-3 text-sm hover:no-underline">
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4" />
                  Acquisition Metadata
                </div>
              </AccordionTrigger>
              <AccordionContent className="pb-3">
                <div className="space-y-1.5 text-xs">
                  {Object.entries(metadata).map(([key, value]) => (
                    <div key={key} className="flex justify-between">
                      <span className="text-muted-foreground capitalize">
                        {key.replace(/([A-Z])/g, " $1").trim()}
                      </span>
                      <span className="font-mono">{value}</span>
                    </div>
                  ))}
                </div>
              </AccordionContent>
            </AccordionItem>

            {/* Run History */}
            <AccordionItem value="history" className="rounded-lg border px-3">
              <AccordionTrigger className="py-3 text-sm hover:no-underline">
                <div className="flex items-center gap-2">
                  <Clock className="h-4 w-4" />
                  Run History
                </div>
              </AccordionTrigger>
              <AccordionContent className="pb-3">
                <div className="space-y-2">
                  {runHistory.map((run, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between rounded bg-muted/50 px-2 py-1.5 text-xs"
                    >
                      <div className="flex items-center gap-2">
                        <Badge
                          variant={run.status === "current" ? "default" : "outline"}
                          className="text-[10px]"
                        >
                          {run.version}
                        </Badge>
                        <span className="text-muted-foreground">{run.time}</span>
                      </div>
                      {run.status === "current" && (
                        <Badge variant="secondary" className="text-[10px]">
                          Current
                        </Badge>
                      )}
                    </div>
                  ))}
                </div>
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </div>
      </ScrollArea>
    </div>
  )
}
