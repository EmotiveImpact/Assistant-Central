# Third-party notices

Open Agent Bridge's original code is copyright © 2026 Mun Boon and licensed under Apache-2.0. This does not replace the licenses or copyright notices of third-party components.

## Manrope font

`src/components/fonts/Manrope.ttf` is copyright 2018 The Manrope Project Authors, licensed under SIL Open Font License 1.1. The full notice is retained in [OFL.txt](src/components/fonts/OFL.txt). The bundled font matches the [Manrope distribution in Google Fonts](https://github.com/google/fonts/tree/main/ofl/manrope). The original upstream URL in the retained copyright notice is no longer available.

## Dependencies

Dependencies are installed separately using `pnpm-lock.yaml`; `node_modules` and runtime binaries are not included in this source repository. [The dependency inventory](docs/dependency-licenses.json) records package names, installed versions, license identifiers, authors and upstream links from the Linux installation reviewed for this release. It is metadata, not a replacement for upstream license texts. Optional packages on other platforms may differ.

The inventory includes MIT, ISC, BSD-3-Clause, 0BSD, Apache-2.0, MPL-2.0, LGPL-3.0-or-later and CC-BY-4.0 material. In particular:

- Manrope retains its separate OFL notice as above.
- `caniuse-lite` data is licensed CC-BY-4.0. Credit Ben Briggs and the upstream [caniuse-lite project](https://github.com/browserslist/caniuse-lite). This project does not modify that installed dataset.
- `lightningcss` and its platform binary use MPL-2.0. Preserve their notices and applicable source availability when redistributing them.
- Sharp's prebuilt libvips package uses LGPL-3.0-or-later and bundles additional libraries. Its upstream package contains component license and version information. Binary/container distributors must review those bundled notices and meet applicable source and replacement requirements.
- Apache-2.0 packages retain any upstream NOTICE files and license text.

Before publishing a binary, container or vendored dependency bundle, collect the licenses and corresponding source required for that actual bundle. This release preparation covers the source repository, not a prebuilt binary distribution.

To refresh the installed metadata, run `pnpm licenses list --json`. Do not publish that raw output: it contains local installation paths. The checked-in inventory omits local paths.

## Project artwork

The bridge illustrations and icon atlas in `public/art/titanium` were generated with an image-generation tool. Their prompt/provenance files are stored alongside them. The project includes these assets under Apache-2.0 to the extent the project holds rights in them. No claim of exclusive copyright in purely generated output is made. The Open Agent Bridge SVG is project branding. Reference screenshots are not included in this source repository.
