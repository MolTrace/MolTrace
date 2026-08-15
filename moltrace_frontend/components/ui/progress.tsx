'use client'

import * as React from 'react'
import * as ProgressPrimitive from '@radix-ui/react-progress'

import { cn } from '@/lib/utils'

function Progress({
  className,
  value,
  ...props
}: React.ComponentProps<typeof ProgressPrimitive.Root>) {
  return (
    <ProgressPrimitive.Root
      data-slot="progress"
      // `value` is forwarded, not only painted. Destructuring it for the
      // Indicator's transform used to swallow it before it reached Radix, so
      // every Progress in the app was announced as an INDETERMINATE progressbar
      // — no aria-valuenow — while visually showing an exact figure. The hero's
      // "87.3%" card was the audit finding, but the fix is for every consumer.
      value={value}
      className={cn(
        'bg-primary/20 relative h-2 w-full overflow-hidden rounded-full',
        className,
      )}
      {...props}
    >
      <ProgressPrimitive.Indicator
        data-slot="progress-indicator"
        className="bg-primary h-full w-full flex-1 transition-all"
        style={{ transform: `translateX(-${100 - (value || 0)}%)` }}
      />
    </ProgressPrimitive.Root>
  )
}

export { Progress }
