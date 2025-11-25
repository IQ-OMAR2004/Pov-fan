#!/usr/bin/env python3
"""
POV Holographic Fan Display - OPTIMIZED FOR CLEAR DISPLAY
Works directly from hall sensor readings with proper timing calculations

For WS2815 LED Strip (72 LEDs) and A3144 Hall Sensor

TIMING CALCULATIONS:
- WS2815 at 800kHz: each bit = 1.25µs
- 72 LEDs × 24 bits = 1728 bits → ~2160µs minimum
- Plus reset time (~280µs) → ~2500µs per LED update
- At 500 RPM: rotation = 120,000µs → max ~48 divisions
- Using 36 divisions for stable display with margin

Button Controls:
- GPIO 17: Draw Circle
- GPIO 27: Draw Square  
- GPIO 22: Display Custom Image
"""

import time
from rpi_ws281x import PixelStrip, Color
import RPi.GPIO as GPIO
import math
from PIL import Image

# ============== HARDWARE CONFIGURATION ==============
NUM_LEDS = 72
LED_PIN = 18
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_BRIGHTNESS = 150  # Increased for better POV visibility
LED_INVERT = False
LED_CHANNEL = 0

HALL_SENSOR_PIN = 4
BUTTON_CIRCLE = 17
BUTTON_SQUARE = 27
BUTTON_IMAGE = 22

# ============== RPM & TIMING CONFIGURATION ==============
# Estimated LED update time in microseconds (72 LEDs @ 800kHz + overhead)
LED_UPDATE_TIME_US = 2800  # ~2.8ms for 72 WS2815 LEDs

# Target/default RPM when starting (before hall sensor calibrates)
DEFAULT_RPM = 500
MIN_RPM = 200
MAX_RPM = 1500

# Calculate safe number of divisions based on LED timing
# Formula: max_divisions = rotation_time_us / LED_UPDATE_TIME_US
# At 500 RPM: 120,000µs / 2800µs ≈ 42 max divisions
# Using 36 for safety margin and cleaner angles (360° / 36 = 10° per division)
NUM_DIVISIONS = 36  # Reduced from 150 for realistic timing!

# Alternative presets - uncomment based on your motor speed:
# NUM_DIVISIONS = 24  # For slower fans (300-400 RPM) - 15° per division
# NUM_DIVISIONS = 48  # For faster fans (600-800 RPM) - 7.5° per division
# NUM_DIVISIONS = 72  # For very fast fans (900+ RPM) - 5° per division

# ============== DISPLAY CONFIGURATION ==============
BRIGHTNESS_RATIO = 0.7  # Increased from 0.5 for better visibility
LINES_TO_SHIFT = -6     # Adjusted for new division count (was -18 for 150 divisions)

# Timing safety margin (microseconds to reserve for overhead)
TIMING_MARGIN_US = 200

# ============== GLOBAL VARIABLES ==============
current_mode = "circle"
display_data = []

# Timing variables with proper defaults
last_rotation_micros = 0
rotation_time_micros = int(60_000_000 / DEFAULT_RPM)  # Default based on expected RPM
time_per_line_micros = rotation_time_micros // NUM_DIVISIONS
current_line = 0
rotation_active = False

# RPM tracking for display and adjustment
current_rpm = DEFAULT_RPM
rpm_history = []  # Store last few RPM readings for smoothing
RPM_HISTORY_SIZE = 5  # Number of rotations to average

# Actual measured timing vs expected
actual_line_time_us = 0

# Button state tracking
last_button_states = {BUTTON_CIRCLE: GPIO.HIGH, BUTTON_SQUARE: GPIO.HIGH, BUTTON_IMAGE: GPIO.HIGH}
last_button_time = {BUTTON_CIRCLE: 0, BUTTON_SQUARE: 0, BUTTON_IMAGE: 0}
DEBOUNCE_TIME = 0.3

# Hall sensor tracking
last_hall_state = GPIO.LOW
rotation_count = 0
missed_lines_count = 0  # Track if we're missing lines due to slow updates

# ============== GPIO SETUP ==============
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

try:
    GPIO.cleanup()
    time.sleep(0.5)
except:
    pass

GPIO.setmode(GPIO.BCM)
GPIO.setup(HALL_SENSOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(BUTTON_CIRCLE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(BUTTON_SQUARE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(BUTTON_IMAGE, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Initialize LED strip
strip = PixelStrip(NUM_LEDS, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
strip.begin()

# ============== UTILITY FUNCTIONS ==============

def clear_strip():
    """Turn off all LEDs"""
    for i in range(NUM_LEDS):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()


def get_time_micros():
    """Get current time in microseconds"""
    return int(time.perf_counter() * 1_000_000)


# ============== SHAPE GENERATION ==============

def generate_circle_data(radius_leds=30, color_rgb=(0, 255, 255)):
    """
    Generate circle data - displays at constant radius from center.
    With fewer divisions, we make the circle thicker for visibility.
    """
    data = []
    center_led = NUM_LEDS // 2
    r, g, b = color_rgb
    
    # Make circle thicker with fewer divisions (more visible)
    # With 36 divisions, each LED position covers 10°, so we need thickness
    circle_thickness = max(2, 5 - NUM_DIVISIONS // 20)  # Thicker for fewer divisions
    
    for angle_idx in range(NUM_DIVISIONS):
        line = [Color(0, 0, 0)] * NUM_LEDS
        
        if radius_leds < NUM_LEDS // 2:
            # Draw circle outline with thickness
            for offset in range(-circle_thickness // 2, circle_thickness // 2 + 1):
                led_pos_1 = center_led - radius_leds + offset
                led_pos_2 = center_led + radius_leds + offset
                
                if 0 <= led_pos_1 < NUM_LEDS:
                    line[led_pos_1] = Color(int(g * BRIGHTNESS_RATIO), 
                                           int(r * BRIGHTNESS_RATIO), 
                                           int(b * BRIGHTNESS_RATIO))
                if 0 <= led_pos_2 < NUM_LEDS:
                    line[led_pos_2] = Color(int(g * BRIGHTNESS_RATIO), 
                                           int(r * BRIGHTNESS_RATIO), 
                                           int(b * BRIGHTNESS_RATIO))
        
        data.append(line)
    
    return data


def generate_square_data(side_length_leds=25, color_rgb=(255, 0, 255)):
    """
    Generate CLEAR square data using proper polar-to-cartesian math.
    A square in polar coordinates has varying radius depending on angle.
    """
    data = []
    center_led = NUM_LEDS // 2
    r, g, b = color_rgb
    
    # Edge thickness for visibility
    edge_thickness = max(2, 4 - NUM_DIVISIONS // 20)
    
    # Half the side length (distance from center to edge at cardinal directions)
    half_side = side_length_leds // 2
    
    for angle_idx in range(NUM_DIVISIONS):
        line = [Color(0, 0, 0)] * NUM_LEDS
        
        # Calculate angle in radians (0 to 2π)
        angle_rad = (angle_idx * 2 * math.pi / NUM_DIVISIONS)
        angle_deg = math.degrees(angle_rad) % 360
        
        # For a square centered at origin, the distance from center to edge
        # varies with angle. Using the formula for a square:
        # r = half_side / max(|cos(θ)|, |sin(θ)|)
        cos_a = abs(math.cos(angle_rad))
        sin_a = abs(math.sin(angle_rad))
        
        # Avoid division by zero
        max_trig = max(cos_a, sin_a, 0.001)
        
        # Distance from center to square edge at this angle
        distance = int(half_side / max_trig)
        
        # Clamp to valid LED range
        distance = min(distance, center_led - 1)
        
        # Draw the square outline with thickness
        for offset in range(-edge_thickness // 2, edge_thickness // 2 + 1):
            led_pos_1 = center_led - distance + offset
            led_pos_2 = center_led + distance + offset
            
            if 0 <= led_pos_1 < NUM_LEDS:
                line[led_pos_1] = Color(int(g * BRIGHTNESS_RATIO), 
                                       int(r * BRIGHTNESS_RATIO), 
                                       int(b * BRIGHTNESS_RATIO))
            if 0 <= led_pos_2 < NUM_LEDS:
                line[led_pos_2] = Color(int(g * BRIGHTNESS_RATIO), 
                                       int(r * BRIGHTNESS_RATIO), 
                                       int(b * BRIGHTNESS_RATIO))
        
        data.append(line)
    
    return data


def load_image_data(image_path):
    """Load image for POV display"""
    try:
        print(f"Loading image: {image_path}")
        image = Image.open(image_path)
        
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Resize for consistency
        target_size = 600
        if image.size[0] != target_size or image.size[1] != target_size:
            image = image.resize((target_size, target_size), Image.LANCZOS)
        
        width, height = image.size
        center_x, center_y = width // 2, height // 2
        radius = min(width, height) // 2 - 1
        
        data = []
        angle_increment = 360.0 / NUM_DIVISIONS
        num_leds_per_side = NUM_LEDS // 2
        
        for slice_idx in range(NUM_DIVISIONS):
            line = [Color(0, 0, 0)] * NUM_LEDS
            angle_deg = slice_idx * angle_increment
            angle_rad = math.radians(angle_deg)
            
            # First side (LEDs 0-35)
            for led_idx in range(num_leds_per_side):
                radial_dist = (led_idx + 1) * (radius / num_leds_per_side)
                x = int(center_x + radial_dist * math.cos(angle_rad))
                y = int(center_y + radial_dist * math.sin(angle_rad))
                
                if 0 <= x < width and 0 <= y < height:
                    r, g, b = image.getpixel((x, y))
                    led_pos = num_leds_per_side - led_idx - 1
                    line[led_pos] = Color(int(g * BRIGHTNESS_RATIO), 
                                         int(r * BRIGHTNESS_RATIO), 
                                         int(b * BRIGHTNESS_RATIO))
            
            # Second side (LEDs 36-71) - opposite angle
            opposite_angle_rad = angle_rad + math.pi
            for led_idx in range(num_leds_per_side):
                radial_dist = (led_idx + 1) * (radius / num_leds_per_side)
                x = int(center_x + radial_dist * math.cos(opposite_angle_rad))
                y = int(center_y + radial_dist * math.sin(opposite_angle_rad))
                
                if 0 <= x < width and 0 <= y < height:
                    r, g, b = image.getpixel((x, y))
                    led_pos = num_leds_per_side + led_idx
                    line[led_pos] = Color(int(g * BRIGHTNESS_RATIO), 
                                         int(r * BRIGHTNESS_RATIO), 
                                         int(b * BRIGHTNESS_RATIO))
            
            data.append(line)
        
        print("✓ Image loaded!")
        return data
        
    except Exception as e:
        print(f"Error: {e}")
        return generate_circle_data()


# ============== BUTTON POLLING ==============

def check_buttons():
    """Poll buttons for mode changes"""
    global display_data, current_mode, last_button_states, last_button_time
    
    current_time = time.time()
    
    buttons = [
        (BUTTON_CIRCLE, "circle", lambda: generate_circle_data(radius_leds=28, color_rgb=(0, 255, 255)), "CIRCLE"),
        (BUTTON_SQUARE, "square", lambda: generate_square_data(side_length_leds=24, color_rgb=(255, 0, 255)), "SQUARE"),
        (BUTTON_IMAGE, "image", lambda: load_image_data('/home/pi/Downloads/Smiley_face.png'), "IMAGE")
    ]
    
    for button_pin, mode_name, mode_func, display_name in buttons:
        current_state = GPIO.input(button_pin)
        
        if current_state == GPIO.LOW and last_button_states[button_pin] == GPIO.HIGH:
            if current_time - last_button_time[button_pin] > DEBOUNCE_TIME:
                print(f"\n✓ Mode: {display_name}")
                current_mode = mode_name
                display_data = mode_func()
                last_button_time[button_pin] = current_time
        
        last_button_states[button_pin] = current_state


# ============== HALL SENSOR POLLING ==============

def check_hall_sensor():
    """
    Poll hall sensor - THIS IS THE KEY!
    When sensor triggers = 0° position (start of rotation)
    Calculate timing from LAST rotation with smoothing
    Use that timing for CURRENT rotation
    """
    global last_hall_state, last_rotation_micros, rotation_time_micros
    global time_per_line_micros, current_line, rotation_count, rotation_active
    global current_rpm, rpm_history, actual_line_time_us, missed_lines_count
    
    current_state = GPIO.input(HALL_SENSOR_PIN)
    
    # Detect rising edge = magnet detected = 0° position
    if current_state == GPIO.HIGH and last_hall_state == GPIO.LOW:
        current_time = get_time_micros()
        
        # Calculate how long the LAST rotation took
        if last_rotation_micros > 0:
            measured_rotation_time = current_time - last_rotation_micros
            
            # Validate the measurement (reject noise/bounces)
            # At MIN_RPM (200): max rotation time = 300,000µs (300ms)
            # At MAX_RPM (1500): min rotation time = 40,000µs (40ms)
            min_rotation_time = int(60_000_000 / MAX_RPM)
            max_rotation_time = int(60_000_000 / MIN_RPM)
            
            if min_rotation_time <= measured_rotation_time <= max_rotation_time:
                # Calculate RPM from this rotation
                instant_rpm = 60_000_000 / measured_rotation_time
                
                # Add to history for smoothing
                rpm_history.append(instant_rpm)
                if len(rpm_history) > RPM_HISTORY_SIZE:
                    rpm_history.pop(0)
                
                # Use smoothed RPM for timing (reduces jitter)
                current_rpm = sum(rpm_history) / len(rpm_history)
                
                # Calculate smoothed rotation time
                rotation_time_micros = int(60_000_000 / current_rpm)
                
                # Calculate time per line with safety margin
                raw_time_per_line = rotation_time_micros // NUM_DIVISIONS
                
                # Ensure we have enough time for LED update
                if raw_time_per_line < LED_UPDATE_TIME_US:
                    # We're running too fast for this many divisions!
                    # Just use what we have and accept some blur
                    time_per_line_micros = LED_UPDATE_TIME_US
                    if rotation_count % 50 == 0:
                        max_safe_divisions = rotation_time_micros // LED_UPDATE_TIME_US
                        print(f"⚠ RPM too high for {NUM_DIVISIONS} divisions!")
                        print(f"  Recommended: NUM_DIVISIONS = {max_safe_divisions}")
                else:
                    time_per_line_micros = raw_time_per_line
                
                # Display status periodically
                if rotation_count % 30 == 0:
                    effective_divisions = rotation_time_micros // LED_UPDATE_TIME_US
                    print(f"RPM: {current_rpm:.0f} | "
                          f"Time/line: {time_per_line_micros}µs | "
                          f"Max safe divisions: {effective_divisions}")
        
        # Reset to position 0° (line 0)
        current_line = 0
        rotation_active = True
        rotation_count += 1
        last_rotation_micros = current_time
        
        if rotation_count == 1:
            print("\n✓ ROTATION DETECTED!")
            print(f"Using {NUM_DIVISIONS} divisions per rotation")
            print(f"LED update time: ~{LED_UPDATE_TIME_US}µs")
            print("Display active. Press buttons to change modes.\n")
    
    last_hall_state = current_state


# ============== DISPLAY FUNCTION - OPTIMIZED ==============

def display_current_line():
    """
    Display the current line with optimized timing.
    Key insight: LED update takes significant time (~2.5ms for 72 LEDs)
    We must account for this in our timing calculations.
    """
    global current_line, actual_line_time_us, missed_lines_count
    
    if not rotation_active or time_per_line_micros <= 0:
        return
    
    # Which line to show (with rotation adjustment)
    line_to_show = (current_line + LINES_TO_SHIFT + NUM_DIVISIONS) % NUM_DIVISIONS
    
    # Start timing for this line
    line_start_time = get_time_micros()
    
    # Set LEDs for this line
    if display_data and line_to_show < len(display_data):
        line_data = display_data[line_to_show]
        for i in range(NUM_LEDS):
            strip.setPixelColor(i, line_data[i])
        strip.show()
    
    # Calculate how long LED update took
    update_time = get_time_micros() - line_start_time
    actual_line_time_us = update_time
    
    # Wait the remaining time for this angular position
    remaining = time_per_line_micros - update_time - TIMING_MARGIN_US
    
    if remaining > 0:
        # Precise busy-wait for accurate timing
        target_time = get_time_micros() + remaining
        while get_time_micros() < target_time:
            pass
    elif remaining < -1000:  # More than 1ms behind
        # We're running behind - the fan is spinning faster than we can update
        # Skip to catch up (this prevents image from drifting)
        lines_to_skip = int((-remaining) / time_per_line_micros)
        if lines_to_skip > 0:
            current_line += lines_to_skip
            missed_lines_count += lines_to_skip
    
    # Move to next line
    current_line += 1
    if current_line >= NUM_DIVISIONS:
        current_line = 0


# ============== MAIN LOOP ==============

def main():
    global display_data
    
    # Calculate timing info for display
    rotation_time_at_default = int(60_000_000 / DEFAULT_RPM)
    time_per_line_at_default = rotation_time_at_default // NUM_DIVISIONS
    max_safe_divisions = rotation_time_at_default // LED_UPDATE_TIME_US
    degrees_per_division = 360.0 / NUM_DIVISIONS
    
    print("\n" + "="*65)
    print("  POV FAN - OPTIMIZED FOR CLEAR DISPLAY")
    print("="*65)
    print("\n▸ TIMING CONFIGURATION:")
    print(f"  • LED strip: {NUM_LEDS} WS2815 LEDs")
    print(f"  • LED update time: ~{LED_UPDATE_TIME_US}µs ({LED_UPDATE_TIME_US/1000:.1f}ms)")
    print(f"  • Divisions per rotation: {NUM_DIVISIONS} ({degrees_per_division:.1f}° each)")
    print(f"  • Brightness: {int(BRIGHTNESS_RATIO * 100)}%")
    
    print("\n▸ RPM CALCULATIONS (at {:.0f} RPM default):".format(DEFAULT_RPM))
    print(f"  • Rotation time: {rotation_time_at_default:,}µs ({rotation_time_at_default/1000:.1f}ms)")
    print(f"  • Time per line: {time_per_line_at_default:,}µs ({time_per_line_at_default/1000:.2f}ms)")
    print(f"  • Max safe divisions: {max_safe_divisions}")
    
    if NUM_DIVISIONS > max_safe_divisions:
        print(f"\n  ⚠ WARNING: {NUM_DIVISIONS} divisions may be too many for {DEFAULT_RPM} RPM!")
        print(f"     Consider reducing to {max_safe_divisions} or increasing fan speed.")
    else:
        print(f"\n  ✓ Configuration looks good for {DEFAULT_RPM} RPM!")
    
    print("\n▸ CONTROLS:")
    print("  • GPIO 17 → Circle (cyan)")
    print("  • GPIO 27 → Square (magenta)")
    print("  • GPIO 22 → Custom Image")
    
    print("\n▸ RPM RANGE: {}-{} RPM".format(MIN_RPM, MAX_RPM))
    
    print("\n" + "="*65)
    print("  Spin the fan to start! Waiting for hall sensor...")
    print("="*65 + "\n")
    
    # Start with circle (regenerate with new NUM_DIVISIONS)
    display_data = generate_circle_data(radius_leds=28, color_rgb=(0, 255, 255))
    
    # Startup indicator - show we're ready
    for i in range(NUM_LEDS):
        if i < 5:
            strip.setPixelColor(i, Color(0, 50, 0))  # Green = ready
        else:
            strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()
    
    try:
        while True:
            # Poll buttons (fast)
            check_buttons()
            
            # Poll hall sensor (fast) - this resets position when triggered
            check_hall_sensor()
            
            # Display current line with precise timing
            display_current_line()
                
    except KeyboardInterrupt:
        print("\n\n" + "-"*40)
        print("Shutting down...")
        if rotation_count > 0:
            print(f"  Total rotations: {rotation_count}")
            print(f"  Final RPM: {current_rpm:.1f}")
            if missed_lines_count > 0:
                print(f"  Missed lines: {missed_lines_count}")
        clear_strip()
        print("-"*40)
        
    finally:
        GPIO.cleanup()
        print("Done!\n")


if __name__ == "__main__":
    main()
