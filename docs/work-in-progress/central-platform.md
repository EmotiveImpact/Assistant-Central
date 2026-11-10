# Central platform design

Coordinator: `/root`. Goal: a working Assistant Central platform with the
typographic weight, spacing and restrained dark palette of the Linear reference.
Base: main `fccc516e9192edd9c4a3ec3226d2acf153914c50`.

Initial commit: coordination only, before implementation.

Owns the new `workspace_ui/` component and its dedicated CI workflow only.
Does not edit `pilot/web/`, `pilot/server.py`, runtime, auth, transport or provider
components owned by other active workstreams (#14 through #18). The alternative
frontend will use the existing owner HTTP API and explicit review operations.

Assignments: root owns design, HTML/CSS, integration and PR; platform logic agent
owns client navigation, projections and search; runtime agent owns the optional
same-origin launcher and disposable fixture; review agent owns browser/regression
verification. Exact agent names and evidence will be recorded as assigned.

Planned verification: actual HTTP browser flows, desktop/mobile layouts, keyboard
navigation, exact review and uncertainty controls, existing pilot regressions.
All fixture content remains fictional; live providers stay disabled. No merge
or deployment without owner approval. Later transfer workspace integration is a
separate composition check with #16.
