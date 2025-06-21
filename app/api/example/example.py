import base64
import json
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import APIRouter, Query, HTTPException
from tortoise.expressions import Q

from db.models.sample_model import SampleModel
from app.models.pagination import PaginatedResponse, CursorResponse, HybridResponse
from models.sample_model import SampleResponse

example_router = APIRouter()


def encode_cursor(data: Dict[str, Any]) -> str:
    """Кодируем данные в безопасный base64 курсор"""
    json_str = json.dumps(data, default=str)
    return base64.b64encode(json_str.encode()).decode()


def decode_cursor(cursor: str) -> Dict[str, Any]:
    """Декодируем курсор обратно в данные"""
    try:
        json_str = base64.b64decode(cursor.encode()).decode()
        return json.loads(json_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid cursor format")


# ============================================================================
# 1. OFFSET-BASED PAGINATION
# ============================================================================


@example_router.get("/samples/offset")
async def get_samples_offset(
    page: int = Query(1, ge=1, description="Номер страницы"),
    size: int = Query(10, ge=1, le=100, description="Размер страницы"),
):
    """
    Классическая offset-based пагинация

    Плюсы:
    ✅ Простота реализации
    ✅ Понятность для пользователей
    ✅ Можно перейти на любую страницу

    Минусы:
    ❌ Медленно на больших offset'ах
    ❌ Проблемы консистентности при изменении данных
    ❌ Дублирование/пропуск записей при обновлениях
    """

    offset = (page - 1) * size

    # Получаем данные с offset
    samples = await SampleModel.all().offset(offset).limit(size)

    # Считаем общее количество (дорогая операция!)
    total = await SampleModel.all().count()

    return {
        "data": [SampleResponse.model_validate(sample) for sample in samples],
        "page": page,
        "size": size,
        "total": total,
        "pages": (total + size - 1) // size,
        "has_next": page * size < total,
        "has_prev": page > 1,
    }


# ============================================================================
# 2. PAGE-BASED PAGINATION
# ============================================================================


@example_router.get("/samples/page", response_model=PaginatedResponse[SampleResponse])
async def get_samples_page(
    page: int = Query(1, ge=1, description="Номер страницы"),
    per_page: int = Query(10, ge=1, le=100, description="Записей на странице"),
):
    """
    Page-based пагинация с улучшенным ответом

    Плюсы:
    ✅ Понятный интерфейс для UI
    ✅ Легко делать навигацию (1, 2, 3... страницы)
    ✅ Структурированный ответ

    Минусы:
    ❌ Те же проблемы производительности что у offset
    ❌ Дорогой count() на каждый запрос
    """

    offset = (page - 1) * per_page
    samples = await SampleModel.all().offset(offset).limit(per_page)
    total = await SampleModel.all().count()
    total_pages = (total + per_page - 1) // per_page

    return PaginatedResponse[SampleResponse](
        data=[SampleResponse.model_validate(sample) for sample in samples],
        current_page=page,
        per_page=per_page,
        total_items=total,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )


# ============================================================================
# 3. CURSOR-BASED PAGINATION
# ============================================================================


@example_router.get("/samples/cursor", response_model=CursorResponse[SampleResponse])
async def get_samples_cursor(
    cursor: Optional[str] = Query(None, description="Курсор для следующей страницы"),
    size: int = Query(10, ge=1, le=100, description="Количество записей"),
):
    """
    Cursor-based пагинация по ID

    Плюсы:
    ✅ Высокая производительность на любом размере данных
    ✅ Консистентность данных (нет дублей/пропусков)
    ✅ Масштабируется до миллиардов записей

    Минусы:
    ❌ Нельзя перейти на произвольную страницу
    ❌ Сложнее реализация
    ❌ Курсор привязан к определенному порядку сортировки
    """

    query = SampleModel.all().order_by("id")

    # Если есть курсор - фильтруем по нему
    if cursor:
        cursor_data = decode_cursor(cursor)
        last_id = cursor_data["last_id"]
        query = query.filter(id__gt=last_id)

    samples = await query.limit(size)

    # Создаем курсор для следующей страницы
    next_cursor = None
    if samples:
        next_cursor = encode_cursor(
            {"last_id": samples[-1].id, "timestamp": datetime.now().isoformat()}
        )

    return CursorResponse[SampleResponse](
        data=[SampleResponse.model_validate(sample) for sample in samples],
        next_cursor=next_cursor,
        size=size,
    )


# ============================================================================
# 4. TIME-BASED CURSOR PAGINATION
# ============================================================================


@example_router.get(
    "/samples/time-cursor", response_model=CursorResponse[SampleResponse]
)
async def get_samples_time_cursor(
    cursor: Optional[str] = Query(None, description="Временной курсор"),
    size: int = Query(10, ge=1, le=100, description="Количество записей"),
):
    """
    Time-based cursor пагинация

    Плюсы:
    ✅ Идеально для временных данных (ленты, логи)
    ✅ Естественная сортировка по времени
    ✅ Высокая производительность
    ✅ Подходит для real-time обновлений

    Минусы:
    ❌ Ограничен сортировкой по времени
    ❌ Нужно учитывать коллизии по времени
    """

    # Сортируем по времени создания (новые сверху)
    query = SampleModel.all().order_by("-created_at", "-id")

    if cursor:
        cursor_data = decode_cursor(cursor)
        cursor_time = datetime.fromisoformat(cursor_data["created_at"])
        cursor_id = cursor_data["id"]

        # Учитываем случаи с одинаковым временем через ID
        query = query.filter(
            Q(created_at__lt=cursor_time) | Q(created_at=cursor_time, id__lt=cursor_id)
        )

    samples = await query.limit(size)

    next_cursor = None
    if samples:
        last_sample = samples[-1]
        next_cursor = encode_cursor(
            {"created_at": last_sample.created_at.isoformat(), "id": last_sample.id}
        )

    return CursorResponse[SampleResponse](
        data=[SampleResponse.model_validate(sample) for sample in samples],
        next_cursor=next_cursor,
        size=size,
    )


# ============================================================================
# 5. KEYSET PAGINATION
# ============================================================================


@example_router.get("/samples/keyset", response_model=CursorResponse[SampleResponse])
async def get_samples_keyset(
    cursor: Optional[str] = Query(None, description="Keyset курсор"),
    size: int = Query(10, ge=1, le=100, description="Количество записей"),
    sort_by: str = Query(
        "name", regex="^(name|created_at)$", description="Поле сортировки"
    ),
):
    """
    Keyset пагинация с произвольной сортировкой

    Плюсы:
    ✅ Произвольная сортировка с высокой производительностью
    ✅ Консистентность данных
    ✅ Масштабируется на больших данных

    Минусы:
    ❌ Сложность реализации
    ❌ Нужны составные индексы для каждого поля сортировки
    ❌ Не подходит для multi-column сортировки

    ВАЖНО: Создайте индексы: (name, id), (created_at, id)
    """

    # Определяем направление сортировки и поле
    order_fields = [sort_by, "id"]
    query = SampleModel.all().order_by(*order_fields)

    if cursor:
        cursor_data = decode_cursor(cursor)
        last_value = cursor_data["last_value"]
        last_id = cursor_data["last_id"]
        sort_field = cursor_data.get("sort_by", sort_by)

        # Проверяем что сортировка не изменилась
        if sort_field != sort_by:
            raise HTTPException(
                status_code=400, detail="Cannot change sort field mid-pagination"
            )

        # Создаем составное условие для keyset пагинации
        if sort_by == "name":
            query = query.filter(
                Q(name__gt=last_value) | Q(name=last_value, id__gt=last_id)
            )
        elif sort_by == "created_at":
            query = query.filter(
                Q(created_at__gt=last_value) | Q(created_at=last_value, id__gt=last_id)
            )

    samples = await query.limit(size)

    next_cursor = None
    if samples:
        last_sample = samples[-1]
        next_cursor = encode_cursor(
            {
                "last_value": getattr(last_sample, sort_by),
                "last_id": last_sample.id,
                "sort_by": sort_by,
            }
        )

    return CursorResponse[SampleResponse](
        data=[SampleResponse.model_validate(sample) for sample in samples],
        next_cursor=next_cursor,
        size=size,
    )


# ============================================================================
# 6. HYBRID PAGINATION
# ============================================================================

# Конфигурация для hybrid пагинации
OFFSET_THRESHOLD = 1000  # После 1000 записей переключаемся на cursor


@example_router.get("/samples/hybrid", response_model=HybridResponse[SampleResponse])
async def get_samples_hybrid(
    page: Optional[int] = Query(
        None, ge=1, description="Номер страницы (для небольших offset)"
    ),
    cursor: Optional[str] = Query(None, description="Курсор (для больших данных)"),
    size: int = Query(10, ge=1, le=100, description="Размер страницы"),
):
    """
    Hybrid пагинация - лучшее из двух миров

    Логика:
    - Для небольших страниц (< 1000 записей) используем offset
    - Для больших данных используем cursor
    - Автоматически переключаемся между режимами

    Плюсы:
    ✅ Оптимальная производительность для всех случаев
    ✅ Удобный UX (номера страниц + бесконечная прокрутка)
    ✅ Гибкость в использовании

    Минусы:
    ❌ Сложная логика
    ❌ Больше кода для поддержки
    """

    # Если передан cursor - используем cursor-based режим
    if cursor:
        cursor_result = await get_samples_cursor(cursor, size)
        return HybridResponse[SampleResponse](
            data=cursor_result.data,
            size=size,
            next_cursor=cursor_result.next_cursor,
            pagination_type="cursor",
        )

    # Если передана страница и она в пределах threshold
    if page and (page - 1) * size < OFFSET_THRESHOLD:
        offset = (page - 1) * size
        samples = await SampleModel.all().offset(offset).limit(size)
        total = await SampleModel.all().count()

        # Проверяем, нужно ли переключиться на cursor для следующей страницы
        next_cursor = None
        if page * size >= OFFSET_THRESHOLD and samples:
            next_cursor = encode_cursor({"last_id": samples[-1].id})

        return HybridResponse[SampleResponse](
            data=[SampleResponse.model_validate(sample) for sample in samples],
            page=page,
            size=size,
            total=total,
            next_cursor=next_cursor,
            pagination_type="offset",
        )

    # Для больших страниц - принудительно используем cursor
    elif page and page * size >= OFFSET_THRESHOLD:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Use cursor-based pagination for large datasets",
                "suggestion": "Start with page=1 or use cursor parameter",
                "threshold": f"Switch to cursor after {OFFSET_THRESHOLD} records",
            },
        )

    # Если ничего не передано - возвращаем первую страницу
    else:
        samples = await SampleModel.all().limit(size)
        total = await SampleModel.all().count()

        return HybridResponse[SampleResponse](
            data=[SampleResponse.model_validate(sample) for sample in samples],
            page=1,
            size=size,
            total=total,
            pagination_type="offset",
        )


# ============================================================================
# УТИЛИТЫ ДЛЯ ТЕСТИРОВАНИЯ
# ============================================================================


@example_router.post("/test/generate-samples/{count}")
async def generate_test_samples(count: int):
    """Генерация тестовых образцов для демонстрации"""

    from faker import Faker

    fake = Faker()

    samples = []
    for i in range(count):
        samples.append(
            SampleModel(name=f"{fake.word()}_{i}_{fake.random_int(1000, 9999)}")
        )

    created_samples = await SampleModel.bulk_create(samples)
    return {"message": f"Created {len(created_samples)} samples"}


@example_router.delete("/test/clear-samples")
async def clear_all_samples():
    """Очистка всех образцов"""
    deleted_count = await SampleModel.all().delete()
    return {"message": f"Deleted {deleted_count} samples"}


@example_router.get("/test/performance/{pagination_type}")
async def test_pagination_performance(
    pagination_type: str,
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
):
    """Тестирование производительности разных типов пагинации"""
    import time

    start_time = time.time()

    if pagination_type == "offset":
        result = await get_samples_offset(page, size)
    elif pagination_type == "cursor":
        # Для cursor нужен предварительный запрос
        if page > 1:
            # Симуляция получения курсора
            offset_samples = (
                await SampleModel.all().offset((page - 1) * size - 1).limit(1)
            )
            if offset_samples:
                cursor = encode_cursor({"last_id": offset_samples[0].id})
                result = await get_samples_cursor(cursor, size)
            else:
                result = await get_samples_cursor(None, size)
        else:
            result = await get_samples_cursor(None, size)
    elif pagination_type == "page":
        result = await get_samples_page(page, size)
    elif pagination_type == "time-cursor":
        if page > 1:
            # Симуляция получения временного курсора
            offset_samples = (
                await SampleModel.all().offset((page - 1) * size - 1).limit(1)
            )
            if offset_samples:
                cursor = encode_cursor(
                    {
                        "created_at": offset_samples[0].created_at.isoformat(),
                        "id": offset_samples[0].id,
                    }
                )
                result = await get_samples_time_cursor(cursor, size)
            else:
                result = await get_samples_time_cursor(None, size)
        else:
            result = await get_samples_time_cursor(None, size)
    elif pagination_type == "keyset":
        if page > 1:
            # Симуляция получения keyset курсора
            offset_samples = (
                await SampleModel.all().offset((page - 1) * size - 1).limit(1)
            )
            if offset_samples:
                cursor = encode_cursor(
                    {
                        "last_value": offset_samples[0].name,
                        "last_id": offset_samples[0].id,
                        "sort_by": "name",
                    }
                )
                result = await get_samples_keyset(cursor, size, "name")
            else:
                result = await get_samples_keyset(None, size, "name")
        else:
            result = await get_samples_keyset(None, size, "name")
    elif pagination_type == "hybrid":
        result = await get_samples_hybrid(page, None, size)
    else:
        raise HTTPException(status_code=400, detail="Invalid pagination type")

    end_time = time.time()
    execution_time = end_time - start_time

    return {
        "pagination_type": pagination_type,
        "page": page,
        "size": size,
        "execution_time_ms": round(execution_time * 1000, 2),
        "data_count": len(result["data"] if "data" in result else result.data),
    }
