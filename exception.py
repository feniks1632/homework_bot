class APIRequestFail(Exception):
    """Ошибка при запросе к API."""

    pass


class NotTokenException(Exception):
    """Исключение - нет всех токенов."""

    pass
