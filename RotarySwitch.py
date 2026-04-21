import RPi.GPIO as GPIO
import time

# --- Pin Configuration ---
# Connect rotary switch COM pin to GND (Pin 6)
# Each position pin connects to a GPIO below
PIN_MODE_1 = 17  # Position 1 → GPIO17 (Pin 11) — Off
PIN_MODE_2 = 27  # Position 2 → GPIO27 (Pin 13)
PIN_MODE_3 = 22  # Position 3 → GPIO22 (Pin 15)
PIN_MODE_4 = 23  # Position 4 → GPIO23 (Pin 16)

SWITCH_PINS = [PIN_MODE_1, PIN_MODE_2, PIN_MODE_3, PIN_MODE_4]

# --- GPIO Setup ---
GPIO.setmode(GPIO.BCM)
for pin in SWITCH_PINS:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    # Pull-up means: pin reads HIGH normally, LOW when switch connects it to GND


# --- Mode Functions ---

def mode_1_off():
    """Mode 1 — Active. Switch is in position 1."""
    print("Mode 1: Active")
    # Nothing runs in this mode


def mode_2():
    """Mode 2 — Add your code here."""
    print("Mode 2: Active")

    # =========================================================
    # YOUR MODE 2 CODE GOES HERE
    # =========================================================

    pass


def mode_3():
    """Mode 3 — Add your code here."""
    print("Mode 3: Active")

    # =========================================================
    # YOUR MODE 3 CODE GOES HERE
    # =========================================================

    pass


def mode_4():
    """Mode 4 — Add your code here."""
    print("Mode 4: Active")

    # =========================================================
    # YOUR MODE 4 CODE GOES HERE
    # =========================================================

    pass


# --- Read Current Switch Position ---

def get_current_mode():
    """
    Returns the active mode (1–4) based on which GPIO pin is LOW.
    If no pin is LOW (switch mid-turn or disconnected), returns None.
    """
    if GPIO.input(PIN_MODE_1) == GPIO.LOW:
        return 1
    elif GPIO.input(PIN_MODE_2) == GPIO.LOW:
        return 2
    elif GPIO.input(PIN_MODE_3) == GPIO.LOW:
        return 3
    elif GPIO.input(PIN_MODE_4) == GPIO.LOW:
        return 4
    return None  # Switch is between positions


# --- Main Loop ---

def run_mode(mode):
    if mode == 1:
        mode_1_off()
    elif mode == 2:
        mode_2()
    elif mode == 3:
        mode_3()
    elif mode == 4:
        mode_4()


def main():
    print("Rotary switch controller running. Press Ctrl+C to exit.")

    # Read the switch position immediately at startup so the correct
    # mode is active from the moment the script starts
    current_mode = get_current_mode()
    if current_mode is not None:
        print(f"\n--- Starting in Mode {current_mode} ---")
        run_mode(current_mode)
    else:
        print("Warning: switch position not detected at startup.")

    try:
        while True:
            new_mode = get_current_mode()

            # Only trigger a mode change when the position actually changes
            if new_mode is not None and new_mode != current_mode:
                current_mode = new_mode
                print(f"\n--- Switched to Mode {current_mode} ---")

                run_mode(current_mode)

            time.sleep(0.05)  # Poll every 50ms — responsive without hammering the CPU

    except KeyboardInterrupt:
        print("\nExiting...")

    finally:
        GPIO.cleanup()  # Always reset GPIO on exit


if __name__ == "__main__":
    main()
