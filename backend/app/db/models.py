from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4
from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Table, Text, func,Computed
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

class IngestionTaskType(str,Enum):
    INGEST = "ingest"
    REINDEX = "reindex"

class IngestionTaskStatus(str,Enum):
    PENDING="pending",
    RUNNING="running",
    SUCCESS="success",
    FAILED="failed"
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

    #空数组视为公开
    #非空数组与用户有效权限标签做重叠匹配
    permission_tags:Mapped[list[str]] = mapped_column(
        ARRAY(String()),nullable=False,default=list,server_default="{}"
    )

    created_by:Mapped[UUID|None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id",ondelete="SET NULL"),
        nullable=True,
    )
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
    version:Mapped[int] = mapped_column(Integer,nullable=False,default=1,server_default="1")
    ingestion_tasks:Mapped[list["IngestionTask"]] = relationship(
        back_populates="document",
        cascade="all,delete-orphan",
        passive_deletes=True,
        order_by="IngestionTask.created_at.desc()"
    )

class IngestionTask(Base):
    __tablename__="ingestion_tasks"
    id:Mapped[UUID] = mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    document_id:Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("documents.id",ondelete = "CASCADE"),
        nullable=False,
        index=True,
    )
    task_type:Mapped[IngestionTaskType] = mapped_column(String(16),nullable=False)
    status:Mapped[IngestionTaskStatus] = mapped_column(
        String(16),nullable=False,default=IngestionTaskStatus.PENDING
    )
    retry_count:Mapped[int] = mapped_column(Integer,nullable=False,default=0)
    error_message:Mapped[str|None] = mapped_column(Text,nullable=True)

    progress_total:Mapped[int] = mapped_column(Integer,nullable=False,default=0)
    progress_done:Mapped[int] = mapped_column(Integer,nullable=False,default=0)

    started_at:Mapped[datetime|None]=mapped_column(
        DateTime(timezone=True),nullable=True
    )
    finish_at:Mapped[datetime|None]=mapped_column(
        DateTime(timezone=True),nullable=True
    )
    created_at:Mapped[datetime] = mapped_column(
        DateTime(timezone=True),server_default=func.now(),nullable=False
    )
    document:Mapped[Document]=relationship(back_populates="ingestion_tasks")


class DocumentChunk(Base):
    __tablename__= "document_chunks"
    __table_args__=(
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding":"vector_cosine_ops"}
        ),
        Index(
            "ix_document_chunks_content_tsv",
            "content_tsv",
            postgresql_using="gin"
        ),
    )
    id:Mapped[UUID] = mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    document_id:Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("documents.id",ondelete = "CASCADE"),
        nullable=False,
        index=True,
    )
    content:Mapped[str] = mapped_column(Text,nullable=False)
    embedding:Mapped[list[float]] = mapped_column(Vector(settings.embedding_dim),nullable=False)

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
    user_id:Mapped[UUID|None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id",ondelete="SET NULL"),
        nullable=True,
        index=True,
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

#评测与BadCase分析
class EvaluationRunStatus(str,Enum):
    RUNNING="running"
    COMPLETED="completed"
    FAILED ="failed"

class EvaluationRun(Base):
    __tablename__="evaluation_runs"
    id:Mapped[UUID] = mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    name:Mapped[str] = mapped_column(String(256),nullable=False)
    #评测集的名称和大小
    dataset_name:Mapped[str] = mapped_column(String(128),nullable=False)
    dataset_size:Mapped[int] = mapped_column(Integer,nullable=False)
    status:Mapped[EvaluationRunStatus] = mapped_column(String(16),nullable=False)

    #完成和失败的评测个数
    progress_total:Mapped[int] = mapped_column(Integer,nullable=False,default=0)
    progress_completed:Mapped[int] = mapped_column(Integer,nullable=False,default=0)
    progress_failed:Mapped[int] = mapped_column(Integer,nullable=False,default=0)

    #一系列评估整个链路的指标
    faithfulness:Mapped[float|None] = mapped_column(Float,nullable=True)
    answer_relevancy:Mapped[float|None] = mapped_column(Float,nullable=True)
    context_precision:Mapped[float|None] = mapped_column(Float,nullable=True)
    context_recall:Mapped[float|None] = mapped_column(Float,nullable=True)
    citation_hit_rate:Mapped[float|None] = mapped_column(Float,nullable=True)
    refusal_accuracy:Mapped[float|None] = mapped_column(Float,nullable=True)
    avg_latency_ms:Mapped[float|None] = mapped_column(Float,nullable=True)
    #首token延迟
    avg_first_token_latency_ms:Mapped[float|None] = mapped_column(Float,nullable=True)

    error_message:Mapped[str|None]=mapped_column(Text,nullable=True)
    started_at:Mapped[datetime|None]=mapped_column(
        DateTime(timezone=True),nullable=True
    )
    finish_at:Mapped[datetime|None]=mapped_column(
        DateTime(timezone=True),nullable=True
    )
    created_at:Mapped[datetime] = mapped_column(
        DateTime(timezone=True),server_default=func.now(),nullable=False
    )

    items:Mapped[list["EvaluationItem"]]=relationship(
        back_populates="run",
        cascade="all,delete-orphan",
        passive_deletes=True
    )

#每条评测的信息
class EvaluationItem(Base):
    __tablename__="evaluation_items"
    id:Mapped[UUID] = mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    run_id:Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("evaluation_runs.id",ondelete = "CASCADE"),
        nullable=False,
        index=True,
    )
    case_id:Mapped[str] = mapped_column(String(64),nullable=False)
    question:Mapped[str] = mapped_column(Text,nullable=False)
    #期望答案,评测集中写好的标准答案
    expected_answer:Mapped[str] = mapped_column(Text,nullable=False)
    expected_document_names:Mapped[list] = mapped_column(JSONB,nullable=False,default=list)
    expected_keywords:Mapped[list]=mapped_column(JSONB,nullable=False,default=list)
    should_refuse:Mapped[bool]=mapped_column(Boolean,nullable=False)
    tags:Mapped[list]=mapped_column(JSONB,nullable=False,default=list)

    #模型生成的答案
    actual_answer:Mapped[str] = mapped_column(Text,nullable=False,default="")
    actual_refused:Mapped[bool] = mapped_column(Boolean,nullable=False,default=False)
    citations:Mapped[list]=mapped_column(JSONB,nullable=False,default=list)
    retrieved_chunks_meta:Mapped[list]=mapped_column(JSONB,nullable=False,default=list)
    #检索的过程
    query_route:Mapped[dict|None]=mapped_column(JSONB,nullable=True)
    agent_steps:Mapped[dict|None]=mapped_column(JSONB,nullable=True)
    verify_result:Mapped[dict|None]=mapped_column(JSONB,nullable=True)
    trace_id:Mapped[str|None]=mapped_column(String(64),nullable=True)
    latency_ms:Mapped[int]=mapped_column(Integer,nullable=False,default=0)
    first_token_latency_ms:Mapped[int|None]=mapped_column(Integer,nullable=True)
    error_message:Mapped[str|None]=mapped_column(Text,nullable=True)

    faithfulness:Mapped[float|None] = mapped_column(Float,nullable=True)
    answer_relevancy:Mapped[float|None] = mapped_column(Float,nullable=True)
    context_precision:Mapped[float|None] = mapped_column(Float,nullable=True)
    context_recall:Mapped[float|None] = mapped_column(Float,nullable=True)
    citation_hit:Mapped[bool|None]=mapped_column(Boolean,nullable=True)
    refusal_correct:Mapped[bool]=mapped_column(Boolean,nullable=False)

    is_bad_case:Mapped[bool]=mapped_column(Boolean,nullable=False,default=False)
    bad_case_category:Mapped[str|None]=mapped_column(String(64),nullable=True)
    bad_case_note:Mapped[str|None]=mapped_column(Text,nullable=True)

    created_at:Mapped[datetime] = mapped_column(
        DateTime(timezone=True),server_default=func.now(),nullable=False
    )

    run:Mapped[EvaluationRun] = relationship(back_populates="items")

class UserStatus(str,Enum):
    ACTIVE ="active"
    DISABLED="disabled"

#用于表示用户和角色的多对多关系
#任何一个ID在另一表删除，都会导致整个表也删光对应的ID
user_roles_table =Table(
    "user_roles",
    Base.metadata,
    Column(
        "user_id",
        PGUUID(as_uuid=True),
        ForeignKey("users.id",ondelete="CASCADE"),
        primary_key =True,
    ),
    Column(
        "role_id",
        PGUUID(as_uuid=True),
        ForeignKey("roles.id",ondelete="CASCADE"),
        primary_key =True,
    ),
)

class User(Base):
    __tablename__="users"
    id:Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    username:Mapped[str]=mapped_column(String(64),nullable=False,unique=True)
    password_hash:Mapped[str] = mapped_column(String(255),nullable=False)
    display_name:Mapped[str] = mapped_column(String(128),nullable=False)
    status:Mapped[UserStatus]=mapped_column(
        String(16),nullable=False,default=UserStatus.ACTIVE
    )
    #server_default 没有时间的话，取创建时间
    created_at:Mapped[datetime] = mapped_column(
        DateTime(timezone=True),server_default=func.now(),nullable=False
    )
    #onupdate 每次更新，需要更新时间
    updated_at:Mapped[datetime] = mapped_column(
        DateTime(timezone=True),server_default=func.now(),nullable=False,onupdate=func.now()
    )
    #用户拥有的角色列表，通过中间表user_roles_table建立多对多的关系
    #selecin表示加载一批用户时，也会同时取回这些用户的角色
    roles:Mapped[list["Role"]] = relationship(
        secondary=user_roles_table,
        back_populates="users",
        lazy="selectin"
    )

class Role(Base):
    __tablename__="roles"
    id:Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    name:Mapped[str]=mapped_column(String(64),nullable=False,unique=True)
    description:Mapped[str]=mapped_column(String(256),nullable=False,default="")
    permission_tags:Mapped[list[str]] = mapped_column(
        ARRAY(String()),nullable=False,default=list,server_default="{}"
    )
    created_at:Mapped[datetime] = mapped_column(
        DateTime(timezone=True),server_default=func.now(),nullable=False
    )
    users:Mapped[list["User"]] = relationship(
        secondary=user_roles_table,
        back_populates="roles",
    )


