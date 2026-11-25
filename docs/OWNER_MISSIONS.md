# Owner-reviewed missions

Open **Conversations**, select a room and choose **Mission agreements**. The coordinating owner opens the panel first after starting the workspace. Create an agreement with an executing room member, a deliverable, success criteria and a simulated budget. Each current member reviews the exact revision using their own login. A revision begins with fresh approvals.

Once everyone agrees, the author can enter a new, directly authored fictional brief. Creating its draft is an explicit step. Use the existing outbox to review and release it. The executor separately accepts the peer task, reviews the provider-visible text and simulated reservation, approves the run and invokes the fixture. The return also requires review, release and a recipient decision. The proposal text, criteria and history are kept out of the provider input. The task carries its agreement commitment, budget and separately entered brief.

The author can enter the incoming artefact ID under the mission to evaluate the exact retained return while the agreement is current. Literal text, UTF-8 length and exact SHA-256 checks produce reproducible observations. Judgement criteria remain open for the owner. The report binds the proposal revision, parent task, artefact and content digest. A passing report cannot accept a return. A failed check does not force another attempt.

### Simulated usage

The only price schedule is fictional. The fixture reserves 20 microUSD per request plus 2 microUSD per permitted output token. A completed response settles against the reported output tokens. The cap applies to one executing owner's provider in one agreement revision on its runtime store. Concurrent claims use the existing SQLite write transaction. A timeout, cancellation after dispatch or malformed response retains the original reservation. New submissions under the same context cannot increase the cap. A new agreement revision has its own cap and authorisations. There is no live billing integration.

### Acceptance

Run the following from the repository root with the pilot requirements installed.

```sh
python -B -m unittest pilot.tests.test_mission_budget workspace_ui.tests.test_mission_handoff -v
```

The handoff check exercises separate local account approvals through the owner HTTP service, then closes the coordinator before opening the requester and executor stores in two different loopback processes. It releases and exchanges exact packets, performs one synthetic run, restarts the coordinator, evaluates the pending return and explicitly rejects it. It verifies that one passing check, one failing check and one owner-review check cause no automatic decision. This uses a trusted host and test accounts. Approval withdrawal or revision prevents fresh mission drafts. A previously released task has its own signed lifetime and cancellation path. Revoking discussion agreement alone cannot recall it.

The separate SDK tests exercise inert drafts. Independent human owners, operational host enrolment, paid models and production hosting need separate acceptance.

### Direct handoff across two owner runtimes

For a bilateral task, open **New proposal** and select **Peer mission**. The requester enters the terms they intend to share, the executing peer, a check and the maximum simulated cost. The full direct offer goes to the named peer only after the requester reviews and releases it. Its signed fields bind the owner identities, offer, expiry and budget. On supported receivers, the explicit provider permission permits only the brief. A receiver running the old protocol refuses the new permission shape. The requester can omit provider permission altogether. A room agreement and access to another owner's vault are unnecessary for this direct route. Each direct offer is its own immutable task. To stop a released offer, use its existing cancellation operation and inspect delivery.

Both owner runtimes can use the existing loopback owner API and separately configured peer transport. After receipt, the executing owner decides on the task and separately on any run. An incoming return can be checked directly in its review dialog. The evidence uses the requester's retained original offer and the exact signed return, even if there is no shared conversation coordinator. A new offer has a separate budget.

```sh
npm ci --prefix agent_bridge --ignore-scripts --no-audit --no-fund
python -B -m unittest workspace_ui.tests.test_peer_mission -v
```

This additional test uses the official OpenAI Agents runner and Cursor/Grok SDK host to prepare owner-local inert notes alongside an actual two-process handoff. The owners select a common fictional task reference. No draft is promoted into a provider request. The test denies an offer without disclosure permission, then exercises a separately authorised offer through acceptance, fixture execution, release, deterministic evidence and recipient acceptance. The SDK paths use a deterministic double and a no-model tool invocation. No model provider was contacted.
