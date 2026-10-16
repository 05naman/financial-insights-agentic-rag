from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChatMessage, ChatSession, Document, DocumentStatus, User


class DocumentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, document_id: int) -> Document | None:
        return await self.session.get(Document, document_id)

    async def get_by_company_year(self, ticker: str, fiscal_year: int) -> Document | None:
        result = await self.session.execute(
            select(Document).where(
                Document.ticker == ticker.upper(), Document.fiscal_year == fiscal_year
            )
        )
        return result.scalar_one_or_none()

    async def list(self) -> list[Document]:
        result = await self.session.execute(
            select(Document).order_by(Document.ticker, Document.fiscal_year)
        )
        return list(result.scalars())

    async def create(self, ticker: str, fiscal_year: int, filename: str) -> Document:
        doc = Document(ticker=ticker.upper(), fiscal_year=fiscal_year, filename=filename)
        self.session.add(doc)
        await self.session.commit()
        return doc

    async def set_status(
        self,
        doc: Document,
        status: DocumentStatus,
        *,
        page_count: int | None = None,
        chunk_count: int | None = None,
        error: str | None = None,
    ) -> Document:
        doc.status = status
        doc.error = error
        if page_count is not None:
            doc.page_count = page_count
        if chunk_count is not None:
            doc.chunk_count = chunk_count
        await self.session.commit()
        return doc

    async def fail_stale_processing(self) -> int:
        """Startup cleanup: rows stuck in pending/processing belong to a run that no longer exists."""
        result = await self.session.execute(
            update(Document)
            .where(Document.status.in_([DocumentStatus.pending, DocumentStatus.processing]))
            .values(
                status=DocumentStatus.failed, error="Interrupted by a restart. Upload it again."
            )
        )
        await self.session.commit()
        return result.rowcount or 0

    async def delete(self, doc: Document) -> None:
        await self.session.delete(doc)
        await self.session.commit()


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    async def create(self, email: str, hashed_password: str) -> User:
        user = User(email=email.lower(), hashed_password=hashed_password)
        self.session.add(user)
        await self.session.commit()
        return user


class ChatRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_session(self, user_id: int, title: str = "New chat") -> ChatSession:
        chat = ChatSession(user_id=user_id, title=title)
        self.session.add(chat)
        await self.session.commit()
        return chat

    async def get_session(self, session_id: int, user_id: int) -> ChatSession | None:
        chat = await self.session.get(ChatSession, session_id)
        return chat if chat and chat.user_id == user_id else None

    async def purge_empty_sessions(self, user_id: int, older_than: timedelta) -> int:
        """Delete the user's sessions that never received a message (abandoned requests)."""
        cutoff = datetime.now(UTC) - older_than
        has_messages = (
            select(ChatMessage.id).where(ChatMessage.session_id == ChatSession.id).exists()
        )
        result = await self.session.execute(
            delete(ChatSession).where(
                ChatSession.user_id == user_id, ChatSession.created_at < cutoff, ~has_messages
            )
        )
        await self.session.commit()
        return result.rowcount or 0

    async def list_sessions(self, user_id: int) -> list[ChatSession]:
        # sessions with no messages (an abandoned request) are not worth showing
        has_messages = (
            select(ChatMessage.id).where(ChatMessage.session_id == ChatSession.id).exists()
        )
        result = await self.session.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user_id, has_messages)
            .order_by(ChatSession.id.desc())
        )
        return list(result.scalars())

    async def delete_session(self, chat: ChatSession) -> None:
        await self.session.execute(delete(ChatMessage).where(ChatMessage.session_id == chat.id))
        await self.session.delete(chat)
        await self.session.commit()

    async def delete_message(self, message_id: int) -> None:
        """Roll back a question whose answer could not be produced, so history never has a dangling turn."""
        await self.session.execute(delete(ChatMessage).where(ChatMessage.id == message_id))
        await self.session.commit()

    async def messages(self, session_id: int) -> list[ChatMessage]:
        result = await self.session.execute(
            select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id)
        )
        return list(result.scalars())

    async def add_message(
        self, session_id: int, role: str, content: str, citations=None, steps=None
    ) -> ChatMessage:
        msg = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            citations=citations or [],
            steps=steps or [],
        )
        self.session.add(msg)
        await self.session.commit()
        return msg
