from sanic.exceptions import SanicException


class ExtractorError(SanicException):
    pass


class FetchException(Exception):
    pass
