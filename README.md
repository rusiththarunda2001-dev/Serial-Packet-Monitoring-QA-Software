# EC Docklight

This project is a serial communication testing and automation application.


## Quick start

```powershell
pip install -r requirements.txt
python main.py
```

## Assistant (chatbot)

Tools > Show/Hide Chatbot opens the Docklight Assistant. It can write scripts,
answer questions about the app and explain the communication window. It uses
Google Gemini with your own API key.

1. Get a free key at https://aistudio.google.com/apikey (sign in with a Google account).
2. In the assistant panel, click the gear button (⚙), paste the key, click
   **Test connection**, then **Save**.

Attaching files: click **📎 Attach file** in the assistant panel to send a PDF
(manual, protocol description; max 14 MB), a text/log/script file or an Excel
workbook with your next question (up to 3 files). Files stay part of the chat for
follow-up questions until **Clear chat**. Ask, for example, "Create the send and
receive sequences from this protocol": the assistant shows them in a box, and
**Add to project** adds them after you confirm (existing sequences are never
changed; names that already exist are skipped).

Where things are kept:

- The API key is stored in Windows Credential Manager ("EC Docklight/Gemini API key").
  It is never written to the project file or to logs. If no key is saved, the
  `GEMINI_API_KEY` environment variable is used.
- Other assistant settings: `%APPDATA%\EC Docklight\ai_settings.json`.

What is sent to Google with each question: the question and earlier chat messages,
the project settings, the send/receive sequence names and data, the current script
and, if "Share communication data" is on, the last 150 lines of the ASCII tab,
plus any files you attach.

The assistant only suggests scripts. The Script Editor changes only when you click
**Insert into script** or **Replace script**. The bot's user manual is in
`core/bot_knowledge.md`; update it when features change.

## Project structure

- `main.py` — application entry point
- `core/` — serial, checksum, matching, and project logic
- `ui/` — Tkinter windows and editors
- `route/` — navigation and action handlers

