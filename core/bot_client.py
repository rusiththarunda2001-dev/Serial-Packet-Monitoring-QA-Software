"""The only file that talks to Google Gemini.

If Google changes its API, only this file needs to change. Every failure is
turned into a BotError with a plain-language message for the user.
"""

from core.bot_files import MAX_REQUEST_FILE_BYTES

MAX_HISTORY_TURNS = 10        # earlier questions/answers sent with a new question
MAX_OUTPUT_TOKENS = 2048
TEMPERATURE = 0.2
REQUEST_TIMEOUT_MS = 60_000

NO_KEY_MESSAGE = (
    "No Gemini API key is set. Click the gear button at the top of this panel and "
    "add your key."
)


class BotError(Exception):
    """A problem talking to Gemini, with a message the user can understand."""


def _import_genai():
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise BotError(
            "The assistant is not installed. Ask whoever installed EC Docklight to "
            "run: pip install -r requirements.txt")
    return genai, types


def friendly_bot_error(exc):
    """Turn any exception from the Gemini library into a plain message."""
    if isinstance(exc, BotError):
        return str(exc)

    code = getattr(exc, "code", None)
    text = str(exc).lower()
    name = type(exc).__name__.lower()

    if code in (401, 403) or "api key not valid" in text or "api_key_invalid" in text:
        return ("Your Gemini API key is not valid. Check it in the assistant settings "
                "(gear button). You can create a new key at aistudio.google.com.")
    if code == 429 or "resource_exhausted" in text or "quota" in text:
        return ("You have reached the usage limit of your Gemini API key. Wait a minute "
                "and try again, or check your plan at aistudio.google.com.")
    if code == 413 or "payload size exceeds" in text or "too large" in text:
        return ("The question with its attached files is too large for Gemini. Remove a "
                "file (or press Clear chat) and try again.")
    if code == 404 or ("model" in text and "not found" in text):
        return ("The selected model is not available for your key. Choose another model "
                "in the assistant settings (gear button).")
    if isinstance(code, int) and code >= 500:
        return "The Gemini service is busy or having problems. Try again in a moment."
    if "timeout" in name or "timed out" in text or "timeout" in text:
        return "Gemini took too long to answer. Try again, or ask a shorter question."
    if ("connect" in name or "network" in name or "getaddrinfo" in text
            or "name resolution" in text or "connection" in text):
        return "Could not reach Gemini. Check your internet connection and try again."
    if code == 400:
        return ("Gemini could not handle this question. Try asking it in a different way, "
                "or press Clear chat and ask again.")
    return "The assistant could not answer ({}). Try again in a moment.".format(
        type(exc).__name__)


class BotClient:
    """Sends a question to Gemini and yields the answer in small pieces."""

    def __init__(self, api_key, model):
        if not (api_key or "").strip():
            raise BotError(NO_KEY_MESSAGE)
        self._api_key = api_key.strip()
        self._model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            genai, types = _import_genai()
            self._client = genai.Client(
                api_key=self._api_key,
                http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
            )
        return self._client

    def stream_reply(self, system_text, history, question, cancel_event=None, attachments=()):
        """Yield pieces of text. history is a list of (role, text) or
        (role, text, attachments) with role 'user' or 'model'; attachments are
        core.bot_files.Attachment objects. Stops early when cancel_event is set."""
        genai, types = _import_genai()
        turns = list(history)[-2 * MAX_HISTORY_TURNS:]
        turns.append(("user", question, tuple(attachments)))
        contents = _build_contents(types, turns)
        config = types.GenerateContentConfig(
            system_instruction=system_text,
            temperature=TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )

        got_text = False
        blocked = False
        stream = None
        try:
            stream = self._get_client().models.generate_content_stream(
                model=self._model, contents=contents, config=config)
            for chunk in stream:
                if cancel_event is not None and cancel_event.is_set():
                    return
                text = None
                try:
                    text = chunk.text
                except Exception:
                    text = None
                if text:
                    got_text = True
                    yield text
                elif _is_blocked(chunk):
                    blocked = True
        except BotError:
            raise
        except GeneratorExit:
            raise
        except Exception as exc:
            raise BotError(friendly_bot_error(exc)) from None
        finally:
            close = getattr(stream, "close", None)
            if close is not None:
                try:
                    close()
                except Exception:
                    pass

        if not got_text and not (cancel_event is not None and cancel_event.is_set()):
            if blocked:
                raise BotError("Gemini did not answer this question because of its safety "
                               "rules. Try asking it in a different way.")
            raise BotError("Gemini sent an empty answer. Try asking again.")

    def test_connection(self):
        """Send a one-word request. Raises BotError with a plain message on failure."""
        for _ in self.stream_reply("Reply with the single word OK.", [], "Test"):
            return
        raise BotError("Gemini sent an empty answer.")


def _attachment_parts(types, attachment):
    if attachment.kind == "pdf":
        return [types.Part(text='Attached file "{}" (PDF document):'.format(attachment.name)),
                types.Part.from_bytes(data=attachment.data, mime_type="application/pdf")]
    note = " (only the first part; the file is longer)" if attachment.truncated else ""
    return [types.Part(text='Attached file "{}"{}:\n----- start of file -----\n{}\n'
                            "----- end of file -----".format(attachment.name, note, attachment.text))]


def _build_contents(types, turns):
    """Gemini contents for the conversation. Files are sent again with every
    question so follow-up questions can use them; when they no longer fit in one
    request, the oldest ones are left out (newest turns get the space first)."""
    budget = MAX_REQUEST_FILE_BYTES
    contents = []
    for turn in reversed(turns):
        role, text = turn[0], turn[1]
        files = turn[2] if len(turn) > 2 else ()
        parts = []
        for attachment in files:
            if attachment.request_size <= budget:
                budget -= attachment.request_size
                parts.extend(_attachment_parts(types, attachment))
            else:
                parts.append(types.Part(text=(
                    '(The file "{}" was attached earlier but is not sent again because of '
                    "the size limit.)").format(attachment.name)))
        if text:
            parts.append(types.Part(text=text))
        if parts:
            contents.append(types.Content(role="model" if role == "model" else "user",
                                          parts=parts))
    contents.reverse()
    return contents


def _is_blocked(chunk):
    feedback = getattr(chunk, "prompt_feedback", None)
    if feedback is not None and getattr(feedback, "block_reason", None):
        return True
    for candidate in getattr(chunk, "candidates", None) or []:
        reason = str(getattr(candidate, "finish_reason", "") or "")
        if "SAFETY" in reason or "PROHIBITED" in reason or "BLOCKLIST" in reason:
            return True
    return False
