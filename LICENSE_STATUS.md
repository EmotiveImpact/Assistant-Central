# Licence status

Original Assistant Central code in this repository is licensed under the
[Apache License, Version 2.0](LICENSE). See [NOTICE](NOTICE) for attribution.

Third-party material keeps its own licence:

- `prototypes/consent-v29/vendor/a4a/`: MIT, with upstream provenance and the
  NIP-44 vector caveat in `THIRD_PARTY_LICENSES.md`.
- `prototypes/consent-v29/vendor/a4a_sdk/nip44_vectors.LICENSE.txt`: preserved
  public vector licence text.
- `workspace_ui/InterVariable.woff2`: SIL Open Font Licence 1.1
  (`workspace_ui/INTER-LICENSE.txt`).
- `research/sources/`: reference snapshots of other projects, each under its
  own MIT or Apache-2.0 licence. They are not part of the software and will be
  removed once the research phase ends.

Runtime dependencies keep their own licences. No package binaries are bundled.

## Hosted relay

The hosted relay in [`relay/`](relay/), which connects people's assistants
across the internet, is a separate package under the GNU Affero General Public
License v3 (`AGPL-3.0-only`, see [relay/LICENSE](relay/LICENSE)). Everything
outside that folder stays Apache-2.0. Contributions are made
under the Developer Certificate of Origin (see [CONTRIBUTING](CONTRIBUTING.md)).
