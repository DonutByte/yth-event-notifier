from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import (
    Handler,
    MessageHandler,
    ConversationHandler,
    CallbackContext,
    Filters
)
from telegram.ext.utils.types import CCT

TELEGRAM_HANDLER = Handler[Update, CCT]
USED_NUMS = {-1, -2, -3}
ADMIN_FUNCTIONS, ADD, REMOVE = USED_NUMS
DEFAULT_BUTTON_LABELS = ['הוספת אדמין', 'מחיקת אדמין']


def enforce_admin(handler):
    handler.enforce_admin = ...

    def wrapper(update: Update, context: CallbackContext):
        if update.effective_user.id not in context.bot_data['admins']:
            return ConversationHandler.END
        return handler(update, context)


@enforce_admin
def admin_menu(button_labels):
    labels = [[label] for label in [*button_labels, *DEFAULT_BUTTON_LABELS]]

    def wrapper(update: Update, _: CallbackContext):
        update.message.reply_text('תפריט מנהלים\nמה תרצה לעשות?',
                                  reply_markup=ReplyKeyboardMarkup(labels))
        return ADMIN_FUNCTIONS

    return wrapper


@enforce_admin
def get_new_admin(update: Update, context: CallbackContext):
    update.message.reply_text('הזן יוזר-אידי של המשתמש שתרצה לקדם כאדמין:')
    return ADD


@enforce_admin
def add_admin(update: Update, context: CallbackContext):
    context.bot_data['admins'].add(update.message.text)
    return ADMIN_FUNCTIONS


@enforce_admin
def get_admin_id(update: Update, context: CallbackContext):
    update.message.reply_text('הזן יוזר-אידי של המשתמש שתרצה לקדם כאדמין:')
    return REMOVE


@enforce_admin
def remove_admin(update: Update, context: CallbackContext):
    context.bot_data['admins'].remove(update.message.text)
    return ADMIN_FUNCTIONS


def create_admin_menu(*,
                      additional_states: dict[int, list[TELEGRAM_HANDLER]],
                      menu_button_labels: list[str],
                      fallbacks: list[TELEGRAM_HANDLER], **kwargs):

    # check `additional_states`s' numbers are not used
    intersection = USED_NUMS.intersection(additional_states.keys())
    if intersection:
        raise ValueError(
            f'additional admin states have overlapping keys with default state; overlapping keys: {intersection}')

    # make sure handlers are wrapped with `enforce_admin` function
    enforced_admin_states = dict()
    for key, handlers in additional_states.items():
        enforced_admin_states[key] = [handler if hasattr(handler, 'enforce_admin') else enforce_admin(handler)
                                      for handler in handlers]

    admin_conversation = ConversationHandler(
        entry_points=[MessageHandler(Filters.regex('^תפריט מנהלים$'), admin_menu(menu_button_labels))],
        states={
            ADMIN_FUNCTIONS: [MessageHandler(Filters.regex('^הוספת אדמין$'), get_new_admin),
                              MessageHandler(Filters.regex('^מחיקת אדמין$'), get_admin_id)],
            ADD: [MessageHandler(Filters.regex(r'\d{6, 10}'), add_admin)],
            REMOVE: [MessageHandler(Filters.regex(r'\d{6, 10}'), remove_admin)],

            **{enforced_admin_states}
        },
        fallbacks=fallbacks,
        **kwargs
    )
