import json
import logging
import os
import time
from logging.handlers import RotatingFileHandler


import requests
import telegram
from dotenv import load_dotenv


from exception import (
    APIRequestFail,
    NotTokenException,
)


load_dotenv()
PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, 'telegram_bot.log')


logger = logging.getLogger(__name__)
log_format = ('%(asctime)s - [%(levelname)s] - %(name)s - '
              '(%(filename)s).%(funcName)s(%(lineno)d) - %(message)s')

logging.basicConfig(
    level=logging.INFO,
    format=log_format
)


file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5000000, backupCount=5)
stream_handler = logging.StreamHandler()
logger.addHandler(file_handler)
logger.addHandler(stream_handler)


logger.debug('Бот начинает свою работу!')


RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens() -> bool:
    """Проверка загрузки переменных из .env."""
    logger.debug('Загружаем переменные из .env')
    if not PRACTICUM_TOKEN:
        logger.critical('Нет токена PRACTICUM_TOKEN')
        return False
    if not TELEGRAM_TOKEN:
        logger.critical('Нет токена TELEGRAM_TOKEN')
        return False
    if not TELEGRAM_CHAT_ID:
        logger.critical('Нет токена TELEGRAM_CHAT_ID')
        return False
    logger.debug('Все токены успешно получены')
    return True


def send_message(bot, message):
    """Функция для отправки сообщения в телеграмм."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except telegram.TelegramError:
        logger.error('Ошибка при отправке сообщения в телеграмм')
    else:
        logger.debug(
            f'Бот отправил сообщение: {message}\n'
            f'пользователю с id: {TELEGRAM_CHAT_ID}'
        )


def get_api_answer(timestamp):
    """Запрос АПИ домашки.
    На вход - момент времени в Unix-time.
    На выход - словарь с последней домашкой, если получен,
    или пустой словарь, если были ошибки в соединении или ответе.
    """
    params = {'from_date': timestamp}
    homework_valid_json = dict()
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=params
        )
        if response.status_code != requests.codes.ok:
            message = 'Сервер домашки не вернул статус 200.'
            raise requests.exceptions.HTTPError(message)
        homework_valid_json = response.json()
    except requests.exceptions.RequestException as e:
        raise APIRequestFail(f'Ошибка API {e}')
    except json.JSONDecodeError as e:
        raise APIRequestFail(f'Ошибка json {e}')
    return homework_valid_json


def check_response(response):
    """Функция для проверки существования ключа в ответе."""
    if not isinstance(response, dict):
        raise TypeError('Неверный формат данных, ожидаем словарь')
    if (homeworks := response.get('homeworks')) is None:
        raise KeyError('В ответе API нет ключа homeworks')
    if not isinstance(homeworks, list):
        raise TypeError('Неверный формат homeworks, ожидаем список')


def parse_status(homework):
    """Функция для проверки существования ключа в ответе."""
    logger.debug('Парсим данные домашки')
    (current_status_homework := homework.get('status'))
    logger.debug(f'Текущий статус работы {current_status_homework}')
    if (current_status_homework is None) or (
        current_status_homework not in HOMEWORK_VERDICTS
    ):
        raise KeyError(f'Ошибка с ключом {current_status_homework}')
    verdict = HOMEWORK_VERDICTS.get(homework.get('status'))
    homework_name = homework.get('homework_name')
    if not homework_name:
        raise KeyError('В домашней работе нет ключа "homework_name"')
    logger.debug(f'Имя текущей работы - {homework_name}')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная функция для запуска бота.
    Этапы:
    1 - Проверяем загрузку токенов из .env
    2 - Инициализируем бота
    3 - Инициализируем переменную для сохранения исключений
    4 - Инициализируем текущее время
    5 - Создаем бесконечный цикл
    6 - Получаем ответ API Яндекс.Домашка
    7 - Проверяем ответ
    8 - Получаем статус ответа
    9 - Отправляем сообщение в телеграмм
    10 - Ставим паузу на 10 минут
    11 - Обрабатываем исключения, при повторной ошибке сообщение не отправляем
    """
    if check_tokens():
        logger.info('Токены впорядке')
    else:
        logger.critical(
            'Не обнаружен один из ключей PRACTICUM_TOKEN,'
            'TELEGRAM_TOKEN, TELEGRAM_CHAT_ID'
        )
        raise NotTokenException(
            'Нет токена.'
        )
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    previous_exception = None
    while True:
        try:
            timestamp = int(time.time())
            response = get_api_answer(timestamp=timestamp)
            check_response(response)
            if 'homeworks' in response and len(response['homeworks']) > 0:
                last_homework = response['homeworks'][0]
                new_message = parse_status(last_homework)
                send_message(bot=bot, message=new_message)
                previous_exception = None
        except Exception as error:
            message = ('В работе бота произошла ошибка: '
                       f'{error}')
            logger.error()
            logger.info('Бот отправляет в Телеграм сообщение '
                        'об ошибке в своей работе.')
            send_message(bot, message)

            if str(previous_exception) != str(error):
                send_message(bot, message)
            previous_exception = error
        finally:
            mins = int(RETRY_PERIOD / 60)
            message = (
                f'Нет результатов проверки домашнего задания. '
                f'Повторим запрос через {mins} минут'
            )
            send_message(bot, message)
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':

    main()
