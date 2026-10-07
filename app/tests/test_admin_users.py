import uuid

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, or_, select
from src.db.models import User, UserEmailHistory
from src.utils.email import hash_email


def new_user(email: str) -> User:
    return User(email=email)


def find_user_by_any_email_hash(session: Session, target_hash: str) -> User | None:
    statement = (
        select(User)
        .outerjoin(UserEmailHistory, col(User.id) == col(UserEmailHistory.user_id))
        .where(
            or_(
                col(User.email_hash) == target_hash,
                col(UserEmailHistory.email_hash) == target_hash,
            )
        )
        .distinct()
    )
    return session.exec(statement).first()


class TestUserEmailHashSqlRules:
    def test_user_creation_populates_initial_email_hash(self, session: Session):
        email = "User.Test@Domain.COM"
        user = new_user(email)

        session.add(user)
        session.commit()
        session.refresh(user)

        expected_hash = hash_email(email)
        assert user.email_hash == expected_hash

        history = session.exec(
            select(UserEmailHistory)
            .where(UserEmailHistory.user_id == user.id)
            .order_by(col(UserEmailHistory.created_at), col(UserEmailHistory.id))
        ).all()
        assert len(history) == 0

    def test_email_update_logs_previous_hash_to_history(self, session: Session):
        initial_email = "old.address@domain.com"
        updated_email = "new.address@domain.com"

        user = new_user(initial_email)
        session.add(user)
        session.commit()
        session.refresh(user)

        initial_hash = user.email_hash

        user.email = updated_email
        session.add(user)
        session.commit()
        session.refresh(user)

        new_expected_hash = hash_email(updated_email)
        assert user.email_hash == new_expected_hash
        assert user.email_hash != initial_hash

        history = session.exec(
            select(UserEmailHistory).where(UserEmailHistory.user_id == user.id)
        ).all()
        assert len(history) == 1
        assert history[0].email_hash == initial_hash
        assert history[0].user_id == user.id

    def test_non_email_update_does_not_modify_hash_or_history(self, session: Session):
        user = new_user("static@domain.com")
        session.add(user)
        session.commit()
        session.refresh(user)

        current_hash = user.email_hash

        user.password_hash = "new_hashed_password"
        session.add(user)
        session.commit()
        session.refresh(user)

        assert user.email_hash == current_hash

        history = session.exec(
            select(UserEmailHistory).where(UserEmailHistory.user_id == user.id)
        ).all()
        assert len(history) == 0

    def test_normalized_equivalent_email_update_does_not_create_history(
        self, session: Session
    ):
        user = new_user("User@Domain.com")
        session.add(user)
        session.commit()
        session.refresh(user)

        current_hash = user.email_hash
        user.email = " user@domain.COM "
        session.commit()
        session.refresh(user)

        assert user.email_hash == current_hash
        history = session.exec(
            select(UserEmailHistory).where(UserEmailHistory.user_id == user.id)
        ).all()
        assert history == []

    def test_multiple_email_updates_accumulate_history(self, session: Session):
        emails = [
            "first@domain.com",
            "second@domain.com",
            "third@domain.com",
        ]

        user = new_user(emails[0])
        session.add(user)
        session.commit()
        session.refresh(user)

        first_hash = hash_email(emails[0])
        second_hash = hash_email(emails[1])
        third_hash = hash_email(emails[2])

        user.email = emails[1]
        session.add(user)
        session.commit()
        session.refresh(user)

        user.email = emails[2]
        session.add(user)
        session.commit()
        session.refresh(user)

        assert user.email_hash == third_hash

        history = session.exec(
            select(UserEmailHistory)
            .where(UserEmailHistory.user_id == user.id)
            .order_by(col(UserEmailHistory.created_at), col(UserEmailHistory.id))
        ).all()

        recorded_hashes = [record.email_hash for record in history]
        assert set(recorded_hashes) == {first_hash, second_hash}

    def test_reusing_an_old_email_records_each_change_event(
        self, session: Session
    ):
        user = new_user("first@domain.com")
        session.add(user)
        session.commit()
        session.refresh(user)

        user.email = "second@domain.com"
        session.commit()
        session.refresh(user)
        user.email = "first@domain.com"
        session.commit()
        session.refresh(user)
        user.email = "third@domain.com"
        session.commit()

        history = session.exec(
            select(UserEmailHistory)
            .where(UserEmailHistory.user_id == user.id)
            .order_by(col(UserEmailHistory.created_at), col(UserEmailHistory.id))
        ).all()
        assert [record.email_hash for record in history] == [
            hash_email("first@domain.com"),
            hash_email("second@domain.com"),
            hash_email("first@domain.com"),
        ]

    def test_incorrect_supplied_hash_is_rejected_on_insert(self, session: Session):
        user = User(
            email="actual@domain.com",
            email_hash=hash_email("incorrect@domain.com"),
        )
        session.add(user)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        assert session.get(User, user.id) is None

    @pytest.mark.parametrize(
        "supplied_hash",
        ["", "not-a-hash", "0" * 64, None],
        ids=["empty", "malformed", "valid-format-wrong-value", "explicit-null"],
    )
    def test_direct_hash_values_on_raw_insert_follow_database_policy(
        self, session: Session, supplied_hash: str | None
    ):
        statement = text(
            """
            INSERT INTO users (id, email, status, email_hash)
            VALUES (:id, :email, 'UNVERIFIED', :email_hash)
            """
        )
        parameters = {
            "id": uuid.uuid4(),
            "email": f"{uuid.uuid4()}@example.com",
            "email_hash": supplied_hash,
        }

        if supplied_hash is None:
            session.execute(statement, parameters)
            session.commit()
        else:
            with pytest.raises(IntegrityError):
                session.execute(statement, parameters)
                session.commit()
            session.rollback()

    def test_correct_supplied_hash_is_rejected_on_insert(self, session: Session):
        email = "correct-value@example.com"
        session.add(User(email=email, email_hash=hash_email(email)))

        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_direct_hash_update_is_rejected(self, session: Session):
        user = new_user("direct-update@example.com")
        session.add(user)
        session.commit()

        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    """
                    UPDATE users
                    SET email_hash = :email_hash
                    WHERE id = :user_id
                    """
                ),
                {
                    "email_hash": hash_email("wrong@example.com"),
                    "user_id": user.id,
                },
            )
            session.commit()
        session.rollback()

        stored_hash = session.execute(
            text("SELECT email_hash FROM users WHERE id = :user_id"),
            {"user_id": user.id},
        ).one()[0]
        assert stored_hash == hash_email("direct-update@example.com")

    def test_bulk_direct_hash_update_is_rejected_atomically(
        self, session: Session
    ):
        users = [new_user("raw-one@example.com"), new_user("raw-two@example.com")]
        session.add_all(users)
        session.commit()

        with pytest.raises(IntegrityError):
            session.execute(
                text("UPDATE users SET email_hash = :email_hash"),
                {"email_hash": hash_email("wrong@example.com")},
            )
            session.commit()
        session.rollback()

        hashes = session.execute(
            text(
                """
                SELECT email_hash
                FROM users
                WHERE id IN (:first_id, :second_id)
                ORDER BY id
                """
            ),
            {"first_id": users[0].id, "second_id": users[1].id},
        ).all()
        assert {row[0] for row in hashes} == {
            hash_email("raw-one@example.com"),
            hash_email("raw-two@example.com"),
        }

    def test_email_and_direct_hash_update_is_rejected(self, session: Session):
        user = new_user("combined-before@example.com")
        session.add(user)
        session.commit()

        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    """
                    UPDATE users
                    SET email = :email, email_hash = :email_hash
                    WHERE id = :user_id
                    """
                ),
                {
                    "email": "combined-after@example.com",
                    "email_hash": hash_email("combined-after@example.com"),
                    "user_id": user.id,
                },
            )
            session.commit()
        session.rollback()

        stored = session.execute(
            text("SELECT email, email_hash FROM users WHERE id = :user_id"),
            {"user_id": user.id},
        ).one()
        assert stored.email == "combined-before@example.com"
        assert stored.email_hash == hash_email("combined-before@example.com")

    def test_tampered_hash_is_rejected_on_non_email_update(self, session: Session):
        user = new_user("actual@domain.com")
        session.add(user)
        session.commit()

        user.email_hash = hash_email("incorrect@domain.com")
        user.password_hash = "new_hashed_password"
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.refresh(user)

        assert user.email_hash == hash_email("actual@domain.com")
        assert user.password_hash is None

    def test_bulk_email_update_updates_hash_and_history(self, session: Session):
        users = [
            new_user("bulk-one@domain.com"),
            new_user("bulk-two@domain.com"),
        ]
        session.add_all(users)
        session.commit()
        session.refresh(users[0])
        session.refresh(users[1])

        old_hashes = {user.id: user.email_hash for user in users}
        session.exec(
            update(User).values(
                email=User.email + ".updated",
            )
        )
        session.commit()

        updated_users = session.exec(select(User)).all()
        assert {user.email_hash for user in updated_users} == {
            hash_email("bulk-one@domain.com.updated"),
            hash_email("bulk-two@domain.com.updated"),
        }
        history = session.exec(select(UserEmailHistory)).all()
        assert {record.email_hash for record in history} == set(old_hashes.values())

    def test_normalized_email_must_be_unique(self, session: Session):
        session.add(new_user("Unique@Domain.com"))
        session.commit()

        session.add(new_user(" unique@domain.COM "))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_normalized_email_uniqueness_applies_to_bulk_update(
        self, session: Session
    ):
        first = new_user("bulk-first@example.com")
        second = new_user("bulk-second@example.com")
        session.add_all([first, second])
        session.commit()

        with pytest.raises(IntegrityError):
            session.exec(
                update(User)
                .where(col(User.id) == second.id)
                .values(email=" BULK-FIRST@EXAMPLE.COM ")
            )
            session.commit()
        session.rollback()

        stored = session.get(User, second.id)
        assert stored is not None
        assert stored.email == "bulk-second@example.com"
        assert stored.email_hash == hash_email("bulk-second@example.com")

    def test_schema_defines_expected_email_integrity_objects(
        self, session: Session
    ):
        columns = session.execute(
            text(
                """
                SELECT column_name, is_nullable, character_maximum_length
                FROM information_schema.columns
                WHERE table_name IN ('users', 'user_email_history')
                  AND column_name = 'email_hash'
                ORDER BY table_name
                """
            )
        ).all()
        assert [(row[0], row[1], row[2]) for row in columns] == [
            ("email_hash", "NO", 64),
            ("email_hash", "NO", 64),
        ]

        indexes = session.execute(
            text(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE indexname IN (
                    'users_normalized_email_key',
                    'ix_users_email_hash',
                    'ix_user_email_history_email_hash'
                )
                ORDER BY indexname
                """
            )
        ).all()
        index_names = {row[0] for row in indexes}
        assert index_names == {
            "users_normalized_email_key",
            "ix_users_email_hash",
            "ix_user_email_history_email_hash",
        }
        normalized_index = next(
            row[1] for row in indexes if row[0] == "users_normalized_email_key"
        )
        assert "UNIQUE INDEX" in normalized_index
        assert "lower(btrim((email)::text))" in normalized_index


class TestUserEmailHashResolution:
    def test_query_by_current_email_hash(self, session: Session):
        user = new_user("current@example.com")
        session.add(user)
        session.commit()
        session.refresh(user)

        assert user.email_hash is not None
        found_user = find_user_by_any_email_hash(session, user.email_hash)
        assert found_user is not None
        assert found_user.id == user.id

    def test_query_by_historical_email_hash(self, session: Session):
        user = new_user("original@example.com")
        session.add(user)
        session.commit()
        session.refresh(user)

        original_hash = user.email_hash
        assert original_hash is not None

        user.email = "updated@example.com"
        session.add(user)
        session.commit()
        session.refresh(user)

        found_user = find_user_by_any_email_hash(session, original_hash)
        assert found_user is not None
        assert found_user.id == user.id

    def test_query_by_unrelated_hash_returns_none(self, session: Session):
        user = new_user("active@example.com")
        session.add(user)
        session.commit()

        random_hash = hash_email("nonexistent@example.com")
        found_user = find_user_by_any_email_hash(session, random_hash)
        assert found_user is None