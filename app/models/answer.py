from datetime import datetime

from sqlalchemy import String, Text, Integer, Boolean, DateTime, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    like_count: Mapped[int] = mapped_column(Integer, server_default="0")
    is_accepted: Mapped[bool] = mapped_column(Boolean, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
