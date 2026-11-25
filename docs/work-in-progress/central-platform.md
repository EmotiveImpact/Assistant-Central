# Central platform design

Coordinator: `/root`. Goal: a working Assistant Central platform with the
typographic weight, spacing and restrained dark palette of the Linear reference.
Base: main `fccc516e9192edd9c4a3ec3226d2acf153914c50`.

Initial commit: coordination only, before implementation. Draft PR #19 was
opened immediately. The alternative workspace is now implemented.

Owns the new `workspace_ui/` component and its dedicated CI workflow only.
Does not edit `pilot/web/`, `pilot/server.py`, runtime, auth, transport or provider
components owned by other active workstreams (#14 through #18). The alternative
frontend will use the existing owner HTTP API and explicit review operations.

Assignments: `/root` owns design, HTML/CSS, integration and PR;
`/root/platform_logic` owns navigation, projections, search and client review;
`/root/platform_runtime` owns the same-origin launcher and disposable fixture;
`/root/platform_review` owns browser/regression verification and dedicated CI.

Verification: 272 existing pilot tests, 7 new HTTP/static tests, 25 existing model
tests, 9 projection tests and both existing actual HTTP contracts pass locally.
Initial hosted browser run 42791642581 passed on 689c1d7. Visual inspection led
to a readability pass, honest activity sequence labels, exact metric filtering
and waiting for the mobile drawer to settle before capturing screenshots. Final
hosted evidence belongs in the PR and workspace_ui/VERIFICATION.md.
All fixture content remains fictional; live providers stay disabled. No merge
or deployment without owner approval. Later transfer workspace integration is a
separate composition check with #16.

## Exact style correction, 10 November

The user requested Linear's exact font and styling. The earlier implementation
named Inter without loading it. `/root` now owns the bundled official Inter 4.1
font/licence, measured component tokens, HTML preload and source reference.
`/root/exact_style_audit` audits reference mappings and cascade conflicts.
`/root/exact_font_tests` owns the narrow font route and HTTP/browser checks.
The existing PR was returned to draft before this correction began.

Eight HTTP tests and nine projection tests pass locally. Browser checks pin the
font bytes and assert successful decoding, the actual family, 510/590 weights,
optical sizing and exact computed geometry. Final hosted evidence and screenshot
inspection are recorded in PR #19. No provider or consent boundary was widened.

## Interface refinement after visual approval

Coordinator `/root` owns HTML/CSS and screenshot integration.
`/root/polish_rendering` owns read-only client presentation changes;
`/root/polish_review` independently reviews visuals and accessibility.
Previous head `2488aef` passed both full regression and workspace browser CI.
The approved Inter font and tokens remain in place. This pass focuses attention
and network panels, reduces repeated overview work, improves mobile density and
metadata contrast, and removes the non-functional workspace-switch chevron.
No authentication, provider, transport or decision endpoint was changed.
