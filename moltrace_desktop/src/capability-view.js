'use strict'
// How a capability verdict is presented to a person.
//
// capabilities.js decides IF something is available. This decides what the person
// is told, and it is a separate concern because the failure mode is different:
// the readout can distinguish four causes perfectly and still be useless if the
// interface renders all four as one grey "unavailable". §4.2 is explicit that the
// four "imply four different next actions", and the whole reason for keeping them
// apart is to send someone to the right place.
//
// So each state carries an ACTION, not just a status. "Unavailable" tells a person
// nothing they did not already know from the control being disabled.

const PRESENTATION = {
  product_not_in_plan: {
    headline: 'Not included in this workspace',
    action: 'Ask whoever manages your MolTrace account about adding it.',
    tone: 'upgrade',
  },
  product_not_enabled: {
    headline: 'Switched off for this installation',
    action: 'An administrator can turn this on for your workspace.',
    tone: 'admin',
  },
  product_not_provisioned: {
    headline: 'Not set up on this computer yet',
    action: 'Finish setting up this installation, then try again.',
    tone: 'setup',
  },
  role_required: {
    headline: 'You do not have permission',
    action: 'Ask an administrator to give your account access.',
    tone: 'permission',
  },
}

// A state this view has not been taught about. It must render LOUDLY rather than
// blankly: an empty cell reads like "fine", and this one is not fine — it means
// the desktop and the deployment disagree about the vocabulary.
const UNRECOGNISED = {
  headline: 'Unavailable for a reason this version does not recognise',
  action: 'This installation may be older than your workspace. Updating it may help.',
  tone: 'unknown',
}

function present(verdict) {
  if (verdict.available) {
    return {
      key: verdict.key,
      displayName: verdict.displayName,
      available: true,
      code: null,
      // A preview build says so HERE, next to the capability, and not only in a
      // banner at the top of the window. A banner is read once and then stops
      // being seen; the line beside the thing you are about to use is not.
      headline: verdict.preview === true ? 'Available in this preview build' : 'Available',
      action: null,
      tone: 'available',
      preview: verdict.preview === true,
    }
  }
  const p = PRESENTATION[verdict.code] || UNRECOGNISED
  return {
    key: verdict.key,
    displayName: verdict.displayName,
    available: false,
    // Carried so a client can branch on it; never rendered.
    code: verdict.code,
    headline: p.headline,
    action: p.action,
    tone: p.tone,
    preview: verdict.preview === true,
  }
}

module.exports = { present, PRESENTATION, UNRECOGNISED }
