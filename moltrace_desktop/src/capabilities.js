'use strict'
// The desktop capability readout (§7.1).
//
// No server endpoint aggregates this. `GET /system/capabilities` reports only
// which products a DEPLOYMENT includes; it says nothing about the entitlement,
// the local pack inventory, or whether the scientific service is reachable. So
// the desktop assembles the answer from four independent sources, and this
// module is the one place that combination happens.
//
// THE INVARIANT, and it is the whole point: never render a capability as
// available and then fail on click. That makes the default DENY — an input that
// is absent, unreadable or unreachable is not "probably fine", it is unknown,
// and unknown is not available. Every gate must affirmatively say yes.

// §4.2's vocabulary. Four distinguishable causes, because they imply four
// different next actions and presenting them as one denial sends a person to the
// wrong place. Do NOT invent a fifth word here — the desktop and the web surface
// must name the same situation identically.
const LOCKED_CODES = [
  'product_not_in_plan',      // the deployment does not serve this product
  'product_not_enabled',      // it is served, but not switched on here
  'product_not_provisioned',  // enabled, but the local side is not set up
  'role_required',            // everything is present; this person may not
]

function assess(capability, world = {}) {
  const name = capability.displayName || capability.key

  // 1. Does the deployment serve the product at all?
  const modules = Array.isArray(world.modules) ? world.modules : null
  if (modules === null) return locked('product_not_in_plan', `${name} is unavailable because this installation could not establish which products the workspace includes.`)
  if (capability.requiresModule && !modules.includes(capability.requiresModule)) {
    return locked('product_not_in_plan', `${name} is not part of the products this workspace includes.`)
  }

  // 2. Is it entitled? An absent or invalid statement is not a soft yes.
  const ent = world.entitlement
  if (!ent || ent.valid !== true) {
    return locked('product_not_enabled', `${name} is switched off for this installation, or its licence could not be confirmed.`)
  }
  // The statement's OWN module list. `Array.isArray(...) &&` was here and made
  // the check permissive: an entitlement with `valid: true` and no `modules`
  // field — truncated, malformed, or an older schema — granted every module.
  // That is the exact inversion of this file's doctrine ten lines up, and of the
  // gate one step earlier, where a non-array `world.modules` is coerced to null
  // and immediately locked. An absent list is not an empty constraint; it is no
  // answer, and no answer is not available.
  if (capability.requiresModule) {
    if (!Array.isArray(ent.modules)) {
      return locked('product_not_enabled', `${name} is unavailable because this installation could not read which products its licence covers.`)
    }
    if (!ent.modules.includes(capability.requiresModule)) {
      return locked('product_not_enabled', `${name} is not switched on for this installation.`)
    }
  }

  // 3. Is the local side actually set up — packs present, service reachable and
  //    carrying the engine this capability needs?
  const packs = Array.isArray(world.packs) ? world.packs : null
  if (packs === null) return locked('product_not_provisioned', `${name} is unavailable because this installation could not read its local reference data.`)
  if (capability.requiresPack && !packs.includes(capability.requiresPack)) {
    return locked('product_not_provisioned', `${name} needs reference data that is not installed here yet.`)
  }
  const svc = world.service
  if (!svc || svc.reachable !== true) {
    return locked('product_not_provisioned', `${name} needs the local science service, which is not running.`)
  }
  if (capability.requiresService && !(svc.versions && capability.requiresService in svc.versions)) {
    return locked('product_not_provisioned', `${name} needs a part of the local science service that this installation does not provide.`)
  }

  // 4. May this person do it? Checked LAST, so a role refusal is never used to
  //    mask a provisioning gap the operator ought to see.
  if (capability.requiresRole && world.role !== capability.requiresRole) {
    return locked('role_required', `${name} is available here, but your account does not have permission to use it.`)
  }

  return { key: capability.key, displayName: name, available: true, code: null, reason: null }

  function locked(code, reason) {
    return { key: capability.key, displayName: name, available: false, code, reason }
  }
}

/** Every declared capability, assessed. No capability is omitted. */
function readout(capabilities, world) {
  return capabilities.map((c) => assess(c, world))
}

module.exports = { assess, readout, LOCKED_CODES }
