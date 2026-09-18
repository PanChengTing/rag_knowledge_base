from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import func

from app.db.models import Conversation, Message, MessageRole

DEFAULT_CONVERSATION_TITLE = "新对话"

class ConversationRepository:
    def __init__(self,session:AsyncSession)->None:
       self.session = session

    #创建一个新的对话
    async def create(self,title:str=DEFAULT_CONVERSATION_TITLE,*,user_id:UUID|None =None)->Conversation:
        conversation = Conversation(title=title,user_id=user_id)
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    #获取一个对话
    async def get(self,conversation_id:UUID,*,user_id:UUID|None =None)->Conversation|None:
        if user_id is None:
            return await self.session.get(Conversation,conversation_id)
        stmt = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id
        )
        return  (await self.session.execute(stmt)).scalar_one_or_none()

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

    #计算这个对话下有几条消息
    async def count_messages(self,conversation_id:UUID)->int:
        stmt = select(
            func.count(Message.id)
        ).where(
            Message.coversation_id==conversation_id
        )
        return int((await self.session.execute(stmt)).scalar_one())

    #侧边栏对话展示：Conversation相关信息，Conversation下面的消息总数，Conversation总数
    async def list_page(
            self,page:int,page_size:int,*,user_id:UUID|None =None,
    )->tuple[list[Conversation,int],int]:
        page = max(page,1)
        page_size = max(min(page_size,100),1)
        offset = (page-1)*page_size

        msg_count = func.count(Message.id).label("message_count")
        #选取一个Conversation以及Conversation下面的Message数量
        stmt = (
            select(Conversation,msg_count)
            .outerjoin(Message,Message.coversation_id == Conversation.id)
            .group_by(Conversation.id)
            .order_by(Conversation.updated_at.desc(),Conversation.id.desc())
            .limit(page_size)
            .offset(offset)
        )
        count_stmt = select(func.count(Conversation.id))
        if user_id is not None:
            stmt = stmt.where(Conversation.user_id == user_id)
            count_item = count_stmt.where(Conversation.user_id==user_id)
        rows =(await self.session.execute(stmt)).all()
        items = [(row[0],int(row[1])) for row in rows]
        total = int(
            (await self.session.execute(count_item)).scalar_one()
        )
        return items,total
    
    #删除对话
    async def delete(self,conversation_id:UUID,*,user_id:UUID|None =None)->bool:
        conversation = await self.get(conversation_id,user_id=user_id)
        if conversation is None:
            return False
        await self.session.delete(conversation)
        await self.session.flush()
        return True

    async def update_title_if_default(
            self,conversation_id:UUID,title:str
    )->None:
        new_title = title.strip()
        if not new_title:
            return
        conversation = await self.get(conversation_id)
        if conversation is None or conversation.title != DEFAULT_CONVERSATION_TITLE:
            return 
        conversation.title = new_title[:30]
        await self.session.flush()