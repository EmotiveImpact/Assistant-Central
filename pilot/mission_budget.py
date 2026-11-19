"""Synthetic usage accounting in the provider's existing claim/result transactions."""
from .mission import BASE_MICROUSD, OUTPUT_MICROUSD


def balance(db, owner, provider, context, limit):
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pilot_mission_usage'").fetchone()
    spent, held = 0, 0
    if exists:
        row = db.execute("""SELECT MIN(cap), MAX(cap), COALESCE(SUM(actual),0),
            COALESCE(SUM(CASE WHEN actual IS NULL THEN reserved ELSE 0 END),0)
            FROM pilot_mission_usage WHERE owner=? AND provider=? AND context=?""", (owner, provider, context)).fetchone()
        if row[0] is not None and (row[0] != limit or row[1] != limit):
            raise ValueError('Mission budget commitment mismatch')
        spent, held = row[2:]
    return {'cap_microusd': limit, 'spent_microusd': spent, 'held_microusd': held,
            'available_microusd': limit - spent - held, 'simulated': True}


def reserve(db, run, binding, quote):
    from .provider import ProviderDenied

    db.execute("""CREATE TABLE IF NOT EXISTS pilot_mission_usage(
        run_id TEXT PRIMARY KEY REFERENCES pilot_provider_runs(id),
        owner TEXT NOT NULL, provider TEXT NOT NULL, context TEXT NOT NULL, cap INTEGER NOT NULL,
        reserved INTEGER NOT NULL, actual INTEGER CHECK(actual BETWEEN 0 AND reserved))""")
    key = (run['owner'], binding['provider'], binding['context'])
    limit, amount = quote['cap_microusd'], quote['reserve_microusd']
    if balance(db, *key, limit)['available_microusd'] < amount:
        raise ProviderDenied('Mission usage limit reached')
    db.execute('INSERT INTO pilot_mission_usage VALUES(?,?,?,?,?,?,NULL)', (run['id'], *key, limit, amount))


def settle(db, run_id, output_tokens):
    actual = BASE_MICROUSD + OUTPUT_MICROUSD * output_tokens
    result = db.execute('UPDATE pilot_mission_usage SET actual=? WHERE run_id=? AND actual IS NULL',
                        (actual, run_id))
    if result.rowcount != 1:
        raise ValueError('Original usage reservation unavailable')


def receipt(db, run_id):
    row = db.execute('SELECT cap,reserved,actual FROM pilot_mission_usage WHERE run_id=?', (run_id,)).fetchone()
    if row is None:
        return None
    return {'simulated': True, 'cap_microusd': row[0], 'reserved_microusd': row[1],
            'actual_microusd': row[2], 'held_microusd': row[1] if row[2] is None else 0}
