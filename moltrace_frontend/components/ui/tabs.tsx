'use client'

import * as React from 'react'
import * as TabsPrimitive from '@radix-ui/react-tabs'

import { cn } from '@/lib/utils'
import { useSlidingIndicator } from '@/components/app/use-sliding-indicator'

function Tabs({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Root>) {
  return (
    <TabsPrimitive.Root
      data-slot="tabs"
      className={cn('flex flex-col gap-2', className)}
      {...props}
    />
  )
}

/**
 * The active tab's fill is a single element that travels between triggers rather
 * than a background each trigger fades in and out of. Switching then reads as one
 * selection being carried across, not as two panels cross-fading.
 *
 * It measures `[data-state="active"]`, which Radix already sets, so no consumer
 * has to carry an extra attribute. If measuring is unavailable — server render,
 * jsdom, a list that has not laid out yet — `rect` stays null, the indicator is
 * not rendered, and `TabsTrigger` keeps its own background as the fallback. The
 * control is never left with no visible selection.
 */
function TabsList({
  className,
  children,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.List>) {
  // No activeKey to pass: Radix owns the selected value and does not surface it
  // here. The hook watches the DOM for the data-state flip instead, which is the
  // same event from a different direction.
  const { containerRef, rect } = useSlidingIndicator<HTMLDivElement>(
    undefined,
    '[data-state="active"]',
  )
  return (
    <TabsPrimitive.List
      ref={containerRef}
      data-slot="tabs-list"
      data-has-indicator={rect ? 'true' : undefined}
      className={cn(
        'bg-muted/60 text-muted-foreground relative inline-flex h-auto w-fit flex-wrap items-center justify-start gap-1 rounded-xl border-2 p-1.5',
        // The indicator paints the selection, so the active trigger drops its own
        // fill. Only the FILL — the foreground colour stays on the trigger, so the
        // label is legible whether the indicator is there or not. Scoped to
        // data-has-indicator so the pre-measure paint keeps a visible selection.
        '[&[data-has-indicator=true]_[data-slot=tabs-trigger][data-state=active]]:bg-transparent',
        '[&[data-has-indicator=true]_[data-slot=tabs-trigger][data-state=active]]:shadow-none',
        className,
      )}
      {...props}
    >
      {rect ? (
        <span
          aria-hidden
          className="bg-primary pointer-events-none absolute left-0 top-0 rounded-lg shadow-sm transition-[transform,width,height] duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] motion-reduce:transition-none"
          style={{
            transform: `translate(${rect.left}px, ${rect.top}px)`,
            width: rect.width,
            height: rect.height,
          }}
        />
      ) : null}
      {children}
    </TabsPrimitive.List>
  )
}

function TabsTrigger({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      className={cn(
        'relative z-10 inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg px-4 py-2 text-sm font-medium',
        // border-2 on BOTH states, transparent when active: the fill is the
        // travelling indicator behind the trigger, so a border that only exists
        // on inactive triggers would shift every neighbour as the selection moved.
        'border-2 border-transparent',
        'transition-colors duration-200 ease-[cubic-bezier(0.4,0,0.2,1)] motion-reduce:transition-none',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
        'disabled:pointer-events-none disabled:opacity-50',
        // Active: sits on the primary fill, so it takes the foreground tuned for it.
        'data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:font-semibold',
        // Inactive: a visible border, which is the part that was asked for and
        // that the stock shadcn tabs did not have at all.
        'data-[state=inactive]:border-border data-[state=inactive]:bg-card data-[state=inactive]:text-muted-foreground',
        'data-[state=inactive]:hover:border-foreground/40 data-[state=inactive]:hover:text-foreground',
        "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        className,
      )}
      {...props}
    />
  )
}

function TabsContent({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return (
    <TabsPrimitive.Content
      data-slot="tabs-content"
      className={cn('flex-1 outline-none', className)}
      {...props}
    />
  )
}

export { Tabs, TabsList, TabsTrigger, TabsContent }
