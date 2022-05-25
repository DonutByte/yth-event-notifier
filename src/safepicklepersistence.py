import pickle
from collections import defaultdict
from telegram.ext import PicklePersistence
import logging
import io
logger = logging.getLogger(__name__)


class SafePicklePersistence(PicklePersistence):
    NOT_PICKLE = '__not pickle__'
    @staticmethod
    def is_pickleable(obj):
        f = io.BytesIO()
        try:
            pickle.dump(obj, f)
            return True
        except Exception:
            return False

    @staticmethod
    def senetize(obj):
        if isinstance(obj, (dict, defaultdict)):
            senetized = obj.__class__()
            for key, value in obj.items():
                sub_senetized = SafePicklePersistence.senetize(value)
                if sub_senetized != SafePicklePersistence.NOT_PICKLE:
                    senetized[key] = sub_senetized
            return senetized
        elif isinstance(obj, (list, tuple, set, frozenset)):
            senetized = obj.__class__()
            for ele in obj:
                sub_senetized = SafePicklePersistence.senetize(ele)
                if sub_senetized != SafePicklePersistence.NOT_PICKLE:
                    if isinstance(sub_senetized, (list, tuple, set, frozenset)):
                        senetized = obj.__class__((*senetized, *sub_senetized))
                    else:
                        senetized = obj.__class__((*senetized, sub_senetized))
            return senetized

        if SafePicklePersistence.is_pickleable(obj):
            return obj
        return SafePicklePersistence.NOT_PICKLE

    def _dump_singlefile(self) -> None:
        with open(self.filename, "wb") as file:
            data = {
                'conversations': SafePicklePersistence.senetize(self.conversations),
                'user_data': SafePicklePersistence.senetize(self.user_data),
                'chat_data': SafePicklePersistence.senetize(self.chat_data),
                'bot_data': SafePicklePersistence.senetize(self.bot_data),
                'callback_data': SafePicklePersistence.senetize(self.callback_data),
            }
            pickle.dump(data, file)

    @staticmethod
    def _dump_file(filename: str, data: object) -> None:
        if SafePicklePersistence.is_pickleable(data):
            with open(filename, "wb") as file:
                pickle.dump(SafePicklePersistence.senetize(data), file)