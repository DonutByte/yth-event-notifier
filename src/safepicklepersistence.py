import pickle
from collections import defaultdict
from telegram.ext import PicklePersistence
import logging
import io

logger = logging.getLogger(__name__)


class SafePicklePersistence(PicklePersistence):
    NOT_PICKLE = '__not pickle__'
    ITERABLES = list, tuple, set, frozenset

    @staticmethod
    def can_pickle(obj):
        """
        checks if ``obj`` can be pickled
        :param obj: the Python object to run the test on
        :return: if ``obj`` can be pickled without a problem
        """
        f = io.BytesIO()
        try:
            pickle.dump(obj, f)
            return True
        except Exception:
            return False

    @staticmethod
    def sanitize(obj):
        """
        sanitizes the object from objects which cannot be pickled
        :param obj: the object to sanitize
        :return: sanitized object
        """
        if isinstance(obj, (dict, defaultdict)):
            sanitize = obj.__class__()
            for key, value in obj.items():
                sub_sanitized = SafePicklePersistence.sanitize(value)
                if sub_sanitized != SafePicklePersistence.NOT_PICKLE:
                    sanitize[key] = sub_sanitized
            return sanitize
        elif isinstance(obj, SafePicklePersistence.ITERABLES):
            sanitize = obj.__class__()
            for ele in obj:
                sub_sanitized = SafePicklePersistence.sanitize(ele)
                if sub_sanitized != SafePicklePersistence.NOT_PICKLE:
                    if isinstance(sub_sanitized, SafePicklePersistence.ITERABLES):
                        sanitize = obj.__class__((*sanitize, *sub_sanitized))
                    else:
                        sanitize = obj.__class__((*sanitize, sub_sanitized))
            return sanitize

        if SafePicklePersistence.can_pickle(obj):
            return obj
        return SafePicklePersistence.NOT_PICKLE

    def _dump_singlefile(self) -> None:
        """
        dumps only data that can be pickled
        :return: None
        """
        with open(self.filename, "wb") as file:
            data = {
                'conversations': SafePicklePersistence.sanitize(self.conversations),
                'user_data': SafePicklePersistence.sanitize(self.user_data),
                'chat_data': SafePicklePersistence.sanitize(self.chat_data),
                'bot_data': SafePicklePersistence.sanitize(self.bot_data),
                'callback_data': SafePicklePersistence.sanitize(self.callback_data),
            }
            pickle.dump(data, file)

    @staticmethod
    def _dump_file(filename: str, data: object) -> None:
        """
        dumps only data that can be pickled
        :return: None
        """
        if SafePicklePersistence.can_pickle(data):
            with open(filename, "wb") as file:
                pickle.dump(SafePicklePersistence.sanitize(data), file)
