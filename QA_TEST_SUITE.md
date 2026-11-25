# EC Docklight – QA Test Suite

Manual functional test suite for **EC Docklight V2.3**, a Windows serial (COM port) testing and automation tool built with Python/Tkinter.

| Item | Value |
|---|---|
| Application | EC Docklight V2.3 (`python main.py`) |
| Branch under test | `feature/1.0.0/1234_development` |
| Platform | Windows 10 / 11, 64-bit |
| Python | 3.14 (project `.venv`) |
| Dependencies | `pyserial`, `pywin32`, `openpyxl`, `tksheet`, `google-genai` (see `requirements.txt`) |

---

## 1. How to use this document

- Each test has an **ID**, the **steps**, the **expected result**, a **priority** and a **Result** column to fill in.
  - **P1**: core function. A failure blocks release.
  - **P2**: important. A failure needs a fix or a sign-off.
  - **P3**: minor or cosmetic.
- Result values: `PASS`, `FAIL`, `BLOCKED`, `N/A`. For every `FAIL`, log a defect with the test ID, the steps, a screenshot and the text in the communication window.
- **Smoke run** (about 30 minutes): run every test marked ★ in the ID column.
- **Full regression**: run every test.
- Unless a test says otherwise, start from a fresh launch with *File > New Project*.
- Section 20 lists **risk areas** found while reading the code. Those tests are the most likely to fail, so give them extra attention.

---

## 2. Test environment and setup

### 2.1 Software
| # | Item | Notes |
|---|---|---|
| E1 | Project virtual environment | `python -m venv .venv`, then `.venv\Scripts\pip install -r requirements.txt` |
| E2 | **com0com** virtual null-modem driver | Create the pairs **COM10⇄COM11**, **COM20⇄COM21** and **COM22⇄COM23**. Data written to one port of a pair arrives on the other. |
| E3 | A second serial terminal | RealTerm, Termite or PuTTY. RealTerm is preferred because it can send HEX and show modem lines. It acts as "the device". |
| E4 | Microsoft Excel or LibreOffice Calc | To inspect `.xlsx` project files |
| E5 | Gemini API key | From https://aistudio.google.com/apikey. A second key that is **invalid** is also needed. |

### 2.2 Hardware (needed for flow-control, RS485 and unplug tests)
| # | Item |
|---|---|
| H1 | Two USB-to-serial adapters (FTDI recommended) and a **null-modem cable** with full handshake lines (RTS/CTS, DTR/DSR/DCD, RI) |
| H2 | An on-board COM port, or a PCI card that supports RS485 RTS toggle (optional) |
| H3 | A loop-back plug: TX–RX, RTS–CTS and DTR–DSR/DCD bridged (optional) |

### 2.3 Standard test data
Create these sequences when a test says "standard project". Save the project as `QA_Standard.xlsx`.

**Send sequences**
| # | Name | Sequence (HEX) | Checksum | Meaning |
|---|---|---|---|---|
| 1 | Ping | `50 49 4E 47` | off | "PING" |
| 2 | Pong | `50 4F 4E 47` | off | "PONG" |
| 3 | PingCR | `50 49 4E 47 <CR> <LF>` | off | "PING\r\n" |
| 4 | ModbusRead | `01 03 00 00 00 01` | CRC-MODBUS L | Sent as `01 03 00 00 00 01 84 0A` |
| 5 | SumTest | `50 49 4E 47` | MOD256 | Sent as `50 49 4E 47 2E` |
| 6 | XorTest | `50 49 4E 47` | XOR | Sent as `50 49 4E 47 10` |

**Receive sequences** (all ticked/active)
| # | Name | Sequence | Action |
|---|---|---|---|
| 1 | Ping | `50 49 4E 47` | Answer → Pong |
| 2 | Hello | `48 45 4C 4C 4F` ("HELLO") | Comment `"Hello" received` |
| 3 | Quit | `51 55 49 54` ("QUIT") | Stop (Stop communication ticked) |

**Reference checksums** (independent values for checking results)
| Data | MOD256 | XOR | CRC-MODBUS (low, high) |
|---|---|---|---|
| `50 49 4E 47` | `2E` | `10` | – |
| `01 02 03` | `06` | `00` | – |
| `01 03 00 00 00 01` | – | – | `84 0A` |

---

## 3. Installation and launch (INS)

| ID | Scenario | Steps | Expected result | Pri | Result |
|---|---|---|---|---|---|
| INS-01 ★ | Clean install | In a new folder, create the venv and run `pip install -r requirements.txt` | All packages install without errors | P1 | |
| INS-02 ★ | Launch | `.venv\Scripts\python.exe main.py` | Main window opens. Title is `EC Docklight V2.3 - Untitled`. No console errors. | P1 | |
| INS-03 | Launch with a project argument | `python main.py QA_Standard.xlsx` | Window opens with the project loaded. Title shows `QA_Standard.xlsx` without `*`. | P2 | |
| INS-04 | Launch with a missing file | `python main.py nothere.xlsx` | The console prints `Could not open project file: Project file not found…` and the process exits with code 1 | P2 | |
| INS-05 | Launch with a corrupt file | Rename a `.txt` file to `.xlsx`, then pass it as the argument | `Could not open project file: Could not read project file…`, exit code 1 | P3 | |
| INS-06 | Launch from a different folder | `cd C:\`, then run `python D:\DOCKLIGHT\docklight\main.py` | The app starts. If imports fail, the console explains to run from the project folder. | P3 | |
| INS-07 | Running routes.py directly | `python route\routes.py` | Prints "routes.py is not the app entry point… Run main.py instead" | P3 | |
| INS-08 | Two instances | Start the app twice | Both open independently. The second one can't open a COM port the first is using (see COM-05). | P3 | |

---

## 4. Main window, menus and toolbar (UI)

| ID | Scenario | Steps | Expected result | Pri | Result |
|---|---|---|---|---|---|
| UI-01 ★ | Layout | Inspect the main window | Send Sequences (top left), Receive Sequences (bottom left), Communication window with tabs ASCII/HEX/Decimal/Binary (top right; **HEX** selected), Script Editor grid with 15 empty rows (bottom right), toolbar, COM button (shows `COM1`), status bar `Communication port closed` | P1 | |
| UI-02 | File menu | Open File | New Project…, Open Project…, Save Project, Save Project As…, Exit | P2 | |
| UI-03 | Edit menu | Open Edit | Add Send Sequence, Add Receive Sequence | P2 | |
| UI-04 | Run menu | Open Run | Start Communication, Stop Communication, Keyboard Console | P2 | |
| UI-05 | Tools menu | Open Tools | Project Settings…, Show/Hide Chatbot | P2 | |
| UI-06 | Scripting menu | Open Scripting | Run / Resume Script, Pause Script, Stop Script, Edit Script | P2 | |
| UI-07 | Help > About | Click About EC Docklight | A dialog says "EC Docklight – Serial communication testing and automation tool." | P3 | |
| UI-08 | Toolbar tooltips | Hover over each toolbar button | Start Communication, Stop Communication, Keyboard Console, Show or hide Chatbot, Run or resume the script, Pause the running script, Stop the script and communication | P3 | |
| UI-09 | Script button states at start | Look at the toolbar | Script Play enabled. Script Pause and Script Stop disabled. | P2 | |
| UI-10 | COM button | Click the COM button (top right) | Project Settings opens. Tooltip: "Project Communication Settings". | P2 | |
| UI-11 | Only one dialog at a time | Open the Send editor, then click another row or open Project Settings | The open dialog is brought to the front. A second dialog does not open. | P2 | |
| UI-12 | Window resize | Resize and maximise the window | Panels resize. Nothing overlaps or gets cut off. The scrollbars work. | P3 | |
| UI-13 | Edit Script menu | Scripting > Edit Script | Keyboard focus moves to the Script Editor grid | P3 | |

---

## 5. Project files (PRJ)

| ID | Scenario | Steps | Expected result | Pri | Result |
|---|---|---|---|---|---|
| PRJ-01 ★ | Save As a new project | Create the standard project. File > Save Project As…, name it `QA_Standard` | Saved as `QA_Standard.xlsx` (extension added). The title shows the name without `*`. | P1 | |
| PRJ-02 ★ | Round trip | Close the app, open `QA_Standard.xlsx` | All settings, send sequences (names, data, checksum, periodic, interval), receive sequences (active flag, checksum, detect mode, action and its options), script lines and display mode are restored exactly | P1 | |
| PRJ-03 | Excel layout | Open the file in Excel | Sheets `Sheet01_Settings`, `Sheet02_Send_Sequences`, `Sheet03_Receive_Sequences`, `Sheet04_Script` with header rows. Script rows are numbered from 1. | P2 | |
| PRJ-04 | Save on an existing path | Change a name, then File > Save Project | Saved without a dialog. `*` disappears. | P1 | |
| PRJ-05 | Save on a new project | File > New, then File > Save Project | The Save As dialog opens with `Untitled.xlsx` filled in | P2 | |
| PRJ-06 | Cancel Save As | Click Cancel in the Save dialog | Nothing saved. `*` stays. | P2 | |
| PRJ-07 | Wrong extension | Save As `test.txt` | Saved as `test.xlsx` | P3 | |
| PRJ-08 ★ | Dirty marker | Do each of these in turn: add a sequence, edit one, delete one, tick a receive box, change settings, type in the script, paste into the script, delete a script cell, switch the comm tab | `*` appears in the title after each change | P1 | |
| PRJ-09 ★ | Unsaved changes prompt: Yes | Make a change, then File > New | Prompt "Save changes to the current project before continuing?" Yes saves (Save As if the project has no path) and then starts a new project | P1 | |
| PRJ-10 | Unsaved changes prompt: No | Same, click No | Changes are discarded. A new empty project opens. | P1 | |
| PRJ-11 | Unsaved changes prompt: Cancel | Same, click Cancel | Nothing changes. The current project stays. | P1 | |
| PRJ-12 | Prompt on Open and Exit | Make a change, then do File > Open and File > Exit (and close with the window X) | The same three-way prompt each time. Cancel on Exit keeps the app open. | P1 | |
| PRJ-13 | No prompt when clean | Save, then File > New | No prompt | P2 | |
| PRJ-14 | New Project resets | With the standard project loaded, File > New, then No | Sequence lists empty, settings back to defaults (COM1 9600 8N1, flow Off, filter All, no aliases), comm window cleared, HEX tab selected, title `Untitled` | P1 | |
| PRJ-15 | **New Project clears the script** | Type a script, File > New | Script Editor is empty. **Risk: see R-01.** | P1 | |
| PRJ-16 | Open an invalid file | Open a renamed `.txt` | Error "Could not read project file…". The current project is unchanged. | P2 | |
| PRJ-17 | Unsupported format version | In Excel set `format_version` to `2`, then open | Error "Unsupported project format version: 2" | P3 | |
| PRJ-18 | Missing sheets | Delete `Sheet04_Script` in Excel, then open | Loads without error. The script is empty. | P3 | |
| PRJ-19 | Read-only or locked file | Open the `.xlsx` in Excel (locked), then Save from the app | Error "Could not save project: …". `*` stays. | P2 | |
| PRJ-20 | Blank script rows | Script with rows 1, 3 and 7 filled. Save, then reopen. | Script reloads as 3 consecutive rows (blank rows dropped). Note this, since row numbers in error messages change. | P3 | |
| PRJ-21 | Special characters | Names/comments with `ä € "quote"` and a comma | Saved and restored exactly | P2 | |
| PRJ-22 | **Alias containing a comma** | Channel 1 alias `Dev,A`. Save, then reopen. | Alias restored as `Dev,A`. **Risk: see R-02.** | P3 | |
| PRJ-23 | Large project | 200 send and 200 receive sequences, a 500-row script | Save and open each take under 5 s. The UI stays usable. | P3 | |

---

## 6. Project Settings dialog (SET)

| ID | Scenario | Steps | Expected result | Pri | Result |
|---|---|---|---|---|---|
| SET-01 ★ | Opening | Tools > Project Settings… | Tabs Communication / Flow Control / Comm. Filter / Alias. The Communication tab is shown, its label in bold and blue. | P1 | |
| SET-02 ★ | Port list | Open the Channel 1 drop-down | Lists the COM ports present, sorted by number (COM3 before COM10), plus the saved port even if it isn't present | P1 | |
| SET-03 | No ports on the PC | Disable all COM ports, then open Settings | The combo can be typed into and shows the saved name | P3 | |
| SET-04 | COM setting values | Open each combo | Baud 1200…115200 (7 values), Data bits 5–8, Parity None/Even/Odd/Mark/Space, Stop bits 1/1.5/2, Parity error char 4 values | P2 | |
| SET-05 ★ | Save settings | COM11, 115200, 7E2, OK | The COM button shows `COM11`. `*` appears in the title. Reopening shows the saved values. | P1 | |
| SET-06 | Cancel | Change values, click Cancel | Nothing changes | P2 | |
| SET-07 | Monitoring mode UI | Select "Monitoring (receive only)" | Title becomes "Monitoring: Receive on Comm. Channels". A Channel 2 combo appears with a monitoring hint. Flow-control radios are disabled and a note is shown. | P1 | |
| SET-08 | Monitoring with the same port twice | Channel 1 = Channel 2 = COM21, OK | Warning "Monitoring needs two different COM ports…". The dialog stays open. | P1 | |
| SET-09 | Monitoring OK | COM21 / COM23, OK | The COM button shows `COM21 / COM23` | P1 | |
| SET-10 | Switch back to Send/Receive | Select Send/Receive | Channel 2 is hidden. Flow-control radios are enabled again. | P2 | |
| SET-11 | Alias "original names" | Comm. Filter tab in Send/Receive mode, then in Monitoring mode | Shows TX / RX in Send/Receive, and the selected COM names in Monitoring | P3 | |
| SET-12 ★ | Changing settings while connected | Start communication on COM10, then change the baud rate and click OK | The port is closed and reopened with the new settings. The status bar shows it open. The keyboard console is switched off. | P1 | |
| SET-13 | Flow control bar | Select each flow-control mode and click OK | The status bar shows the right mode label. In **Manual** it also shows RTS/DTR/CTS/DSR/DCD/RI lights. | P2 | |

---

## 7. Communication start/stop and errors (COM)

Setup: COM10⇄COM11 pair, the app on COM10, the terminal on COM11, same settings.

| ID | Scenario | Steps | Expected result | Pri | Result |
|---|---|---|---|---|---|
| COM-01 ★ | Start | Toolbar Play | Status bar: `Communication port COM10 open` | P1 | |
| COM-02 ★ | Stop | Toolbar Stop | `Communication port closed`. The terminal sees the port drop (if the driver shows it). | P1 | |
| COM-03 | Start twice | Press Play twice | No error. Still open. | P2 | |
| COM-04 ★ | Port not found | Set COM99, then Play | Error "Could not start communication. COM99 was not found. Check that the device is plugged in…" | P1 | |
| COM-05 ★ | Port busy | Open COM10 in the terminal, then Play in the app | "COM10 is already being used by another program…" | P1 | |
| COM-06 | Unsupported settings | Choose settings the driver rejects (for example 5 data bits with 2 stop bits on FTDI) | "COM… could not be opened with the current settings…" | P3 | |
| COM-07 | Fast stop/start | Press Stop then Play 10 times quickly | It always reopens. No "access denied" error. | P2 | |
| COM-08 ★ | Cable unplugged while open | USB adapter: start, then unplug | A red line says "The connection to COMx was lost…". Communication stops. Status `Communication port closed`. | P1 | |
| COM-09 | Run menu | Run > Start/Stop Communication | Same as the toolbar buttons | P2 | |
| COM-10 | Exit while open | Start, then File > Exit (project saved) | The app closes cleanly. The port is released, so the terminal can open COM10 straight away. | P2 | |

---

## 8. Send sequences (SND)

| ID | Scenario | Steps | Expected result | Pri | Result |
|---|---|---|---|---|---|
| SND-01 ★ | Add | "Add Sequence" (send panel) or Edit > Add Send Sequence | A row "New Sequence" is added and the "Edit Send Sequence" dialog opens on it | P1 | |
| SND-02 ★ | Edit and OK | Name `Ping`, data `50 49 4E 47`, OK | The row shows `Ping` and `50 49 4E 47`. Dialog closes. | P1 | |
| SND-03 | Apply | Change the name, click Apply | The list updates and the dialog stays open | P2 | |
| SND-04 | Cancel | Change the name, click Cancel | The change is not saved | P2 | |
| SND-05 | Open by clicking a row | Click the name or sequence column | The editor opens for that row. Clicking the arrow (→) column does **not** open it. | P2 | |
| SND-06 | Delete | Delete Sequence | The row is removed and any repeat sending stops | P1 | |
| SND-07 | Reorder with the index | Sequence 3: set Index to 1 (type it, or use `<` `>`), OK | The row moves to position 1 | P2 | |
| SND-08 | Index out of range | Index 99, OK | The row moves to the last position. No crash. | P3 | |
| SND-09 ★ | Send while closed | Click → while communication is stopped | Warning "Start communication before sending a sequence." | P1 | |
| SND-10 ★ | Send | Start, click → on Ping | The terminal receives `PING`. The comm window shows `<timestamp> [TX] - 50 49 4E 47` in blue (HEX tab). | P1 | |
| SND-11 | Control characters | Send PingCR | The terminal gets `PING\r\n`. HEX tab shows `50 49 4E 47` followed by `<CR><LF>`. | P1 | |
| SND-12 | All control names | Send `<ACK> <BEL> <BS> <HT> <LF> <VT> <FF> <CR> <SO> <SI> <DLE> <DC1> <DC2> <DC3> <DC4> <NAK> <SYN> <ETB> <CAN> <EM> <SUB> <ESC> <FS> <GS> <RS> <US> <SP> <DEL>` | Bytes 06 07 08 09 0A 0B 0C 0D 0E 0F 10 11 12 13 14 15 16 17 18 19 1A 1B 1C 1D 1E 1F 20 7F | P2 | |
| SND-13 | Unknown control name | Data `<STX>`, send | Error "Could not encode sequence: Unknown placeholder: <STX>" | P2 | |
| SND-14 | Empty sequence | Empty data, send | Error "Could not encode sequence: Sequence is empty." | P2 | |
| SND-15 ★ | Checksums | Send ModbusRead, SumTest, XorTest | The terminal gets `…84 0A`, `…2E` and `…10` (reference table in 2.3) | P1 | |
| SND-16 ★ | Periodic send | Ping: tick "Send periodically", 1 s, OK. Start, click → | Sent at once and then every 1 s (check the timestamps) | P1 | |
| SND-17 | Minimum interval | Interval `0.01` | Sends no faster than every 100 ms | P2 | |
| SND-18 | Interval 0 or text | Interval `0` or `abc` | No repeat. Sends once. | P3 | |
| SND-19 | Repeat stops | While repeating: Stop communication / delete a sequence / New Project / change settings | Repeat stops in every case and does not start again on the next Start | P1 | |
| SND-20 | Edit while repeating | While repeating, change the interval to 2 s and click OK | Repeat continues at 2 s. Unticking "periodic" stops it. | P2 | |
| SND-21 | Monitoring mode | Monitoring mode, click → | Warning "Sending is not available in Monitoring mode." | P1 | |
| SND-22 | Send queue full | Hardware flow control with CTS held low (H1, the other side's RTS off). Click → more than 256 times, or repeat every 0.1 s. | After 256 queued: a red line "Send of "…" skipped: send queue is full (device is not accepting data)." The UI doesn't freeze. | P3 | |
| SND-23 ★ | Address byte (?) in the editor | Send sequence `Read`: press **F7**, then type `03 00 00 00 02`. Checksum CRC-MODBUS. | Shows `?|03|00|00|00|02|`. The list shows `? 03 00 00 00 02`. The checksum preview says it is calculated when sent. A hint line under the editor explains F7. | P1 | |
| SND-24 | `?` in each mode | Type `?` in HEX/Decimal/Binary. In ASCII press F7, and type `?` | `?` in HEX/Decimal/Binary inserts a ? byte. In ASCII, F7 shows `<?>` and typing `?` is the normal character 3F. Switching modes keeps both correct. | P2 | |
| SND-25 ★ | Manual send asks for the address | Start, click → on `Read`, enter `01` | Dialog "Send Sequence Parameter" shows the sequence. The terminal receives `01 03 00 00 00 02 C4 0B` (CRC computed after filling). | P1 | |
| SND-26 | Parameter dialog checks | Enter `zz`, then `01 02`, then Cancel | Warning for `zz` and for the wrong number of values. Cancel sends nothing. Reopening suggests the last value. | P2 | |
| SND-27 | Several ? bytes | Sequence `? 06 00 ? 00 01`, enter `05 0A` | Sends `05 06 00 0A 00 01` (+ checksum if set) | P3 | |
| SND-28 | Periodic with ? | `Read` periodic every 1 s, click →, enter `05` | Repeats to address 05 with a correct CRC each time | P3 | |
| SND-29 | ? sequence as an automatic answer | A receive sequence answers with `Read` | Note "Automatic answer for "…" failed: send sequence "Read" contains wildcards." Nothing is sent. | P3 | |
| SND-30 | Saved with the project | Save, reopen | `?` bytes are kept | P2 | |

---

## 9. Sequence data editor (EDT): used in both send and receive dialogs

| ID | Scenario | Steps | Expected result | Pri | Result |
|---|---|---|---|---|---|
| EDT-01 ★ | HEX typing | HEX mode, type `5049` | Cells `50|49|` appear automatically. Letters are shown in upper case. | P1 | |
| EDT-02 | HEX invalid characters | Type `G`, `z`, `!` | Ignored (a short beep) | P2 | |
| EDT-03 | Decimal typing | Decimal mode, type `80`, a space, then `73` | Cells `80|73|`. Space (or comma) finishes the byte being typed. | P2 | |
| EDT-04 | Decimal over 255 | Type `300`; then in a new cell type `256` | `300` → cells `30|0|` (30 can't take another digit). `256` → the `6` is refused with a beep and the cell stays `25`. A value is never changed to 255. | P2 | |
| EDT-05 | Binary typing | Type `01010000` | A cell finishes after 8 bits. Only 0/1 accepted. | P2 | |
| EDT-06 | ASCII typing | Type `PING` and a space | Each character becomes one cell. A space becomes byte 20. | P2 | |
| EDT-07 ★ | Switching mode keeps the data | Enter `50 49 4E 47`, switch HEX→ASCII→Decimal→Binary→HEX | Shown as `P I N G` / `80 73 78 71` / `01010000…` and back to `50 49 4E 47` | P1 | |
| EDT-08 | Non-printable bytes in ASCII | Data `0D 0A 41` in ASCII mode | Shown as `0D|0A|A` (hex for non-printable) | P3 | |
| EDT-09 | Control names stay as they are | Data with `<CR>` switched between modes | `<CR>` stays `<CR>` in every mode | P2 | |
| EDT-10 | Position label | Move the cursor | "Pos. x / n" shows the current cell and the number of bytes | P3 | |
| EDT-11 | Backspace and arrow keys | Backspace/←/→ across cells | Edits and moves cell by cell without corrupting separators | P2 | |
| EDT-12 | Enter and Tab | Press Enter or Tab in the field | No new line is inserted | P3 | |
| EDT-13 ★ | Paste | HEX mode: paste `01 03 00 00 00 02`, then `0102`, then `0x0A, 0x0B` | Each value becomes its own cell: `01|03|00|00|00|02|`, `01|02|`, `0A|0B|`. Pasting `01 XY` shows "Nothing was pasted…" and changes nothing. | P1 | |
| EDT-15 ★ | Delete key | `01|03|00|02|`, cursor right after `01`, press Delete | `03` is removed → `01|00|02|`. Bytes are never merged (no `0103`). | P1 | |
| EDT-16 ★ | Typing inside an existing byte | `01|03|`, click before `03`, type `55` | A new byte is inserted: `01|55|03|`. `03` is not changed. | P1 | |
| EDT-17 | Selection | Select across `03|00` (partly), then type `FF` / press Delete / Backspace / Ctrl+X | Every byte touched by the selection is replaced or removed as a whole. Ctrl+X puts it on the clipboard. | P2 | |
| EDT-18 | Paste in other modes | Decimal: paste `1 3 255`. ASCII: paste `A|B` and a text with a line break | `01 03 FF`; ASCII gives `41 7C 42` and `0D 0A` for the line break | P2 | |
| EDT-19 | `|` in ASCII mode | ASCII mode, type `A|B` | Shown as `A|7C|B|`, saved as `41 7C 42` | P3 | |
| EDT-20 | Blocked Ctrl keys | Press Ctrl+T, Ctrl+D, Ctrl+K in the field | Nothing happens (they would swap or delete single characters) | P3 | |
| EDT-21 ★ | Save checks | Try OK with: an empty name; a name used by another sequence of the same list (any upper/lower case); an empty sequence | Each is refused with a clear message and the dialog stays open | P1 | |
| EDT-22 | Repeat time check | Send sequence, Repeat field `abc`, OK | Refused: "…is not a number of seconds…" | P2 | |
| EDT-23 ★ | Add then Cancel | Add a send sequence, press Cancel (or the window X). Same for a receive sequence. | No empty row is left. If the project was saved before, it is not marked changed (`*`). Add → Apply → Cancel keeps the row. | P1 | |
| EDT-24 | Delete asks first | Delete Sequence in the dialog | Asks for confirmation. For a send sequence used as an automatic answer it names those receive sequences, which become "No answer". | P2 | |
| EDT-14 ★ | Global display mode sync | Change the edit mode in the dialog | The comm window tab and both lists change to the same mode. Changing the comm tab while a dialog is open changes the dialog's mode. | P2 | |

---

## 10. Checksums (CHK)

| ID | Scenario | Steps | Expected result | Pri | Result |
|---|---|---|---|---|---|
| CHK-01 ★ | Options | Open the Checksum tab drop-down | 15 entries: off, MOD256, XOR, CRC-MODBUS L, MOD65536, LRC, LRC-ASCII, CRC-7, CRC-8, CRC-DOW, CRC-CCITT, CRC-XMODEM, CRC-16, CRC-32 and a custom `CRC:16,1021,…` example. The field can be typed into. | P1 | |
| CHK-02 ★ | Preview | `50 49 4E 47` with MOD256 in HEX mode | "Preview: {50 49 4E 47} = (2E)" plus the description | P1 | |
| CHK-03 | Preview XOR / CRC | XOR on `50 49 4E 47`; CRC on `01 03 00 00 00 01` | `(10)`; `(84 0A)` | P1 | |
| CHK-04 | Preview with invalid data | Data `<STX>` with MOD256 | "Preview: (invalid sequence)" | P3 | |
| CHK-05 | Preview with checksum off | Select `# (off…)` | Preview area empty | P3 | |
| CHK-06 | Preview follows the mode | Switch to Decimal | The preview shows decimal bytes | P3 | |
| CHK-07 ★ | Standard check values | Send data `31 32 33 34 35 36 37 38 39` ("123456789") with each checksum. Look at the preview and at the bytes the terminal receives. | CRC-7 `75`, CRC-8 `F4`, CRC-DOW `A1`, CRC-CCITT `29 B1`, CRC-XMODEM `31 C3`, CRC-16 `BB 3D`, CRC-MODBUS L `37 4B`, CRC-32 `CB F4 39 26`, MOD256 `DD`, MOD65536 `01 DD`, XOR `31`, LRC `23` | P1 | |
| CHK-08 | Low byte first | Type `CRC-16 L` | Preview and sent bytes `3D BB` | P2 | |
| CHK-09 ★ | Custom CRC | Type `CRC:16,8005,FFFF,0000,Yes,Yes` | Same result as CRC-MODBUS (`4B 37` for "123456789") | P1 | |
| CHK-10 | Invalid checksum text | Type `CRC-99`, `CRC:16,8005,FFFF` and `CRC:8,07,00,00,maybe,No`, then OK | Preview "(checksum not valid)". OK and Apply show a clear error and the dialog stays open. | P1 | |
| CHK-11 | MODBUS ASCII | Send sequence in ASCII mode `:010300000001` followed by `<CR> <LF>`, checksum LRC-ASCII | Sent as `:010300000001FB` + CR LF (the LRC goes before CR LF) | P2 | |
| CHK-12 | Receive with a new CRC | Receive `AA ?` with CRC-CCITT, Detect OK. Send a correct frame, then one with a wrong CRC. | The correct frame is detected, the wrong one isn't. "Checksum Wrong" mode reverses this. | P1 | |
| CHK-13 ★ | Old projects | Open a project saved before this change (MOD256 / XOR / CRC-MODBUS L labels) | Loads. The same checksum is shown and sent as before. | P1 | |
| CHK-14 | Saved with the project | Use a custom CRC with a comment (`CRC-16 L # my note`), save, reopen | Kept exactly, and still works | P2 | |

---

## 11. Receive sequences and detection (RCV)

Setup: standard project, the app on COM10, the terminal on COM11, communication started.

| ID | Scenario | Steps | Expected result | Pri | Result |
|---|---|---|---|---|---|
| RCV-01 ★ | Add | "Add Sequence" (receive panel) | A new row (inactive ☐) is added and the "Edit Receive Sequence" dialog opens. Action tabs: Answer/Comment/Stop/Checksum. | P1 | |
| RCV-02 ★ | Default action | Add a receive sequence | The Comment tab is selected and the Answer tab shows "No answer". The new sequence is ticked (☑). Nothing is sent when it is detected. | P1 | |
| RCV-03 ★ | Tick/untick | Click the Active column | Toggles ☐/☑ without opening the editor. `*` appears in the title. | P1 | |
| RCV-04 ★ | Detection with Comment | Terminal sends `HELLO` | RX line in dark red with `"Hello" received` after it on the same line | P1 | |
| RCV-05 | Inactive is ignored | Untick Hello, send `HELLO` | Plain RX data without a comment | P1 | |
| RCV-06 ★ | Automatic answer | Terminal sends `PING` | The app sends `PONG` back right away (TX line). The terminal receives PONG. | P1 | |
| RCV-07 | "No answer" | Set Ping's answer to "No answer" | No TX on detection. The Answer column shows "No answer". | P2 | |
| RCV-08 | Answer column | Inspect the receive list | Shows the name of the sequence it answers with (blank for Comment/Stop) | P3 | |
| RCV-09 | Answer with control names | Answer sequence contains `<CR>` | Note "Automatic answer for "…" failed: send sequence "…" contains wildcards." | P2 | |
| RCV-10 ★ | Stop action | Terminal sends `QUIT` | "Communication stopped by receive sequence "Quit"." The port closes. | P1 | |
| RCV-11 | Stop with the box unticked | Stop tab chosen, but the checkbox unticked | Detected and shown, but communication keeps running | P3 | |
| RCV-12 | Comment with timestamp | Comment tab: tick "Additional time stamp" | The comment ends with `M/D/YYYY HH:MM:SS.mmm` | P2 | |
| RCV-13 | Default comment text | New receive named `Status reply` | The comment defaults to `"Status" received` (first word) | P3 | |
| RCV-14 | Several matches in one chunk | Terminal sends `PINGxxPING` in one write | Two detections, two answers. The unmatched `xx` is shown between them. | P2 | |
| RCV-15 | Match split by a pause | Send `PI`, wait 500 ms, send `NG` | **Note** the behaviour. RX is grouped by a 120 ms quiet gap, so the match is probably missed. Record it as expected behaviour or a defect. | P2 | |
| RCV-16 | Checksum "Detect OK" | Receive `01 03 00 00 00 01`, CRC-MODBUS, Detect OK. Send `01 03 00 00 00 01 84 0A` | Detected | P1 | |
| RCV-17 | Checksum wrong | Send `01 03 00 00 00 01 00 00` with "Detect OK" | Not detected | P1 | |
| RCV-18 | "Checksum Wrong" mode | Same wrong frame with "Checksum Wrong" | Detected. The line says `Checksum wrong for receive sequence "…".` | P2 | |
| RCV-19 | "Both OK/Wrong" | Send a good frame and a bad frame | Both detected | P2 | |
| RCV-20 | **Checksum frame followed by more bytes** | Good CRC frame followed by `0D 0A` in the same write | **Note** the result. **See R-05.** | P2 | |
| RCV-21 | Delete | Delete Sequence | Row removed | P1 | |
| RCV-22 | Answers after deleting a send sequence | Ping answers with "Pong" (send #2). Delete send #1; then delete Pong. | Ping's Answer column still shows **Pong**; after deleting Pong it shows **No answer** (never another sequence). | P1 | |
| RCV-23 | Answers after reordering | Move Pong from index 2 to 1 with the Index field | Ping still answers with Pong | P2 | |
| RCV-28 | Rename keeps the comment in step | Receive sequence `Reply01` with the automatic comment, rename it to `Reply02` | The comm window shows `"Reply02" received`. A comment you typed yourself is kept. | P3 | |
| RCV-24 | No answer in Monitoring | Monitoring mode, the monitored device sends PING | Detected and commented. Nothing is sent. | P1 | |
| RCV-25 ★ | ? matches any byte | Receive `Reply` = `? 03 04`. The terminal sends `01 03 04 …` and later `05 03 04 …` | Both are detected. The window shows the bytes really received (01… / 05…). | P1 | |
| RCV-26 | Only one address | Receive `05 03 04` | Detected only for address 05 | P2 | |
| RCV-27 | ? with a checksum | `? 03 04` with CRC-MODBUS / Detect OK. Send a correct reply, then one with a wrong CRC. | The correct one is detected, the wrong one isn't | P2 | |

---

## 12. Communication window (DSP)

| ID | Scenario | Steps | Expected result | Pri | Result |
|---|---|---|---|---|---|
| DSP-01 ★ | Four views | Send `50 49 4E 47 0D 0A` | ASCII `PING<CR><LF>`, HEX `50 49 4E 47<CR><LF>`, Decimal `80 73 78 71<CR><LF>`, Binary 8-bit groups. Line endings shown as green control tokens. | P1 | |
| DSP-02 | Line format | Inspect any line | `M/D/YYYY HH:MM:SS.mmm [TX] - data`. TX blue, RX dark red, comments/status green, errors red. | P2 | |
| DSP-03 | CR/LF splits lines | Receive `A\rB\nC\r\nD` | Separate lines with `<CR>`, `<LF>`, `<CR><LF>` markers | P2 | |
| DSP-04 | Non-printable in ASCII | Receive `01 02` | Shown as `..` | P3 | |
| DSP-05 ★ | Clear | Click Clear | All four tabs are emptied | P1 | |
| DSP-06 | Read only | Type in the comm window (keyboard console off) | No text can be typed | P2 | |
| DSP-07 | Auto scroll | Receive 500 lines | The view follows the newest line | P3 | |
| DSP-08 ★ | Filter "channel 1/TX only" | Settings > Comm. Filter, then send and receive | Only TX lines are shown | P2 | |
| DSP-09 | Filter "channel 2/RX only" | Same | Only RX lines | P2 | |
| DSP-10 | Filter "comments only" | Same, with Hello detected | No data lines. Only the comment text (with header). | P2 | |
| DSP-11 | Aliases | Alias 1 `PC`, alias 2 `Device` | Lines show `[PC]` / `[Device]` instead of `[TX]` / `[RX]` | P2 | |
| DSP-12 | Monitoring labels | Monitoring without aliases | Lines show `[COM21]` / `[COM23]` | P2 | |
| DSP-13 | High data rate | 115200 baud, the terminal sends a 1 MB file | The UI stays responsive. No crash. All bytes are shown (compare the count in the HEX tab). | P2 | |

---

## 13. Keyboard console (KBD)

| ID | Scenario | Steps | Expected result | Pri | Result |
|---|---|---|---|---|---|
| KBD-01 | Port not open | Run > Keyboard Console while stopped | Warning "Start communication before using the keyboard console." | P2 | |
| KBD-02 | Monitoring mode | Monitoring, open the keyboard console | Warning "The keyboard console is only available in Send/Receive mode." | P2 | |
| KBD-03 ★ | Typing and sending | Start, enable the console, click in the comm window, type `hello`, Enter | Status bar shows "…Keyboard Console On". The terminal receives `hello` (no CR/LF added). It is echoed as a TX line. | P1 | |
| KBD-04 | Backspace | Type `helo`, Backspace twice, `lo`, Enter | Sends `hello` | P2 | |
| KBD-05 | Turning off | Click the keyboard button again | The console turns off and the comm window is read-only again | P2 | |
| KBD-06 | Switched off automatically | With the console on: Stop communication / change settings / New Project | The console turns off | P2 | |
| KBD-07 | Non-ASCII | Type `é` | Sent as byte `E9` (latin-1). `€` is replaced with `?`. | P3 | |

---

## 14. Flow control and handshake lines (FLW): hardware H1 needed

| ID | Scenario | Steps | Expected result | Pri | Result |
|---|---|---|---|---|---|
| FLW-01 ★ | Off | Flow Off, start | RTS and DTR are on (check on the other side). Data flows freely. | P1 | |
| FLW-02 ★ | Manual indicators | Flow Manual, start | Status bar shows "Manual RTS/DTR Control" with 6 lights. Inputs (CTS/DSR/DCD/RI) follow the other side within about 200 ms. | P1 | |
| FLW-03 ★ | Toggling RTS/DTR | Double-click the RTS light, then DTR | The light and the real line change. Only RTS and DTR have a hand cursor. CTS/DSR/DCD/RI can't be toggled. | P1 | |
| FLW-04 | Manual levels kept across reopen | Set RTS off, Stop, then Start | RTS stays off after reopening, without a glitch | P3 | |
| FLW-05 | Hardware RTS/CTS | Other side drops RTS (our CTS low), send | Data is held. When CTS goes high it is delivered. Stop Communication cancels a held send. | P2 | |
| FLW-06 | Software XON/XOFF | Other side sends XOFF (13), then send | Held until XON (11) | P2 | |
| FLW-07 | RS485 not supported | RS485 mode on a USB adapter, start | Error "COMx does not support 'RS485 Transceiver Control' (RTS toggle)…" | P2 | |
| FLW-08 | RS485 supported | H2 hardware | RTS goes high only while sending (check with a scope or logic analyser) | P3 | |
| FLW-09 | Monitoring ignores flow | Monitoring with any flow setting | The ports open with no handshaking. Neither device is held off. | P2 | |

---

## 15. Monitoring mode (MON)

Setup: the terminal on COM20 (device A) sends to app channel 1 = COM21. A second terminal on COM22 (device B) sends to channel 2 = COM23.

| ID | Scenario | Steps | Expected result | Pri | Result |
|---|---|---|---|---|---|
| MON-01 ★ | Start | Play | Status "Monitoring COM21 (channel 1) and COM23 (channel 2)" | P1 | |
| MON-02 ★ | Two channels | Device A sends `AAA`, device B sends `BBB` | `[COM21] - AAA` in blue, `[COM23] - BBB` in dark red | P1 | |
| MON-03 | Channel 2 missing | Channel 2 = a port that doesn't exist | Error naming the missing port. Channel 1 is closed again (can be reopened). | P2 | |
| MON-04 | Sending blocked | Click →, run SendSequence, SetRTS, open the keyboard console | Each is refused with the monitoring message | P1 | |
| MON-05 | Detection works | Receive sequences match on either channel | Comments are shown. No answers are sent. | P2 | |

---

## 16. Script editor and engine (SCR)

Setup: standard project, the app on COM10, the terminal on COM11 echoing or answering as each test says. Type one command per grid row. Run it with **Script Play**.

### 16.1 Editor and controls
| ID | Scenario | Steps | Expected result | Pri | Result |
|---|---|---|---|---|---|
| SCR-01 ★ | Grid editing | Type, copy, paste, cut, delete, undo, insert/delete rows (right-click) | Works like a spreadsheet. Row numbers are shown. | P1 | |
| SCR-02 | Dirty after row insert/delete | Insert or delete a row from the right-click menu | `*` appears in the title. **See R-06.** | P2 | |
| SCR-03 ★ | Empty script | Play with an empty grid | Info "The script editor is empty." Buttons unchanged. | P1 | |
| SCR-04 ★ | Button states | Play a long script (`Pause(10000)`) | Play disabled, Pause and Stop enabled. When it ends, Play enabled and the others disabled. | P1 | |
| SCR-05 ★ | Pause/Resume | During `SendSequence("Ping",1000,10)` press Pause, wait 5 s, press Play | Sending stops during the pause and continues afterwards. All 10 are sent. | P1 | |
| SCR-06 | Pause holds the timer | `Pause(5000)`. Pause after 1 s for 10 s, then resume. | Total about 15 s (the paused time isn't counted) | P2 | |
| SCR-07 ★ | Stop | Press Stop during a long script | The script stops at once. **Communication is also closed.** Buttons go back to idle. | P1 | |
| SCR-08 | Menu equivalents | Scripting menu Run / Pause / Stop | Same as the buttons | P2 | |
| SCR-09 | Run while running | While a script runs, Scripting > Run / Resume Script | The old run stops and a new run starts from row 1 (confirm this is intended) | P3 | |
| SCR-10 | Row numbers in errors | Error on grid row 5 with blank rows 2–4 | The message says "row 5" | P2 | |

### 16.2 Commands: working cases
| ID | Command | Expected result | Pri | Result |
|---|---|---|---|---|
| SCR-20 ★ | `StartCommunication()` | Port opens (status bar) | P1 | |
| SCR-21 ★ | `SendSequence("Ping", 100, 3)` | 3 × PING, about 100 ms apart, no wait after the last one | P1 | |
| SCR-22 | `SendSequence(" ping ", 0, 1)` | Works (case and surrounding spaces ignored) | P2 | |
| SCR-23 ★ | `WaitForSequence("Ping", 1, 5000)`, then the terminal sends PING within 5 s | Continues as soon as it arrives | P1 | |
| SCR-24 ★ | Same, but nothing is sent | After 5 s a red line: `Row n: "Ping" was not received within 5000 ms. The script continues.` | P1 | |
| SCR-25 | `WaitForSequence("Ping", 3, 5000)`, 2 received | `"Ping" was received only 2 of 3 times…` | P2 | |
| SCR-26 | `WaitForSequence("Ping", -1, 3000)`, 4 received | `"Ping" was received 4 time(s) in 3000 ms.` | P2 | |
| SCR-27 | Detections are not counted twice | Two waits in a row for 1 Ping each, the terminal sends PING once | The 2nd wait doesn't reuse the 1st detection (it times out) | P2 | |
| SCR-28 | Wait opens the port | `WaitForSequence` with the port closed | The port is opened automatically | P3 | |
| SCR-29 | `WaitForSequence(0, 1, 1000)` (number) | Uses receive row 0 (the first one) | P3 | |
| SCR-30 ★ | `Comment("Test started")` | `<timestamp> - Test started` in green, then a blank line, after any data already sent | P1 | |
| SCR-31 | `Pause(500)` | About 500 ms delay | P2 | |
| SCR-32 | `ClearScreen()` | Comm window cleared after data already sent | P2 | |
| SCR-33 ★ | `StopCommunication()` after sends | Queued data is sent first, then the port closes | P1 | |
| SCR-34 | `ShowMessage("Switch on device")` | A dialog appears and the script waits until OK is clicked | P2 | |
| SCR-35 | `SetRTS("ON")` / `SetDTR("off")` with Manual flow | Line changes. `RTS set to ON` / `DTR set to OFF` shown. `1/0/true/false` also accepted. | P2 | |
| SCR-36 | Variables and builtins: `n = WaitForSequence("Ping",1,1000)` then `Comment("got " + str(n))` | `got 0` or `got 1` | P3 | |
| SCR-37 | One-line loop: `for i in range(3): SendSequence("Ping",0,1)` | Sends 3 times | P3 | |
| SCR-38 | Multi-line block: `for i in range(3):` on row 1 and an indented `SendSequence(...)` on row 2 | **Note** the result. Cells are trimmed, so expect a syntax error on row 2. Document it as a limitation or a defect. | P3 | |
| SCR-39 ★ | Terminal answers each PING with PONG. `SendSequence("Ping",100,3)`, `Pause(300)`, then `GetReceiveCounter("Pong")` on its own row | Green line `Row n: "Pong" was received 3 time(s) since the script started.` | P1 | |
| SCR-40 ★ | Count only during the script: the terminal sends PONG 5 times **before** Play, then a script with only `GetReceiveCounter("Pong")` | Shows **0** (detections from before the script are not counted). Running the script again also starts at 0. | P1 | |
| SCR-41 ★ | One-line check: `if GetReceiveCounter("Pong") < 3: Comment("FAIL")` with 2 replies, then with 3 | 2 replies: FAIL comment. 3 replies: no comment. **No** "was received" line for a counter inside an `if`. | P1 | |
| SCR-42 | `ResetReceiveCounter()` after 3 replies, then `GetReceiveCounter("Pong")` | "Receive counters set to 0." then `…received 0 time(s) since the counters were reset.` | P2 | |
| SCR-43 | Reset and WaitForSequence: 1 reply arrives, then `ResetReceiveCounter()`, then `WaitForSequence("Pong",1,1000)` with no new reply | The wait times out (the reply before the reset is not counted) | P2 | |
| SCR-44 | Name details: `GetReceiveCounter(" pong ")` and `GetReceiveCounter(0)` (row number, from 0) | Both count the "Pong" sequence | P3 | |
| SCR-45 | In a value: `Comment("Pong count: " + str(GetReceiveCounter("Pong")))` | `Pong count: 3` | P2 | |
| SCR-46 | Pause while counting | Press Script Pause just before a GetReceiveCounter row, wait, press Play | The counter row runs after Play and counts what arrived in between | P3 | |
| SCR-47 | Late reply | Device answers 50 ms after the request. `SendSequence(...)` then `GetReceiveCounter` immediately, without a Pause | **Note** the result. The reply may not be counted yet (data is grouped after a 0.1 s pause). With `Pause(200)` before it, it is counted. | P3 | |
| SCR-48 ★ | Send to an address: `SendSequence("Read", 0, 1, "05")` | Sends `05 03 00 00 00 02 C5 8F` | P1 | |
| SCR-49 ★ | Poll several addresses: `SendSequence("Read",0,1,"01")`, `WaitForSequence("Reply",1,500)`, the same for 02 (no device) and 05 | 01 and 05 answered. A red "not received within 500 ms" line for 02. | P1 | |
| SCR-76 | Number as the address: `SendSequence("Read", 0, 1, 10)` | Same as `"0A"` | P3 | |
| SCR-77 | Missing address: `SendSequence("Read", 0, 1)` on a sequence with ? | `The send sequence "Read" has 1 parameter byte(s) (?)… Give the value(s) as the 4th value: SendSequence("Read", 0, 1, "05")` | P1 | |
| SCR-78 | Address not needed: `SendSequence("Ping", 0, 1, "05")` on a sequence without ? | `…has no parameter bytes (?), so it does not need the 4th value…` | P2 | |
| SCR-79 | Wrong values: `SendSequence("Read", 0, 1, "GG")` / `"01 02"` / `300` | Plain error naming the problem (not a HEX byte / wrong number of values / not 0–255) | P2 | |

### 16.3 Commands: error handling
Each of these must stop the script with a red `Script stopped at row N: …` line, except where noted.

| ID | Input | Expected message (main part) | Pri | Result |
|---|---|---|---|---|
| SCR-50 ★ | `SendSequence("Ping", 100, 1)` with the port closed | "Communication is not started. Press the Play button…" | P1 | |
| SCR-51 ★ | `SendSequence("Nope", 0, 1)` | `There is no send sequence called "Nope"…` | P1 | |
| SCR-52 | `SendSequence("Ping", "abc", 1)` | "The time between sends in SendSequence must be a number of milliseconds (no letters)…" | P2 | |
| SCR-53 | `SendSequence("Ping", 100, 0)` | "The number of sends in SendSequence must be at least 1…" | P2 | |
| SCR-54 | `SendSequence("Ping", -5, 1)` | "…cannot be below 0…" | P3 | |
| SCR-55 | `SendSequence("Ping")` | "SendSequence is missing a value or has too many. Write it like this: …" | P2 | |
| SCR-56 ★ | `sendsequence("Ping",0,1)` | `"sendsequence" must be written with the same capital letters: SendSequence` | P1 | |
| SCR-57 | `SendSequense("Ping",0,1)` | "…is not a known command. Did you mean SendSequence?" | P2 | |
| SCR-58 | `Foo()` | "…is not a known command. The commands you can use are: …" | P2 | |
| SCR-59 ★ | `SendSequence("Ping", 100, 3` | "This line is not written correctly. Check that text is inside "quotes"…" | P1 | |
| SCR-60 | `ClearScreen` (no brackets) | "ClearScreen needs brackets at the end, like this: ClearScreen()" | P2 | |
| SCR-61 | `import os` | "Lines starting with import are not allowed in a script." | P1 | |
| SCR-62 | `open("x.txt")` / `__import__("os")` | Refused (not a known command / not allowed). No file is created. | P1 | |
| SCR-63 | `WaitForSequence("Ping", 0, 1000)` | "The count in WaitForSequence must be 1 or more (or -1…)" | P2 | |
| SCR-64 | `WaitForSequence("Ping", -1, -1)` | "…count -1 also needs a wait time, otherwise it would wait forever…" | P2 | |
| SCR-65 | `WaitForSequence("Ping", 1, -5)` | "The wait time … must be 0 or more (or -1…)" | P3 | |
| SCR-66 | Wait for an unticked sequence | `The receive sequence "…" is switched off. Tick its box…` | P1 | |
| SCR-67 | `WaitForSequence(99, 1, 100)` | "There is no receive sequence number 99." | P3 | |
| SCR-68 | Communication stopped during a wait | Press toolbar Stop while waiting | Script ends without a crash | P2 | |
| SCR-69 | `SetRTS("ON")` with flow ≠ Manual | `SetRTS only works when Flow Control is set to "Manual"…` | P2 | |
| SCR-70 | `SetDTR("maybe")` | `SetDTR needs "ON" or "OFF". You wrote "maybe"…` | P3 | |
| SCR-71 | `StartCommunication()` with COM99 | "Could not start communication. COM99 was not found…" (no pop-up; shown in the window) | P2 | |
| SCR-72 | `Pause(1.5)` | "The time in Pause must be a number of milliseconds…" | P3 | |
| SCR-73 | `GetReceiveCounter("Nope")` | `There is no receive sequence called "Nope"…` | P2 | |
| SCR-74 | `GetReceiveCounter("Off")` for an unticked sequence | `The receive sequence "Off" is switched off, so it is never counted. Tick its box…` | P2 | |
| SCR-75 | `GetReceiveCounter()` / `ResetReceiveCounter(1)` | "… is missing a value or has too many. Write it like this: …" | P3 | |

---

## 17. Logging from scripts (LOG)

| ID | Scenario | Steps | Expected result | Pri | Result |
|---|---|---|---|---|---|
| LOG-01 ★ | Createlog, project saved | Project saved in `D:\QA\`. Send data, then `Createlog("run1", "ASCII")` | `D:\QA\run1.txt` created with the ASCII tab contents (including replies that arrived just before). Green line "Log saved to …". | P1 | |
| LOG-02 | Createlog, project not saved | Untitled project | The file goes in the application folder | P2 | |
| LOG-03 | Createlog replaces the file | Run it twice | Second message ends with "(the old file was replaced)". The file contains only the latest contents. | P2 | |
| LOG-04 | Each log type | "HEX", "decimal", "BINARY" (any case) | The contents of that tab | P2 | |
| LOG-05 | Wrong type | `Createlog("x", "PDF")` | `The log type "PDF" is not known. Use "HEX", "ASCII", "Decimal" or "Binary"…` | P2 | |
| LOG-06 | Empty name | `Createlog("", "ASCII")` | "Createlog needs a file name…" | P3 | |
| LOG-07 | Folder missing | `Createlog("C:\\nope\\a.txt","ASCII")` | `Could not save the log: the folder "C:\nope" does not exist.` | P2 | |
| LOG-08 | File locked | Open the log in Excel (locked), then run Createlog | "…The file may be open in another program, or the folder may be read-only." | P3 | |
| LOG-09 ★ | StartLogging / StopLogging | `StartLogging("cont","HEX")`, send 3 times, `StopLogging()` | The file holds only the data from after StartLogging, including the last replies. Lines "Logging started: …" and "Logging stopped. The log is saved in …". | P1 | |
| LOG-10 | StartLogging appends | Run the same script twice | The second run adds to the file. The message says "New data is added to the end of the existing file." | P2 | |
| LOG-11 | Log closed when the script ends | StartLogging without StopLogging | At the end: "Logging stopped because the script ended. The log is saved in …" | P1 | |
| LOG-12 | StopLogging without StartLogging | `StopLogging()` | "Logging was not running, so there was nothing to stop." The script continues. | P3 | |
| LOG-13 | StartLogging twice | Two StartLogging lines with different files | The second message says "The previous log file was closed." | P3 | |
| LOG-14 | Stop button while logging | Press Stop mid-script | The log file is closed and readable | P2 | |

---

## 18. Assistant / chatbot (BOT)

Setup: internet access and a valid Gemini key. Delete `%APPDATA%\EC Docklight\ai_settings.json` and the Credential Manager entry "EC Docklight/Gemini API key" before BOT-01.

### 18.1 Panel and settings
| ID | Scenario | Steps | Expected result | Pri | Result |
|---|---|---|---|---|---|
| BOT-01 ★ | Show/hide | Tools > Show/Hide Chatbot, or the toolbar button | The panel opens on the right with the cursor in the message box. Clicking again hides it. | P1 | |
| BOT-02 ★ | No key | Open the panel with no key | Welcome text plus "To use the assistant, add your Gemini API key." and an "Add API key…" button | P1 | |
| BOT-03 | Ask with no key | Send "hi" | Red message "No Gemini API key is set. Click the gear button…" | P1 | |
| BOT-04 ★ | Settings dialog | Gear button (⚙) | Key field (masked •), Show checkbox, link to aistudio.google.com, Model list (Flash, Flash-Lite), share checkbox (ticked by default), Test connection, Save/Cancel | P1 | |
| BOT-05 | Show key | Tick Show | The key is shown in plain text. Untick to mask it again. | P3 | |
| BOT-06 | Link | Click the "How to get a free key" link | The browser opens aistudio.google.com/apikey | P3 | |
| BOT-07 ★ | Test with an empty key | Empty field, no env var, Test connection | "Type your API key first." in red | P2 | |
| BOT-08 ★ | Test with a valid key | Paste a valid key, Test | "Testing…" then "✔ Connected" in green. The button is disabled while testing. | P1 | |
| BOT-09 ★ | Test with an invalid key | Invalid key, Test | "Your Gemini API key is not valid…" in red | P1 | |
| BOT-10 | Test offline | Disconnect the network, Test | "Could not reach Gemini. Check your internet connection…" (record the actual text; **see R-07**) | P2 | |
| BOT-11 | Model test | Test with each model | Each says Connected, or a clear model or busy message | P2 | |
| BOT-12 | Testing doesn't save | Test, then Cancel, then reopen | The key isn't saved | P2 | |
| BOT-13 ★ | Save the key | Save, reopen the settings | The key is shown masked. It is in Windows Credential Manager > Generic: "EC Docklight/Gemini API key". | P1 | |
| BOT-14 ★ | Key not in files | Search the project `.xlsx`, `ai_settings.json` and the comm/log files for the key | **The key isn't found anywhere** | P1 | |
| BOT-15 | Clear the key | Empty the field and Save | The credential is removed | P2 | |
| BOT-16 | Key from the environment | No saved key, set `GEMINI_API_KEY`, restart, open the settings | Note "Using the key from the GEMINI_API_KEY environment variable…". Questions work. | P2 | |
| BOT-17 | Saved key beats the env var | Both set to different keys | The saved key is used | P3 | |
| BOT-18 | Settings saved to file | Change the model and the share option, Save | `%APPDATA%\EC Docklight\ai_settings.json` updated. Kept after a restart. | P2 | |
| BOT-19 | Welcome after adding a key | Add a key from the welcome button | Status line "Settings saved. You can ask a question now." Note: the old "add your key" text stays in the history (**R-08**). | P3 | |

### 18.2 Chatting
| ID | Scenario | Steps | Expected result | Pri | Result |
|---|---|---|---|---|---|
| BOT-30 ★ | Privacy notice | First question ever | A dialog lists what is sent to Google. Cancel = nothing is sent. OK = sent, and the notice isn't shown again (also after a restart). | P1 | |
| BOT-31 ★ | Ask | "How do I add a checksum?" | "You" block, then "Assistant" with the streamed answer. Status "Thinking…" then "Writing…". The Send button changes to "Stop" while it works. | P1 | |
| BOT-32 | Enter / Shift+Enter | Enter sends. Shift+Enter makes a new line. | As described | P2 | |
| BOT-33 | Stop | Press Stop while it is writing | Stops. The partial answer is kept and "Stopped." is shown. | P2 | |
| BOT-34 | Formatting | Ask for a list with bold text | `**bold**` shown in bold, `` `code` `` in monospace, `-`/`*` lists as bullets, `#` headings removed | P3 | |
| BOT-35 | Follow-up | Ask "and for XOR?" after a checksum question | Uses the earlier context (up to 10 earlier turns) | P3 | |
| BOT-36 | Clear chat | Clear chat | History cleared. The welcome message is shown again. Any request in progress is cancelled. | P2 | |
| BOT-37 | Quick prompts | "Write script" | Puts "Write a script that " in the box without sending | P2 | |
| BOT-38 | Quick prompts that send | "Explain error" / "No reply?" | Sent straight away | P2 | |
| BOT-39 ★ | Uses project context | Ask "What are my send sequences?" | The answer lists Ping, Pong, … from the project | P1 | |
| BOT-40 | Sharing off | Untick "Share communication data", then ask "Explain the last error" | The answer says it can't see the communication window | P2 | |
| BOT-41 ★ | Script box | "Write a script that sends Ping 3 times and waits for Pong" | The answer shows a framed script box with "Insert into script" and "Replace script" | P1 | |
| BOT-42 ★ | Script check warnings | Ask for a script that uses a sequence that doesn't exist | The script box shows an orange "Check before using:" list (for example `There is no send sequence called …`) | P2 | |
| BOT-43 ★ | Insert into script | Click "Insert into script" | The lines are added to the end of the Script Editor. Status "Lines added to the end of the script." `*` appears in the title. | P1 | |
| BOT-44 ★ | Replace script | With a script in the editor, click "Replace script" | Asks "Replace the whole script…?" Yes replaces it, No leaves it. | P1 | |
| BOT-45 | Insert while a script runs | Insert while a script is running | Info "A script is running. Stop it first…" | P2 | |
| BOT-46 | Script from the bot runs | Insert the script and press Play | Runs without "is not a known command" errors | P2 | |

### 18.3 Error handling (record the exact message)
| ID | Condition | Expected message | Pri | Result |
|---|---|---|---|---|
| BOT-60 ★ | Invalid key (401/403) | "Your Gemini API key is not valid…" | P1 | |
| BOT-61 | Quota reached (429) | "You have reached the usage limit of your Gemini API key…" | P2 | |
| BOT-62 | Model not available (404) | "The selected model is not available for your key…" | P2 | |
| BOT-63 | Server overloaded (503) | "The Gemini service is busy or having problems…". Switching to Flash-Lite works. | P2 | |
| BOT-64 | No network | "Could not reach Gemini…" (**R-07**: may show "took too long" instead) | P2 | |
| BOT-65 | `google-genai` not installed | Uninstall the package and ask | "The assistant is not installed… pip install -r requirements.txt" | P3 | |
| BOT-66 | UI stays responsive | While a request is waiting, use the rest of the app | The main window still responds | P1 | |

### 18.4 Attaching files and creating sequences
Prepare: a device manual PDF (under 14 MB), a PDF over 14 MB, a `.log` file, a `.txt` over 100,000 characters, an `.xlsx` (for example `QA_Standard.xlsx`), a `.docx`, an empty `.txt`, and a `.png` renamed to `.txt`.

| ID | Scenario | Steps | Expected result | Pri | Result |
|---|---|---|---|---|---|
| BOT-70 ★ | Attach a PDF | 📎 Attach file, pick the manual PDF | "📎 manual.pdf" shown next to the button, with ✕. The file dialog filter shows PDF, text and Excel types. | P1 | |
| BOT-71 ★ | Ask about the PDF | Ask "What baud rate does this device use?" | The question shows "📎 manual.pdf (PDF, x MB)". The answer uses the manual and names it. The 📎 label is cleared after sending. | P1 | |
| BOT-72 | Follow-up question | Ask a second question about the same PDF without attaching it again | Still answered from the PDF (it stays in the chat until Clear chat) | P2 | |
| BOT-73 | Text / log file | Attach the `.log`, ask "Explain the errors in this log" | The answer refers to lines in the log | P1 | |
| BOT-74 | Excel file | Attach `QA_Standard.xlsx`, ask "What sequences are in this file?" | Lists Ping, Pong, … from the sheets | P2 | |
| BOT-75 | Long text file | Attach the long `.txt` | Status "The file is long; only the first part will be sent." The label in the question says "only the first part is used". | P3 | |
| BOT-76 | Rejected files | Attach the `.docx`, the empty `.txt`, the renamed `.png`, and the PDF over 14 MB | A warning for each: type not supported / empty / not a text file / too large. Nothing is attached. | P2 | |
| BOT-77 | Limits | Attach 4 files, or several large PDFs totalling over 14 MB | Only 3 files allowed. The combined-size warning appears. | P3 | |
| BOT-78 | Remove, Clear and empty question | ✕ removes the attachments. Clear chat removes them too. Attach a file and press Send with an empty box. | Removed as described. An empty box with a file sends "Please look at the attached file…". | P2 | |
| BOT-79 | Files kept after an error | Attach a file, disconnect the network, send | Error shown. The 📎 file is attached again, so it can simply be re-sent. | P3 | |
| BOT-80 ★ | Create sequences from a protocol | Attach a protocol PDF or text, ask "Create the send and receive sequences from this protocol" | A box lists the send and receive sequences with HEX data, checksum and action, plus an "Add to project" button. **The bytes match the document exactly, including start/end bytes (STX 02, ETX 03, CR/LF).** | P1 | |
| BOT-81 ★ | Add to project | Click "Add to project", then Yes | Sequences added to the end of both lists. New receive sequences are ticked. `*` in the title. The button changes to "Added" (disabled). Status "Added n send and m receive sequence(s)." | P1 | |
| BOT-82 | Cancel adding | Click "Add to project", then No | Nothing changes | P2 | |
| BOT-83 | Existing names | Ask for a sequence whose name already exists (for example "Ping") and add it | The existing sequence is not changed. Message "… already exists, so it was not added." | P1 | |
| BOT-84 | Answer links | A receive sequence that answers with a new send sequence | After adding, its Answer column shows that send sequence. Sending the trigger bytes makes the app reply. | P2 | |
| BOT-85 | Invalid entries | Ask for something unclear or with bad values | Bad entries listed in orange under "Not included:". Only valid ones can be added. | P3 | |
| BOT-86 | Added sequences work | Send an added send sequence. The terminal sends the reply bytes. | Correct bytes on the wire (checksum appended if set). The reply is detected with its comment. | P1 | |
| BOT-87 | Saved with the project | Save, close, reopen | The added sequences are kept | P2 | |
| BOT-88 | Privacy notice | Delete `ai_settings.json`, then ask the first question | The notice lists "any file you attach with the 📎 button" | P3 | |

---

## 19. Non-functional (NFR)

| ID | Scenario | Steps | Expected result | Pri | Result |
|---|---|---|---|---|---|
| NFR-01 ★ | Long run | Repeat Ping every 0.1 s, with the terminal answering, for 1 hour | No crash. Memory stays stable (Task Manager). UI responsive. | P1 | |
| NFR-02 | Comm window growth | Leave it running overnight without Clear | Note memory use and responsiveness (there is no limit on the window size) | P3 | |
| NFR-03 | Script timing accuracy | `SendSequence("Ping", 50, 100)` | Timestamps 50 ms apart, ±15 ms on average | P3 | |
| NFR-04 | Closing during activity | Exit while a script runs, a repeat is active and a chatbot answer is coming in | Closes cleanly. The port is released. No error output. | P2 | |
| NFR-05 | Display scaling | Run at 100%, 150% and 200% scaling | Dialogs and buttons are readable and nothing is cut off | P3 | |
| NFR-06 | Error messages are plain | Review the messages seen in this run | Plain language, no Python tracebacks shown in the UI | P2 | |

---

## 20. Risk areas found while reading the code (check these first)

These came from reading the source during preparation and have not been confirmed by running the app. Each is linked to a test above.

| Ref | Area | What the code seems to do | Test |
|---|---|---|---|
| R-01 | New Project | `reset_project_state()` doesn't clear the Script Editor, so the old script may stay after File > New | PRJ-15 |
| R-02 | Channel aliases in the file | Aliases are saved joined with `", "` and split on `,` when loaded, so an alias containing a comma may be cut | PRJ-22 |
| R-03 | Receive answers | *Fixed:* answers are stored by position but are now updated when send sequences are moved or deleted (a deleted answer becomes "No answer"). Retest. | RCV-22, RCV-23 |
| R-04 | New receive sequence | *Fixed:* new receive sequences default to Comment / "No answer" and are ticked. Older projects keep their saved actions — check them. | RCV-02 |
| R-05 | Checksum matching | With a checksum on, the frame is taken as *everything from the match to the end of the received chunk*, so trailing bytes (such as CR/LF) may make a good frame fail the checksum | RCV-20 |
| R-06 | Script dirty flag | Only cell edit, paste and delete mark the project as changed. Inserting or deleting rows from the right-click menu may not. | SCR-02 |
| R-07 | Chatbot timeout message | Connect timeouts (blocked network) show "Gemini took too long… ask a shorter question" instead of a network message | BOT-10, BOT-64 |
| R-08 | Chatbot welcome | "To use the assistant, add your Gemini API key" stays visible after a key is saved | BOT-19 |
| R-09 | RX split by pauses | Received data is grouped by a 120 ms quiet gap. A sequence split across two groups is not detected. | RCV-15 |
| R-10 | Multi-line script blocks | Script cells are trimmed, so indented blocks (`for`/`if` bodies on separate rows) can't work | SCR-38 |

---

## 21. Test summary (fill in after the run)

| Area | Total | Pass | Fail | Blocked | N/A |
|---|---|---|---|---|---|
| INS | 8 | | | | |
| UI | 13 | | | | |
| PRJ | 23 | | | | |
| SET | 13 | | | | |
| COM | 10 | | | | |
| SND | 30 | | | | |
| EDT | 24 | | | | |
| CHK | 14 | | | | |
| RCV | 28 | | | | |
| DSP | 13 | | | | |
| KBD | 7 | | | | |
| FLW | 9 | | | | |
| MON | 5 | | | | |
| SCR | 70 | | | | |
| LOG | 14 | | | | |
| BOT | 62 | | | | |
| NFR | 6 | | | | |
| **Total** | **349** | | | | |

| Run info | |
|---|---|
| Tester | |
| Date | |
| Build / commit | |
| Windows version | |
| Serial hardware used | |
| Defects raised | |
