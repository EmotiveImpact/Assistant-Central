"""Disposable fictional workspace, seeded through actual authenticated runtimes.

The password below is public fixture data. Never use it for a real owner. This
demo creates fresh temporary keys and stores and makes no external calls.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
import time

from pilot.auth import LocalOwnerAuth
from pilot.crypto import digest, fingerprint
from pilot.mission import mission_context, task_text
from pilot.runtime import PilotRuntime
from pilot import team
from pilot.workflow import FIXTURE_GRANT
from .server import WorkspaceHTTPServer

PASSWORD = "Fictional browser test password"


def seed_workspace(directory, story=False):
    """Return the local owner path after all fixture decisions have been saved.

    With story=True the public demo also gets missions with spending limits and a team mission,
    so Money and Team missions show what the approved design shows. Tests use the plain seed.
    """
    root = Path(directory)
    identities = (("blair", "Beacon"), ("alex", "Atlas"), ("casey", "Mira"), ("drew", "Orbit"))
    with ExitStack() as cleanup:
        accounts = []
        for owner, agent in identities:
            auth = LocalOwnerAuth(root / owner)
            cleanup.callback(auth.close)
            auth.bootstrap(owner, agent, PASSWORD)
            token = auth.login(PASSWORD)
            runtime = PilotRuntime(root / owner, auth)
            cleanup.callback(runtime.close)
            accounts.append((auth, token, runtime))
        local = accounts[0]
        for peer in accounts[1:]:
            local[2].enrol_peer(local[1], peer[0].public_identity(), fingerprint(peer[0].public_identity()))
            peer[2].enrol_peer(peer[1], local[0].public_identity(), fingerprint(local[0].public_identity()))

        counter = 0

        def propose(sender, recipient, title, *, decision=None, grant=False, release=True,
                    kind="task", parent=None, content=None, context=None):
            nonlocal counter
            counter += 1
            context = parent["context"] if parent else context or hashlib.sha256(title.encode()).hexdigest()
            task_id = parent["task_id"] if parent else "CENTRAL-" + str(100 + counter)
            expires = min(time.time() + 3300, parent["expires"]) if parent else time.time() + 3300
            item = sender[2].propose(sender[1], fingerprint(recipient[0].public_identity()), kind,
                title, content or ("SYNTHETIC ONLY\n\n" + title + ".\n\n"
                    "Prepare a concise first draft for the fictional Northstar studio launch. "
                    "Include the central idea, a proposed structure and the questions for owner review. "
                    "Use fictional material only. No publication or onward sharing is authorised."),
                context, task_id, expires, parent_id=parent["id"] if parent else None,
                provider_disclosure=FIXTURE_GRANT if grant else None)
            if release:
                sender[2].release(sender[1], item["id"], sender[2].review(sender[1], item["id"])["review_digest"])
                recipient[2].receive(recipient[1], sender[2].prepare_delivery(sender[1], "proposal-" + item["id"]))
            if decision:
                decided = recipient[2].decide(recipient[1], item["id"],
                    recipient[2].review(recipient[1], item["id"])["review_digest"], decision)
                sender[2].receive(sender[1], recipient[2].prepare_delivery(recipient[1], "decision-" + decided["decision_digest"]))
            return item

        propose(accounts[1], local, "Shape the launch narrative", grant=True)
        propose(accounts[2], local, "Review the research brief")
        propose(accounts[3], local, "Explore the visual direction")
        propose(accounts[2], local, "Map the onboarding journey", decision="accept", grant=True)
        propose(accounts[3], local, "Prepare the community welcome", decision="reject")
        propose(local, accounts[1], "Draft the launch announcement", release=False)
        propose(local, accounts[3], "Outline the first team session", release=False)
        task = propose(local, accounts[2], "Collect audience insights", decision="accept")
        propose(accounts[2], local, "Audience research brief", kind="artifact", parent=task,
            decision="accept", content="SYNTHETIC ONLY · FICTIONAL RESEARCH BRIEF\n\n"
            "Northstar studio / Audience exploration\n\n"
            "The opportunity\nA shared workspace helps a small creative team keep requests, "
            "decisions and original results together.\n\n"
            "Three questions to explore\n1. Which requests need the owner's attention?\n"
            "2. What does each assistant need before starting?\n"
            "3. How should the original result return for review?\n\n"
            "This is authored fictional fixture content. No research or model call was performed.")

        if story:
            # A team mission: one piece of work split across three people's assistants, led by yours.
            # Each part is an ordinary signed proposal carrying its own must and must-not rules.
            site = hashlib.sha256(b"parlu/demo-team/launch-website").hexdigest()
            def part(recipient, name, brief, must, must_not, pounds, **options):
                return propose(local, recipient, "Launch website: " + name, context=site,
                    content=team.part_text("SYNTHETIC ONLY. " + brief, must, must_not,
                                           {"cap_micro": pounds * 1_000_000, "currency": "GBP"}), **options)

            def result(sender, item, rules, summary, kept, used_pence, **options):
                checks = [{"rule": rule, "side": side, "kept": kept} for side in ("must", "must_not") for rule in rules[side]]
                text = team.RESULT + json.dumps({"summary": "SYNTHETIC ONLY. " + summary, "checks": checks,
                    "compute_used": {"micro": used_pence * 10_000, "currency": "GBP"}}, sort_keys=True, separators=(",", ":"))
                return propose(sender, local, item["title"] + " result", kind="artifact", parent=item, content=text, **options)

            booking = part(accounts[1], "Booking form", "Build the guest booking form.",
                ["Works with a screen reader"], ["No tracking scripts"], 10, decision="accept")
            deposits = part(accounts[2], "Card deposits", "Take refundable deposits in pounds.",
                ["Refundable in GBP"], ["Never store card numbers"], 15, decision="accept")
            part(accounts[3], "Calendar sync", "Add each booking to the host calendar.",
                ["Read-only calendar"], ["Guest names stay in the app"], 10)
            result(accounts[1], booking, {"must": ["Works with a screen reader"], "must_not": ["No tracking scripts"]}, "The booking form is built and tested.", True, 310, decision="accept")
            result(accounts[2], deposits, {"must": ["Refundable in GBP"], "must_not": ["Never store card numbers"]}, "Deposits work with a test card and refund in full.", True, 680)
            # Missions with a spending limit, so Money shows real budgets. The agreement digest is a
            # public fixture value: no payment is possible and nothing is spent.
            def mission(sender, recipient, title, pounds, brief, **options):
                limit, commitment = pounds * 1_000_000, digest(["parlu/demo-mission/1", title])
                return propose(sender, recipient, title, content=task_text(brief, limit, commitment, "GBP"),
                               context=mission_context(commitment, limit, "GBP"), **options)

            mission(local, accounts[1], "Book the launch party venue", 400,
                "SYNTHETIC ONLY. Find and hold a venue for 60 people on a Saturday evening in March.",
                decision="accept")
            mission(accounts[2], local, "Print the launch posters", 150,
                "SYNTHETIC ONLY. Print 200 A2 posters for the launch. Proofs come back before anything is paid.")

    return root / identities[0][0]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Disposable Central workspace with fictional data only")
    parser.add_argument("--port", type=int, default=8877)
    parser.add_argument("--story", action="store_true", help="Add the public demo story: missions with budgets and a team mission")
    args = parser.parse_args(argv)
    if args.port != 0 and not 1024 <= args.port <= 65535:
        parser.error("Choose a loopback port from 1024 to 65535, or 0 for an ephemeral port")
    with tempfile.TemporaryDirectory(prefix="central-workspace-fixture-") as directory:
        owner = seed_workspace(directory, story=args.story)
        server = WorkspaceHTTPServer(owner, args.port, synthetic_workflow=True)
        print(json.dumps({"url": server.origin, "synthetic_fixture": True,
                          "password": PASSWORD, "live_provider_enabled": False}), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
