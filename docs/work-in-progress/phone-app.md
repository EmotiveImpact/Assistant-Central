# Work notice: the Parlu phone app (Expo)

- Coordinating agent: Claude (project thread "Build the Expo phone app"), for Edem.
- Goal: an iOS and Android app built with Expo, in `phone_app/`, that follows the
  approved full app mock and the phone direction: Home as a short paragraph with one
  card at a time, Decide as a sheet, hold to agree for money and consent, the agreed
  receipt, Recents, Money, team missions, questions from your assistant, invite links
  with QR, and Settings.
- Boundaries: the desktop web app (`workspace_ui/`) stays as it is. The phone app
  reads the same owner API and reuses the pure projection modules from
  `workspace_ui/` and `pilot/web/model.mjs` rather than copying them. Customers never
  bring an AI key. No hosted resources, Expo account or app store account are created
  in this work.
- Claimed files: `phone_app/**`, `.github/workflows/phone-app.yml`, this notice, and a
  small opt-in phone address option in `workspace_ui/server.py` with its tests.
- Verification planned: TypeScript check, Jest tests for the API client and screens'
  logic, a web and Android bundle export in CI, and screenshots of the running app.
