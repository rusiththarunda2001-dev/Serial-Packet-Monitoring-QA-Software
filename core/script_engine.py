"""Python Script Execution Engine."""

import threading
import time
import traceback
import tkinter.messagebox as messagebox


def _format_script_error(error):
    if isinstance(error, (NameError, SyntaxError)):
        return "[ERR] Invalid command"

    if isinstance(error, SyntaxError):
        line_number = error.lineno
        description = "Script syntax error"
        details = error.msg
    else:
        script_frames = [
            frame
            for frame in traceback.extract_tb(error.__traceback__)
            if frame.filename == "<string>"
        ]
        line_number = script_frames[-1].lineno if script_frames else None
        description = "Script error"
        details = str(error)

    if line_number is not None:
        return "{} on line {}: {}".format(description, line_number, details)
    return "{}: {}".format(description, details)


class CustomScriptCommands:
    """Provides the 5 specific custom commands to the execution environment."""
    def __init__(self, home_page):
        self.home = home_page

    def Pause(self, milliseconds):
        """Pauses the script execution for the specified time in milliseconds."""
        try:
            freq_ms = int(milliseconds)
        except ValueError:
            self.home.after(0, lambda: self.home._append_comm_line(
                "Pause Error: Time must be an integer representing milliseconds.", 
                tag="error", show_channel=False
            ))
            return

        # Convert to seconds for time.sleep
        sleep_time = freq_ms / 1000.0
        
        # Break the sleep into tiny steps so it stays highly responsive 
        # to the UI "Pause" and "Stop" script button flags
        steps = max(1, int(sleep_time / 0.05))
        for _ in range(steps):
            # 1. Stop Check
            if getattr(self.home, "_script_stopped", False):
                raise SystemExit()

            # 2. Pause Check (Hold thread execution until unpaused)
            while getattr(self.home, "_script_paused", False):
                if getattr(self.home, "_script_stopped", False):
                    raise SystemExit()
                time.sleep(0.1)

            time.sleep(sleep_time / steps)



    def Comment(self, message):
            """Prints a message with a timestamp, followed by a blank line."""
            text = str(message)
            def _log():
                # Grab the timestamp manually from the home page
                timestamp = self.home._format_comm_timestamp()
                
                # Format the text with the timestamp, omitting the [TX] channel label
                full_message = f"{timestamp} - {text}"
                
                # Use show_channel=False to prevent the UI from auto-generating the [TX]/[RX] header
                self.home._append_comm_line(full_message, tag="status", show_channel=False)
                self.home._append_comm_blank_line()
                
            self.home.after(0, _log)

    def SendSequence(self, sequence_name, frequency, count):
            """Sends a named sequence count times, pausing frequency milliseconds between sends."""
            
            
            if not self.home.comm_service.is_connected():
                self.home.after(0, lambda: messagebox.showwarning(
                    "Script Engine",
                    "Please start communication (Play button) before running a script, or add StartCommunication() to your script.",
                    parent=self.home,
                ))
                raise SystemExit()
                
            seq_name = str(sequence_name)
            
            try:
                freq_ms = int(frequency)
                loops = int(count)
            except ValueError:
                self.home.after(0, lambda: self.home._append_comm_line(
                    "SendSequence Error: Frequency and Count must be integers.", 
                    tag="error", show_channel=False
                ))
                return

            target_index = -1
            for index, row in enumerate(self.home._send_rows):
                if row[1] == seq_name:
                    target_index = index
                    break

            if target_index != -1:
                for _ in range(loops):
                    # --- CHECK FOR CONTROL FLAGS ---
                    # 1. Stop Check
                    if getattr(self.home, "_script_stopped", False):
                        raise SystemExit()

                    # 2. Pause Check (Hold thread execution execution until unpaused)
                    while getattr(self.home, "_script_paused", False):
                        if getattr(self.home, "_script_stopped", False):
                            raise SystemExit()
                        time.sleep(0.1)

                    self.home.after(0, lambda idx=target_index: self.home._send_sequence_by_index(idx))
                    
                    # Sleep increments safely to allow interrupt response
                    sleep_time = freq_ms / 1000.0
                    steps = max(1, int(sleep_time / 0.05))
                    for _ in range(steps):
                        if getattr(self.home, "_script_stopped", False):
                            raise SystemExit()
                        time.sleep(sleep_time / steps)
            else:
                self.home.after(0, lambda msg=seq_name: self.home._append_comm_line(
                    f"SendSequence Error: '{msg}' not found.", tag="error", direction="TX", show_channel=False
                ))

    def StartCommunication(self):
        """Opens the COM port."""
        self.home.after(0, self.home.routes.start_communication)

    def WaitForSequence(self, nameOrIndex, maxCounter=1, timeout=-1):
        """Wait for an active receive sequence and return its detected count."""
        return self.home.wait_for_receive_sequence(
            nameOrIndex,
            max_counter=maxCounter,
            timeout=timeout,
        )

    def StopCommunication(self):
        """Closes the COM port."""
        self.home.after(0, self.home.routes.stop_communication)

    def Createlog(self, path, log_type):
        """Saves the contents of a specific communication tab to a text file."""
        mapping = {
            "hex": "HEX",
            "ascii": "ASCII",
            "decimal": "Decimal",
            "binary": "Binary"
        }
        tab_name = mapping.get(str(log_type).strip().lower(), "HEX")
        file_path = str(path)

        def _save_file():
            try:
                text_widget = self.home._comm_texts.get(tab_name)
                if text_widget:
                    content = text_widget.get("1.0", "end-1c")
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    self.home._append_comm_line(
                        f"Log saved successfully to {file_path}", tag="meta", show_channel=False
                    )
                else:
                    self.home._append_comm_line(
                        f"Createlog Error: Tab '{tab_name}' not found.", tag="error", show_channel=False
                    )
            except Exception as e:
                self.home._append_comm_line(
                    f"Createlog Error: {str(e)}", tag="error", show_channel=False
                )

        self.home.after(0, _save_file)

    def ClearScreen(self):
            """Clears the entire communication terminal display immediately."""
            # Check if the home page has the exact panel clearing method defined
            if hasattr(self.home, "_clear_communication_panel"):
                self.home.after(0, self.home._clear_communication_panel)

def run_script(script_text, home_page):
    """Executes the raw Python script text using the custom commands."""
    # Reset control state variables on the home page instance
    home_page._script_paused = False
    home_page._script_stopped = False

    def _execute():
        try:
            commands = CustomScriptCommands(home_page)
            
            exec_globals = {
                "Comment": commands.Comment,
                "SendSequence": commands.SendSequence,
                "StartCommunication": commands.StartCommunication,
                "StopCommunication": commands.StopCommunication,
                "WaitForSequence": commands.WaitForSequence,
                "Createlog": commands.Createlog,
                "ClearScreen": commands.ClearScreen,
                "Pause": commands.Pause,
                "__builtins__": __builtins__
            }

            exec(script_text, exec_globals)

        except SystemExit:
            # Silent termination catch
            pass
        except Exception as e:
            error_message = _format_script_error(e)
            if not isinstance(e, (NameError, SyntaxError)):
                error_message = "Script Engine Error: {}".format(error_message)
            home_page.after(0, lambda msg=error_message: home_page._append_comm_line(
                msg, tag="error", direction="TX", show_channel=False
            ))
        finally:
            def _ui_finish():
                home_page._btn_script_play.set_state(True)     # Activate Play
                home_page._btn_script_pause.set_state(False)   # Deactivate Pause
                home_page._btn_script_stop.set_state(False)    # Deactivate Stop
            home_page.after(0, _ui_finish)


    threading.Thread(target=_execute, daemon=True, name="script-engine").start()