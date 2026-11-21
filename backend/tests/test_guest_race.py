"""Two first-time guests arriving together must both get the shared guest account, never a 500."""
import auth
from models import User


def test_concurrent_guest_creation_reuses_the_winner(app):
    from database import SessionLocal

    first, second = SessionLocal(), SessionLocal()
    try:
        first.query(User).filter(User.email == auth.DEMO_EMAIL).delete()
        first.commit()

        # Both requests looked before either created the account.
        original_query = second.query
        calls = {"n": 0}

        def stale_first_lookup(*args, **kwargs):
            query = original_query(*args, **kwargs)
            calls["n"] += 1
            if calls["n"] == 1:
                class _Empty:
                    def filter(self, *a, **k):
                        return self

                    def first(self):
                        return None
                return _Empty()
            return query

        winner = auth._get_or_create_demo_user(first)
        second.query = stale_first_lookup
        loser = auth._get_or_create_demo_user(second)

        assert loser.id == winner.id
        assert loser.email == auth.DEMO_EMAIL
    finally:
        first.close()
        second.close()
