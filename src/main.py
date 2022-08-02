import warnings
import logging
from telegram.ext import dispatcher
from bot import Bot
import os

from creds import BOT_TOKEN

# BOT_TOKEN = os.environ.get("BOT_TOKEN", None)

warnings.filterwarnings(
    action='ignore',
    category=RuntimeWarning,
    module=r'telegram\.ext\.basepersistence.*'
)
logging.getLogger(dispatcher.__name__).setLevel(logging.CRITICAL)


def main():
    excel_path = 'לוח מבחנים.xlsx'
    bot = Bot(BOT_TOKEN,
              'userdata.json', excel_path, True)
    bot.run()


if __name__ == '__main__':
    main()
