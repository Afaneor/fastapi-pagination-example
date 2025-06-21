from tortoise import fields
from tortoise import models


class SampleModel(models.Model):
    # Автоинкрементный первичный ключ (нужен для cursor-based пагинации)
    id = fields.IntField(pk=True)

    # Основное поле
    name = fields.TextField()

    # Временные метки (нужны для time-based пагинации)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        # Индексы для оптимизации пагинации
        indexes = [
            # Составные индексы для keyset пагинации
            ("name", "id"),
            ("created_at", "id"),
        ]
