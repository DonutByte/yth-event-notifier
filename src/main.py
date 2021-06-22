from creds import BOT_TOKEN
from bot import Bot
from excel_handler import ExcelWorker

def main():
    excel = ExcelWorker('../לוח מבחנים.xlsx')
    bot = Bot(BOT_TOKEN, '../userdata.json', excel, True)
    bot.run()


if __name__ == '__main__':
    main()
