from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import (
    Handler,
    MessageHandler,
    ConversationHandler,
    CallbackContext,
    Filters
)
from telegram.ext.utils.types import CCT
from collections import defaultdict
import inspect


TELEGRAM_HANDLER = Handler[Update, CCT]
USED_NUMS = {-1, -2, -3}
ADMIN_FUNCTIONS, ADD, REMOVE = USED_NUMS
BUTTON_LABELS = ['הוספת אדמין', 'מחיקת אדמין']


def enforce_admin(handler):
    if inspect.ismethod(handler):
        handler.__func__.enforce_admin = ...
    else:
        handler.enforce_admin = ...

    def wrapper(update: Update, context: CallbackContext):
        if update.effective_user.id not in context.bot_data['admins']:
            return ConversationHandler.END
        return handler(update, context)

    return wrapper


def admin_menu(button_labels):
    global BUTTON_LABELS
    BUTTON_LABELS.extend(button_labels)
    BUTTON_LABELS = [[label] for label in BUTTON_LABELS]

    @enforce_admin
    def wrapper(update: Update, _: CallbackContext):
        update.message.reply_text('תפריט מנהלים\nמה תרצה לעשות?',
                                  reply_markup=ReplyKeyboardMarkup(BUTTON_LABELS))
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
                      fallbacks: list[TELEGRAM_HANDLER], **kwargs) -> ConversationHandler:
    """
    creates basic admin menu and adds custom handlers to it
    :param additional_states: the custom handlers
    :param menu_button_labels: list of labels used in the custom handlers (will show up in keyboard)
    :param fallbacks: the ConversationHandler fallback
    :param kwargs: additional arguments to ConversationHandler
    :return: the ConversationHandler with default and custom handlers
    """

    # check `additional_states`s' numbers are not used - except from `ADMIN_FUNCTIONS` which is ok
    intersection = USED_NUMS.intersection(additional_states.keys()).symmetric_difference({ADMIN_FUNCTIONS})
    if intersection:
        raise ValueError(
            f'additional admin states have overlapping keys with default state; overlapping keys: {intersection}')

    # make sure handlers are wrapped with `enforce_admin` function
    enforced_admin_states = defaultdict(lambda: [])
    for key, handlers in additional_states.items():
        for handler in handlers:
            callback = handler.callback
            handler.callback = callback if hasattr(callback, 'enforce_admin') else enforce_admin(callback)
            enforced_admin_states[key].append(handler)

    additional_admin_functions = enforced_admin_states.pop(ADMIN_FUNCTIONS)

    return ConversationHandler(
        entry_points=[MessageHandler(Filters.regex('^תפריט מנהלים$'), admin_menu(menu_button_labels))],
        states={
            ADMIN_FUNCTIONS: [MessageHandler(Filters.regex('^הוספת אדמין$'), get_new_admin),
                              MessageHandler(Filters.regex('^מחיקת אדמין$'), get_admin_id)]
                             + additional_admin_functions,
            ADD: [MessageHandler(Filters.regex('\d{6,10}'), add_admin)],
            REMOVE: [MessageHandler(Filters.regex('\d{6,10}'), remove_admin)],

            **enforced_admin_states
        },
        fallbacks=fallbacks,
        **kwargs
    )
