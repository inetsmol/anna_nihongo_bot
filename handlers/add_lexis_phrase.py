from aiogram.types import CallbackQuery, Message, BufferedInputFile
from aiogram_dialog import DialogManager, Dialog, Window
from aiogram_dialog.widgets.input import TextInput, ManagedTextInput
from aiogram_dialog.widgets.kbd import Select, Group, Cancel, Back
from aiogram_dialog.widgets.text import Format, Multi

from external_services.google_cloud_services import google_text_to_speech
from external_services.openai_services import openai_gpt_add_space, openai_gpt_translate
from handlers.system_handlers import get_user_categories
from models import Category, Phrase, User
from services.i18n_format import I18NFormat, I18N_FORMAT_KEY
from states import AddPhraseSG


async def get_current_category(dialog_manager: DialogManager, **kwargs):
    category_name = dialog_manager.dialog_data['category']
    return {'category': category_name}


# Хэндлер для выбора категории
async def category_selection(callback: CallbackQuery, widget: Select, dialog_manager: DialogManager, item_id: str):
    category = await Category.get_or_none(id=item_id)
    dialog_manager.dialog_data['category'] = category.name
    await dialog_manager.next()


# Хэндлер для ввода новой категории
async def category_input(message: Message, widget: ManagedTextInput, dialog_manager: DialogManager, text: str):
    user_id = dialog_manager.event.from_user.id
    category = await Category.create(name=text, user_id=user_id)
    dialog_manager.dialog_data['category'] = category.name
    await dialog_manager.next()


# Хэндлер для ввода текста фразы
async def phrase_input(message: Message, widget: ManagedTextInput, dialog_manager: DialogManager, text_phrase: str):
    i18n_format = dialog_manager.middleware_data.get(I18N_FORMAT_KEY)
    if not await Phrase.get_or_none(text_phrase=text_phrase):
        category_name = dialog_manager.dialog_data['category']
        category = await Category.get(name=category_name)
        spaced_phrase = await openai_gpt_add_space(text_phrase)
        translation = await openai_gpt_translate(text_phrase)

        text_to_speech = await google_text_to_speech(text_phrase)
        voice = BufferedInputFile(text_to_speech.audio_content, filename="voice_tts.ogg")
        i18n_format = dialog_manager.middleware_data.get(I18N_FORMAT_KEY)
        msg = await message.answer_voice(voice=voice, caption=i18n_format("voice-acting"))
        voice_id = msg.voice.file_id

        user_id = dialog_manager.event.from_user.id
        user = await User.get_or_none(id=user_id)

        await Phrase.create(
            category=category,
            text_phrase=text_phrase,
            spaced_phrase=spaced_phrase,
            translation=translation,
            audio_id=voice_id,
            user=user
        )
        await message.answer(i18n_format("phrase-saved"))
        # await dialog_manager.done()
    else:
        await message.answer(i18n_format("phrase-saved"))


# Описание диалога
add_lexis_phrase_dialog = Dialog(
    Window(
        I18NFormat('Выберите категорию или добавьте новую:'),
        Group(
            Select(
                Format('{item[0]}'),
                id='category',
                item_id_getter=lambda x: x[1],
                items='categories',
                on_click=category_selection,
            ),
            width=2
        ),
        TextInput(
            id='category_input',
            on_success=category_input,
        ),
        Group(
            Cancel(I18NFormat('cancel'), id='button_cancel'),
            width=3
        ),
        state=AddPhraseSG.category,
        getter=get_user_categories
    ),
    Window(
        Multi(
            I18NFormat('Выбранная категория: <b>{category}</b>'),
            I18NFormat(text='Введите текст новой фразы:'),
        ),
        TextInput(
            id='phrase_input',
            on_success=phrase_input,
        ),
        Group(
            Back(I18NFormat('back'), id='back'),
            Cancel(I18NFormat('cancel'), id='button_cancel'),
            width=3
        ),
        state=AddPhraseSG.phrase,
        getter=get_current_category,
    ),
)
