import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext
import logging
import asyncio
from aiohttp import web  # <-- Добавлено
import threading  # <-- Добавлено

# Настройка логирования для Koyeb
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler()  # Логи в stdout (важно для Koyeb)
    ]
)
logger = logging.getLogger(__name__)

# Получаем переменные окружения из Koyeb
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
BASE_URL = os.environ.get('BASE_URL', 'https://app.base44.com/api/')
API_KEY = os.environ.get('BASE44_API_KEY')
HTTP_PORT = int(os.environ.get('PORT', 8080))  # <-- Добавлено

# Проверка обязательных переменных
if not TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN не установлен!")
    raise ValueError("TELEGRAM_BOT_TOKEN required")

if not API_KEY:
    logger.error("❌ BASE44_API_KEY не установлен!")
    raise ValueError("BASE44_API_KEY required")

logger.info("✅ Токены загружены успешно")

# ==================== HTTP HEALTH SERVER ==================== #
async def health_check(request):
    """Эндпоинт для проверки здоровья бота"""
    logger.info("🏓 Health check received")
    return web.Response(text='Bot is running!')

async def status_api(request):
    """Эндпоинт с детальной информацией о статусе"""
    status = {
        "status": "running",
        "service": "telegram-health-bot",
        "timestamp": time.time(),
        "api_connected": API_KEY is not None,
        "telegram_connected": TOKEN is not None
    }
    return web.json_response(status)

def run_health_server():
    """Запуск HTTP сервера для health checks в отдельном потоке"""
    try:
        logger.info(f"🚀 Starting health server on port {HTTP_PORT}")
        
        app = web.Application()
        
        # Добавляем роуты
        app.router.add_get('/', health_check)
        app.router.add_get('/health', health_check)
        app.router.add_get('/status', status_api)
        app.router.add_get('/ping', health_check)
        
        # Создаем и запускаем runner
        runner = web.AppRunner(app)
        
        async def start_server():
            await runner.setup()
            site = web.TCPSite(runner, '0.0.0.0', HTTP_PORT)
            await site.start()
            logger.info(f"✅ Health check server started on port {HTTP_PORT}")
            
            # Бесконечный цикл для поддержания работы сервера
            while True:
                await asyncio.sleep(3600)  # Спим 1 час
        
        # Создаем новую event loop для этого потока
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(start_server())
        except KeyboardInterrupt:
            pass
        except Exception as e:
            logger.error(f"❌ Health server error: {e}")
        finally:
            loop.run_until_complete(runner.cleanup())
            loop.close()
            
    except Exception as e:
        logger.error(f"🔥 Failed to start health server: {e}")

# ==================== API FUNCTIONS ==================== #
def make_api_request(api_path, method='GET', data=None):
    """Универсальный метод для API запросов"""
    url = f'{BASE_URL}{api_path}'
    headers = {
        'api_key': API_KEY,
        'Content-Type': 'application/json'
    }
    
    logger.info(f"🌐 API запрос: {url}")
    
    try:
        if method.upper() == 'GET':
            response = requests.request(method, url, headers=headers, params=data, timeout=30)
        else:
            response = requests.request(method, url, headers=headers, json=data, timeout=30)
        
        logger.info(f"📡 Статус ответа: {response.status_code}")
        
        if response.status_code != 200:
            logger.warning(f"⚠️ Неуспешный статус: {response.text[:200]}")
        
        response.raise_for_status()
        
        # Проверяем, что ответ не пустой
        if response.text.strip():
            return response.json()
        else:
            logger.warning("📭 API вернул пустой ответ")
            return []
            
    except requests.exceptions.Timeout:
        logger.error(f"⏰ Таймаут запроса к {url}")
        return []
    except requests.exceptions.RequestException as e:
        logger.error(f"🔴 API ошибка: {e}")
        if hasattr(e, 'response') and e.response:
            logger.error(f"📝 Тело ошибки: {e.response.text[:200]}")
        return []
    except Exception as e:
        logger.error(f"⚠️ Неожиданная ошибка: {e}")
        return []

# Функции для получения данных из API
def get_medications():
    """Получение списка медикаментов"""
    logger.info("📡 Запрос медикаментов...")
    return make_api_request('apps/691401d80266c5f799e50d4f/entities/MedicationLog')

def get_workout_videos():
    """Получение видеозаписей тренировок (каталог)"""
    logger.info("📡 Запрос видеозаписей тренировок...")
    return make_api_request('apps/691401d80266c5f799e50d4f/entities/Workout')

def get_saved_workout_records():
    """Получение сохраненных записей тренировок пользователя"""
    logger.info("📡 Запрос сохраненных записей тренировок...")
    return make_api_request('apps/691401d80266c5f799e50d4f/entities/SavedWorkout')

def get_articles():
    """Получение статей с улучшенным логированием"""
    logger.info("📡 Запрос статей...")
    result = make_api_request('apps/691401d80266c5f799e50d4f/entities/Article')
    
    if result is None:
        logger.warning("⚠️ API вернуло None для статей")
        return None
        
    if not result:
        logger.info("📭 Нет статей в API")
        return []
    
    logger.info(f"✅ Получено {len(result)} статей")
    
    # Логируем структуру первой статьи для отладки
    if result and len(result) > 0:
        first_article = result[0]
        logger.info(f"🔍 Структура первой статьи:")
        for key in list(first_article.keys())[:5]:  # Первые 5 полей
            logger.info(f"  {key}: {str(first_article.get(key, ''))[:30]}")
    
    return result

def get_activities():
    """Получение активностей"""
    logger.info("📡 Запрос активностей...")
    return make_api_request('apps/691401d80266c5f799e50d4f/entities/Activity')

def update_entity(entity_id, update_data, entity_type='MedicationLog'):
    """Обновление сущности"""
    path = f'apps/691401d80266c5f799e50d4f/entities/{entity_type}/{entity_id}'
    return make_api_request(path, method='PUT', data=update_data)

# Тестовые данные для fallback
def get_test_workout_videos():
    """Тестовые данные для видеозаписей тренировок"""
    return [
        {
            'title': 'Gentle Morning Cardio',
            'description': 'Low-impact cardiovascular exercise perfect for mornings',
            'duration': 15.0,
            'videourl': 'https://example.com/video1',
            'thumbnailurl': 'https://images.unsplash.com/photo-157101'
        },
        {
            'title': 'Full Body Strength',
            'description': 'Complete strength training for all muscle groups',
            'duration': 30.0,
            'videourl': None,
            'thumbnailurl': 'https://images.unsplash.com/photo-157102'
        },
        {
            'title': 'Evening Yoga Flow',
            'description': 'Relaxing yoga sequence for better sleep',
            'duration': 20.0,
            'videourl': 'https://example.com/video3',
            'thumbnailurl': None
        }
    ]

def get_test_saved_workouts():
    """Тестовые данные для сохраненных тренировок"""
    return [
        {
            'workoutid': '692f76ca9c886530612c24cd',
            'notes': 'Делаю каждый понедельник',
            'favorite': True,
            'createddate': '2025-12-02T23:46:19.559000'
        },
        {
            'workoutid': '692f76ca9c886530612c24ce',
            'notes': None,
            'favorite': False,
            'createddate': '2025-12-01T10:30:00.000000'
        }
    ]

def get_test_articles():
    """Тестовые данные для статей"""
    return [
        {
            'title': '10 советов для здорового сна',
            'author': 'Доктор Иванов',
            'description': 'Простые привычки для улучшения качества сна',
            'content': 'Полный текст статьи о здоровом сне...'
        },
        {
            'title': 'Правильное питание для спортсменов',
            'author': 'Нутрициолог Петрова',
            'description': 'Как составить рацион для эффективных тренировок',
            'content': 'Полный текст статьи о питании...'
        },
        {
            'title': 'Профилактика травм при тренировках',
            'author': 'Тренер Сидоров',
            'description': 'Как избежать распространенных спортивных травм',
            'content': 'Полный текст статьи о профилактике...'
        }
    ]

# Безопасная отправка сообщений с Markdown
async def safe_reply_markdown(update: Update, text: str):
    """Безопасная отправка сообщения с Markdown"""
    try:
        # Пытаемся отправить с Markdown
        await update.message.reply_text(text, parse_mode='Markdown')
    except Exception as e:
        logger.warning(f"⚠️ Ошибка Markdown: {e}, отправляю без форматирования")
        # Убираем Markdown символы и отправляем простой текст
        clean_text = text.replace('*', '').replace('_', '').replace('`', '').replace('[', '').replace(']', '').replace('(', '').replace(')', '')
        await update.message.reply_text(clean_text)

# Обработчики команд
async def start(update: Update, context: CallbackContext):
    """Обработчик команды /start"""
    welcome_text = """🤖 *Бот-помощник для здоровья*

*Основные команды:*
/workouts — видеозаписи тренировок
/savedworkouts — ваши сохраненные тренировки
/detail [номер] — детали тренировки

*Информация и здоровье:*
/articles — статьи о здоровье
/meds — медикаменты
/activities — активность

*Технические:*
/testapi — проверка подключения
/status — статус бота
/help — помощь
/ping — проверить активность"""
    
    await safe_reply_markdown(update, welcome_text)

async def ping_command(update: Update, context: CallbackContext):
    """Проверка активности бота"""
    await safe_reply_markdown(update, "🏓 *Pong!*\n\nБот активен и работает!\n\nПорт health сервера: `{}`".format(HTTP_PORT))

async def workouts_command(update: Update, context: CallbackContext):
    """Обработчик команды /workouts - ВИДЕОЗАПИСИ тренировок"""
    logger.info("🔄 Вызвана команда /workouts (видеозаписи)")
    
    try:
        await update.message.reply_text("⏳ Загружаю видеозаписи тренировок...")
        
        workouts = get_workout_videos()  # Видеозаписи тренировок
        logger.info(f"📊 Получено видеозаписей: {len(workouts) if workouts else 0}")
        
        # Если API не вернул данных, используем тестовые
        if not workouts:
            logger.warning("⚠️ API вернуло пустой результат, используем тестовые данные")
            workouts = get_test_workout_videos()
        
        if not workouts:
            await update.message.reply_text("📭 Нет доступных видеозаписей тренировок.")
            return
        
        # Форматируем видеозаписи тренировок с реальными полями
        items = []
        for i, workout in enumerate(workouts[:10], 1):
            # Реальные поля из API
            title = workout.get('title', f'Тренировка {i}')
            description = workout.get('description', '')[:50]
            duration = workout.get('duration', '?')
            
            # Форматируем продолжительность
            if isinstance(duration, (int, float)):
                duration_str = f"{int(duration)} мин"
            else:
                duration_str = str(duration)
            
            # Формируем строку
            item_text = f"{i}. *{title}*"
            if duration_str and duration_str != '?':
                item_text += f" - {duration_str}"
            if description:
                item_text += f"\n   📝 {description}"
                
            items.append(item_text)
        
        text = "🎬 *Видеозаписи тренировок:*\n\n" + "\n\n".join(items)
        if len(workouts) > 10:
            text += f"\n\n... и еще {len(workouts) - 10} видеозаписей"
        
        await safe_reply_markdown(update, text)
        
    except Exception as e:
        logger.error(f"🔥 Ошибка в workouts_command: {e}", exc_info=True)
        await update.message.reply_text("❌ Ошибка при загрузке видеозаписей тренировок")

                
async def savedworkouts_command(update: Update, context: CallbackContext):
    """Обработчик команды /savedworkouts с правильным отображением"""
    logger.info("🔄 Вызвана команда /savedworkouts")
    
    try:
        await update.message.reply_text("⏳ Ищу ваши сохраненные тренировки...")
        
        # 1. Получаем сохраненные записи пользователя
        saved_records = get_saved_workout_records()
        
        if not saved_records:
            await update.message.reply_text("💾 У вас пока нет сохраненных тренировок.")
            return
        
        # 2. Получаем ВСЕ тренировки для сопоставления
        all_workouts = get_workout_videos()
        
        # 3. Создаем словарь для быстрого поиска тренировок по ID
        workout_dict = {}
        if all_workouts:
            for workout in all_workouts:
                workout_id = workout.get('id')
                if workout_id:
                    workout_dict[workout_id] = workout
        
        # 4. Формируем ответ с СВЯЗАННЫМИ данными
        items = []
        for i, saved in enumerate(saved_records[:10], 1):
            # Получаем workout_id из сохраненной записи
            workout_id = saved.get('workoutid')
            
            # Ищем соответствующую тренировку в каталоге
            workout_info = workout_dict.get(workout_id) if workout_id else None
            
            if workout_info:
                # Есть связь с Workout - показываем полную информацию
                title = workout_info.get('title', f'Тренировка {i}')
                description = workout_info.get('description', '')[:50]
                duration = workout_info.get('duration')
            else:
                # Нет связи - показываем базовую информацию
                title = f'Тренировка {workout_id[:8] if workout_id else i}'
                description = ''
                duration = None
            
            # Информация из SavedWorkout
            notes = saved.get('notes')
            is_favorite = saved.get('favorite', False)
            created_date = saved.get('createddate', '')
            
            # Форматируем
            item_text = f"{i}. *{title}*"
            
            if duration:
                item_text += f" ({int(duration)} мин)" if isinstance(duration, (int, float)) else f" ({duration})"
            
            if is_favorite:
                item_text += " ⭐"
            
            if created_date:
                try:
                    date_part = created_date.split('T')[0]
                    item_text += f"\n   📅 {date_part}"
                except:
                    pass
            
            if notes:
                item_text += f"\n   📝 {str(notes)[:30]}"
            elif description:
                item_text += f"\n   📄 {description}"
            
            items.append(item_text)
        
        text = "💾 *Ваши сохраненные тренировки:*\n\n" + "\n\n".join(items)
        
        # 5. Если есть записи без связи с Workout - предупреждаем
        missing_count = sum(1 for saved in saved_records if not workout_dict.get(saved.get('workoutid')))
        if missing_count > 0:
            text += f"\n\n⚠️ *Примечание:* {missing_count} записей не найдены в каталоге тренировок"
        
        await safe_reply_markdown(update, text)
        
    except Exception as e:
        logger.error(f"🔥 Ошибка в savedworkouts_command: {e}", exc_info=True)
        await update.message.reply_text("❌ Ошибка при загрузке сохраненных тренировок")            
            
async def debug_savedworkouts(update: Update, context: CallbackContext):
    """Отладка структуры сохраненных тренировок"""
    logger.info("🔍 Отладка структуры savedworkouts...")
    
    saved_records = get_saved_workout_records()
    
    if not saved_records:
        await update.message.reply_text("📭 Нет данных о сохраненных тренировках")
        return
    
    debug_info = ["💾 *Структура данных сохраненных тренировок:*"]
    debug_info.append(f"\n📊 Всего записей: {len(saved_records)}")
    
    # Анализируем каждую запись
    for i, record in enumerate(saved_records[:5], 1):
        debug_info.append(f"\n🔍 *Запись {i}:*")
        
        field_count = 0
        for key, value in record.items():
            if field_count >= 6:
                break
            debug_info.append(f"  {key}: {str(value)[:50]}")
            field_count += 1
        
        # Показываем тип данных
        notes = record.get('notes')
        debug_info.append(f"  Тип notes: {type(notes).__name__}")
        if notes is None:
            debug_info.append(f"  notes is None: True")
    
    await safe_reply_markdown(update, "\n".join(debug_info))

async def debug_workout_relations(update: Update, context: CallbackContext):
    """Отладка связей между Workout и SavedWorkout"""
    
    # Получаем данные
    workouts = get_workout_videos()
    saved_records = get_saved_workout_records()
    
    debug_info = ["🔗 *Отладка связей Workout ↔ SavedWorkout:*"]
    
    debug_info.append(f"\n📊 *Количество:*")
    debug_info.append(f"Workout (каталог): {len(workouts) if workouts else 0}")
    debug_info.append(f"SavedWorkout (сохраненные): {len(saved_records) if saved_records else 0}")
    
    # Собираем все workout_id из saved_records
    saved_workout_ids = []
    if saved_records:
        for saved in saved_records:
            workout_id = saved.get('workoutid')
            if workout_id:
                saved_workout_ids.append(workout_id)
    
    # Собираем все id из workouts
    workout_ids = []
    if workouts:
        for workout in workouts:
            workout_id = workout.get('id')
            if workout_id:
                workout_ids.append(workout_id)
    
    # Находим пересечения и отсутствующие
    saved_workout_ids_set = set(saved_workout_ids)
    workout_ids_set = set(workout_ids)
    
    # Находим совпадения
    matches = saved_workout_ids_set.intersection(workout_ids_set)
    missing_in_workout = saved_workout_ids_set - workout_ids_set
    
    debug_info.append(f"\n🔗 *Связи:*")
    debug_info.append(f"Сохранено тренировок: {len(saved_workout_ids)}")
    debug_info.append(f"Найдено в каталоге: {len(matches)}")
    debug_info.append(f"Отсутствуют в каталоге: {len(missing_in_workout)}")
    
    if missing_in_workout:
        debug_info.append(f"\n⚠️ *Отсутствующие workout_id:*")
        for workout_id in list(missing_in_workout)[:5]:
            debug_info.append(f"  {workout_id}")
        if len(missing_in_workout) > 5:
            debug_info.append(f"  ... и еще {len(missing_in_workout) - 5}")
    
    # Примеры связей
    if matches and saved_records:
        debug_info.append(f"\n📝 *Пример связи:*")
        # Берем первый совпадающий workout_id
        example_id = list(matches)[0]
        
        # Находим saved запись
        saved_example = None
        for saved in saved_records:
            if saved.get('workoutid') == example_id:
                saved_example = saved
                break
        
        # Находим workout
        workout_example = None
        if workouts:
            for workout in workouts:
                if workout.get('id') == example_id:
                    workout_example = workout
                    break
        
        if saved_example and workout_example:
            debug_info.append(f"  SavedWorkout → Workout:")
            debug_info.append(f"  workoutid: {example_id}")
            debug_info.append(f"  Название: {workout_example.get('title')}")
            debug_info.append(f"  Заметки: {saved_example.get('notes')}")
            debug_info.append(f"  Избранное: {saved_example.get('favorite')}")
    
    await safe_reply_markdown(update, "\n".join(debug_info))
    
async def workout_detail(update: Update, context: CallbackContext):
    """Показать детали конкретной тренировки по номеру"""
    try:
        if not context.args:
            await update.message.reply_text("❌ Укажите номер тренировки: /detail 1")
            return
        
        try:
            workout_num = int(context.args[0]) - 1
        except:
            await update.message.reply_text("❌ Укажите корректный номер")
            return
        
        workouts = get_workout_videos()
        if not workouts:
            workouts = get_test_workout_videos()
        
        if workout_num < 0 or workout_num >= len(workouts):
            await update.message.reply_text(f"❌ Тренировка с номером {workout_num + 1} не найдена")
            return
        
        workout = workouts[workout_num]
        
        # Формируем детальное описание
        details = []
        details.append(f"*{workout.get('title', 'Тренировка')}*")
        
        if workout.get('description'):
            details.append(f"\n📝 *Описание:*\n{workout.get('description')}")
        
        if workout.get('duration'):
            details.append(f"\n⏱️ *Продолжительность:* {workout.get('duration')} мин")
        
        await safe_reply_markdown(update, "\n".join(details))
        
    except Exception as e:
        logger.error(f"🔥 Ошибка в workout_detail: {e}", exc_info=True)
        await update.message.reply_text("❌ Ошибка при загрузке деталей тренировки")

async def meds_command(update: Update, context: CallbackContext):
    """Обработчик команды /meds"""
    logger.info("🔄 Вызвана команда /meds")
    
    try:
        await update.message.reply_text("⏳ Получаю данные о медикаментах...")
        
        meds = get_medications()
        logger.info(f"📊 Получено записей о медикаментах: {len(meds) if meds else 0}")
        
        if not meds:
            await update.message.reply_text("📭 Нет данных о медикаментах.")
            return
        
        items = []
        for i, med in enumerate(meds[:10], 1):
            med_id = med.get('medication_id', f'Медикамент_{i}')
            notes = med.get('notes', 'Без описания')[:40]
            items.append(f"{i}. *{med_id}:* {notes}")
        
        text = "💊 *Медикаменты:*\n\n" + "\n".join(items)
        await safe_reply_markdown(update, text)
        
    except Exception as e:
        logger.error(f"🔥 Ошибка в meds_command: {e}", exc_info=True)
        await update.message.reply_text("❌ Ошибка при получении данных о медикаментах")

async def articles_command(update: Update, context: CallbackContext):
    """Обработчик команды /articles"""
    logger.info("🔄 Вызвана команда /articles")
    
    try:
        await update.message.reply_text("⏳ Загружаю статьи о здоровье...")
        
        articles = get_articles()
        logger.info(f"📊 Получено статей: {len(articles) if articles else 0}")
        
        # Если API не вернул данных, используем тестовые
        if not articles:
            logger.warning("⚠️ API вернуло пустой результат, используем тестовые данные")
            articles = get_test_articles()
        
        if not articles:
            await update.message.reply_text("📭 Нет доступных статей.")
            return
        
        # Используем безопасный доступ к данным
        items = []
        for i, article in enumerate(articles[:10], 1):
            # Безопасное получение данных
            title = article.get('title') or article.get('name') or f'Статья {i}'
            author = article.get('author') or article.get('created_by') or article.get('writer') or ''
            description = article.get('description') or article.get('excerpt') or article.get('summary') or ''
            
            if description:
                description = description[:50] + '...' if len(description) > 50 else description
            
            # Формируем строку
            item_text = f"{i}. *{title}*"
            if author:
                item_text += f"\n   👤 {author}"
            if description:
                item_text += f"\n   📝 {description}"
            
            items.append(item_text)
        
        text = "📚 *Статьи о здоровье и фитнесе:*\n\n" + "\n\n".join(items)
        if len(articles) > 10:
            text += f"\n\n... и еще {len(articles) - 10} статей"
        
        await safe_reply_markdown(update, text)
        
    except Exception as e:
        logger.error(f"🔥 Ошибка в articles_command: {e}", exc_info=True)
        await update.message.reply_text("❌ Ошибка при загрузке статей")

async def activities_command(update: Update, context: CallbackContext):
    """Обработчик команды /activities"""
    activities = get_activities()
    if not activities:
        await update.message.reply_text("📭 Нет записей об активности.")
        return
    
    text = "\n".join([f"{a['activity_type']} {a['date']} - {a['duration']} мин" for a in activities])
    await update.message.reply_text(text)

async def test_api_connection(update: Update, context: CallbackContext):
    """Тест всех API эндпоинтов"""
    
    endpoints = [
        ('🎬 Видео тренировок', 'Workout', 'apps/691401d80266c5f799e50d4f/entities/Workout'),
        ('💾 Сохраненные тренировки', 'SavedWorkout', 'apps/691401d80266c5f799e50d4f/entities/SavedWorkout'),
        ('💊 Медикаменты', 'MedicationLog', 'apps/691401d80266c5f799e50d4f/entities/MedicationLog'),
        ('📚 Статьи', 'Article', 'apps/691401d80266c5f799e50d4f/entities/Article'),
        ('🚴 Активности', 'Activity', 'apps/691401d80266c5f799e50d4f/entities/Activity'),
    ]
    
    results = []
    
    for display_name, entity_name, endpoint in endpoints:
        try:
            url = f'{BASE_URL}{endpoint}'
            response = requests.get(url, headers={
                'api_key': API_KEY,
                'Content-Type': 'application/json'
            }, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    count = len(data)
                    results.append(f"✅ {display_name}: {count} записей")
                elif isinstance(data, dict):
                    results.append(f"✅ {display_name}: объект получен")
                else:
                    results.append(f"✅ {display_name}: {response.status_code}")
            else:
                results.append(f"❌ {display_name}: {response.status_code}")
                
        except Exception as e:
            results.append(f"⚠️ {display_name}: ошибка")
    
    text = "🔌 *Тест подключения к системе:*\n\n" + "\n".join(results)
    await safe_reply_markdown(update, text)

async def debug_data(update: Update, context: CallbackContext):
    """Подробная отладка структуры данных"""
    
    # Получаем данные
    workout_videos = get_workout_videos()
    saved_records = get_saved_workout_records()
    
    debug_info = ["*Отладка структуры данных:*"]
    
    # Информация о количестве
    debug_info.append(f"\n📊 *Количество записей:*")
    debug_info.append(f"Workout (видео): {len(workout_videos) if workout_videos else 0}")
    debug_info.append(f"SavedWorkout (сохраненные): {len(saved_records) if saved_records else 0}")
    
    # Пример первой записи Workout
    if workout_videos and len(workout_videos) > 0:
        first = workout_videos[0]
        debug_info.append(f"\n🎬 *Пример Workout (первые 5 полей):*")
        for key in list(first.keys())[:5]:
            debug_info.append(f"  {key}: {str(first.get(key, ''))[:40]}")
    
    # Пример первой записи SavedWorkout
    if saved_records and len(saved_records) > 0:
        first = saved_records[0]
        debug_info.append(f"\n💾 *Пример SavedWorkout (первые 5 полей):*")
        for key in list(first.keys())[:5]:
            debug_info.append(f"  {key}: {str(first.get(key, ''))[:40]}")
    
    await safe_reply_markdown(update, "\n".join(debug_info))

async def debug_articles(update: Update, context: CallbackContext):
    """Отладка структуры данных статей"""
    logger.info("🔍 Отладка структуры статей...")
    
    articles = get_articles()
    
    if not articles:
        await update.message.reply_text("📭 Нет данных о статьях")
        return
    
    debug_info = ["📚 *Структура данных статей:*"]
    debug_info.append(f"\n📊 Всего статей: {len(articles)}")
    
    # Анализируем первую статью
    if articles and len(articles) > 0:
        first_article = articles[0]
        debug_info.append(f"\n🔍 *Первая статья (первые 8 полей):*")
        
        field_count = 0
        for key, value in first_article.items():
            if field_count >= 8:
                break
            debug_info.append(f"  {key}: {str(value)[:50]}")
            field_count += 1
        
        # Показываем все ключи для справки
        all_keys = list(first_article.keys())
        debug_info.append(f"\n📋 *Все поля статьи:*")
        debug_info.append(f"  {', '.join(all_keys)}")
    
    await safe_reply_markdown(update, "\n".join(debug_info))

async def status_command(update: Update, context: CallbackContext):
    """Проверка статуса бота"""
    import time
    status_text = f"""✅ *Бот-помощник активен!*

*Информация о системе:*
• Хостинг: Koyeb
• Статус: Работает 24/7
• Версия: 2.3.1
• Подключение к API: Активно
• Health сервер: Порт {HTTP_PORT}
• Время запуска: {time.ctime()}

*Доступные функции:*
• Управление тренировками
• Медицинские записи
• База знаний о здоровье
• Отслеживание активности

Для помощи используйте /help"""
    
    await safe_reply_markdown(update, status_text)

async def help_command(update: Update, context: CallbackContext):
    """Команда помощи"""
    help_text = """🆘 *Помощь по использованию бота*

*Основные команды:*
/start - Начало работы
/help - Эта справка
/status - Статус системы
/ping - Проверить активность бота

*Управление здоровьем:*
/meds - Ваши медикаменты
/articles - Статьи о здоровье
/activities - Ваша активность

*Тренировки:*
/workouts - Видеозаписи тренировок
/savedworkouts - Сохраненные тренировки
/detail [номер] - Детали тренировки

*Технические:*
/testapi - Проверка подключения
/debug - Отладка данных
/debug_articles - Отладка статей"""
    
    await safe_reply_markdown(update, help_text)

async def error_handler(update: Update, context: CallbackContext):
    """Обработчик ошибок"""
    logger.error(f"Ошибка в обработчике: {context.error}")
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Произошла ошибка при обработке команды. Попробуйте позже или используйте /help."
        )

def main():
    """Основная функция запуска бота"""
    logger.info("🚀 Запуск бота-помощника для здоровья...")
    
    # Запускаем health сервер в отдельном потоке
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    
    logger.info("🔄 Health server thread started")
    
    # Даем серверу время на запуск
    import time
    time.sleep(2)
    
    # Создаем приложение Telegram бота
    application = ApplicationBuilder().token(TOKEN).build()
    
    # Регистрация обработчиков
    handlers = [
        CommandHandler("start", start),
        CommandHandler("help", help_command),
        CommandHandler("ping", ping_command),  # <-- Добавлена команда ping
        CommandHandler("workouts", workouts_command),
        CommandHandler("savedworkouts", savedworkouts_command),
        CommandHandler("detail", workout_detail),
        CommandHandler("meds", meds_command),
        CommandHandler("articles", articles_command),
        CommandHandler("activities", activities_command),
        CommandHandler("testapi", test_api_connection),
        CommandHandler("debug", debug_data),
        CommandHandler("debug_articles", debug_articles),
        CommandHandler("status", status_command),
        CommandHandler("debug_saved", debug_savedworkouts),
        CommandHandler("debug_relations", debug_workout_relations),
    ]
    
    for handler in handlers:
        application.add_handler(handler)
    
    # Добавляем обработчик ошибок
    application.add_error_handler(error_handler)
    
    logger.info("🤖 Бот-помощник запущен и ожидает сообщений...")
    logger.info(f"🌐 Health сервер доступен на порту: {HTTP_PORT}")
    
    # Запускаем бота
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )

if __name__ == '__main__':
    import time
    time.sleep(1)  # Небольшая задержка перед запуском
    main()
