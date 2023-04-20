class ConnectException(Exception):
    """Ошибка соединения."""

    pass


class TimeoutException(Exception):
    """Ошибка таймаута."""

    pass


class BadRequestException(Exception):
    """Ошибка отправки запроса."""

    pass


class JSONDecodeException(Exception):
    """Не удалось прочитать json-объект."""

    pass
