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
USED_NUMS = {10, 11, 12}
ADMIN_FUNCTIONS, ADD, REMOVE = USED_NUMS
BUTTON_LABELS = ['הוספת אדמין', 'מחיקת אדמין']
MAINTAINER_ID = 640360349


def enforce_admin(*, fallbacks: list[TELEGRAM_HANDLER]):
    def decorator(handler):
        if inspect.ismethod(handler):
            handler.__func__.enforce_admin = ...
        else:
            handler.enforce_admin = ...

        def wrapper(update: Update, context: CallbackContext):
            if update.effective_user.id not in context.bot_data['admins']:
                for fallback in fallbacks:
                    obj = fallback.check_update(update)
                    if obj:
                        fallback.handle_update(update, context.dispatcher, obj, context)
                    return ConversationHandler.END
            return handler(update, context)

        return wrapper

    return decorator


def admin_menu(button_labels, *, fallbacks: list[TELEGRAM_HANDLER]):
    global BUTTON_LABELS
    BUTTON_LABELS.extend(button_labels)
    BUTTON_LABELS = [[label] for label in BUTTON_LABELS]

    @enforce_admin(fallbacks=fallbacks)
    def wrapper(update: Update, context: CallbackContext):
        markup = context.user_data['lastMarkup'] = BUTTON_LABELS
        update.message.reply_text('תפריט מנהלים\nמה תרצה לעשות?',
                                  reply_markup=ReplyKeyboardMarkup(markup))
        return ADMIN_FUNCTIONS

    return wrapper


def get_new_admin(update: Update, _: CallbackContext):
    update.message.reply_text('הזן יוזר-אידי של המשתמש שתרצה לקדם כאדמין:')
    return ADD


def add_admin(update: Update, context: CallbackContext):
    context.bot_data['admins'].add(int(update.message.text))
    markup = context.user_data['lastMarkup'] = BUTTON_LABELS
    update.message.reply_text('המשתמש עכשיו אדמין', reply_markup=ReplyKeyboardMarkup(markup))
    return ADMIN_FUNCTIONS


def get_admin_id(update: Update, _: CallbackContext):
    update.message.reply_text('הזן יוזר-אידי של המשתמש שתרצה למחוק כאדמין:')
    return REMOVE


def remove_admin(update: Update, context: CallbackContext):
    user_id = int(update.message.text)
    if user_id == MAINTAINER_ID:
        update.message.reply_text('אין לך הרשאה למחוק את המשתמש הזה כאדמין!')
        return ADMIN_FUNCTIONS

    try:
        context.bot_data['admins'].remove(user_id)
    except (KeyError, ValueError):
        # user_id is not an admin or message is not a number
        pass
    markup = context.user_data['lastMarkup'] = BUTTON_LABELS
    update.message.reply_text('המשתמש כבר לא אדמין', reply_markup=ReplyKeyboardMarkup(markup))
    return ADMIN_FUNCTIONS


def create_admin_menu(*,
                      additional_states: dict[int, list[TELEGRAM_HANDLER]],
                      menu_button_labels: list[str],
                      fallbacks: list[TELEGRAM_HANDLER],
                      unhandled_message_handlers: list[TELEGRAM_HANDLER],
                      **kwargs) -> ConversationHandler:
    """
    creates basic admin menu and adds custom handlers to it
    :param unhandled_message_handlers: the handler to call when theres an unhandled message
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
    states = {
        ADMIN_FUNCTIONS: [MessageHandler(Filters.regex('^הוספת אדמין$'), get_new_admin),
                          MessageHandler(Filters.regex('^מחיקת אדמין$'), get_admin_id)]
                          + additional_states.pop(ADMIN_FUNCTIONS),

        ADD: [MessageHandler(Filters.regex(r'\d{6,10}'), add_admin)],
        REMOVE: [MessageHandler(Filters.regex(r'\d{6,10}'), remove_admin)],
        **additional_states
    }
    enforced_admin_states = defaultdict(lambda: [])
    for key, handlers in states.items():
        for handler in handlers:
            callback = handler.callback
            handler.callback = (callback
                                if hasattr(callback, 'enforce_admin')
                                else enforce_admin(fallbacks=unhandled_message_handlers)(callback))
            enforced_admin_states[key].append(handler)

    return ConversationHandler(
        entry_points=[MessageHandler(Filters.regex('^תפריט מנהלים$'), admin_menu(menu_button_labels,
                                                                                 fallbacks=unhandled_message_handlers))],
        states=enforced_admin_states,
        fallbacks=fallbacks,
        **kwargs
    )
