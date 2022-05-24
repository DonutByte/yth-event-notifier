from typing import (
    Optional,
    Tuple,
    overload,
)
from collections import defaultdict
from telegram.ext import PicklePersistence
from telegram.ext.utils.types import UD, CD, BD, ConversationDict, CDCData
import logging
import dill

logger = logging.getLogger(__name__)


class SafePicklePersistence(PicklePersistence):
    @overload
    def update_conversation(
            self, name: str, key: Tuple[int, ...], new_state: Optional[object]
    ) -> None:
        """Will update the conversations for the given handler and depending on :attr:`on_flush`
       save the pickle file.

       Args:
           name (:obj:`str`): The handler's name.
           key (:obj:`tuple`): The key the state is changed for.
           new_state (:obj:`tuple` | :obj:`any`): The new state for the given key.
       """
        if not self.conversations:
            self.conversations = {}
        if self.conversations.setdefault(name, {}).get(key) == new_state:
            return

        # my addition: check that new_state is pickle-able
        if not dill.pickles(new_state):
            logger.log(logging.WARNING, f"state: {new_state} could not be pickled!")
            return

        self.conversations[name][key] = new_state
        if not self.on_flush:
            if not self.single_file:
                filename = f"{self.filename}_conversations"
                self._dump_file(filename, self.conversations)
            else:
                self._dump_singlefile()

    @overload
    def update_user_data(self, user_id: int, data: UD) -> None:
        """Will update the user_data and depending on :attr:`on_flush` save the pickle file.

       Args:
           user_id (:obj:`int`): The user the data might have been changed for.
           data (:class:`telegram.ext.utils.types.UD`): The
               :attr:`telegram.ext.dispatcher.user_data` ``[user_id]``.
       """
        if self.user_data is None:
            self.user_data = defaultdict(self.context_types.user_data)
        if self.user_data.get(user_id) == data:
            return

        # my addition: check that new_state is pickle-able
        if not dill.pickles(data):
            logger.log(logging.WARNING, f"user_data: {data} could not be pickled!")
            return

        self.user_data[user_id] = data
        if not self.on_flush:
            if not self.single_file:
                filename = f"{self.filename}_user_data"
                self._dump_file(filename, self.user_data)
            else:
                self._dump_singlefile()

    @overload
    def update_chat_data(self, chat_id: int, data: CD) -> None:
        """Will update the chat_data and depending on :attr:`on_flush` save the pickle file.

       Args:
           chat_id (:obj:`int`): The chat the data might have been changed for.
           data (:class:`telegram.ext.utils.types.CD`): The
               :attr:`telegram.ext.dispatcher.chat_data` ``[chat_id]``.
       """
        if self.chat_data is None:
            self.chat_data = defaultdict(self.context_types.chat_data)
        if self.chat_data.get(chat_id) == data:
            return

        # my addition: check that new_state is pickle-able
        if not dill.pickles(data):
            logger.log(logging.WARNING, f"chat_data: {data} could not be pickled!")
            return

        self.chat_data[chat_id] = data
        if not self.on_flush:
            if not self.single_file:
                filename = f"{self.filename}_chat_data"
                self._dump_file(filename, self.chat_data)
            else:
                self._dump_singlefile()

    @overload
    def update_bot_data(self, data: BD) -> None:
        """Will update the bot_data and depending on :attr:`on_flush` save the pickle file.

       Args:
           data (:class:`telegram.ext.utils.types.BD`): The
               :attr:`telegram.ext.dispatcher.bot_data`.
       """
        if self.bot_data == data:
            return

        # my addition: check that new_state is pickle-able
        if not dill.pickles(data):
            logger.log(logging.WARNING, f"bot_data: {data} could not be pickled!")
            return

        self.bot_data = data
        if not self.on_flush:
            if not self.single_file:
                filename = f"{self.filename}_bot_data"
                self._dump_file(filename, self.bot_data)
            else:
                self._dump_singlefile()

    @overload
    def update_callback_data(self, data: CDCData) -> None:
        """Will update the callback_data (if changed) and depending on :attr:`on_flush` save the
       pickle file.

       .. versionadded:: 13.6

       Args:
           data (:class:`telegram.ext.utils.types.CDCData`:): The relevant data to restore
               :attr:`telegram.ext.dispatcher.bot.callback_data`.
       """
        if self.callback_data == data:
            return

        # my addition: check that new_state is pickle-able
        if not dill.pickles(data):
            logger.log(logging.WARNING, f"user_data: {data} could not be pickled!")
            return

        self.callback_data = (data[0], data[1].copy())
        if not self.on_flush:
            if not self.single_file:
                filename = f"{self.filename}_callback_data"
                self._dump_file(filename, self.callback_data)
            else:
                self._dump_singlefile()
