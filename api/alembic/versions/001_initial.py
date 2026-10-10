"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, TSVECTOR

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector if available, otherwise fallback
    conn = op.get_bind()
    has_vector = False
    try:
        res = conn.execute(sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")).scalar()
        if res:
            op.execute("CREATE EXTENSION IF NOT EXISTS vector")
            has_vector = True
    except Exception:
        pass

    try:
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    except Exception:
        pass

    # -- Users --
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- Collections --
    op.create_table(
        "collections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "name", name="uq_collection_user_name"),
    )

    # -- Bookmarks --
    op.create_table(
        "bookmarks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("canonical_url", sa.Text, nullable=False),
        sa.Column("title", sa.Text),
        sa.Column("description", sa.Text),
        sa.Column("content_text", sa.Text),
        sa.Column("summary", sa.Text),
        sa.Column("key_takeaways", JSONB),
        sa.Column("notes", sa.Text),
        sa.Column(
            "status",
            sa.Enum("pending", "processing", "completed", "failed", name="bookmark_status"),
            server_default="pending",
        ),
        sa.Column("error_message", sa.Text),
        sa.Column("content_hash", sa.String(64)),
        sa.Column(
            "collection_id", UUID(as_uuid=True),
            sa.ForeignKey("collections.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("archived", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", "canonical_url", name="uq_bookmark_user_url"),
    )
    op.create_index("ix_bookmark_user_created", "bookmarks", ["user_id", "created_at"])

    # -- Tags --
    op.create_table(
        "tags",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
    )
    # Functional unique index on (user_id, lower(name))
    op.execute(
        "CREATE UNIQUE INDEX uq_tag_user_name ON tags (user_id, lower(name))"
    )

    # -- Bookmark Tags --
    op.create_table(
        "bookmark_tags",
        sa.Column(
            "bookmark_id", UUID(as_uuid=True),
            sa.ForeignKey("bookmarks.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column(
            "tag_id", UUID(as_uuid=True),
            sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column(
            "source",
            sa.Enum("ai", "user", name="tag_source"),
            nullable=False,
        ),
    )

    # -- Content Chunks --
    op.create_table(
        "content_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "bookmark_id", UUID(as_uuid=True),
            sa.ForeignKey("bookmarks.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "user_id", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("chunk_text", sa.Text, nullable=False),
        sa.Column("tsv", TSVECTOR),
        sa.Column("model_name", sa.String(100)),
    )
    # Add vector or float[] column
    if has_vector:
        op.execute("ALTER TABLE content_chunks ADD COLUMN embedding vector(1536)")
        op.execute(
            "CREATE INDEX ix_chunks_embedding ON content_chunks "
            "USING hnsw (embedding vector_cosine_ops)"
        )
    else:
        op.execute("ALTER TABLE content_chunks ADD COLUMN embedding float[]")
    # Auto-update tsvector from chunk_text
    op.execute("""
        CREATE OR REPLACE FUNCTION chunks_tsv_trigger() RETURNS trigger AS $$
        BEGIN
            NEW.tsv := to_tsvector('english', NEW.chunk_text);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_chunks_tsv
        BEFORE INSERT OR UPDATE OF chunk_text ON content_chunks
        FOR EACH ROW EXECUTE FUNCTION chunks_tsv_trigger();
    """)

    # -- Jobs --
    op.create_table(
        "jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "bookmark_id", UUID(as_uuid=True),
            sa.ForeignKey("bookmarks.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "user_id", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("queued", "running", "completed", "failed", name="job_status"),
            server_default="queued",
        ),
        sa.Column("stage", sa.String(50)),
        sa.Column("attempt_count", sa.Integer, server_default="0"),
        sa.Column("error_message", sa.Text),
        sa.Column("run_after", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_jobs_status_run_after", "jobs", ["status", "run_after"])

    # -- AI Usage --
    op.create_table(
        "ai_usage",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id", UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("stage", sa.String(50), nullable=False),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("input_tokens", sa.Integer, server_default="0"),
        sa.Column("output_tokens", sa.Integer, server_default="0"),
        sa.Column("duration_ms", sa.Integer, server_default="0"),
        sa.Column("error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("ai_usage")
    op.drop_table("jobs")
    op.execute("DROP TRIGGER IF EXISTS trg_chunks_tsv ON content_chunks")
    op.execute("DROP FUNCTION IF EXISTS chunks_tsv_trigger()")
    op.drop_table("content_chunks")
    op.drop_table("bookmark_tags")
    op.drop_table("tags")
    op.drop_table("bookmarks")
    op.drop_table("collections")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS bookmark_status")
    op.execute("DROP TYPE IF EXISTS job_status")
    op.execute("DROP TYPE IF EXISTS tag_source")
