"""Synthetic usage reservations. Mutations share the caller's claim/result transaction."""
from .mission import BASE_MICROUSD, OUTPUT_MICROUSD


def reserve(db, run, binding, quote):
    from .provider import ProviderDenied

    db.execute("""CREATE TABLE IF NOT EXISTS pilot_mission_usage(
        run_id TEXT PRIMARY KEY REFERENCES pilot_provider_runs(id),
        owner TEXT NOT NULL, provider TEXT NOT NULL, context TEXT NOT NULL, cap INTEGER NOT NULL,
        reserved INTEGER NOT NULL, actual INTEGER CHECK(actual BETWEEN 0 AND reserved))""")
    key = (run['owner'], binding['provider'], binding['context'])
    lowest, highest, used = db.execute("""SELECT MIN(cap), MAX(cap), COALESCE(SUM(COALESCE(actual,reserved)),0)
        FROM pilot_mission_usage WHERE owner=? AND provider=? AND context=?""", key).fetchone()
    limit, amount = quote['cap_microusd'], quote['reserve_microusd']
    if (lowest is not None and (lowest != limit or highest != limit)) or used + amount > limit:
        raise ProviderDenied('Mission usage limit reached or changed')
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
        raise ValueError('Original usage reservation unavailable')
    return {'simulated': True, 'cap_microusd': row[0], 'reserved_microusd': row[1],
            'actual_microusd': row[2], 'held_microusd': row[1] if row[2] is None else 0}
