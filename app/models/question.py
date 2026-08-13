import math
from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    author: Mapped["User"] = relationship(foreign_keys="Question.author_id")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    answer_count: Mapped[int] = mapped_column(Integer, server_default="0")
    view_count: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 此方法为python方法，算出所有的热度之后进行排序，排序完成之后在进行切分，浪费资源。更新成数据库方法，用多少查多少
    # def hot_score(self):
    #     hot = math.log2(self.view_count + 1) + self.answer_count * 10
    #     return hot