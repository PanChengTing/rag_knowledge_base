from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Conversation, Message, MessageRole

class ConversationRepository:
    def __init__(self,session:AsyncSession)->None:
       self.session = session

    #创建一个新的对话
    async def create(self,title:str="新对话")->Conversation:
        conversation = Conversation(title=title)
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    #获取一个对话
    async def get(self,conversation_id:UUID)->Conversation|None:
        return await self.session.get(Conversation,conversation_id)

    async def list_message(self,conversation_id:UUID)->list[Message]:
        #按时间正序展示所有的消息，前端展示历史用
        stmt = (
            select(Message)
            .where(Message.coversation_id==conversation_id)
            .order_by(Message.created_at.asc(),Message.id.asc())
            #把这条消息对应的引用文一起加载起来
            .options(selectinload(Message.citations))
        )
        rows = list((await self.session.execute(stmt)).scalars().all())
        return rows

    async def recent_messages(self,conversation_id:UUID,limit:int)->list[Message]:
        """取最近的N条消息，按照时间正序返回"""
        if limit<= 0:
            return []
        stmt = (
            select(Message)
            .where(Message.coversation_id==conversation_id)
            .order_by(Message.created_at.desc(),Message.id.desc())
            .limit(limit)
        )
        rows = list((await self.session.execute(stmt)).scalars().all())
        return list(reversed(rows))

    #表里面增加一堆消息
    async def add_messages(self,messages:Sequence[Message])->None:
        if not messages:
            return
        self.session.add_all(messages)
        await self.session.flush()

    #对话ID，对话内容，合成一条Message数据库记录
    @staticmethod
    def make_user_message(conversation_id:UUID,content:str)->Message:
        return Message(coversation_id=conversation_id,role=MessageRole.USER,content=content)

    #对话ID,对话内容，额外附加，合成一条Assistant消息
    @staticmethod
    def make_assistant_message(
        conversation_id:UUID,
        content:str,
        *,
        extra_metadata:dict|None = None,
    )->Message:
        return Message(
            coversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content = content,
            extra_metadata= extra_metadata or {},
        )