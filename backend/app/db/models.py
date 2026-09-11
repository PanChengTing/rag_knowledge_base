from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4
from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func,Computed
from sqlalchemy.orm import Mapped,mapped_column,relationship
from sqlalchemy.dialects.postgresql import JSONB,UUID as PGUUID
from sqlalchemy.dialects.postgresql import TSVECTOR

from app.db.base import Base
from app.core.config import settings

class DocumentStatus(str,Enum):
    #文档声明周期管理

    UPLOADING = "uploading"
    PARASING = "parsing"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"


class Document(Base):
    __tablename__="documents"

    id:Mapped[UUID] = mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    name:Mapped[str] = mapped_column(String(512),nullable=False)

    file_hash:Mapped[str] = mapped_column(String(64),nullable=False,unique=True,index=True)
    mime_type:Mapped[str] = mapped_column(String(128),nullable=False)
    size:Mapped[int] = mapped_column(BigInteger,nullable=False)

    storage_provider:Mapped[str] = mapped_column(String(32),nullable=False,default="cos")
    cos_bucket:Mapped[str] = mapped_column(String(128),nullable=False)
    cos_object_key:Mapped[str] = mapped_column(String(512),nullable=False)
    cos_region:Mapped[str] = mapped_column(String(64),nullable=False)

    status:Mapped[DocumentStatus] = mapped_column(String(32),nullable=False,default=DocumentStatus.UPLOADING)
    error_message:Mapped[str|None] = mapped_column(Text,nullable=True)

    #server_default 没有时间的话，取创建时间
    created_at:Mapped[datetime] = mapped_column(
        DateTime(timezone=True),server_default=func.now(),nullable=False
    )
    #onupdate 每次更新，需要更新时间
    updated_at:Mapped[datetime] = mapped_column(
        DateTime(timezone=True),server_default=func.now(),nullable=False,onupdate=func.now()
    )
    chunks:Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document",
        cascade="all,delete-orphan",
        passive_deletes=True
    )

class DocumentChunk(Base):
    __tablename__= "document_chunks"
    id:Mapped[UUID] = mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    document_id:Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("documents.id",ondelete = "CASCADE"),
        nullable=False,
        index=True,
    )
    content:Mapped[str] = mapped_column(Text,nullable=False)
    embeding:Mapped[list[float]] = mapped_column(Vector(settings.embedding_dim),nullable=False)

    page_no:Mapped[int|None] = mapped_column(Integer,nullable=True)
    section_path:Mapped[str|None] = mapped_column(String(1024),nullable=True)
    chunk_index:Mapped[int] = mapped_column(Integer,nullable=False)
    chunk_hash:Mapped[str] = mapped_column(String(32),nullable=False,index=True)
    extra_metadata:Mapped[dict]= mapped_column(
        "metadata",JSONB,nullable=False,default=dict
    )
    #这是给每个chunk添加中文分词及索引
    content_tsv:Mapped[str] =mapped_column(
        TSVECTOR,
        Computed("to_tsvector('chinese_zh',content)",persisted=True),
        nullable=False
    )

    created_at:Mapped[datetime] = mapped_column(
        DateTime(timezone=True),server_default=func.now(),nullable=False
    )
    document:Mapped[Document] = relationship(back_populates="chunks")

class MessageRole(str,Enum):
    USER="user"
    ASSISTANT="assistant"
    SYSTEM="system"

class Conversation(Base):
    __tablename__="conversations"
    id:Mapped[UUID] = mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    title:Mapped[str] = mapped_column(String(256),nullable=False,default="新对话")
    created_at:Mapped[datetime] = mapped_column(
        DateTime(timezone=True),server_default=func.now(),nullable=False
    )
    #onupdate 每次更新，需要更新时间
    updated_at:Mapped[datetime] = mapped_column(
        DateTime(timezone=True),server_default=func.now(),nullable=False,onupdate=func.now()
    )
    messages:Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all,delete-orphan",
        passive_deletes=True,
        order_by="Message.created_at"
    )

class Message(Base):
    __tablename__="messages"
    id:Mapped[UUID] = mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    coversation_id:Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversations.id",ondelete = "CASCADE"),
        nullable=False,
        index=True,
    )
    role:Mapped[MessageRole] = mapped_column(String(16),nullable=False)
    content:Mapped[str] = mapped_column(Text,nullable=False)
    extra_metadata:Mapped[dict]=mapped_column("metadata",JSONB,nullable=False,default=dict)
    created_at:Mapped[datetime] = mapped_column(
        DateTime(timezone=True),server_default=func.now(),nullable=False
    )
    #back_populates表明这两个属性具有双向的关系，这里指向的是Conversation中的messages字段
    conversation:Mapped[Conversation]=relationship(back_populates="messages")
    citations:Mapped[list["AnswerCitation"]]= relationship(
        back_populates="message",
        cascade="all,delete-orphan",
        passive_deletes=True,
        order_by="AnswerCitation.ordinal"
    )

class AnswerCitation(Base):
    __tablename__="answer_citations"
    id:Mapped[UUID] = mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    message_id:Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("messages.id",ondelete = "CASCADE"),
        nullable=False,
        index=True,
    )
    ordinal:Mapped[int]=mapped_column(Integer,nullable=False)
    #原文档可以被删除
    document_id:Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("documents.id",ondelete = "SET NULL"),
        nullable=True
    )
    chunk_id:Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("document_chunks.id",ondelete = "SET NULL"),
        nullable=True
    )
    document_name:Mapped[str] = mapped_column(String(512),nullable=False)
    page_no:Mapped[int|None] = mapped_column(Integer,nullable=True)
    quote:Mapped[str]=mapped_column(Text,nullable=False)

    message:Mapped[Message] = relationship(back_populates="citations")
    #每个引用都应该有精确搜索和语义搜索的分数
    retrieval_meta:Mapped[dict|None] = mapped_column(JSONB,nullable=True)