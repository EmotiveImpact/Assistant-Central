# Agent collaboration source research

Coordination notice, 10 November 2026. This first commit contains no imported
implementation and changes no product behaviour.

## Ownership and scope

The research worker owns `research/**` on this branch, coordinated with the
Assistant Central network work. Base: `main` at
`55b7df104b12f69336055ca9d5ba0d773d8b10a5`.

The goal is to keep actual, revision-pinned upstream source snapshots for the
requested agent collaboration projects, preserve their licences and notices,
and mine the code for methods relevant to Assistant Central. These files are
reference material, not product dependencies or verified integrations.

## Planned verification

- Resolve exact repositories before import and record commits and source URLs.
- Inspect tracked tree sizes, nested dependencies, licences and suspicious files.
- Keep imports inert: no installing, running upstream code, hooks or submodules.
- Record exclusions rather than silently presenting partial copies as complete.
- Verify per-file hashes and ensure product workflows do not execute the copies.
- Compare conversation persistence, membership, historical access, task handoff,
  compact messages, security and actual supported assistant connection surfaces.

An ambiguously named Open Agent Bridge source is being resolved with the
coordinator. No existing personal assistant account or model is activated.
