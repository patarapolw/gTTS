# -*- coding: utf-8 -*-
from gtts.tokenizer import pre_processors, Tokenizer, tokenizer_cases
from gtts.utils import _minimize, _clean_tokens, _translate_url
from gtts.lang import tts_langs, _fallback_deprecated_lang
from gtts.gbe.core import gBatchPayload, gBatchExecute
from gtts.version import __version__

import requests
import logging
import base64
import json
import re

from random import randint

__all__ = ["gTTS", "gTTSError"]

# Logger
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class Speed:
    """Read Speed

    The Google TTS Translate API supports two speeds:
        Slow: ``True``
        Normal: ``None``
    """

    SLOW = True
    NORMAL = None


class gTTS:
    """gTTS -- Google Text-to-Speech.

    An interface to Google Translate's Text-to-Speech API.

    Args:
        text (string): The text to be read.
        tld (string): Top-level domain for the Google Translate host,
            i.e `https://translate.google.<tld>`. Different Google domains
            can produce different localized 'accents' for a given
            language. This is also useful when ``google.com`` might be blocked
            within a network but a local or different Google host
            (e.g. ``google.cn``) is not. Default is ``com``.
        lang (string, optional): The language (IETF language tag) to
            read the text in. Default is ``en``.
        slow (bool, optional): Reads text more slowly. Defaults to ``False``.
        lang_check (bool, optional): Strictly enforce an existing ``lang``,
            to catch a language error early. If set to ``True``,
            a ``ValueError`` is raised if ``lang`` doesn't exist.
            Setting ``lang_check`` to ``False`` skips Web requests
            (to validate language) and therefore speeds up instanciation.
            Default is ``True``.
        pre_processor_funcs (list): A list of zero or more functions that are
            called to transform (pre-process) text before tokenizing. Those
            functions must take a string and return a string. Defaults to::

                [
                    pre_processors.tone_marks,
                    pre_processors.end_of_line,
                    pre_processors.abbreviations,
                    pre_processors.word_sub
                ]

        tokenizer_func (callable): A function that takes in a string and
            returns a list of string (tokens). Defaults to::

                Tokenizer([
                    tokenizer_cases.tone_marks,
                    tokenizer_cases.period_comma,
                    tokenizer_cases.colon,
                    tokenizer_cases.other_punctuation
                ]).run

    See Also:
        :doc:`Pre-processing and tokenizing <tokenizer>`

    Raises:
        AssertionError: When ``text`` is ``None`` or empty; when there's nothing
            left to speak after pre-precessing, tokenizing and cleaning.
        ValueError: When ``lang_check`` is ``True`` and ``lang`` is not supported.
        RuntimeError: When ``lang_check`` is ``True`` but there's an error loading
            the languages dictionary.

    """

    GOOGLE_TTS_MAX_CHARS = 200  # Max characters the Google TTS API takes at a time
    GOOGLE_TTS_PATH = "_/TranslateWebserverUi/data/batchexecute"
    GOOGLE_TTS_HEADERS = {
        "Referer": "http://translate.google.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/47.0.2526.106 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
    }
    GOOGLE_TTS_RPC = "jQ1olc"

    def __init__(
        self,
        text,
        tld="com",
        lang="en",
        slow=False,
        lang_check=True,
        pre_processor_funcs=[
            pre_processors.tone_marks,
            pre_processors.end_of_line,
            pre_processors.abbreviations,
            pre_processors.word_sub,
        ],
        tokenizer_func=Tokenizer(
            [
                tokenizer_cases.tone_marks,
                tokenizer_cases.period_comma,
                tokenizer_cases.colon,
                tokenizer_cases.other_punctuation,
            ]
        ).run,
    ) -> None:
    
        # Debug flag
        self.DEBUG = log.getEffectiveLevel() == logging.DEBUG

        if self.DEBUG:
            log.debug(f"gTTS v{__version__}")
            for k, v in dict(locals()).items():
                if k == "self":
                    continue
                log.debug("%s: %s", k, v)

        # Text
        assert text, "No text to speak"
        self.text = text

        # Translate URL top-level domain
        self.tld = tld

        # Language
        self.lang_check = lang_check
        self.lang = lang

        if self.lang_check:
            # Fallback lang in case it is deprecated
            self.lang = _fallback_deprecated_lang(lang)

            try:
                langs = tts_langs()
                if self.lang not in langs:
                    raise ValueError("Language not supported: %s" % lang)
            except RuntimeError as e:
                log.debug(str(e), exc_info=True)
                log.warning(str(e))

        # Read speed
        if slow:
            self.speed = Speed.SLOW
        else:
            self.speed = Speed.NORMAL

        # Pre-processors and tokenizer
        self.pre_processor_funcs = pre_processor_funcs
        self.tokenizer_func = tokenizer_func

    def _tokenize(self, text):
        # Pre-clean
        text = text.strip()

        # Apply pre-processors
        for pp in self.pre_processor_funcs:
            log.debug("pre-processing: %s", pp)
            text = pp(text)

        if len(text) <= self.GOOGLE_TTS_MAX_CHARS:
            return _clean_tokens([text])

        # Tokenize
        log.debug("tokenizing: %s", self.tokenizer_func)
        tokens = self.tokenizer_func(text)

        # Clean
        tokens = _clean_tokens(tokens)

        # Minimize
        min_tokens = []
        for t in tokens:
            min_tokens += _minimize(t, " ", self.GOOGLE_TTS_MAX_CHARS)

        # Filter empty tokens, post-minimize
        tokens = [t for t in min_tokens if t]

        return min_tokens

    def write_to_fp(self, fp):
        """Do the TTS API request and write bytes to a file-like object.

        Args:
            fp (file object): Any file-like object to write the ``mp3`` to.

        Raises:
            :class:`gTTSError`: When there's an error with the API request.
            TypeError: When ``fp`` is not a file-like object that takes bytes.

        """

        # TODO: write_to_fp docs
        # TODO: Proper reqid?
        # TODO: try/except for base64
        # TODO: try/except for gbe decode
        """
        print(f"{quoted_payload_size=}B")
        print(f"{quoted_payload_size/1024=:.2f}KB")

        log.debug("headers-%i: %s", idx, r.request.headers)
        log.debug("url-%i: %s", idx, r.request.url)
        log.debug("status-%i: %s", idx, r.status_code)
        """

        # Tokenize text
        text_parts = self._tokenize(self.text)
        log.debug(f"text_parts: {text_parts}")
        log.debug(f"text_parts: {len(text_parts)}")
        assert text_parts, "No text to send to TTS API"

        # Request(s) URL
        url = _translate_url(tld=self.tld, path=self.GOOGLE_TTS_PATH)

        tts_rpc_payload = [
            gBatchPayload("jQ1olc", [t, self.lang, self.speed, "null"])
            for t in text_parts
        ]

        tts_rpc = gBatchExecute(
            payload=tts_rpc_payload,
            url="https://translate.google.com/_/TranslateWebserverUi/data/batchexecute",
            reqid=randint(0, 99999),
            idx=1,
        )

        with requests.Session() as session:
            raw_response = session.post(
                url=url,
                params=tts_rpc.query,
                data=tts_rpc.data,
                headers=self.GOOGLE_TTS_HEADERS.update(tts_rpc.headers),
            )

        try:
            raw_response.raise_for_status()
        except:
            pass

        try:
            response = tts_rpc.decode(
                raw_response.content, charset=raw_response.encoding
            )

            for segment in response:
                rpcidx, rpcid, data = segment
                base64_audio = data[0]
                audio = base64.b64decode(base64_audio)
                log.debug(f"Wrting {rpcid} ({rpcidx})")
                fp.write(audio)

        except requests.exceptions.HTTPError as e:  # pragma: no cover
            # Request successful, bad response
            log.debug(str(e))
            raise gTTSError(tts=self, response=r)
        except requests.exceptions.RequestException as e:  # pragma: no cover
            # Request failed
            log.debug(str(e))
            raise gTTSError(tts=self)
        except (AttributeError, TypeError) as e:
            raise TypeError(
                "'fp' is not a file-like object or it does not take bytes: %s" % str(e)
            )

    def save(self, savefile):
        """Do the TTS API request and write result to file.

        Args:
            savefile (string): The path and file name to save the ``mp3`` to.

        Raises:
            :class:`gTTSError`: When there's an error with the API request.

        """
        with open(str(savefile), "wb") as f:
            self.write_to_fp(f)
            log.debug("Saved to %s", savefile)


class gTTSError(Exception):
    """Exception that uses context to present a meaningful error message"""

    def __init__(self, msg=None, **kwargs):
        self.tts = kwargs.pop("tts", None)
        self.rsp = kwargs.pop("response", None)
        if msg:
            self.msg = msg
        elif self.tts is not None:
            self.msg = self.infer_msg(self.tts, self.rsp)
        else:
            self.msg = None
        super(gTTSError, self).__init__(self.msg)

    def infer_msg(self, tts, rsp=None):
        """Attempt to guess what went wrong by using known
        information (e.g. http response) and observed behaviour

        """
        cause = "Unknown"

        if rsp is None:
            premise = "Failed to connect"

            if tts.tld != "com":
                host = _translate_url(tld=tts.tld)
                cause = f"Host '{host}' is not reachable"

        else:
            # rsp should be <requests.Response>
            # http://docs.python-requests.org/en/master/api/
            status = rsp.status_code
            reason = rsp.reason

            premise = f"{status} ({reason}) from TTS API"

            if status == 403:
                cause = "Bad token or upstream API changes"
            elif status == 200 and not tts.lang_check:
                cause = (
                    "No audio stream in response. Unsupported language '%s'"
                    % self.tts.lang
                )
            elif status >= 500:
                cause = "Uptream API error. Try again later."

        return f"{premise}. Probable cause: {cause}"
