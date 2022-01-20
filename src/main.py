from creds import BOT_TOKEN, DEV_TOKEN
from bot import Bot
TEST = False


def main():
    excel_path = '../לוח מבחנים.xlsx'
    bot = Bot(DEV_TOKEN if TEST else BOT_TOKEN,
              '../userdata.json', excel_path, True)
    bot.run()


if __name__ == '__main__':
    main()
