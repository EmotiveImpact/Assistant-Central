# Frozen r5: observed runtime dependency inventory

**Result:** the currently installed metadata closure is consistent on **CPython 3.12.14, Linux x86_64**. The three runtime roots are **MCP 1.29.0, AnyIO 4.14.2, and cryptography 50.0.0**. Their active closure has **29 distributions and 47 active requirement edges**. Every active version specifier and every package’s `Requires-Python` constraint is satisfied. No missing distribution, active conflict, direct-URL requirement, or uncertain marker was found in this scope.

This is a **version snapshot**, not a wheel-hash lock, package provenance proof, clean-install result, resolver result, portable target lock, or native host/provider acceptance. No package was fetched or installed. No runtime, host, server, inherited test suite, owner object, or peer process was run.

## Files

- `dependency-inventory.json`: exact observed versions; active and excluded requirement edges; complete evaluated PEP 508 environment; extra propagation; Python-version checks; static import evidence and source digests; frozen-input comparisons; limitations.
- `requirements-observed-linux-py312.txt`: inert exact-version pins for this closure, preserving the activated `pyjwt[crypto]` extra. Its presence does not authorize installation.

Observation date: 8 November 2026. Inventory parsing used installed `packaging` 26.3 with `importlib.metadata`; packaging is analysis tooling and is not a runtime dependency in this closure.

## Scope and method

The launcher and its reachable permitted local modules were parsed for import declarations, including package initializers. This establishes the external roots `anyio`, `mcp`, and `cryptography`; Pydantic 2.13.4 is a transitive MCP dependency. Static import evidence includes the Ed25519/X25519 types and the MCP low-level server/message/types modules used by the frozen code. **No imported local code was executed and no runtime import smoke test was performed.** Static tracing is not proof of all dynamic imports or executed code paths.

For each reached distribution, installed `Requires-Dist` metadata was parsed as PEP 508, markers were evaluated for this exact platform, and requested extras were propagated to a fixed point. The inventory records evaluation under the base context (`extra=""`) and every declared extra, with only the base plus actually requested extras selecting active edges. Observed installed versions were compared with active specifiers, allowing prereleases for this comparison rather than doing resolver candidate selection. Package `Requires-Python` constraints were checked against 3.12.14. Unselected optional targets were not resolved or inspected merely because they appeared in metadata.

This is the full **active declared dependency closure**, not the smallest set of modules executed by the pilot. HTTP, SSE, JWT and server packages remain where MCP metadata makes them mandatory. Their inclusion does not enable or approve networking, authentication, listeners or external communication. Standard-library modules, operating-system libraries and native extension build dependencies are not Python distribution edges in this inventory.

Only reached distribution metadata was inventoried. There was no global environment dump, environment-variable inspection, credential-file access, `direct_url.json` read, pip invocation, package-cache read, download or network access. The excluded `fixture.py`, `pipes.py`, `worker.py` and `endpoint.py` source files were not read or reviewed. No additional peer concurrency, shutdown or descriptor-lifecycle review was performed. No preflight utility was added because the inventory and recorded comparisons are sufficient for this step.

## Extras and platform exclusions

- MCP’s mandatory `pyjwt[crypto]` requirement activates **PyJWT’s crypto extra**, which requires cryptography. This is the only activated package extra.
- MCP **cli**, **rich** and **ws** extras are not selected. Optional Typer, Rich and WebSocket edges are excluded. The CLI-marked MCP `python-dotenv` edge is excluded, but **python-dotenv 1.2.2 remains mandatory through pydantic-settings**.
- AnyIO trio, cryptography ssh, HTTPX optional protocol/CLI extras, Pydantic email/timezone, secret-manager integrations, Uvicorn standard and all other unselected extras remain outside the selected closure. Their metadata edges are recorded separately, without resolving their dependency trees.
- Windows-only pywin32 and requirements for other Python/platform marker branches are excluded for this Linux/Python 3.12 environment. In total, **76 requirement edges** are inactive. An inactive optional edge can point to a package that is independently active elsewhere.

## Frozen inputs and unchanged runtime contract

Both supplied hashes matched before and after inventory collection:

- `agent-network-synthetic-stdio-r5/launcher.py`: `4df94f7f454989f864ac327da182b1054fff8952e4288915cb988fe891529571`
- `agent-network-synthetic-stdio-experimental-r5.zip`: `050d8d91a06f683a40d7ef7b9ab76e7f46238e2db8313b106bf6b353abef2d88`

The frozen runtime remains Python 3.12/POSIX FIFO stdio, interpreter flags `-I -B`, no application arguments, the exact fixed public text, and no owner or peer instances. This inventory does not widen that contract. Prior synthetic checks remain prior evidence, not new results from this task.

## Minimal later steps, after selecting and approving a real target

1. Record the exact machine, OS/architecture/ABI, Python executable/build, host product/build, provider and temporary synthetic-only scope. Confirm compatible POSIX FIFO stdio. Reevaluate markers on that machine; do not assume this Linux snapshot is portable or change frozen constants to hide differences.
2. Approve the exact official package sources and acquisition/install scope. Resolve the same root versions and intended extras for that target in isolation, recording resolver/tool versions. Treat a missing compatible artifact or changed dependency requirement as a decision, not permission to update the frozen release.
3. Obtain the exact target wheels through those approved sources, record filenames, platform tags, distribution hashes and source/provenance evidence, and retain a bounded wheelhouse. Include interpreter and relevant OS/native-library identity. If a source build is unavoidable, separately pin and record its compiler, build requirements and resulting artifact. A versions-only file cannot supply these facts.
4. With installation approval, build a disposable isolated target environment from the reviewed artifacts, enforce complete hashes and compare its installed metadata with the reviewed target lock. Record the clean-install outcome. Do not alter system Python or unrelated environments.
5. Perform only separately approved synthetic stdio validation against the preserved release and record its exact scope. Native host/provider acceptance remains a later, separately approved gate. The additional peer-process review remains uncompleted and excluded; this preparation does not reopen it.

A metadata-consistent installed closure is a useful foundation. It does not establish that the package bytes are authentic, that another resolver can fetch the same bytes, that native extensions will work on another machine, or that a native host will accept this pilot. `-I -B` does not eliminate trust in the interpreter, startup hooks or installed package contents.
