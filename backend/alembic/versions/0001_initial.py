"""initial schema: users, documents, chunks (pgvector), conversations, messages

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-24
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 768


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    uuid_pk = lambda: sa.Column(  # noqa: E731
        "id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    ts_now = lambda name: sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)  # noqa: E731

    op.create_table(
        "users",
        uuid_pk(),
        sa.Column("email", sa.Text, nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("full_name", sa.Text),
        ts_now("created_at"),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "documents",
        uuid_pk(),
        sa.Column("owner_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_filename", sa.Text, nullable=False),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("vehicle_model", sa.Text, nullable=False),
        sa.Column("model_year", sa.Text),
        sa.Column("storage_path", sa.Text, nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("sha256", sa.Text),
        sa.Column("page_count", sa.Integer),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.Text, nullable=False, server_default="pending_upload"),
        sa.Column("status_detail", sa.Text),
        ts_now("uploaded_at"),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status in ('pending_upload','queued','processing','ready','failed')", name="documents_status_check"
        ),
    )
    op.create_index("documents_owner_sha_idx", "documents", ["owner_id", "sha256"])
    op.create_index("documents_status_idx", "documents", ["status"])

    op.create_table(
        "chunks",
        uuid_pk(),
        sa.Column(
            "document_id", pg.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("vehicle_model", sa.Text, nullable=False),
        sa.Column("page_number", sa.Integer, nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("section", sa.Text),
        sa.Column("variants", pg.ARRAY(sa.Text)),
        sa.Column("content_type", sa.Text, nullable=False, server_default="text"),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("tsv", pg.TSVECTOR, sa.Computed("to_tsvector('english', content)", persisted=True)),
        sa.CheckConstraint("content_type in ('text','table','ocr')", name="chunks_content_type_check"),
    )
    op.execute("CREATE INDEX chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)")
    op.execute("CREATE INDEX chunks_tsv_gin ON chunks USING gin (tsv)")
    op.create_index("chunks_model_idx", "chunks", ["vehicle_model"])
    op.create_index("chunks_doc_idx", "chunks", ["document_id"])

    op.create_table(
        "conversations",
        uuid_pk(),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text, nullable=False, server_default="New chat"),
        ts_now("created_at"),
        ts_now("updated_at"),
    )
    op.create_index("conversations_user_idx", "conversations", ["user_id", "updated_at"])

    op.create_table(
        "messages",
        uuid_pk(),
        sa.Column(
            "conversation_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("sources", pg.JSONB),
        sa.Column("intent", sa.Text),
        ts_now("created_at"),
        sa.CheckConstraint("role in ('user','assistant')", name="messages_role_check"),
    )
    op.create_index("messages_conv_idx", "messages", ["conversation_id", "created_at"])


def downgrade() -> None:
    for t in ("messages", "conversations", "chunks", "documents", "users"):
        op.drop_table(t)
