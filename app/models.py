from datetime import datetime, timezone
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
class Base(DeclarativeBase): pass
def now(): return datetime.now(timezone.utc)
class DocumentVersion(Base):
    __tablename__='document_versions'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    document_key: Mapped[str]=mapped_column(String(200),index=True)
    version: Mapped[str]=mapped_column(String(80))
    source_name: Mapped[str]=mapped_column(String(500))
    source_sha256: Mapped[str]=mapped_column(String(64))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    nodes: Mapped[list['DocumentNode']]=relationship(back_populates='document',cascade='all, delete-orphan')
    __table_args__=(UniqueConstraint('document_key','version'),)
class DocumentNode(Base):
    __tablename__='document_nodes'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    logical_id: Mapped[str]=mapped_column(String(64),index=True)
    document_version_id: Mapped[int]=mapped_column(ForeignKey('document_versions.id'),index=True)
    parent_id: Mapped[int|None]=mapped_column(ForeignKey('document_nodes.id'),nullable=True,index=True)
    ordinal: Mapped[int]=mapped_column(Integer)
    heading: Mapped[str]=mapped_column(Text)
    level: Mapped[int]=mapped_column(Integer)
    body: Mapped[str]=mapped_column(Text,default='')
    content_hash: Mapped[str]=mapped_column(String(64),index=True)
    changed: Mapped[bool]=mapped_column(default=False)
    change_kind: Mapped[str|None]=mapped_column(String(30),nullable=True)
    document: Mapped[DocumentVersion]=relationship(back_populates='nodes')
    parent: Mapped['DocumentNode|None']=relationship(remote_side='DocumentNode.id',back_populates='children')
    children: Mapped[list['DocumentNode']]=relationship(back_populates='parent',order_by='DocumentNode.ordinal')
    tables: Mapped[list['DocumentTable']]=relationship(back_populates='node',order_by='DocumentTable.page_number',cascade='all, delete-orphan')
class DocumentTable(Base):
    __tablename__='document_tables'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    document_version_id: Mapped[int]=mapped_column(ForeignKey('document_versions.id'),index=True)
    node_id: Mapped[int|None]=mapped_column(ForeignKey('document_nodes.id'),nullable=True,index=True)
    page_number: Mapped[int]=mapped_column(Integer)
    heading_context: Mapped[str|None]=mapped_column(Text,nullable=True)
    caption: Mapped[str|None]=mapped_column(Text,nullable=True)
    bbox_json: Mapped[str]=mapped_column(Text)
    cells_json: Mapped[str]=mapped_column(Text)
    content_hash: Mapped[str]=mapped_column(String(64),index=True)
    node: Mapped[DocumentNode|None]=relationship(back_populates='tables')
class Selection(Base):
    __tablename__='selections'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    name: Mapped[str]=mapped_column(String(250))
    document_key: Mapped[str]=mapped_column(String(200),index=True)
    document_version_id: Mapped[int]=mapped_column(ForeignKey('document_versions.id'))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    items: Mapped[list['SelectionItem']]=relationship(cascade='all, delete-orphan')
class SelectionItem(Base):
    __tablename__='selection_items'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    selection_id: Mapped[int]=mapped_column(ForeignKey('selections.id'),index=True)
    node_id: Mapped[int]=mapped_column(ForeignKey('document_nodes.id'))
    node_logical_id: Mapped[str]=mapped_column(String(64),index=True)
    content_hash: Mapped[str]=mapped_column(String(64))
    heading_snapshot: Mapped[str]=mapped_column(Text)
    text_snapshot: Mapped[str]=mapped_column(Text)
