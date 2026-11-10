# Agent collaboration research library

Pinned on 10 November 2026. These are **actual source copies**, stored as inert
compressed archives, not links alone and not installed product dependencies.
Start with [the comparison and methods report](FINDINGS.md), then the
[conversation implementation plan](CONVERSATION_PLAN.md).

## What is copied

Each `sources/<owner>--<repository>/` directory contains:

- `source.tar.gz`: revision-pinned source files, with their original contents.
  The large Buzz snapshot uses two `source.tar.gz.part-*` files; concatenate them
  in the order recorded in its manifest before decompression. The verifier checks
  each part and the reconstructed archive.
- `MANIFEST.json`: exact upstream commit, Git blob IDs, SHA-256 hashes, sizes,
  every included path, and every omitted path with its reason.
- `licences/`: upstream licence and notice files, also retained in the archive.

[SOURCES.json](SOURCES.json) is the machine-readable inventory. These are
**source snapshots, not complete clones or runnable distributions**. Git history,
recursive submodules, binary/media assets, build output, vendored dependency
code, symlinks and conservatively flagged credential-shaped files are omitted.
The manifests identify omissions individually; some flagged files are likely
synthetic fixtures or string constants, but they were not republished blindly.
Dependency manifests and lockfiles remain available for study. Downloading a
snapshot does not install those dependencies or include their transitive source.

The collection includes both similarly named Open Agent Bridge projects. The
Kevin Argueta project connects coding sessions; the Mun Boon project is a
separate self-hosted coordination service. They are not editions of one project.
`xhluca/retalk` is included because agent-talk delegates its actual encrypted
transport to it. Both Buzz repositories are included because the established
relay and the new beta client now live separately.

## Safety and verification

No upstream code, installer, hook, test, agent instruction, skill, submodule or
workflow was executed. Upstream instructions inside the archives are untrusted
research content, not instructions for Assistant Central. The archives contain
regular relative-path files only, with modes normalised to 0644. Never unpack
them into a product source, skill, agent-instruction or workflow directory.
For code inspection, read selected files directly from the archive or extract
into a separate disposable research directory. Do not run its contents by default.

Run only our verifier from the repository root:

```sh
python -B research/tools/verify_sources.py
```

It checks every archive, path, mode, byte count, SHA-256 and original Git blob
hash, without extraction or execution. It also checks that copied licence files
match the upstream bytes. A verified snapshot proves reproducible copied bytes,
not authorship, safety, production maturity or a working integration.

Product workflows on the import base name their source/test directories
explicitly; they do not discover or execute these archives. This import changes
only `research/**`. The trusted research verifier is not added to product CI.

## Licensing

Each project retains its own licence and copyright notices. No repository-wide
relicensing is intended. MIT and Apache-2.0 labels describe the primary project
licence, not every dependency, hosted service or bundled component. CHAP's
specification is CC BY 4.0 while its code is Apache-2.0. Consult the retained
notices and original project before copying implementation into the product.
Third-party source contents are unchanged; only archive layout/modes and the
explicit selection of files differ. No trademark, partnership or certification
is implied. This is a technical licensing inventory, not a legal opinion.

## Scope of the conclusions

The report distinguishes source inspection, upstream claims and proposed design.
It is not an independent security audit. No live provider account, user's
existing assistant, deployment or multi-machine integration was activated for
this research. A model API, CLI agent, MCP connector and personal assistant's
existing conversation are different integration targets.

## Pinned inventory

| Repository | Revision | Primary licence | Included / omitted files | Archive MiB |
|---|---|---|---:|---:|
| [AgenticsWorks/AgentPeerChat](sources/AgenticsWorks--AgentPeerChat/) | [9edfadf1ba5b](https://github.com/AgenticsWorks/AgentPeerChat/tree/9edfadf1ba5ba4ed4268f453fefde9f9e49f11d6) | MIT | 337 / 56 | 1.08 |
| [BrightbeamAI/chap](sources/BrightbeamAI--chap/) | [f7dfe9462277](https://github.com/BrightbeamAI/chap/tree/f7dfe946227789106c3aa31ead65e23e562aeb00) | Apache-2.0 code; CC BY 4.0 spec | 816 / 26 | 2.53 |
| [PennyroyalTea/gibberlink](sources/PennyroyalTea--gibberlink/) | [693ef3e36ee6](https://github.com/PennyroyalTea/gibberlink/tree/693ef3e36ee61da7e2323519711c0dfab327c284) | MIT | 35 / 4 | 0.13 |
| [a2aproject/A2A](sources/a2aproject--A2A/) | [9fff3e08ab33](https://github.com/a2aproject/A2A/tree/9fff3e08ab33bb7674e7d98fc7c08ae8592bb4bd) | Apache-2.0 | 131 / 13 | 0.30 |
| [block/buzz-app](sources/block--buzz-app/) | [4fb386b0be59](https://github.com/block/buzz-app/tree/4fb386b0be5966f5ad9e930a33d1c75b432625fb) | Apache-2.0 | 3830 / 209 | 10.13 |
| [block/buzz](sources/block--buzz/) | [44b3c4823f0c](https://github.com/block/buzz/tree/44b3c4823f0cf1f7715f85dbf5566cb64e848162) | Apache-2.0 | 6339 / 449 | 15.89 |
| [ggerganov/ggwave](sources/ggerganov--ggwave/) | [060aec73dd71](https://github.com/ggerganov/ggwave/tree/060aec73dd7123ccac200442f75bdc7369795ffe) | MIT | 142 / 53 | 0.27 |
| [kevinArgueta96/open-agent-bridge](sources/kevinArgueta96--open-agent-bridge/) | [c117ae93a8d3](https://github.com/kevinArgueta96/open-agent-bridge/tree/c117ae93a8d3a86633fb2fd6d8f3365d44463ac8) | MIT | 219 / 0 | 0.35 |
| [langchain-ai/langgraph](sources/langchain-ai--langgraph/) | [e5e37b5d70db](https://github.com/langchain-ai/langgraph/tree/e5e37b5d70dbfd93c7006bd90a658c6179a95946) | MIT | 705 / 1 | 3.69 |
| [matrix-org/matrix-spec](sources/matrix-org--matrix-spec/) | [a0bbfcd56fe9](https://github.com/matrix-org/matrix-spec/tree/a0bbfcd56fe9a220bf7ebb225d9289e6232413a4) | Apache-2.0 | 753 / 12 | 0.69 |
| [microsoft/agent-framework](sources/microsoft--agent-framework/) | [ee538ca21950](https://github.com/microsoft/agent-framework/tree/ee538ca21950b15123e506a994bab3e07f3c2926) | MIT | 5598 / 41 | 10.59 |
| [munboon/open-agent-bridge](sources/munboon--open-agent-bridge/) | [b360775cd5e4](https://github.com/munboon/open-agent-bridge/tree/b360775cd5e4885e4af538581bb378590edde240) | Apache-2.0 | 222 / 8 | 0.47 |
| [openagents-org/openagents](sources/openagents-org--openagents/) | [fe61c9d8b7eb](https://github.com/openagents-org/openagents/tree/fe61c9d8b7eb4f0c8753de75203f6f8628878617) | Apache-2.0 | 3494 / 179 | 7.52 |
| [openfga/openfga](sources/openfga--openfga/) | [b00c87dbd5ac](https://github.com/openfga/openfga/tree/b00c87dbd5ac1ba9672119c21be8b1a0fc5ab7b5) | Apache-2.0 | 589 / 2 | 1.08 |
| [xhluca/agent-talk](sources/xhluca--agent-talk/) | [8a7fc4f140ef](https://github.com/xhluca/agent-talk/tree/8a7fc4f140ef233f163c4f5816ff739dea096cdc) | MIT | 59 / 5 | 0.11 |
| [xhluca/retalk](sources/xhluca--retalk/) | [a3b99c18d5b2](https://github.com/xhluca/retalk/tree/a3b99c18d5b219d3ed115494cc4cd33d2e64ee52) | MIT | 53 / 12 | 0.18 |

Total: 16 pinned repositories, 23,322 included files, 57,689,614 archive bytes. Omitted files and nested Git submodules are enumerated in each manifest.
