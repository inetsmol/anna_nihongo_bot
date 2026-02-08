import base64
import logging
import os
import random

from aiogram.types import CallbackQuery, BufferedInputFile
from aiogram_dialog import DialogManager, ShowMode
from aiogram_dialog.widgets.kbd import Select, Button
from tortoise.expressions import Q

from bot_init import bot
from external_services.kandinsky import generate_image
from models import User, Category, Phrase, Subscription
from services.i18n_format import I18N_FORMAT_KEY
from services.services import replace_random_words

location = os.getenv('LOCATION')

logger = logging.getLogger('default')

# Получение списка разрешенных ID пользователей из переменной окружения
admin_ids = os.getenv('ADMIN_IDS')
# Преобразование строки в список целых чисел
admin_ids = [int(user_id) for user_id in admin_ids.split(',')]


async def getter_prompt(dialog_manager: DialogManager, **kwargs):
    prompt = dialog_manager.dialog_data.get('prompt')
    if prompt:
        is_prompt = True
    else:
        is_prompt = False

    return {
        'is_prompt': is_prompt,
    }


async def repeat_ai_generate_image(callback: CallbackQuery, button: Button, dialog_manager: DialogManager):
    prompt = dialog_manager.dialog_data['prompt']
    i18n_format = dialog_manager.middleware_data.get(I18N_FORMAT_KEY)
    await callback.message.answer(text=i18n_format("starting-generate-image"))
    try:
        images = await generate_image(prompt)
        if images and len(images) > 0:
            image_data = base64.b64decode(images[0])
            image = BufferedInputFile(image_data, filename="image.png")
            await callback.message.answer_photo(photo=image, caption=i18n_format("generated-image"))
        else:
            await callback.message.answer(i18n_format("failed-generate-image"))
    except Exception as e:
        logger.error('Ошибка при генерации изображения: %s', e)
        await callback.message.answer(text=i18n_format("failed-generate-image"))

    # await dialog_manager.show(show_mode=ShowMode.SEND)
    dialog_manager.show_mode = ShowMode.SEND


async def start_getter(dialog_manager: DialogManager, event_from_user: User, **kwargs):

    response = {'username': event_from_user.first_name or event_from_user.username}
    if dialog_manager.start_data:
        response['not_new_user'] = dialog_manager.start_data.get("not_new_user", False)
        response['new_user'] = dialog_manager.start_data.get("new_user", False)
    else:
        response['not_new_user'] = True
        response['new_user'] = False

    subscription = await Subscription.get_or_none(user_id=event_from_user.id).prefetch_related('type_subscription')
    if subscription:
        if subscription.type_subscription.name not in ('Free', 'Free trial'):
            response['subscription'] = '💎 VIP'
            response['is_vip'] = True
            response['is_not_vip'] = False
        else:
            response['subscription'] = subscription.type_subscription.name
            response['is_vip'] = False
            response['is_not_vip'] = True

        if subscription.type_subscription.name != 'Vip':
            response['is_not_subscribe'] = True
        else:
            response['is_not_subscribe'] = False

    if event_from_user.id in admin_ids:
        response['is_admin'] = True
    else:
        response['is_admin'] = False

    if location == 'ja-JP':
        response['is_jp'] = True
    else:
        response['is_jp'] = False

    if location == 'en-US':
        response['is_en'] = True
    else:
        response['is_en'] = False
    return response


async def get_user_categories(dialog_manager: DialogManager, **kwargs):
    user_id = dialog_manager.event.from_user.id
    # categories = await Category.filter(user_id=user_id).all()
    categories = await Category.filter(user_id=user_id).prefetch_related('phrases').filter(phrases__isnull=False).distinct()
    items = [(category.name, str(category.id)) for category in categories]

    categories_for_all = await Category.filter(public=True).exclude(user_id=user_id).prefetch_related('phrases').filter(phrases__isnull=False).distinct()
    cat_for_all = [(category.name, str(category.id)) for category in categories_for_all]

    return {'categories': items, 'categories_for_all': cat_for_all}


async def get_user_categories_to_manage(dialog_manager: DialogManager, **kwargs):
    user_id = dialog_manager.event.from_user.id
    categories = await Category.filter(user_id=user_id).all()
    items = [(category.name, str(category.id)) for category in categories]
    dialog_manager.dialog_data['categories'] = items
    return dialog_manager.dialog_data


async def get_phrases(dialog_manager: DialogManager, **kwargs):
    if dialog_manager.start_data:
        category_id = dialog_manager.start_data.get('category_id')
    else:
        category_id = dialog_manager.dialog_data['category_id']

    category = await Category.get_or_none(id=category_id)
    user_id = dialog_manager.event.from_user.id

    if category.public:
        user_phrases = await Phrase.filter(category_id=category_id).all()
    else:
        user_phrases = await Phrase.filter(category_id=category_id, user_id=user_id).all()

    phrases = [(phrase.text_phrase, str(phrase.id)) for phrase in user_phrases]
    if phrases:
        show_random_button = True
    else:
        show_random_button = False
    if dialog_manager.start_data:
        dialog_manager.start_data.popitem()
    return {'phrases': phrases, 'category': category.name, 'show_random_button': show_random_button}


async def get_user_data(dialog_manager: DialogManager, **kwargs):
    return dialog_manager.dialog_data


async def get_non_admin_users(dialog_manager: DialogManager, **kwargs):

    users = await User.exclude(id__in=admin_ids).all()
    items = [(user.username, user.first_name, str(user.id)) for user in users]
    return {'users': items}


async def category_selected(callback: CallbackQuery, widget: Select, dialog_manager: DialogManager, item_id: str):
    category = await Category.get(id=item_id)
    dialog_manager.dialog_data['category_id'] = category.id
    user_id = dialog_manager.event.from_user.id
    phrases = await Phrase.filter(Q(category_id=item_id) & (Q(user_id=user_id) | Q(category__public=True))).all()
    items = [(phrase.text_phrase, str(phrase.id)) for phrase in phrases]
    dialog_manager.dialog_data['phrases'] = items
    await dialog_manager.next()


async def get_random_phrase(dialog_manager: DialogManager, item_id: str, **kwargs):
    phrases = await Phrase.filter(category_id=item_id).all()

    if dialog_manager.dialog_data.get('question'):
        text_phrase = dialog_manager.dialog_data['question']
        if len(phrases) > 1:
            filtered_phrases = [phrase for phrase in phrases if phrase.text_phrase != text_phrase]
        else:
            filtered_phrases = phrases
    else:
        filtered_phrases = phrases
    random_phrase = random.choice(filtered_phrases)

    with_gap_phrase = replace_random_words(random_phrase.spaced_phrase)
    dialog_manager.dialog_data['with_gap_phrase'] = with_gap_phrase
    dialog_manager.dialog_data['question'] = random_phrase.text_phrase
    dialog_manager.dialog_data['audio_id'] = random_phrase.audio_id
    dialog_manager.dialog_data['translation'] = random_phrase.translation
    dialog_manager.dialog_data['counter'] = 0
    category = await Category.get_or_none(id=item_id)
    dialog_manager.dialog_data['category'] = category.name
    dialog_manager.dialog_data['category_id'] = item_id


async def get_context(dialog_manager: DialogManager, **kwargs):
    with_gap_phrase = dialog_manager.dialog_data.get('with_gap_phrase')
    question = dialog_manager.dialog_data.get('question')
    translation = dialog_manager.dialog_data.get('translation')
    counter = dialog_manager.dialog_data.get('counter')
    category = dialog_manager.dialog_data.get('category')
    category_id = dialog_manager.dialog_data.get('category_id')
    first_time = dialog_manager.current_context().dialog_data.get("first_open", True)
    if first_time:
        dialog_manager.current_context().dialog_data["first_open"] = False
    return {'with_gap_phrase': with_gap_phrase,
            'question': question,
            'translation': translation,
            'counter': counter,
            'category': category,
            "show_widget": first_time,
            'category_id': category_id}


def first_answer_getter(data, widget, dialog_manager: DialogManager):
    # до первого ответа вернет False
    return 'answer' in dialog_manager.dialog_data


def second_answer_getter(data, widget, dialog_manager: DialogManager):
    return not first_answer_getter(data, widget, dialog_manager)


async def check_day_counter(dialog_manager: DialogManager) -> bool:
    user_id = dialog_manager.event.from_user.id

    if user_id in admin_ids:
        return True
    user = await User.get(id=user_id)
    subscription = await Subscription.get_or_none(user=user).prefetch_related('type_subscription')
    day_counter = user.day_counter
    if str(subscription.type_subscription) != 'Free' or (str(subscription.type_subscription) == 'Free' and day_counter <= 50):
        user.day_counter += 1
        await user.save()
        return True
    else:
        i18n_format = dialog_manager.middleware_data.get(I18N_FORMAT_KEY)
        await bot.send_message(chat_id=user_id,
                               text=i18n_format('daily-limit'))
        return False
