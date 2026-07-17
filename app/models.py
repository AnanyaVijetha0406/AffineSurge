from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    versions: Mapped[list["DocumentVersion"]] = relationship(back_populates="document")


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_number", name="uq_doc_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    source_filename: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped["Document"] = relationship(back_populates="versions")
    nodes: Mapped[list["Node"]] = relationship(back_populates="version")


class Node(Base):
    __tablename__ = "nodes"
    __table_args__ = (UniqueConstraint("version_id", "node_key", name="uq_version_node_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id"), index=True)
    node_key: Mapped[str] = mapped_column(String(256), index=True)  # stable logical key across versions
    heading: Mapped[str] = mapped_column(String(512))
    section_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    level: Mapped[int] = mapped_column(Integer)
    body_text: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("nodes.id"), nullable=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    node_type: Mapped[str] = mapped_column(String(32), default="section")  # section|table|list
    changed_from_previous: Mapped[bool] = mapped_column(Boolean, default=False)
    previous_node_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    version: Mapped["DocumentVersion"] = relationship(back_populates="nodes")
    parent: Mapped["Node | None"] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list["Node"]] = relationship(back_populates="parent")


class Selection(Base):
    __tablename__ = "selections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    items: Mapped[list["SelectionItem"]] = relationship(back_populates="selection", cascade="all, delete-orphan")


class SelectionItem(Base):
    __tablename__ = "selection_items"
    __table_args__ = (UniqueConstraint("selection_id", "node_id", name="uq_selection_node"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    selection_id: Mapped[int] = mapped_column(ForeignKey("selections.id"), index=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), index=True)
    # Snapshot of content at selection time (version-pinned)
    node_key: Mapped[str] = mapped_column(String(256))
    heading_snapshot: Mapped[str] = mapped_column(String(512))
    body_snapshot: Mapped[str] = mapped_column(Text)
    content_hash_snapshot: Mapped[str] = mapped_column(String(64))
    version_number: Mapped[int] = mapped_column(Integer)

    selection: Mapped["Selection"] = relationship(back_populates="items")
