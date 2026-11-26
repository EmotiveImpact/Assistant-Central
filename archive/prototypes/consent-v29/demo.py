"""Run `python demo.py` for manual consent or `python demo.py --simulate` for fixtures."""
import argparse
import json
import tempfile
import time
from pathlib import Path
from network import Agent, Broker, Denied, Meeting, Slot, context_digest
from durable import LocalDelivery
from session import PersistentSession
from review import render_review


def slot(start, end):
    return Slot(f"2026-11-06T{start}:00Z", f"2026-11-06T{end}:00Z")


def fixture():
    people = ("alice", "bob", "charlie", "dana")
    candidates = tuple(slot(f"{hour:02d}:00", f"{hour:02d}:30") for hour in range(13, 17))
    meeting = Meeting("friday-four", "alice", people, candidates)
    windows = ((slot("13:00", "17:00"),), (slot("14:00", "16:00"),),
               (slot("15:00", "17:00"),), (slot("14:30", "16:00"),))
    agents = tuple(Agent(person, free, time.monotonic) for person, free in zip(people, windows))
    return meeting, agents, Broker(agents, meeting)


class PauseDemo(Exception):
    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulate", action="store_true", help="Synthetic approvals only, no real users or accounts")
    parser.add_argument("--state-directory", help="Preserve fictional state in this directory")
    parser.add_argument("--resume", action="store_true", help="Resume the same persisted meeting without replaying completed steps")
    parser.add_argument("--stop-after", type=int, help="Pause after this many new messages to exercise recovery")
    parser.add_argument("--cancel-as", choices=("alice", "bob", "charlie", "dana"),
                        help="Stop an existing fictional meeting as this local participant; requires --resume")
    args = parser.parse_args()
    if args.resume and not args.state_directory:
        raise Denied("Resume requires a state directory")
    if args.cancel_as and not args.resume:
        raise Denied("Cancellation requires --resume and an existing state directory")
    if args.cancel_as and args.stop_after is not None:
        raise Denied("Cancellation cannot be combined with stop-after")
    if args.stop_after is not None and args.stop_after < 1:
        raise Denied("Stop-after must be positive")
    if args.stop_after is not None and not args.state_directory:
        raise Denied("Stop-after requires a state directory so the paused session can be resumed")
    meeting, agents, _ = fixture()
    print("LOCAL SIMULATION. Fictional people and calendars; no network or calendar writes.")
    print("SIMULATED APPROVALS, NOT HUMAN AUTHORIZATION." if args.simulate else
          "One local operator plays all four humans. Type the displayed consent phrase to continue.")
    print("Meeting:", meeting.id, "Participants:", ", ".join(meeting.participants))
    for i, candidate in enumerate(meeting.candidates):
        print(f"Candidate {i}: {candidate.start} – {candidate.end}")

    temp = tempfile.TemporaryDirectory() if args.state_directory is None else None
    state = Path(temp.name if temp else args.state_directory)
    state.mkdir(parents=True, exist_ok=True)
    db_path = state / "demo.sqlite3"
    if db_path.exists() and not args.resume:
        raise Denied("Existing state preserved. Use --resume or choose a fresh directory.")
    if args.resume and not db_path.exists():
        raise Denied("No session exists to resume")
    delivery = LocalDelivery(db_path)
    session = PersistentSession(delivery, agents, meeting)
    sent = 0

    def send(agent, message):
        nonlocal sent
        print("\n" + render_review(meeting, message))
        print("\nReview exact message:", json.dumps(message, indent=2))
        print("This shares only the data shown above with", message["recipient"])
        phrase = f"APPROVE {agent.identity} {message['type']} TO {message['recipient']}"
        if not args.simulate and input(f"Type '{phrase}' or anything else to deny: ") != phrase:
            raise PauseDemo("Denied. No message sent; workflow paused.")
        approval = delivery.owner_approve(message)
        session.submit(agent, message, approval)
        sent += 1
        if args.stop_after is not None and sent >= args.stop_after:
            raise PauseDemo(f"Paused after {sent} new messages. Committed state is preserved.")

    try:
        delivery.db.execute("CREATE TABLE IF NOT EXISTS demo_mode (session_id TEXT PRIMARY KEY, simulated INTEGER NOT NULL)")
        with delivery.transaction():
            if not args.resume:
                delivery.db.execute("INSERT INTO demo_mode VALUES (?,?)", (meeting.id, int(args.simulate)))
            prior = delivery.db.execute("SELECT simulated FROM demo_mode WHERE session_id=?", (meeting.id,)).fetchone()
            if prior is None or prior[0] != int(args.simulate):
                raise Denied("Approval provenance differs or is missing. Resume with the original --simulate/manual mode; simulated approval is never human approval.")
        if args.cancel_as:
            phrase = f"CANCEL {meeting.id} AS {args.cancel_as}"
            print("Cancellation stops this local workflow permanently and invalidates unused approvals.")
            print("It cannot recall shared information. No remote message or calendar cancellation is sent.")
            if not args.simulate and input(f"Type '{phrase}' or anything else to deny: ") != phrase:
                raise PauseDemo("Cancellation denied. Existing state is unchanged.")
            owner = next(agent for agent in agents if agent.identity == args.cancel_as)
            result = session.owner_cancel(owner)
            print("Meeting cancelled by", result["owner"], ". No messages sent.")
            return
        if session.view().cancellation:
            print("This session is cancelled. No messages replayed or sent. Create a new meeting to start again.")
            return
        if session.view().agreed:
            print("This session is already agreed. No messages replayed.")
            return
        for agent in agents:
            try:
                delivery._paired(agent.identity, "alice", context_digest(meeting))
                continue
            except Denied:
                pass
            for owner, peer in dict.fromkeys(((agent.identity, "alice"), ("alice", agent.identity))):
                phrase = f"PAIR {owner} WITH {peer} FOR {meeting.id}"
                if not args.simulate and input(f"Type '{phrase}' to approve this meeting-only contact: ") != phrase:
                    raise PauseDemo("Pairing denied. No availability sent.")
                delivery.owner_pair(owner, peer, context_digest(meeting))
        for agent in agents:
            if agent.identity not in session.view()._received:
                send(agent, agent.preview_availability(meeting))
        proposal = session.view().propose(agents[0])
        if proposal is None:
            print("No common candidate. No meeting scheduled.")
            return
        print("\nCoordinator's proposed slot:", proposal.start, "to", proposal.end)
        for agent in agents:
            broker = session.view()
            if agent.identity not in broker._offered:
                send(agents[0], broker.preview_proposal(agents[0], agent.identity))
            broker = session.view()
            if agent.identity not in broker._acceptances:
                send(agent, broker.preview_acceptance(agent))
        broker = session.view()
        print("\nAll four accepted:", broker.agreed)
        print("No calendar event created. Booking would require a separate approved action.")
        print("Audit events:", len(broker.audit))
    except PauseDemo as exc:
        print(str(exc))
    finally:
        delivery.close()
        if args.state_directory:
            print("Fictional inbox and consent records preserved at:", db_path)
        if temp:
            temp.cleanup()


if __name__ == "__main__":
    try:
        main()
    except (Denied, EOFError, KeyboardInterrupt) as exc:
        print("Stopped safely:", str(exc))
