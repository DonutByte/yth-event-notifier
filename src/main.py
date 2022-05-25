from bot import Bot
import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", None)
from creds import BOT_TOKEN

def main():
    excel_path = 'לוח מבחנים.xlsx'
    bot = Bot(BOT_TOKEN,
              'userdata.json', excel_path, True)
    bot.run()


if __name__ == '__main__':
    main()
