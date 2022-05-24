import threading

from telegram import ParseMode, ReplyKeyboardMarkup, Update
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackContext,
    ConversationHandler,
    Filters,
    MessageHandler,
)
import telegram
from apscheduler.schedulers.background import BackgroundScheduler
from dateutil import tz
from excel_handler import ExcelWorker
from event import Event
from safepicklepersistence import SafePicklePersistence
import admin_handler
from typing import Union
import logging
import json
import time
import os

EXCEL_URL = os.environ['EXCEL_URL']

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

START, GRADE, WEEK = range(3)
NAME_TO_ID, GET_MESSAGE, BROADCAST_MESSAGE = range(3)


def catch_errors(func):
    def wrapper(self, *args):
        try:
            return func(self, *args)
        except Exception as e:
            logger.exception(e)

    return wrapper


def enforce_signup(func):
    def wrapper(self, update: Update, context: CallbackContext):
        if not any(str(update.effective_user.id) in ids for grades in self.users for ids in self.users[grades].keys()):
            update.message.reply_text('עליך קודם להירשם!\nלחץ ▶️התחל')
            return

        if 'lock' not in context.user_data:
            context.user_data['lock'] = threading.Lock()

        if not context.user_data['lock'].locked():
            to_return = None
            context.user_data['lock'].acquire()
            try:
                to_return = func(self, update, context)
            except Exception as e:
                logger.error(f'{func.__name__} raised an exception "{e}"')
                message = f'חלה שגיאה\nאם הודעה זו נשלחת כמה פעמים פנה ל' \
                          f'<a href="tg://user?id={admin_handler.MAINTAINER_ID}">מנהל הבוט</a>'
                if update.message:
                    update.message.reply_html(message)
                else:
                    update.callback_query.edit_message_text(message, parse_mode=ParseMode.HTML)
            finally:
                context.user_data['lock'].release()
            return to_return

        else:
            update.message.reply_text(
                'בקשתך הקודמת עדיין בתהליך, אנא המתן...')

    return wrapper


# TODO: update users when schedule has changed

class Bot(Updater):
    WEEKS_FORMAT = {0: 'שבוע הזה', 1: 'שבוע הבא',
                    2: 'עוד שבועיים', 3: 'עוד שלושה שבועות '}
    MAX_WEEK = 4
    MIN_WEEK = 1
    GRADES = {  # 'ט': 9, 'י': 10, 'יא': 11, 'יב': 12,
        "ט'": 9, "י'": 10, "יא'": 11, "יב'": 12}
    NUM_TO_GRADE = {str(val): key for key, val in GRADES.items()}
    GRADES_KEYBOARD = [["ט'"], ["י'"], ["יא'"], ["יב'"]]
    WEEKS_KEYBOARD = [[f'{i} שבוע/ות']
                      for i in range(MIN_WEEK, MAX_WEEK + 1)] + [['לא ארצה עדכון אוטומטי']]
    RETURN_OPTION = [['🔙חזור']]
    DETAILS = "\n\n💡 לחיצה על התאריך תשלח אתכם ליומן גוגל\n" \
              rf"ללוח מבחנים המלא: <a href='{EXCEL_URL}'>לחץ כאן</a>"

    # noinspection PyTypeChecker
    def __init__(self, bot_token: str, user_info_filepath: str, excel_path: str, use_context=False,
                 update_interval: Union[list, None] = None):

        assert len(
            self.WEEKS_FORMAT) == self.MAX_WEEK, "WEEKS_FORMAT should match the number of WEEKS"

        if not (isinstance(update_interval, list) or update_interval is None):
            raise TypeError(
                f'update_interval expected: list or None, got: {type(update_interval).__name__}')
        if update_interval is None:
            self.update_interval = [7 * i for i in range(self.MAX_WEEK)]
        else:
            self.update_interval = update_interval

        super().__init__(bot_token, use_context=use_context, persistence=SafePicklePersistence('data.pickle'))
        self.bot_token = bot_token
        self.save_users_filepath = user_info_filepath
        self.excel_handler = ExcelWorker(excel_path, self.update_interval)
        self.dispatcher.bot_data['admins'] = {admin_handler.MAINTAINER_ID}

        if not os.path.exists(user_info_filepath):
            with open(user_info_filepath, 'w') as f:
                f.write("""{
                    "9": {},
                    "10": {},
                    "11": {},
                    "12": {},
                    "graduates": {},
                }""")
        self.users = self.get_user_info(user_info_filepath)

        # init command handlers
        start = [CommandHandler('start', self.start), MessageHandler(
            Filters.regex('^▶️התחל$'), self.start)]
        help = [CommandHandler('help', self.help), MessageHandler(
            Filters.regex('^❓עזרה$'), self.help)]
        update = [CommandHandler('update', self.update_one), MessageHandler(
            Filters.regex('^עדכן$'), self.update_one)]
        join_grade = [CommandHandler('join_grade', self.join_grade), MessageHandler(Filters.regex('^הצטרף לכיתה$'),
                                                                                    self.join_grade)]
        leave_grade = [CommandHandler('leave_grade', self.leave_grade), MessageHandler(Filters.regex('^צא מכיתה$'),
                                                                                       self.leave_grade)]
        week = [CommandHandler('notice', self.change_week), MessageHandler(Filters.regex('^שנה אופק התראה$'),
                                                                           self.change_week)]
        stop = [CommandHandler('stop', self.stop_updating_me), MessageHandler(Filters.regex('^עצור עדכון אוטומטי$'),
                                                                              self.stop_updating_me)]
        restart = [CommandHandler('restart', self.start_updating_me),
                   MessageHandler(Filters.regex('^שחזר עדכון אוטומטי$'), self.start_updating_me)]
        cancel = [CommandHandler('cancel', self.cancel), MessageHandler(
            Filters.regex('^🔙חזור$'), self.cancel)]

        setup_handler = ConversationHandler(
            entry_points=start,
            states={
                START: start,
                GRADE: [MessageHandler(Filters.regex('|'.join(self.GRADES)), self.grade)],
                WEEK: [MessageHandler(Filters.regex(f'[{self.MIN_WEEK}-{self.MAX_WEEK}] שבוע/ות') ^ Filters.regex(
                    '^לא ארצה עדכון אוטומטי$'), self.week)],
            },
            fallbacks=cancel,
            persistent=True,
            name='setup conv',
        )

        join_grade_handler = ConversationHandler(
            entry_points=join_grade,
            states={
                START: join_grade,
                GRADE: [MessageHandler(Filters.regex('|'.join(self.GRADES)), self.join_grade_callback)],
            },
            fallbacks=cancel,
            persistent=True,
            name='join grade conv',
        )

        leave_grade_handler = ConversationHandler(
            entry_points=leave_grade,
            states={
                START: leave_grade,
                GRADE: [MessageHandler(Filters.regex('|'.join(self.GRADES)), self.leave_grade_callback)],
            },
            fallbacks=cancel,
            persistent=True,
            name='leave grade conv',
        )

        change_notice_handler = ConversationHandler(
            entry_points=week,
            states={
                START: week,
                WEEK: [MessageHandler(Filters.regex(f'[{self.MIN_WEEK}-{self.MAX_WEEK}] שבוע/ות|לא ארצה עדכון אוטומטי'),
                                      self.week)],
            },
            fallbacks=cancel,
            persistent=True,
            name='change notice conv',
        )

        admin_menu_handler = admin_handler.create_admin_menu(
            additional_states={
                admin_handler.ADMIN_FUNCTIONS: [MessageHandler(Filters.regex('^שם ליוזר-אידי$'), self.get_name),
                                                MessageHandler(Filters.regex('^שלח עדכון$'), self.get_grade)],
                NAME_TO_ID: [MessageHandler(Filters.text
                                            & ~Filters.command
                                            & ~Filters.regex(self.RETURN_OPTION[0][0]), self.name_to_user_id)],
                GET_MESSAGE: [MessageHandler(Filters.regex('|'.join(list(self.GRADES.keys()) + ['כולם'])),
                                             self.get_message)],
                BROADCAST_MESSAGE: [MessageHandler(~Filters.command
                                                   & ~Filters.regex(self.RETURN_OPTION[0][0]),
                                                   self.broadcast_message)],
            },
            menu_button_labels=['שם ליוזר-אידי', 'שלח עדכון', self.RETURN_OPTION[0][0]],
            fallbacks=cancel,
            unhandled_message_handler=self.unknown_message,
            run_async=True,
            persistent=True,
            name='admin menu conv',
        )

        self.add_handler(setup_handler)
        self.add_handler(join_grade_handler)
        self.add_handler(leave_grade_handler)
        self.add_handler(change_notice_handler)
        self.add_handler(admin_menu_handler)
        self.add_handler(help)
        self.add_handler(stop)
        self.add_handler(restart)
        self.add_handler(update)

        self.add_handler(MessageHandler(
            Filters.text, self.unknown_message))

        # update_all scheduler
        scheduler = BackgroundScheduler()
        israel_timezone = ... # tz.gettz('Jerusalem Daylight Time')
        scheduler.add_job(lambda: self.update_all(
            self.bot), trigger='cron', day_of_week='sun', hour='7', minute='00', timezone=israel_timezone)
        scheduler.add_job(lambda : self.increment_grades, trigger='cron', month=9, day=1, hour='0', minute='0', timezone=israel_timezone)
        scheduler.start()

    def add_handler(self, handler):
        if isinstance(handler, (list, tuple)):
            for item in handler:
                self.dispatcher.add_handler(item)
        else:
            self.dispatcher.add_handler(handler)

    def add_task(self, task_func, interval):
        self.job_queue.run_repeating(task_func, interval=interval)

    def run(self):
        self.start_webhook(listen='0.0.0.0',
                           port=int(os.environ.get('PORT', '3333')),
                           url_path=self.bot_token,
                           webhook_url=f'https://yth-event-notifier-production.up.railway.app/{self.bot_token}')
        self.idle()

    @staticmethod
    def get_user_info(filepath) -> dict[str, dict]:
        with open(filepath) as f:
            return json.load(f)

    def save_user_info(self):
        with open(self.save_users_filepath, 'w') as f:
            json.dump(self.users, f, indent=4)

    @staticmethod
    def get_main_menu_labels(update: Update, context: CallbackContext):
        user_id = update.effective_user.id
        admins = context.bot_data['admins']
        return ReplyKeyboardMarkup(keyboard=[['עדכן'], ['שנה אופק התראה'], ['הצטרף לכיתה', 'צא מכיתה'],
                                             ['עצור עדכון אוטומטי', 'שחזר עדכון אוטומטי'],
                                             (['תפריט מנהלים'] if user_id in admins else []), ['▶️התחל', '❓עזרה']])

    def start(self, update: Update, context: CallbackContext):
        # check if it's not the first login
        if any(str(update.effective_user.id) in ids for grades in self.users for ids in self.users[grades].keys()):
            markup = context.user_data['lastMarkup'] = self.get_main_menu_labels(update, context).keyboard
            update.message.reply_text('אתה כבר רשום במערכת\n'
                                      f'תוכל לשנות/לראות נתונים ע"י לחיצה על הכפתור המתאים👇',
                                      reply_markup=ReplyKeyboardMarkup(markup))
            return

        user = update.message.from_user
        logger.info("User %s started the conversation.", user.full_name)
        context.user_data['lastMarkup'] = markup = self.GRADES_KEYBOARD
        update.message.reply_text(text=f"שלום {user.first_name}, באיזה כיתה אתה?",
                                  reply_markup=ReplyKeyboardMarkup(markup, one_time_keyboard=True))
        return GRADE

    @enforce_signup
    def stop_updating_me(self, update: Update, context: CallbackContext):
        for grade in context.user_data['grade']:
            self.users[grade][str(update.effective_user.id)]['wantsUpdate'] = False
        update.message.reply_text(
            "😔 לא תקבל עוד עדכונים...\nאם תתחרט לחץ 'שחזר עדכון אוטומטי'")
        self.save_user_info()

    @enforce_signup
    def start_updating_me(self, update: Update, context: CallbackContext):
        for grade in context.user_data['grade']:
            self.users[grade][str(update.effective_user.id)]['wantsUpdate'] = True
        update.message.reply_text(
            "משבוע הבא תקבל עדכונים אוטומטים!\nכדי להפסיק לחץ 'עצור עדכון אוטומטי'")
        self.save_user_info()

    def grade(self, update: Update, context: CallbackContext):
        result = self.join_grade_callback(update, context)
        if result == GRADE:
            return GRADE
        else:
            markup = context.user_data['lastMarkup'] = self.WEEKS_KEYBOARD
            update.message.reply_text(text=f'בחרת בכיתה {update.message.text} עוד מעט תוכל להצטרף לעוד כיתות\n'
                                           f'אבל לפני שתוכל, הבוט ישלח כל יום ראשון ב7:00 לו"ז של השבועות הבאים (עפ"י '
                                           f'בחירתכם)\nכמה שבועות תרצו לראות מראש?',
                                      reply_markup=ReplyKeyboardMarkup(markup, one_time_keyboard=True))
            return WEEK

    def week(self, update: Update, context: CallbackContext):
        user = str(update.effective_user.id)
        if update.message.text == 'לא ארצה עדכון אוטומטי':
            context.user_data['days'] = 7
            context.user_data['wantsUpdate'] = False
            for grade in context.user_data['grade']:
                self.users[grade][user] = {}
                self.users[grade][user]['days'] = 7
                self.users[grade][user]['wantsUpdate'] = False
                self.users[grade][user]['name'] = update.effective_user.full_name

            context.user_data['lastMarkup'] = self.get_main_menu_labels(update, context).keyboard
            update.message.reply_text("לא תקבל עדכונים שבועיים אך תמיד תוכל לבקש ידנית: /update או 'עדכן'",
                                      reply_markup=self.get_main_menu_labels(update, context))
            self.save_user_info()
        else:

            try:
                weeks = int(update.message.text.replace(' שבוע/ות', ''))
                if weeks < self.MIN_WEEK or weeks > self.MAX_WEEK:
                    update.message.reply_text(
                        f'הזן מספר בין {self.MIN_WEEK} ל{self.MAX_WEEK}')
                    return WEEK

                context.user_data['wantsUpdate'] = True
                context.user_data['days'] = weeks * 7

                # update days
                for grade in context.user_data['grade']:
                    self.users[grade][user] = {}
                    self.users[grade][user]['wantsUpdate'] = True
                    self.users[grade][user]['days'] = weeks * 7
                    self.users[grade][user]['name'] = update.effective_user.full_name

                context.user_data['lastMarkup'] = self.get_main_menu_labels(update, context).keyboard
                update.message.reply_text(f'החל משבוע הבא, תקבל עדכון ל{weeks} שבוע/ות הבא/ים',
                                          reply_markup=self.get_main_menu_labels(update, context))
                self.save_user_info()

            except (IndexError, ValueError):
                context.user_data['lastMarkup'] = self.get_main_menu_labels(update, context).keyboard
                if self.users[user]["wantsUpdate"]:
                    update.message.reply_text(
                        f'אתה מקבל התראה של *__{self.users[user]["days"] // 7} שבוע/ות__*\n'
                        "כדי לשנות: /notice או 'שנה אופק התראה'", parse_mode=ParseMode.MARKDOWN_V2,
                        reply_markup=self.get_main_menu_labels(update, context))
                else:
                    update.message.reply_text("**אינך מקבל התרעות אוטומטיות**\n"
                                              "כדי לקבל: /restart או 'שחזר עדכון אוטומטי'",
                                              parse_mode=ParseMode.MARKDOWN_V2, reply_markup=self.get_main_menu_labels(update, context))

        return ConversationHandler.END

    @enforce_signup
    def join_grade(self, update: Update, context: CallbackContext):
        grades = ','.join(map(lambda g: self.NUM_TO_GRADE[g], context.user_data["grade"]))
        context.user_data['lastMarkup'] = markup = ([grade for grade in self.GRADES_KEYBOARD
                                                    if str(self.GRADES[grade[0]]) not in context.user_data["grade"]]
                                                        + self.RETURN_OPTION)
        update.message.reply_text(f'אתה בכית{"ה" if len(context.user_data["grade"]) == 1 else "ות"} {grades}'
                                  f'\nאם אתה רוצה להצטרף כיתה, בחר את הכיתה החדשה:\n'
                                  f"אם לא לחץ '{self.RETURN_OPTION[0][0]}'",
                                  parse_mode=ParseMode.MARKDOWN_V2,
                                  reply_markup=ReplyKeyboardMarkup(markup, one_time_keyboard=True))
        return GRADE

    @enforce_signup
    def leave_grade(self, update: Update, context: CallbackContext):
        markup = context.user_data['lastMarkup'] = [[grade] for grade, num in self.GRADES.items()
                                                    if str(num) in context.user_data["grade"]] + self.RETURN_OPTION
        update.message.reply_markdown_v2('בחר בכיתה שתרצה לצאת ממנה:\n'
                                         f"אם לא לחץ '{self.RETURN_OPTION[0][0]}'",
                                         reply_markup=ReplyKeyboardMarkup(markup, one_time_keyboard=True))
        return GRADE

    @enforce_signup
    def change_week(self, update: Update, context: CallbackContext):
        if context.user_data["wantsUpdate"]:
            current_grade_msg = f'אתה מקבל התראה של *__{context.user_data["days"] // 7} שבוע/ות__*'
        else:
            current_grade_msg = "**אינך מקבל התרעות אוטומטיות**"
        markup = context.user_data['lastMarkup'] = self.WEEKS_KEYBOARD + self.RETURN_OPTION
        update.message.reply_text(f'{current_grade_msg}\nאם אתה רוצה לשנות בחר אופציה חדשה\n'
                                  f"אם לא לחץ '{self.RETURN_OPTION[0][0]}'",
                                  reply_markup=ReplyKeyboardMarkup(markup),
                                  parse_mode=ParseMode.MARKDOWN_V2)
        return WEEK

    def cancel(self, update: Update, context: CallbackContext):
        context.user_data['lastMarkup'] = self.get_main_menu_labels(update, context).keyboard
        update.message.reply_text(
            'אני עדיין פה אם תצטרך!', reply_markup=self.get_main_menu_labels(update, context))
        return ConversationHandler.END

    def unknown_message(self, update: Update, context: CallbackContext):
        update.message.reply_text(f"לא הבנתי\nבבקשה תשתמש בכפתורים\n",
                                  parse_mode=ParseMode.MARKDOWN_V2,
                                  reply_markup=ReplyKeyboardMarkup(context.user_data['lastMarkup']))

    def join_grade_callback(self, update: Update, context: CallbackContext):
        user = str(update.effective_user.id)

        # get a grade - if there's one
        if 'grade' in context.user_data and context.user_data['grade']:
            prev_grade, *_ = context.user_data['grade']
        else:
            prev_grade = None

        try:
            if 'grade' not in context.user_data or not context.user_data['grade']:
                context.user_data['grade'] = frozenset()

            grade = str(self.GRADES[update.message.text])
            context.user_data['grade'] = context.user_data['grade'].union({grade})
        except KeyError:
            if prev_grade is None:
                context.user_data['lastMarkup'] = markup = self.GRADES_KEYBOARD
                update.message.reply_text('הכיתה שבחרת לא קיימת, בבקשה תשתמש בכפתורים',
                                          reply_markup=ReplyKeyboardMarkup(markup, one_time_keyboard=True))
            else:
                context.user_data['lastMarkup'] = markup = self.GRADES_KEYBOARD + self.RETURN_OPTION
                update.message.reply_text(f"כיתה שבחרת לא קיימת\nאם לא תרצה לשנות לחץ '{self.RETURN_OPTION[0][0]}'",
                                          reply_markup=ReplyKeyboardMarkup(markup, one_time_keyboard=True))

            return GRADE
        else:
            if prev_grade is not None:
                self.users[grade][user] = self.users[prev_grade][user]
                self.save_user_info()
                context.user_data['lastMarkup'] = self.get_main_menu_labels(update, context).keyboard
                update.message.reply_text(
                    'הכיתה הוספה בהצלחה!', reply_markup=self.get_main_menu_labels(update, context))

        return ConversationHandler.END

    @enforce_signup
    def leave_grade_callback(self, update: Update, context: CallbackContext):
        user = str(update.effective_user.id)
        context.user_data['lastMarkup'] = self.get_main_menu_labels(update, context).keyboard
        try:
            grade = str(self.GRADES[update.message.text])
            context.user_data['grade'] = context.user_data['grade'].difference({grade})
        except ValueError:
            update.message.reply_text(f'לא היית בכיתה {update.message.text}', reply_markup=self.get_main_menu_labels(update, context))
        else:
            del self.users[grade][user]
            update.message.reply_text(f'יצאת מכיתה {update.message.text} בהצלחה!\n'
                                      'תוכל תמיד להצטרף שוב 🙂', reply_markup=self.get_main_menu_labels(update, context))
        return ConversationHandler.END

    @catch_errors
    def update_all(self, bot: telegram.Bot) -> None:
        schedule: dict[int, list[list[Event]]] = self.excel_handler.get_schedule(self.update_interval)
        for grade, events in schedule.items():
            for user_id, user_details in self.users[str(grade)].items():
                if 'days' not in user_details or not user_details['wantsUpdate']:
                    continue
                message = f'<u><b>לוח מבחנים של כיתה {self.NUM_TO_GRADE[str(grade)]}</b></u>\n\n' + self.format_schedule(
                    events[:user_details['days'] // 7]) + self.DETAILS
                try:
                    # TODO: add main menu keyboard
                    bot.send_message(chat_id=user_id, text=message, parse_mode=ParseMode.HTML,
                                     disable_web_page_preview=True)
                except Exception:
                    print(f'Failed to update {user_id}')
                finally:
                    time.sleep(1)

    @catch_errors
    @enforce_signup
    def update_one(self, update: Update, context: CallbackContext):
        try:
            schedule: dict[int, list[list[Event]]] = self.excel_handler.get_schedule(
                self.update_interval)
        except RuntimeError as e:
            logger.exception(e)
            update.message.reply_text('חלה שגיאה, נסה שנית')
        else:
            for grade in context.user_data['grade']:
                message = f'<u><b>לוח מבחנים של כיתה {self.NUM_TO_GRADE[grade]}</b></u>\n\n' + \
                          self.format_schedule(schedule[int(grade)][: context.user_data['days'] // 7]) \
                          + self.DETAILS
                update.message.reply_html(text=message, disable_web_page_preview=True, reply_markup=self.get_main_menu_labels(update, context))
                context.user_data['lastMarkup'] = self.get_main_menu_labels(update, context).keyboard

    def help(self, update: Update, context: CallbackContext):
        help_message = ''
        for idx, command in enumerate(context.bot.get_my_commands()):
            help_message += f'{chr(ord("א") + idx)}. /{command.command} - {command.description}\n'
        help_message += '\n\n' + 'לשאלות נוספות אנא פנו ל<a href="t.me/Da_Donut">מנהל הבוט</a>'
        update.message.reply_text(help_message, reply_markup=self.get_main_menu_labels(update, context),
                                  parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        context.user_data['lastMarkup'] = self.get_main_menu_labels(update, context).keyboard

    def format_schedule(self, schedule: list[list[Event]]):
        msg = ''
        for i, week in enumerate(schedule):
            msg += f'<u><b>{self.WEEKS_FORMAT[i]}</b></u>\n'

            # only notice the weeks where there are event
            if len(week) == 0:
                msg += "<b>אין אירועים</b>😁"

            for event in week:
                msg += f'{event: <10|%d/%m/%y}\n'
            msg += '\n'
        return msg

    # admin shit
    def get_name(self, update: Update, _: CallbackContext):
        update.message.reply_text('שלח שם של משתמש:')
        return NAME_TO_ID

    def name_to_user_id(self, update: Update, context: CallbackContext):
        query = update.message.text
        visited = set()
        message = ''
        for users in self.users.values():
            for user_id, user_details in users.items():
                if user_id in visited:
                    continue
                if query.lower() in user_details['name'].lower():
                    message += f'{user_details["name"]} - <pre>{user_id}</pre>\n'
                    visited.add(user_id)
        context.user_data['lastMarkup'] = markup = admin_handler.BUTTON_LABELS
        update.message.reply_html(f'תוצאות:\n\n{message}', reply_markup=ReplyKeyboardMarkup(markup))
        return admin_handler.ADMIN_FUNCTIONS

    def get_grade(self, update: Update, context: CallbackContext):
        context.user_data['lastMarkup'] = markup = [[choice] for choice in (['כולם'] + list(self.GRADES.keys()))]
        update.message.reply_text('בחר את הכיתה אליה תרצה לשלוח עדכון:',
                                  reply_markup=ReplyKeyboardMarkup(markup))
        return GET_MESSAGE

    def get_message(self, update: Update, context: CallbackContext):
        context.user_data['sentTo'] = update.message.text
        update.message.reply_text(('שלח הודעה שתרצה להודיע ל' +
                                   ('כיתה ' if update.message.text != 'כולם' else '') + update.message.text))
        return BROADCAST_MESSAGE

    def broadcast_message(self, update: Update, context: CallbackContext):
        if context.user_data['sentTo'] == 'כולם':
            # set makes sure user doesn't get message twice
            ids = {user_id for users in self.users.values() for user_id in users}
        else:
            ids = self.users[str(self.GRADES[context.user_data['sentTo']])].keys()
        for user_id in ids:
            try:
                context.bot.copy_message(user_id, update.effective_chat.id, update.effective_message.message_id)
            except Exception:
                print(f'failed to update {user_id}')

            time.sleep(1)

        context.user_data['lastMarkup'] = markup = admin_handler.BUTTON_LABELS
        update.message.reply_text('ההודעה נשלחה בהצלחה', reply_markup=ReplyKeyboardMarkup(markup))
        return admin_handler.ADMIN_FUNCTIONS

    def increment_grades(self):
        updated = dict()
        for grade, pupils in self.users.items():
            if grade in ('12', 'graduates'): # seniors will be graduates
                continue
            updated[str(int(grade) + 1)] = pupils

        # reset freshmen
        self.users['9'] = dict()
        # add seniors to graduates
        self.users['graduates'].update(self.users['12'])

