"""add SQL email hash validation and history triggers

Revision ID: 132546352b3d
Revises: 1a9d0fc41de9
Create Date: 2026-10-07 16:26:38.345042

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '132546352b3d'
down_revision: Union[str, Sequence[str], None] = '1a9d0fc41de9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # Add the column nullable so existing users can be backfilled safely.
    op.add_column(
        "users",
        sa.Column("email_hash", sa.String(length=64), nullable=True),
    )
    op.execute(
        """
        UPDATE users
        SET email_hash = encode(digest(lower(btrim(email)), 'sha256'), 'hex')
        WHERE email_hash IS NULL
        """
    )
    op.alter_column("users", "email_hash", nullable=False)

    op.create_table('user_email_history',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('email_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_email_history_email_hash'), 'user_email_history', ['email_hash'], unique=False)
    op.create_index(op.f('ix_user_email_history_user_id'), 'user_email_history', ['user_id'], unique=False)
    op.create_index(op.f('ix_users_email_hash'), 'users', ['email_hash'], unique=False)
    op.create_index(
        "users_normalized_email_key",
        "users",
        [sa.text("lower(btrim(email))")],
        unique=True,
    )

    op.create_check_constraint(
        "users_email_hash_format_check",
        "users",
        "email_hash ~ '^[a-f0-9]{64}$'",
    )
    op.create_check_constraint(
        "user_email_history_email_hash_format_check",
        "user_email_history",
        "email_hash ~ '^[a-f0-9]{64}$'",
    )
    op.create_check_constraint(
        "users_email_hash_matches_email_check",
        "users",
        """
        email_hash = encode(digest(lower(btrim(email)), 'sha256'), 'hex')
        """,
    )

    op.execute(
        """
        CREATE FUNCTION sync_users_email_hash()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            expected_hash text;
        BEGIN
            expected_hash :=
                encode(digest(lower(btrim(NEW.email)), 'sha256'), 'hex');

            IF TG_OP = 'INSERT' AND NEW.email_hash IS NULL THEN
                NEW.email_hash := expected_hash;
            ELSIF TG_OP = 'INSERT' THEN
                RAISE EXCEPTION 'email_hash must not be supplied'
                    USING ERRCODE = '23514';
            ELSIF NEW.email_hash IS DISTINCT FROM OLD.email_hash THEN
                RAISE EXCEPTION 'email_hash must not be updated'
                    USING ERRCODE = '23514';
            ELSIF NEW.email IS DISTINCT FROM OLD.email THEN
                NEW.email_hash := expected_hash;
            END IF;

            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE FUNCTION record_users_email_history()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF lower(btrim(OLD.email)) <> lower(btrim(NEW.email)) THEN
                INSERT INTO user_email_history (id, user_id, email_hash)
                VALUES (
                    gen_random_uuid(),
                    OLD.id,
                    encode(digest(lower(btrim(OLD.email)), 'sha256'), 'hex')
                );
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER users_sync_email_hash
        BEFORE INSERT OR UPDATE OF email, email_hash ON users
        FOR EACH ROW
        EXECUTE FUNCTION sync_users_email_hash();
        """
    )
    op.execute(
        """
        CREATE TRIGGER users_record_email_history
        AFTER UPDATE OF email ON users
        FOR EACH ROW
        EXECUTE FUNCTION record_users_email_history();
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS users_record_email_history ON users")
    op.execute("DROP TRIGGER IF EXISTS users_sync_email_hash ON users")
    op.execute("DROP FUNCTION IF EXISTS record_users_email_history()")
    op.execute("DROP FUNCTION IF EXISTS sync_users_email_hash()")
    op.drop_constraint("users_email_hash_matches_email_check", "users", type_="check")
    op.drop_constraint("user_email_history_email_hash_format_check", "user_email_history", type_="check")
    op.drop_constraint("users_email_hash_format_check", "users", type_="check")
    op.drop_index("users_normalized_email_key", table_name="users")
    op.drop_index(op.f('ix_users_email_hash'), table_name='users')
    op.drop_column('users', 'email_hash')
    op.drop_index(op.f('ix_user_email_history_user_id'), table_name='user_email_history')
    op.drop_index(op.f('ix_user_email_history_email_hash'), table_name='user_email_history')
    op.drop_table('user_email_history')
