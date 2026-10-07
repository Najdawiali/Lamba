"""In-memory stand-in for the refresh token store (see app/services/refresh_tokens.py).

Used by test_refresh_tokens.py and by the end-to-end harness. It has no locking: it only checks the
rules, not what the database adds. The SQL store is checked in test_refresh_token_store_pg.py.
"""

from types import SimpleNamespace


class InMemoryRefreshStore:
    def __init__(self, rows=None):
        self.rows = rows if rows is not None else []

    async def add(self, **fields):
        row = SimpleNamespace(used_at=None, replaced_by_id=None, revoked_at=None, revoked_reason=None, **fields)
        self.rows.append(row)
        return row

    async def get_for_update(self, token_hash):
        return next((r for r in self.rows if r.token_hash == token_hash), None)

    async def get_by_id_for_update(self, row_id):
        return next((r for r in self.rows if r.id == row_id), None)

    async def revoke_family(self, family_id, reason, now):
        for r in self.rows:
            if r.family_id == family_id and r.revoked_at is None:
                r.revoked_at, r.revoked_reason = now, reason

    async def revoke_user(self, user_id, reason, now):
        hit = [r for r in self.rows if r.user_id == user_id and r.revoked_at is None]
        for r in hit:
            r.revoked_at, r.revoked_reason = now, reason
        return len(hit)

    async def prune_family(self, family_id, now):
        self.rows[:] = [r for r in self.rows
                        if not (r.family_id == family_id and (r.expires_at <= now or r.family_expires_at <= now))]

    async def prune_user(self, user_id, now):
        self.rows[:] = [r for r in self.rows
                        if not (r.user_id == user_id and (r.expires_at <= now or r.family_expires_at <= now))]
