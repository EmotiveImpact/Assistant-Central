# Roadmap

## Current implementation

Python remains the current orchestration and experimentation language. The team
coordinator, consent/protocol prototype and synthetic MCP stdio launcher are
separately tested. Their presence in one repository does not make them integrated.

## Next engineering gates

1. Define a stable mapping between team task/artifact digests and the existing
   consent/protocol messages. Test scope, disclosure and recipient authority
   independently, including revoked, declined, expired and uncertain outcomes.
2. Bind one authenticated local owner control and one narrowly scoped agent/tool
   route. A lead must never mint another owner's grants. Keep private local
   sessions separate from explicitly shared outcomes.
3. Validate one named host/provider with synthetic input: startup, logging,
   restart, cancellation, environment handling and rollback. The current r5
   launcher does not prove native-host acceptance.
4. Design persistent owner identity, protected key custody, named-peer enrollment,
   encrypted transport and recovery. Require threat modeling and independent
   security review before real personal data or production use.
5. Exercise idempotent outbox/inbox behavior and bounded wake/cancellation semantics.
   Do not reinterpret timeouts as permission to resend or assign work elsewhere.
6. Measure realistic workloads and failure modes before making scale, throughput
   or reliability claims. Keep compatibility, observability and operational
   complexity visible alongside performance.

## Rust remains an option

Evaluate Rust for bounded message validation, cryptographic boundary components
or measured throughput bottlenecks. A rewrite is not assumed. A candidate must
demonstrate interoperability with Python, a simpler or defensible operational
model, reproducible performance results, maintainable interfaces and security
review. Memory safety does not replace authentication, consent or key custody.

## Reuse research

Evaluate orchestration frameworks, durable workflow engines and secure messaging
projects separately. Existing libraries can help with execution adapters,
checkpointing and transport, but none should silently become the authority for
another human owner's actions. Preserve upstream notices and review license
obligations before code reuse, especially copyleft distribution boundaries.

The [source-linked landscape review](docs/research/orchestration-landscape.md)
compares 14 main candidates and 7 alternatives. Evaluate a minimal stack: keep
owner control independent, consider LangGraph for coordination and Pydantic AI
for a Python runtime adapter, use DSH Squad as a receiver-authority design
reference, and assess A4A/A2A at their separate transport/protocol boundaries.
These are research recommendations, not selected dependencies or tested integrations.
