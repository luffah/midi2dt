# requirements
python3, xdotool, python3-tk

# (very) fast user manual:
1. Connect the USB MIDI keyboard

  2. Run the program midi2dt.py

  3. To assign a MIDI key to a (normal) keyboard shortcut, select the programming mode in the interface
    * Press a MIDI key
    * Press on a normal keyboard the desired shortcut
    * Repeat

  4. To use it, deactivate the "programming mode"

  5. You can disable keys, by selecting one and pressing 'BackSpace'

  6. You can can change state of the key, by pressing 'Space'
    * State 0 : standard mode
        * pressing a **note** press the key and releasing release the key. There is 2 values possibles : normal pressure, or strong pressure.
        * (if no --abs option is provided) a **controller** have 2 values : increasing or decreasing which hit the key
    * State 1 :
        * pressing a **note** hit the key and releasing hit another key. (Add another value on release)
        * (if no --abs option is provided) a **controller** have 2 values : low value and high value, if it have a value > 65 (middle) then it press the key for high (if value < 64 then if press the key for low). When pot is in the middle it the key is released.
        * (if --abs option is provided) a **controller** have 10 values : each time it move to a position it hit the associated key

  7. Save the new layout by pressing "Save configs" button


# Possible future of this program
  * chording notes
  * mouse events or direct command line shorcuts
  * for absolute controller mode, press / release event or a unique hit instead a hit each time the pot the move
