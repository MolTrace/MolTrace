"use client"

import * as React from "react"
import { Eye, EyeOff } from "lucide-react"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

/**
 * Password field with an in-field show/hide toggle (eye icon).
 *
 * Thin wrapper over the shared <Input>: it owns only the visibility state and
 * toggles the input `type` between "password" and "text". Every other prop
 * (id, name, autoComplete, required, disabled, …) forwards straight through,
 * so it's a drop-in replacement for `<Input type="password" />` in the auth
 * forms — they stay uncontrolled / FormData-driven.
 *
 * Accessibility:
 *  - the toggle is `type="button"` so it never submits the surrounding form
 *  - its `aria-label` flips between "Show password" / "Hide password" and it
 *    carries `aria-pressed` so screen readers announce the current state
 *  - the toggle inherits the field's `disabled` state
 *  - the input reserves right padding (pr-10) so masked text never runs
 *    underneath the icon
 */
type PasswordInputProps = Omit<React.ComponentProps<typeof Input>, "type">

function PasswordInput({ className, disabled, ...props }: PasswordInputProps) {
  const [visible, setVisible] = React.useState(false)

  return (
    <div className="relative">
      <Input
        {...props}
        type={visible ? "text" : "password"}
        disabled={disabled}
        className={cn("pr-10", className)}
      />
      <button
        type="button"
        // Keep the control out of the way of password managers but still
        // reachable by keyboard (natural tab order, no tabIndex override).
        onClick={() => setVisible((v) => !v)}
        disabled={disabled}
        aria-label={visible ? "Hide password" : "Show password"}
        aria-pressed={visible}
        title={visible ? "Hide password" : "Show password"}
        className={cn(
          "absolute inset-y-0 right-0 flex items-center pr-3 text-muted-foreground",
          "transition-colors hover:text-foreground focus-visible:text-foreground",
          "focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50",
        )}
      >
        {visible ? (
          <EyeOff className="h-4 w-4" aria-hidden />
        ) : (
          <Eye className="h-4 w-4" aria-hidden />
        )}
      </button>
    </div>
  )
}

export { PasswordInput }
