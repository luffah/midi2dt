#!/usr/bin/python3
# Requiere xdotool, python3-tk
import subprocess
import threading
import queue
import logging
import json
import sys
import os
try:
    import Tkinter as tk
    import tkFont
    import ttk
except ImportError:  # Python 3
    import tkinter as tk
    import tkinter.font as tkFont
    import tkinter.ttk as ttk

# Get arguments
options = []
files = []
if len(sys.argv) > 1:
    for i in sys.argv[1:]:
        if i.startswith('-'):
            options.append(i)
        else:
            files.append(i)

opt_desc = {
    '--abs':
        'Absolute mode : usefull to assign many keys to one pot controller',
    './config.json':
        'Path to configuration file'
}

if '--help' in options or '-h' in options:
    print('Usage :' + sys.argv[0] + ' ' +
          ' '.join(map(lambda a: '[%s]' % a, opt_desc.keys())))
    for (k, v) in opt_desc.items():
        print("{0:<14s} {1:s}".format(k, v))
    exit()
ABSOLUTE_CTL = ('--abs' in options)
DEFAULT_CONFIG_FILE = (len(files) > 0 and
                       files[0] or
                       os.path.dirname(sys.argv[0]) + '/configs.json')
DEFAULT_CONFIG_FORMAT = 'json'

# Sensitivity settings
# Notes are in range [0,127]
NOTE_PRESSURE_MIDDLE = 64
NOTE_PRESSURE_STRONG = 63

# CONSTANTS <<12
NOTE_PRESSURE_MIDDLE_DELTA = 0x2
NOTE_PRESSURE_STRONG_DELTA = 0x3


class MidiKeyboard(object):

    def __init__(self, device=None, *args, **kwargs):
        self._device = device
        self._running = threading.Event()
        self._queue = queue.Queue()
        self.start_thread(device)

    def start_thread(self, device=None):
        if device is None:
            if self._device is None:
                return
            device = self.device
        else:
            self._device = device
        # TODO: Check if the device exists
        try:
            self._thread = threading.Thread(
                target=self._read_device,
                args=(self._queue, device))
            self._thread.setDaemon(True)
            self._thread.start()
        except Exception:
            print("Exception!", sys.exc_info()[2])
            pass

    def stop_thread(self):
        logging.info('Stop midi-thread request')
        if self._running.is_set():
            logging.debug('setting running flag off...')
            self._running.clear()
            logging.debug('closing pipe...')
            self._device_pipe.kill()
            self._device_pipe.stdout.close()
            self._thread.join(1)
            logging.debug('Midi-thread closed')

    def _read_device(self, queue, device):
        self._device_pipe = subprocess.Popen(
            ['cat', device],
            stdout=subprocess.PIPE, bufsize=0)
        message = []
        expected_length = -1
        self._running.set()
        data = None
        # cmd  meaning        #par param 1    param 2
        # ----+--------------+----+----------+-------
        # 0x80 Note-off       2    key        velocity
        # 0x90 Note-on        2    key        velocity
        # 0xA0 Aftertouch     2    key        touch
        # 0xB0 Continuous
        #      Controller     2    controller value
        # 0xC0 Patch change   2    instrument
        # 0xD0 Channel
        #      Pressure       1    pressure
        # 0xE0 Pitch bend     2    lsb(7bits) msb(7bits)
        # 0xF0 (non-musical commands)
        with self._device_pipe.stdout as f:
            while self._running.is_set():
                try:
                    data = ord(f.read(1))
                    if data is not None and data >= 0x80:
                        # status message
                        message = []
                        if data < 0xC0:
                            expected_length = 3
                        else:
                            expected_length = -1
                except Exception:
                    if data is not None:
                        logging.error(
                            "Midi message not understood: %s - %s",
                            hex(data), message)
                    else:
                        logging.error("Midi message was NONE")
                    expected_length = -1
                    data = None

                if expected_length:
                    message.append(data)
                    if len(message) >= expected_length:
                        queue.put(message)
                        expected_length = -1

    def read(self):
        try:
            return self._queue.get(False)
        except Exception:
            return False

    def is_running(self):
        return self._running.is_set()

    def set_device(self, device=None):
        if device is not None:
            self._device = device


class TkWindow(tk.Frame):

    def __init__(self, parent):
        tk.Frame.__init__(self, parent)
        self.parent = parent
        self.parent.bind('<KeyPress>', self.onKeyPress)
        self.midikb = None
        self._midi_key_list = []
        self._midi_key_values = {}
        self._midi_key_types = {}
        self._programming_mode = tk.IntVar()
        self._tree_selection = None
        self.initUI()
        self.read_configs()
        if len(self._cbox_device.get()):
            self.connect_to_device()

    def initUI(self):
        self.parent.title("midi2dt")
        self.pack(fill="both", expand=True)

        frame1 = ttk.Frame(self)
        frame1.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        frame1_1 = ttk.Frame(frame1)
        frame1_1.pack(side="top", fill="both", expand=True)
        frame1_2 = ttk.Frame(frame1)
        frame1_2.pack(side="bottom", fill="both", expand=False)

        frame2 = ttk.Frame(self)
        frame2.pack(side="right", fill="y", expand=False, padx=5, pady=5)

        tree_headers = [
            ('Type', 90),
            ('Key ID', 10),
            ('Modifier', 10),
            ('Key', 90),
            ('Abs', 5)
        ]
        self._tree = ttk.Treeview(
            frame1_1,
            columns=[name for name, _ in tree_headers],
            show="headings",
            height=20
        )
        self._tree.pack(side='left', fill='both', expand=True)
        self._tree.bind('<<TreeviewSelect>>', self.selected_item)
        self._tree.bind('<<TreeviewClose>>', self.onMouseClick)
        self._tree.bind('<<TreeviewOpen>>', self.onMouseClick)
        for column, width in tree_headers:
            self._tree.heading(column, text=column)
            self._tree.column(
                column,
                width=(
                    tkFont.Font().measure(column) +
                    width),
                anchor='w')

        vsb = ttk.Scrollbar(
            frame2,
            orient="vertical",
            command=self._tree.yview)
        vsb.pack(side='right', fill='y')
        self._tree.configure(yscrollcommand=vsb.set)

        check = ttk.Checkbutton(
            frame1_2,
            text='Programming mode',
            variable=self._programming_mode)
        check.pack(side='left', padx=5, pady=5)
        self._cbox_device = tk.StringVar()
        try:
            device_options = subprocess.check_output(
                'find /dev/ -type d ! \
                    -perm -g+r,u+r,o+r \
                    -prune -o -name *midi* \
                    -print'.split()
            )
            cbox = ttk.Combobox(
                frame1_2,
                textvariable=self._cbox_device,
                values=device_options)
            cbox.pack(side='bottom', padx=5, pady=5)
            cbox.set(device_options.split()[0])
        except IndexError:
            print("No midi device detected ! Leave...")
            exit()

        button = ttk.Button(
            frame1_2,
            text='Save configs',
            command=self.save_configs)
        button.pack(side='right', padx=5, pady=5)
        button = ttk.Button(
            frame1_2,
            text='Connect to device',
            command=self.connect_to_device)
        button.pack(side='right', padx=5, pady=5)
        # TODO: programming mode ->True
        # as default when no configuration has been set
        self._programming_mode.set(0)

    def connect_to_device(self):
        self.midikb = MidiKeyboard(self._cbox_device.get())

    def read_configs(self,
                     file_format=DEFAULT_CONFIG_FORMAT,
                     file_name=DEFAULT_CONFIG_FILE):
        try:
            with open(file_name, "r") as f:
                options = json.load(f)
            for line in options:
                line["tags"][0] = int(line['tags'][0], 16)
                self._midi_key_list.append(line["tags"][0])
                (v1, v2, v3, v4, v5) = line["values"]
                self._ins(line["tags"][0],
                          v1, v2, v3, v4, v5)
            self.sort_treeview(column=1)
        except Exception:
            self._programming_mode.set(1)

    def save_configs(self,
                     file_format=DEFAULT_CONFIG_FORMAT,
                     file_name=DEFAULT_CONFIG_FILE):
        if file_format == 'json':
            options = []
            for child in self._tree.get_children():
                key = self._tree.item(child)
                key["tags"][0] = hex(key["tags"][0])
                options.append(key)
            with open(file_name, "w") as f:
                json.dump(options, f, sort_keys=True, indent=4)

    def send_keystroke(self, midikey, key, keypress):
        # key = keyid
        # keypress = mod key
        keyevt = None

        # TODO: use same index ranges
        # on keypress and continuous controller
        kidx = ((ABSOLUTE_CTL or ((key >> 8) <= 0x9)) and keypress or key << 1)
        keytype = (
            (key >> 8) -
            (
                kidx in self._midi_key_types
                and self._midi_key_types[kidx]
                and 8
                or 0)
        )
        # print(midikey, hex(kidx),hex(key),hex(keypress),hex(keytype))
        if keytype == 0x0:
            keyevt = "key"

        elif keytype == 0x1:
            keyevt = "key"

        elif keytype == 0x3:
            if not ABSOLUTE_CTL:
                keyevt = "keydown"
                if (midikey[2] == 0) or (midikey[2] < 63):
                    # Zero and/or decreasing
                    self._midi_key_values[str(key)] = 0
                    key = (key << 1) | 0x0
                elif (midikey[2] > 65):
                    # Increasing
                    self._midi_key_values[str(key)] = 1
                    key = (key << 1) | 0x1
                elif str(key) in self._midi_key_values.keys():
                    # neutral
                    key = (
                        (self._midi_key_values[str(key)] == 0) and
                        ((key << 1) | 0x0) or
                        ((key << 1) | 0x1))
                    keyevt = "keyup"
            else:
                # Realease existing key
                cc = midikey[1]
                if str(cc) in self._midi_key_values.keys():
                    keyr = self._midi_key_values[str(cc)]
                    keyevt = "keyup"
                    if self._tree.exists(keyr):
                        modifier = self._tree.item(keyr, option="values")[2]
                        value = self._tree.item(keyr, option="values")[3]
                        if value != "<<Undefined>>":
                            if len(modifier) > 1:
                                value = "{}{}".format(modifier, value)
                            # p =
                            subprocess.Popen(["xdotool", keyevt, value])

                # Press next key
                keyevt = "keydown"
                # warning: can be buggy with cc and note in the same range
                # usually note are in range 20..256 and cc in range 0..10
                self._midi_key_values[str(midikey[1])] = keypress
                key = keypress

        elif keytype == 0x8:
            note = str(midikey[1])
            if note in self._midi_key_values.keys():
                key = self._midi_key_values[note]
            keyevt = "keyup"

        elif keytype == 0x9:
            keyevt = "keydown"
            self._midi_key_values[str(midikey[1])] = keypress
            key = keypress

        elif keytype == 0xB:
            if not ABSOLUTE_CTL:
                if str(key) in self._midi_key_values.keys():
                    # print(key)
                    if (
                            (midikey[2] == 0) or
                            (midikey[2] <
                                self._midi_key_values[str(key)])
                    ):
                        # Zero and/or decreasing
                        key = (key << 1) | 0x0
                    else:
                        # Increasing
                        key = (key << 1) | 0x1
                    self._midi_key_values[str(key >> 1)] = midikey[2]
                else:
                    self._midi_key_values[str(key)] = midikey[2]
                    return
            else:
                key = keypress
            keyevt = "key"

        if keyevt:
            if self._tree.exists(key):
                # print("key",key)
                modifier = self._tree.item(key, option="values")[2]

                value = self._tree.item(key, option="values")[3]
                if value == "<<Undefined>>":
                    return
                if len(modifier) > 1:
                    value = "{}{}".format(modifier, value)
                # p =
                subprocess.Popen(
                    ["xdotool", keyevt, value])

    def sort_treeview(self, column=0, reverse=False):
        new_treeview = [
            (self._tree.set(child, column), child)
            for child in self._tree.get_children('')]
        new_treeview.sort(reverse=reverse)

        # rearrange items in sorted positions
        for index, (value, child) in enumerate(new_treeview):
            self._tree.move(child, '', index)

    def selected_item(self, tree_item):
        self._tree_selection = self._tree.selection()

    def _ins(self, midikey, typ, key_note, mod, val, key_type):
        self._tree.insert(
            '', 'end',
                midikey,
                tags=midikey,
                values="{} {} {} {} {}".format(
                    typ,
                    key_note,
                    mod or '-',
                    val or '<<Undefined>>',
                    key_type))
        self._midi_key_types[midikey] = key_type

    def add_keys_availables(
            self, midikey=None, tags=None, values=None):
        key_type = (midikey & 0xF00) >> 8
        key_note = str((midikey & 0xFF))
        if key_type == 0x8:
            self._ins(midikey, "Note-off",
                      key_note, "-", "<<Undefined>>", 0)
        elif key_type == 0x9:
            self._ins(midikey, "Note-on" + (
                "(middle)"
                if midikey >> 12 == NOTE_PRESSURE_MIDDLE_DELTA
                else
                "(strong)"
                if midikey >> 12 == NOTE_PRESSURE_STRONG_DELTA
                else " "
            ),
                key_note, "-", "<<Undefined>>", 0)
        elif key_type == 0xb:
            if ABSOLUTE_CTL:
                self._ins(midikey, "CC" + str(midikey >> 12) + '/10',
                          key_note, "-", "<<Undefined>>", 0)
            else:
                self._ins((midikey << 1) | 1, "CC",
                          key_note + '+', "-", "<<Undefined>>", 0)
                self._ins((midikey << 1) | 0, "CC",
                          key_note + '-', "-", "<<Undefined>>", 0)
        else:
            print("%x - %s" % (key_type, key_note))

    def check_item(self, tree_item):
        key = int(tree_item[0])
        self._midi_key_types[key] = (not (
            key in self._midi_key_types and
            self._midi_key_types[key] or 0
        )
        )
        self._tree.set(
            tree_item,
            4,
            self._midi_key_types[key]
        )

    def onMouseClick(self, event):
        self.check_item(self._tree_selection)

    def onKeyPress(self, event):
        key = event.__dict__['keysym']
        if not self._programming_mode.get():
            # if key == 'Return':
                # self._programming_mode.set(1)
            if key == 'BackSpace':
                self._tree.set(self._tree_selection, 2, '-')
                self._tree.set(self._tree_selection, 3, '<<Undefined>>')
            return
        # Mask     Modifier         Binary
        # 0x0001  Shift.           b0000 0001
        # 0x0002  Caps Lock.       b0000 0010
        # 0x0004  Control.         b0000 0100
        # 0x0008  Left-hand Alt.   b0000 1000
        # 0x0010  Num Lock.        b0001 0000
        # 0x0020  ???              b0010 0000
        # 0x0040  Windows key      b0100 0000
        # 0x0080  Right-hand Alt.  b1000 0000
        # 0x0100  Mouse button 1.
        # 0x0200  Mouse button 2.
        # 0x0400  Mouse button 3.
        if (self._tree_selection is not None and
                len(self._tree_selection) > 0):
            midikey = int(self._tree_selection[0])
            if (
                    midikey >> 8 == 0x8 and
                    not (
                        midikey in self._midi_key_types and
                        self._midi_key_types[midikey])
            ):
                return

            if (
                    "Control" in key or
                    "Alt" in key or
                    "Shift" in key or
                    "Caps_Lock" in key or
                    "Super" in key):
                return

            state = event.__dict__['state']
            modifier = ""
            if state & (1 << 2):
                modifier = "Ctrl+"
            if state & (1 << 3) or state & (1 << 7):
                modifier = modifier + "Alt+"
            if state & (1 << 0):
                modifier = modifier + "Shift+"
            if state & (1 << 6):
                modifier = modifier + "Super+"

            for child in self._tree.get_children():
                if key == self._tree.item(child, option="values")[2]:
                    self._tree.set(child, 3, "<<Undefined>>")

            self._tree.set(self._tree_selection, 2, modifier)
            self._tree.set(self._tree_selection, 3, key)
#           Useless behavior
#             next = self._tree.next(self._tree_selection)
#             self._tree.selection_set(next)
#             if next == '':
#                 self._tree_selection = None

    def update_keys_list(self, code):
        if code not in self._midi_key_list:
            self._midi_key_list.append(code)
            self.add_keys_availables(code)

    def check_midi_device(self):
        if self.midikb:
            if self.midikb.is_running():
                self.after(1, self.check_midi_device)
            else:
                print("is not running")
                self.after(1, self.check_midi_device)
                return
            command = self.midikb.read()
        else:
            print("Midi device disappeared")
            exit()
        if command:
            # print(command)
            # Only pay attention to 0x9X Note on and 0xBX Continuous controller
            keyini = (command[0] >> 4)
            key = None
            keyorig = None
#             key = ((keyini << 8) | command[1])
#             keyorig=key
            if keyini == 0x8:
                key = (0x800 | command[1])
                keyorig = key
            elif keyini == 0xB:
                key = (0xB00 | command[1])
                keyorig = key
                if ABSOLUTE_CTL:
                    def a(x):
                        return round(x * 9 / 127) + 1
                    p = command[2]
                    val = a(p)
                    key = (key | (val << 12))
            elif keyini == 0x9:
                p = command[2]
                if p == 0:
                    key = (0x800 | command[1])
                    keyorig = key
                else:
                    key = (0x900 | command[1])
                    keyorig = key
                    if p > NOTE_PRESSURE_MIDDLE:
                        if p > NOTE_PRESSURE_STRONG:
                            key = key | NOTE_PRESSURE_STRONG_DELTA << 12
                        else:
                            key = key | NOTE_PRESSURE_MIDDLE_DELTA << 12
            else:
                return
            if (self._programming_mode.get()):
                self.update_keys_list(key)
                if keyini == 0xB and not ABSOLUTE_CTL:
                    key = key << 1
                idx = self._tree.index(key)
                treeitem = self._tree.get_children()
                movement = float((idx - 5) / len(treeitem))
                self._tree.yview('moveto', movement)
                self._tree.selection_set(key)
            else:
                self.send_keystroke(command, keyorig, key)
            logging.debug('Key: %s %s', hex(key), hex(command[2]))

    def on_closing(self):
        logging.debug('User want to close the app')
        self.midikb.stop_thread()
        self.parent.destroy()
        logging.debug('Thanks for using this app :)')


def main():
    # logging.basicConfig(level=logging.DEBUG)
    logging.basicConfig(level=logging.INFO)
    root = tk.Tk()
    # root.geometry("400x300")
    app = TkWindow(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.after(500, app.check_midi_device)
    root.mainloop()


if __name__ == '__main__':
    main()
