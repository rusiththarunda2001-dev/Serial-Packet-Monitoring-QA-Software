"""Assistant (chatbot) settings, saved for the Windows user, not in the project.

The Gemini API key is kept in Windows Credential Manager, the same place Windows
keeps saved passwords. It is never written to the project file or to any log.
If no key is saved there, the GEMINI_API_KEY environment variable is used.
"""

import json
import os
from pathlib import Path

DEFAULT_MODEL = "gemini-3.8-flash"
MODEL_CHOICES = (
    ("gemini-3.8-flash", "Gemini Flash (recommended)"),
    ("gemini-3.5-flash-lite", "Gemini Flash-Lite (cheaper, simpler answers)"),
)
CREDENTIAL_TARGET = "EC Docklight/Gemini API key"
ENV_KEY_NAME = "GEMINI_API_KEY"

DEFAULT_AI_SETTINGS = {
    "model": DEFAULT_MODEL,
    "share_comm_data": True,
    "privacy_notice_accepted": False,
}


def settings_folder():
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "EC Docklight"


def settings_path():
    return settings_folder() / "ai_settings.json"


def load_ai_settings():
    """Settings as a dict. Missing or damaged files give the defaults."""
    values = dict(DEFAULT_AI_SETTINGS)
    try:
        with open(settings_path(), encoding="utf-8") as handle:
            stored = json.load(handle)
        if isinstance(stored, dict):
            for key in DEFAULT_AI_SETTINGS:
                if key in stored:
                    values[key] = stored[key]
    except (OSError, ValueError):
        pass
    if not isinstance(values["model"], str) or not values["model"].strip():
        values["model"] = DEFAULT_MODEL
    values["share_comm_data"] = bool(values["share_comm_data"])
    values["privacy_notice_accepted"] = bool(values["privacy_notice_accepted"])
    return values


def save_ai_settings(values):
    """Save the settings (never the API key). Raises OSError if it fails."""
    data = {key: values.get(key, default) for key, default in DEFAULT_AI_SETTINGS.items()}
    folder = settings_folder()
    folder.mkdir(parents=True, exist_ok=True)
    with open(settings_path(), "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


# ----------------------------------------------------------------------
# API key
# ----------------------------------------------------------------------

def _win32cred():
    try:
        import win32cred  # pywin32
        return win32cred
    except ImportError:
        return None


def load_saved_api_key():
    """The key saved in Credential Manager, or '' if there is none."""
    cred = _win32cred()
    if cred is None:
        return ""
    try:
        entry = cred.CredRead(CREDENTIAL_TARGET, cred.CRED_TYPE_GENERIC)
    except Exception:
        return ""
    blob = entry.get("CredentialBlob") or b""
    if isinstance(blob, str):
        return blob.strip()
    try:
        return blob.decode("utf-16-le").strip()
    except UnicodeDecodeError:
        return ""


def load_api_key():
    """The key to use: the saved one first, then the GEMINI_API_KEY variable."""
    return load_saved_api_key() or os.environ.get(ENV_KEY_NAME, "").strip()


def api_key_source():
    """'saved', 'environment' or '' (no key)."""
    if load_saved_api_key():
        return "saved"
    if os.environ.get(ENV_KEY_NAME, "").strip():
        return "environment"
    return ""


def save_api_key(key):
    """Save the key in Credential Manager; an empty key removes it.

    Raises RuntimeError with a plain message if it cannot be saved.
    """
    cred = _win32cred()
    if cred is None:
        raise RuntimeError(
            "The API key could not be saved because a Windows component (pywin32) "
            "is missing. You can set the GEMINI_API_KEY environment variable instead.")
    key = (key or "").strip()
    if not key:
        try:
            cred.CredDelete(CREDENTIAL_TARGET, cred.CRED_TYPE_GENERIC)
        except Exception:
            pass  # nothing was saved
        return
    try:
        cred.CredWrite({
            "Type": cred.CRED_TYPE_GENERIC,
            "TargetName": CREDENTIAL_TARGET,
            "UserName": "Gemini",
            "CredentialBlob": key,
            "Persist": cred.CRED_PERSIST_LOCAL_MACHINE,
            "Comment": "Used by the EC Docklight assistant",
        }, 0)
    except Exception:
        raise RuntimeError("The API key could not be saved in Windows Credential Manager.")
