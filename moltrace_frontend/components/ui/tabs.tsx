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
        'bg-muted text-muted-foreground relative inline-flex h-9 w-fit items-center justify-center rounded-lg p-[3px]',
        // The indicator now paints the selection, so the active trigger stands
        // down. Scoped to data-has-indicator so the no-JS / pre-measure render
        // keeps the original look rather than showing no selection at all.
        '[&[data-has-indicator=true]_[data-slot=tabs-trigger][data-state=active]]:bg-transparent',
        '[&[data-has-indicator=true]_[data-slot=tabs-trigger][data-state=active]]:shadow-none',
        'dark:[&[data-has-indicator=true]_[data-slot=tabs-trigger][data-state=active]]:bg-transparent',
        'dark:[&[data-has-indicator=true]_[data-slot=tabs-trigger][data-state=active]]:border-transparent',
        className,
      )}
      {...props}
    >
      {rect ? (
        <span
          aria-hidden
          className="bg-background pointer-events-none absolute bottom-[3px] left-0 top-[3px] rounded-md shadow-sm transition-[transform,width] duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] motion-reduce:transition-none dark:border-input dark:bg-input/30 dark:border"
          style={{ transform: `translateX(${rect.left}px)`, width: rect.width }}
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
        "relative z-10 data-[state=active]:bg-background dark:data-[state=active]:text-foreground focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:outline-ring dark:data-[state=active]:border-input dark:data-[state=active]:bg-input/30 text-foreground dark:text-muted-foreground inline-flex h-[calc(100%-1px)] flex-1 items-center justify-center gap-1.5 rounded-md border border-transparent px-2 py-1 text-sm font-medium whitespace-nowrap transition-[color,box-shadow] focus-visible:ring-[3px] focus-visible:outline-1 disabled:pointer-events-none disabled:opacity-50 data-[state=active]:shadow-sm data-[state=inactive]:hover:bg-background data-[state=inactive]:hover:text-foreground data-[state=inactive]:hover:shadow-sm dark:data-[state=inactive]:hover:border-input dark:data-[state=inactive]:hover:bg-input/30 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
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
