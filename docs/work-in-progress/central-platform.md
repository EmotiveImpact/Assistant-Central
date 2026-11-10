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
