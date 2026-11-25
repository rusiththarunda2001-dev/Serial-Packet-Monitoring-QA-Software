"""Files the user attaches to a question for the assistant.

A file is read once, when it is attached:
- text files (logs, scripts, CSV...) are sent as text,
- Excel workbooks (.xlsx, e.g. another EC Docklight project) are turned into text,
- PDF documents (device manuals, protocol descriptions) are sent as they are.

Every problem is raised as an AttachmentError with a plain-language message.
"""

from dataclasses import dataclass
from pathlib import Path

TEXT_EXTENSIONS = (".txt", ".log", ".csv", ".md", ".json", ".xml", ".ini", ".cfg")
EXCEL_EXTENSIONS = (".xlsx", ".xlsm")
PDF_EXTENSIONS = (".pdf",)

FILE_DIALOG_TYPES = [
    ("Supported files", " ".join("*" + ext for ext in
                                 PDF_EXTENSIONS + TEXT_EXTENSIONS + EXCEL_EXTENSIONS)),
    ("PDF documents", "*.pdf"),
    ("Text, logs and scripts", " ".join("*" + ext for ext in TEXT_EXTENSIONS)),
    ("Excel workbooks", " ".join("*" + ext for ext in EXCEL_EXTENSIONS)),
]

# Gemini accepts about 20 MB per request; files are sent base64-encoded (+33 %).
MAX_REQUEST_FILE_BYTES = 14 * 1024 * 1024
MAX_PDF_BYTES = MAX_REQUEST_FILE_BYTES
MAX_TEXT_FILE_BYTES = 20 * 1024 * 1024   # larger text files are not read at all
MAX_TEXT_CHARS = 100_000                 # only the first part of a long file is sent
MAX_ATTACHMENTS = 3


class AttachmentError(Exception):
    """A file could not be attached, with a message the user can understand."""


@dataclass(frozen=True)
class Attachment:
    name: str
    kind: str            # "text" or "pdf"
    text: str = ""       # kind "text": the content sent to the assistant
    data: bytes = b""    # kind "pdf": the file itself
    file_size: int = 0   # size of the file on disk
    truncated: bool = False

    @property
    def request_size(self):
        """Bytes this attachment adds to a request."""
        if self.kind == "pdf":
            return len(self.data)
        return len(self.text.encode("utf-8"))

    def label(self):
        """For the chat, e.g. 'manual.pdf (PDF, 1.2 MB)'."""
        kind = "PDF" if self.kind == "pdf" else Path(self.name).suffix.lstrip(".").upper() or "text"
        note = ", only the first part is used" if self.truncated else ""
        return "{} ({}, {}{})".format(self.name, kind, format_size(self.file_size), note)


def format_size(size):
    if size < 1024:
        return "{} bytes".format(size)
    if size < 1024 * 1024:
        return "{:.0f} KB".format(size / 1024)
    return "{:.1f} MB".format(size / (1024 * 1024))


def load_attachment(path):
    """Read a file the user picked. Raises AttachmentError."""
    source = Path(path)
    if not source.is_file():
        raise AttachmentError('The file "{}" was not found.'.format(source))
    extension = source.suffix.lower()
    try:
        size = source.stat().st_size
    except OSError:
        raise AttachmentError('The file "{}" could not be read.'.format(source.name))
    if size == 0:
        raise AttachmentError('The file "{}" is empty.'.format(source.name))

    if extension in PDF_EXTENSIONS:
        return _load_pdf(source, size)
    if extension in EXCEL_EXTENSIONS:
        return _load_excel(source, size)
    if extension in TEXT_EXTENSIONS:
        return _load_text(source, size)
    raise AttachmentError(
        'Files of type "{}" cannot be attached. You can attach PDF documents, text '
        "files (logs, scripts, CSV) and Excel workbooks (.xlsx).".format(extension or source.name))


def _read_bytes(source):
    try:
        return source.read_bytes()
    except PermissionError:
        raise AttachmentError(
            'The file "{}" could not be read. It may be open in another program.'.format(source.name))
    except OSError:
        raise AttachmentError('The file "{}" could not be read.'.format(source.name))


def _load_pdf(source, size):
    if size > MAX_PDF_BYTES:
        raise AttachmentError(
            'The PDF "{}" is too large ({}). The limit is {}. Save only the pages you '
            "need as a new PDF and attach that.".format(
                source.name, format_size(size), format_size(MAX_PDF_BYTES)))
    data = _read_bytes(source)
    if not data.startswith(b"%PDF"):
        raise AttachmentError('"{}" is not a valid PDF document.'.format(source.name))
    return Attachment(name=source.name, kind="pdf", data=data, file_size=size)


def _decode_text(data):
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _limit(text):
    if len(text) <= MAX_TEXT_CHARS:
        return text, False
    cut = text[:MAX_TEXT_CHARS]
    if "\n" in cut:
        cut = cut[:cut.rfind("\n")]  # do not end in the middle of a line
    return cut, True


def _load_text(source, size):
    if size > MAX_TEXT_FILE_BYTES:
        raise AttachmentError('The file "{}" is too large ({}). The limit is {}.'.format(
            source.name, format_size(size), format_size(MAX_TEXT_FILE_BYTES)))
    data = _read_bytes(source)
    if b"\x00" in data[:4096]:
        raise AttachmentError(
            '"{}" does not look like a text file, so it cannot be attached.'.format(source.name))
    text, truncated = _limit(_decode_text(data).replace("\r\n", "\n"))
    return Attachment(name=source.name, kind="text", text=text, file_size=size,
                      truncated=truncated)


def _cell_text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).replace("\n", " ").strip()


def _load_excel(source, size):
    import openpyxl

    try:
        workbook = openpyxl.load_workbook(source, read_only=True, data_only=True)
    except PermissionError:
        raise AttachmentError(
            'The file "{}" could not be read. It may be open in another program.'.format(source.name))
    except Exception:
        raise AttachmentError('"{}" is not a valid Excel workbook.'.format(source.name))

    lines = []
    length = 0
    truncated = False
    has_data = False
    try:
        for sheet in workbook.worksheets:
            lines.append("### Sheet: {}".format(sheet.title))
            for row in sheet.iter_rows(values_only=True):
                cells = [_cell_text(value) for value in row]
                while cells and not cells[-1]:
                    cells.pop()
                if not cells:
                    continue
                line = " | ".join(cells)
                length += len(line) + 1
                if length > MAX_TEXT_CHARS:
                    truncated = True
                    break
                lines.append(line)
                has_data = True
            if truncated:
                break
            lines.append("")
    finally:
        workbook.close()

    text = "\n".join(lines).strip()
    if not has_data:
        raise AttachmentError('The workbook "{}" has no data.'.format(source.name))
    return Attachment(name=source.name, kind="text", text=text, file_size=size,
                      truncated=truncated)
