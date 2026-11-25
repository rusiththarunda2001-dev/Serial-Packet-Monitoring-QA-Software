# EC Docklight – user manual for the assistant

EC Docklight is a Windows tool for testing devices that talk over a serial (COM)
port, such as RS232 or RS485 devices. The user defines messages to send ("send
sequences"), messages to look for ("receive sequences"), and can automate a test
with a simple script.

## Main window
- **Send Sequences** list (left, top). Each row has a name and the bytes to send.
  The arrow button (→) on a row sends it once. Click a row to edit it.
  Add a new one with the + button or Edit > Add Send Sequence.
- **Receive Sequences** list (left, bottom). Each row has a tick box (active or
  switched off), a name and the bytes to look for, and an action. Click a row to
  edit it. Add a new one with the + button or Edit > Add Receive Sequence.
- **Communication window** (right, top). Shows everything sent [TX] and received
  [RX], with tabs HEX, ASCII, Decimal and Binary showing the same data in
  different forms. The Clear button empties it.
- **Script Editor** (right, bottom). A grid; one script command per row.
- **Toolbar**: Play starts communication (opens the COM port), Stop closes it.
  The script has its own Play (run / resume), Pause and Stop buttons.
- **Tools > Project Settings**: COM port, baud rate, data bits, parity, stop
  bits, flow control, contents filter and channel aliases.
- **Tools > Show/Hide Chatbot**: shows this assistant. With the **📎 Attach file**
  button the user can attach up to 3 files to a question: PDF documents (device
  manuals, protocol descriptions, up to 14 MB), text files (.txt, .log, .csv, .md,
  .json, .xml, .ini, .cfg) and Excel workbooks (.xlsx). The assistant can then
  answer questions about them, write scripts, or propose send and receive
  sequences, which the user adds with the **Add to project** button.
- **Run > Keyboard Console**: type characters straight to the port.
- Projects are saved as Excel files (.xlsx) with File > Save Project. A project
  holds the settings, the sequences and the script.

## Communication modes (Project Settings)
- **Send/Receive**: one COM port. The app sends and receives on it.
- **Monitoring (receive only)**: two COM ports, both only listened to. Used to
  watch the traffic between two other devices (for example with a monitoring
  cable). Sending, SetRTS and SetDTR are not possible in this mode.

## COM port settings
Baud rate, data bits, parity and stop bits must be the same as the device's
settings, otherwise the received data looks like random characters. Common
settings are 9600 baud, 8 data bits, no parity, 1 stop bit ("9600 8N1").

## Flow control (Project Settings > Flow Control Support)
- **Off**: no handshaking.
- **Manual**: the user switches the RTS and DTR lines on or off. Small status
  lights for RTS, DTR, CTS, DSR, DCD and RI are shown; double-click RTS or DTR to
  switch it. Scripts can use SetRTS / SetDTR only in this mode.
- **Hardware Handshaking – RTS/CTS**: the device tells the app when it may send.
- **Software Handshaking – XON/XOFF**: flow control with special characters.
- **RS485 Transceiver Control**: RTS is set high while sending, for RS485
  converters that need it to switch between sending and receiving.

## Writing sequence data
Data is written as bytes separated by spaces:
- Two-digit HEX values: `50 49 4E 47` (this is "PING").
- Decimal values 0–255 are also accepted when typed in Decimal mode.
- Control characters in angle brackets: `<CR>` (carriage return, 0D),
  `<LF>` (line feed, 0A), `<SP>` (space, 20), `<ESC>` (1B), `<ACK>` (06),
  `<NAK>` (15). Also available: `<BEL> <BS> <HT> <VT> <FF> <SO> <SI> <DLE>
  <DC1> <DC2> <DC3> <DC4> <SYN> <ETB> <CAN> <EM> <SUB> <FS> <GS> <RS> <US>
  <DEL>`. Other names (such as `<STX>`) are not supported; write the HEX value
  instead (STX = 02, ETX = 03).
- The editor can show the data as HEX, ASCII, Decimal or Binary.
- **? bytes (wildcards)**: press F7 in the sequence editor (or type ? in HEX,
  Decimal or Binary mode) to insert a ? byte. In ASCII mode it is shown as <?>.
  - In a **send sequence** a ? is a parameter filled in when the sequence is sent,
    for example the device address on an RS485 / Modbus bus: `? 03 00 00 00 02`
    with checksum CRC-MODBUS. Clicking → asks for the value(s) (HEX, e.g. 05).
    In a script: SendSequence("Read", 0, 1, "05") sends it to address 05;
    several ? bytes take several values, e.g. "05 0A". The checksum is calculated
    after the ? bytes are filled in. A periodic sequence repeats with the values
    entered when it was started.
  - In a **receive sequence** a ? matches any one byte, e.g. `? 03 04` detects a
    reply from any address; `05 03 04` only from address 05.
  - A send sequence with ? bytes cannot be used as an automatic answer.
- Polling several devices on a bus, example:
  SendSequence("Read", 0, 1, "01")
  WaitForSequence("Reply", 1, 500)
  SendSequence("Read", 0, 1, "02")
  WaitForSequence("Reply", 1, 500)
A send sequence can also repeat automatically (Repeat tab, with an interval).

## Checksums
A sequence can get a checksum added automatically (Checksum tab). The checksum
is calculated over all bytes of the sequence and added at the end; the sequence
data itself never contains the checksum bytes. Choose from the list or type one:
- `# (off, no checksum)`
- `MOD256` – one-byte sum; `MOD65536` – two-byte sum
- `XOR` – one-byte XOR
- `LRC` (also `-MOD256`) – negative one-byte sum, so all bytes add up to 0
- `LRC-ASCII` – MODBUS ASCII: LRC over the HEX text after ":", added as two HEX
  characters before a final CR LF
- `CRC-7` (MMC/SD), `CRC-8` (poly 07), `CRC-DOW` (Dallas/Maxim 1-Wire)
- `CRC-CCITT` (poly 1021, init FFFF), `CRC-XMODEM` (poly 1021, init 0000)
- `CRC-16` (IBM/ARC), `CRC-MODBUS L` (MODBUS RTU, low byte first), `CRC-32`
- Your own CRC: `CRC:width,polynomial,init,finalXOR,reflectIn,reflectOut`, values
  in HEX, reflect Yes/No, e.g. `CRC:16,8005,FFFF,0000,Yes,Yes` (= CRC-MODBUS).
- Add ` L` after the name to send a multi-byte result low byte first
  (e.g. `CRC-16 L`); otherwise the high byte comes first.
- Not available: choosing which bytes are covered or where the result goes
  (Docklight's (start,len) and @ options) and ASCII-HEX output (A), except for
  LRC-ASCII as described.
For receive sequences you can choose whether to detect messages with a correct
checksum ("Detect Checksum OK"), a wrong one ("Checksum Wrong") or both.

## Receive sequence actions
When an active receive sequence is detected, its action runs:
- **Answer**: send one of the send sequences back (or "No answer").
- **Comment**: write a comment line in the communication window (optionally
  with a time stamp).
- **Stop**: stop communication.
Only receive sequences with a tick in their box are detected.

## Contents filter and channel aliases
The contents filter chooses what is shown: all data, only channel 1 / [TX],
only channel 2 / [RX], or only comments. Channel aliases replace the names of
the channels in the window with names the user prefers.

## Scripts
A script is a list of commands, one per row in the Script Editor. Rows run from
top to bottom. Text goes inside "double quotes", numbers are written without
quotes, and values are separated by commas. Times are in milliseconds
(1000 ms = 1 second). Sequence names must be written exactly as in the lists
(upper/lower case and spaces around the name are ignored).

Commands (examples):
{command_list}

Notes:
- Run a script with the script Play button. Pause holds it; Stop ends it.
- If communication is not started, use StartCommunication() at the top.
- WaitForSequence only counts receive sequences that are ticked (active). If the
  reply does not arrive in time, a red line says so and the script continues.
- GetReceiveCounter("Name") gives how many times a ticked receive sequence was
  detected since the script started (or since ResetReceiveCounter()). It does not
  wait. On a row of its own it shows the number in the communication window, e.g.
  'Row 4: "Pong" was received 3 time(s) since the script started.' It can also be
  used in a one-line check:
  if GetReceiveCounter("Pong") < 3: Comment("FAIL")
- ResetReceiveCounter() counts all receive sequences from 0 again. It also means
  WaitForSequence only counts replies received after it.
- Replies are counted about 0.1 s after the last byte arrives, so put a short
  Pause(200) before GetReceiveCounter if the reply may still be arriving.
- Createlog saves what is in one tab now (an existing file is replaced).
  StartLogging saves everything from now until StopLogging() or the end of the
  script (an existing file is added to).
- A log file name without a folder is saved next to the project file.
- SetRTS and SetDTR need Flow Control set to Manual.
- ShowMessage shows a window and waits until the user clicks OK.

## Common error messages and what they mean
- "COM1 was not found": the device is unplugged, or a different COM number is
  used. Check Windows Device Manager and Project Settings.
- "COM1 is already being used by another program": close the other program
  (another terminal, another EC Docklight window) and try again.
- "COM1 is not responding": unplug the device, plug it in again, try again.
- "COM1 could not be opened with the current settings": a baud rate, data bits,
  parity or stop bits value the port does not support.
- "Communication is not started": press Play in the toolbar or put
  StartCommunication() at the top of the script.
- "There is no send/receive sequence called …": the name in the script does not
  match a name in the lists.
- "… was not received within … ms": the device did not answer in time. Check the
  cable, the COM settings (baud rate etc.), that the receive sequence data is
  right and that it is ticked, and try a longer wait time.
- "… is not a known command": the command is misspelled; use the list above.
- "This line is not written correctly": a quote, bracket or comma is missing.
- Garbled characters in the ASCII tab: usually a wrong baud rate or other COM
  setting.
- No data at all: wrong COM port, cable not connected, TX/RX lines swapped, or
  the device needs a handshake (check Flow Control).
