# Central transfer composition

Coordinating role: platform integration. Review role: independent network and interface review.

Compose the refined Central workspace from PR #19 at
83a7d1539e9cf13abf5911157fdc265aea20a00f with the owner transfer controls
from PR #16 at 002d4afd0784f7ac68e2e6e106a2c4a09cc9d61f.
Both dependency commits are retained. Main integration remains separately gated.

Claimed paths: workspace_ui/**, .github/workflows/workspace-ui.yml and this notice.
No pilot authentication, runtime, storage, provider or transport changes. No changes
to conversation/**, agent_bridge/** or research/**. Persistent conversation UI
integration remains reserved for PR #22. The existing receipt-recovery documentation
is not an edit target.

Planned work: close the exact browser module graph; compose explicit transfer
review, send, retry, import and cached receipt controls into one shell; add trusted
optional transfer configuration; correct contrast, named dialogs, skip focus and
logout hygiene. Preserve all owner session, mutation and uncertainty gates.

Verification: actual recursive HTTP module graph, full combined Python and model
regressions, disposable loopback HTTP/TLS browser scenarios, accessibility and
mobile focus checks, hosted screenshots. Local Chromium is blocked by the known
socket restriction; no workaround or local browser pass is claimed.

The initial commit contains dependency composition and coordination only, not
working transfer integration. No live provider, real data or public deployment.

## Implementation decisions

- Retain one Central shell and the shared model/transfer validators. The transfer
  view has no new session, backend authority, automatic retry or import path.
- Add only the exact descriptor-pinned shared transfer module. Keep private host
  configuration optional and use the existing loader without changing its checks.
- Keep transport ACK, signed receipt, owner acceptance and execution separate.
  Show immutable attempt history and warn that local withdrawal cannot recall bytes.
- Improve quiet/placeholder contrast while retaining original Central assets and
  layout. Name all dialogs, preserve skip-link routing and clear hidden owner data.
- Use real disposable HTTP/TLS owners and explicit browser actions. Test-only
  response faults and a post-TLS completion gate reproduce uncertainty and
  in-flight withdrawal; they are never available in the production launcher.

Current local regression results and hosted evidence are tracked in
[workspace verification](../../workspace_ui/VERIFICATION.md). This remains a draft
until exact combined-tree browser, aggregate CI and independent review are complete.
