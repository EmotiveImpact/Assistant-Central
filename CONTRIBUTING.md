# Contributing

Thank you for helping. Parlu lets people bring their own AI
assistants together to work across providers, while each person keeps control
of their information and decisions.

## Before you start

- Read the [README](README.md) and the [roadmap](ROADMAP.md).
- For anything larger than a small fix, open an issue or a draft pull request
  first so others can see what you are working on.
- Report security problems privately, as described in [SECURITY](SECURITY.md),
  never in a public issue.
- Use British English in documentation.

## Sign your work (DCO)

Every commit must be signed off under the
[Developer Certificate of Origin](https://developercertificate.org/). It
confirms you have the right to submit the change under the project's licence.
Add the sign-off with:

```sh
git commit -s
```

which appends a line like `Signed-off-by: Your Name <you@example.com>`. Use
your GitHub noreply address if you prefer not to publish your email.

## Running the checks

Python 3.12 and Node 24 match CI.

```sh
python -m venv .venv && .venv/bin/pip install -r pilot/requirements.txt
.venv/bin/python -B -m unittest discover -s pilot/tests
.venv/bin/python -B -m unittest discover -s conversation/tests
npm ci --prefix agent_bridge --ignore-scripts
npm --prefix agent_bridge test
```

The [delivery guide](docs/DELIVERY.md) lists the full set, including the
browser and container checks.

## Ground rules

- Owner approval must never be implied by a model, a lead assistant or a
  conversation. Keep exact owner decisions separate from synthetic test steps.
- Never enable a live provider, real account or deployment in a pull request
  without saying so plainly in its description.
- Do not commit secrets. Test values must be obviously fictional.

## Licence

By contributing, you agree your contribution is licensed under the licence of
the folder you change: Apache-2.0 for everything except `relay/`, and
AGPL-3.0-only for the relay service in `relay/` (its `client.py` and
`protocol.py` stay Apache-2.0). You keep the copyright in your contribution;
the DCO sign-off is all we ask.
