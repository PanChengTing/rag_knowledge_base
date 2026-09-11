"""add hybird retrieval support

Revision ID: aa3432276741
Revises: b6a9b091b71e
Create Date: 2026-09-11 19:59:49.025513

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'aa3432276741'
down_revision: Union[str, Sequence[str], None] = 'b6a9b091b71e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS zhparser")
    op.execute("CREATE TEXT SEARCH CONFIGURATION chinese_zh (PARSER = zhparser)")
    #自定义文本搜索配置 chinese_zh
    #n=名词 v=动词 a=形容词 i=习用词 e=叹词 l=习惯用词
    #只把这6类词语用来建立索引
    op.execute(
        "ALTER TEXT SEARCH CONFIGURATION chinese_zh "
        "ADD MAPPING FOR n,v,a,i,e,l WITH simple"
    )
    #给document——chunks表格新增一列content_tsv
    #并且设置为永远由数据库自己根据content计算 而不应该用代码插入
    op.execute(
        "ALTER TABLE document_chunks "
        "ADD COLUMN content_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('chinese_zh',content)) STORED"
    )
    #建立gin索引
    op.execute(
        "CREATE INDEX ix_document_chunks_content_tsv "
        "ON document_chunks USING GIN(content_tsv)"
    )
    #给answer_citations加上一列retrieval_meta，主要是为了存储各种搜索的分数
    #不用列存是因为后续还会加上新的字段，而且这个字段也参与SQL的查询
    op.add_column(
        "answer_citations",
        sa.Column("retrieval_meta",postgresql.JSONB(),nullable=True)
    )
    pass


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("answer_citations","retrieval_meta")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_content_tsv")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS content_tsv")
    op.execute("DROP TEXT SEARCH CONFIGURATION IF EXISTS chinese_zh")
    op.execute("DROP EXTENTION IF EXISTS zhparser")
    pass
