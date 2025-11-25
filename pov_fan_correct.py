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

# Target/default RPM - set based on your actual motor!
# Your logs show average ~800-900 RPM with spikes to 1200+
DEFAULT_RPM = 900
MIN_RPM = 250      # Reject readings below this (noise)
MAX_RPM = 1400     # Reject readings above this (noise)

# IMPORTANT: Based on your logs showing 800-1200 RPM typical:
# At 1200 RPM: rotation = 50,000µs → max 17 divisions
# At 900 RPM: rotation = 66,667µs → max 23 divisions  
# Using 16 divisions for stable display at high RPM!
NUM_DIVISIONS = 16  # Safe for your 800-1200 RPM range (22.5° per division)

# Alternative presets based on your motor:
# NUM_DIVISIONS = 12  # Ultra-stable, works up to 1400 RPM
# NUM_DIVISIONS = 18  # Good for 700-1100 RPM
# NUM_DIVISIONS = 20  # Good for 600-1000 RPM

# ============== DISPLAY CONFIGURATION ==============
BRIGHTNESS_RATIO = 0.8  # Higher brightness for faster spin (less persistence time)
LINES_TO_SHIFT = -3     # Adjusted for 16 divisions

# Timing safety margin (microseconds to reserve for overhead)
TIMING_MARGIN_US = 300  # Increased for more headroom

# ============== NOISE FILTERING ==============
# Hall sensor debounce - ignore triggers too close together
MIN_ROTATION_TIME_US = 40000   # Max 1500 RPM = 40ms minimum between triggers
HALL_DEBOUNCE_US = 5000        # Ignore triggers within 5ms of last one

# RPM change threshold - reject sudden jumps (likely noise)
MAX_RPM_CHANGE_PERCENT = 40    # Reject if RPM changes more than 40% suddenly

# ============== GLOBAL VARIABLES ==============
current_mode = "circle"
display_data = []

# Timing variables with proper defaults
last_rotation_micros = 0
rotation_time_micros = int(60_000_000 / DEFAULT_RPM)  # Default based on expected RPM
time_per_line_micros = rotation_time_micros // NUM_DIVISIONS
current_line = 0
rotation_active = False

# RPM tracking with aggressive smoothing
current_rpm = DEFAULT_RPM
stable_rpm = DEFAULT_RPM           # Filtered/stable RPM value
rpm_history = []                   # Store RPM readings for smoothing
RPM_HISTORY_SIZE = 15              # Increased! More samples = smoother (was 5)
rpm_locked = False                 # Once stable, lock the RPM
rpm_lock_threshold = 10            # Lock after this many stable readings
rpm_stable_count = 0               # Count of consecutive stable readings

# Actual measured timing vs expected
actual_line_time_us = 0

# Button state tracking
last_button_states = {BUTTON_CIRCLE: GPIO.HIGH, BUTTON_SQUARE: GPIO.HIGH, BUTTON_IMAGE: GPIO.HIGH}
last_button_time = {BUTTON_CIRCLE: 0, BUTTON_SQUARE: 0, BUTTON_IMAGE: 0}
DEBOUNCE_TIME = 0.3

# Hall sensor tracking with debouncing
last_hall_state = GPIO.LOW
last_hall_trigger_time = 0         # For debouncing
rotation_count = 0
valid_rotation_count = 0           # Only count valid (non-noise) rotations
missed_lines_count = 0             # Track if we're missing lines
noise_rejected_count = 0           # Track rejected noise triggers

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

def generate_circle_data(radius_leds=28, color_rgb=(0, 255, 255)):
    """
    Generate circle data - displays at constant radius from center.
    With fewer divisions (16-20), we make the circle thicker for visibility.
    """
    data = []
    center_led = NUM_LEDS // 2
    r, g, b = color_rgb
    
    # Thicker circle for fewer divisions (more visible at high RPM)
    # 16 divisions = 22.5° each, need thick outline
    circle_thickness = max(3, 7 - NUM_DIVISIONS // 5)  # 3-5 LEDs thick
    
    for angle_idx in range(NUM_DIVISIONS):
        line = [Color(0, 0, 0)] * NUM_LEDS
        
        if radius_leds < NUM_LEDS // 2:
            # Draw circle outline with thickness (both sides of strip)
            for offset in range(-circle_thickness // 2, circle_thickness // 2 + 1):
                # Inner half of strip (LEDs 0 to center)
                led_pos_1 = center_led - radius_leds + offset
                # Outer half of strip (LEDs center to end)
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


def generate_square_data(side_length_leds=24, color_rgb=(255, 0, 255)):
    """
    Generate square using polar-to-cartesian math.
    Optimized for low division counts (16-20 divisions).
    """
    data = []
    center_led = NUM_LEDS // 2
    r, g, b = color_rgb
    
    # Thicker edges for fewer divisions
    edge_thickness = max(3, 6 - NUM_DIVISIONS // 5)
    
    # Half the side length
    half_side = side_length_leds // 2
    
    for angle_idx in range(NUM_DIVISIONS):
        line = [Color(0, 0, 0)] * NUM_LEDS
        
        # Calculate angle in radians
        angle_rad = (angle_idx * 2 * math.pi / NUM_DIVISIONS)
        
        # Square formula: r = half_side / max(|cos(θ)|, |sin(θ)|)
        cos_a = abs(math.cos(angle_rad))
        sin_a = abs(math.sin(angle_rad))
        max_trig = max(cos_a, sin_a, 0.001)
        
        # Distance from center to square edge
        distance = int(half_side / max_trig)
        distance = min(distance, center_led - 2)  # Keep within LED range
        
        # Draw thick outline
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


def load_binary_image_data(binary_data, color_rgb=(255, 255, 255)):
    """
    Load image from binary format (generated by POV Image Converter web app).
    
    The binary format stores 8 pixels per byte:
    - Each row is an array of bytes
    - Each byte represents 8 LEDs (MSB first)
    - Bit = 1 means LED is on, 0 means off
    
    Args:
        binary_data: 2D array of bytes [divisions][bytes_per_line]
        color_rgb: Color for lit pixels (R, G, B tuple)
    
    Returns:
        Display data array compatible with POV display
    """
    r, g, b = color_rgb
    data = []
    
    num_divisions = len(binary_data)
    bytes_per_line = len(binary_data[0]) if binary_data else 0
    
    print(f"Loading binary image: {num_divisions} divisions, {bytes_per_line} bytes/line")
    
    for slice_idx in range(num_divisions):
        line = [Color(0, 0, 0)] * NUM_LEDS
        
        for byte_idx in range(bytes_per_line):
            byte_val = binary_data[slice_idx][byte_idx]
            
            for bit in range(8):
                led_pos = byte_idx * 8 + bit
                
                if led_pos < NUM_LEDS:
                    # MSB first (bit 7 = first pixel in byte)
                    if byte_val & (1 << (7 - bit)):
                        line[led_pos] = Color(int(g * BRIGHTNESS_RATIO),
                                             int(r * BRIGHTNESS_RATIO),
                                             int(b * BRIGHTNESS_RATIO))
        
        data.append(line)
    
    # Pad if binary data has fewer divisions than configured
    while len(data) < NUM_DIVISIONS:
        data.append([Color(0, 0, 0)] * NUM_LEDS)
    
    print(f"✓ Binary image loaded ({len(data)} divisions)")
    return data


# Example binary image data (smiley face) - replace with your own!
# Generated by POV Image Converter web app
Image_1 = [
    [0xFF, 0xFF, 0x1E, 0x7E, 0x7E, 0x3E, 0x7C, 0xFF, 0xFF],
    [0xFF, 0xFF, 0xF1, 0xC3, 0xFC, 0xF3, 0xCF, 0xFF, 0xFF],
    [0xFF, 0xFF, 0xFC, 0xFF, 0xFC, 0xE7, 0x9F, 0xFF, 0xFF],
    [0xFF, 0xFF, 0xF1, 0xE0, 0x7C, 0xF3, 0xCF, 0xFF, 0xFF],
    [0xFF, 0xFF, 0x1F, 0x1F, 0x3E, 0x7C, 0x7C, 0x7F, 0xFF],
    [0xFF, 0xFF, 0xF3, 0xE0, 0x7C, 0xF7, 0xCF, 0xFF, 0xFF],
    [0xFF, 0xFF, 0xFC, 0xFF, 0xFC, 0xE7, 0x1F, 0xFF, 0xFF],
    [0xFF, 0xFF, 0xF9, 0xC1, 0xFC, 0xF3, 0xCF, 0xFF, 0xFF],
    [0xFF, 0xFF, 0x3E, 0x7C, 0x7E, 0x7E, 0x78, 0xFF, 0xFF],
    [0xFF, 0xFF, 0xF3, 0xCF, 0x3F, 0xC3, 0x8F, 0xFF, 0xFF],
    [0xFF, 0xFF, 0xF9, 0xE7, 0x3F, 0xFF, 0x3F, 0xFF, 0xFF],
    [0xFF, 0xFF, 0xF3, 0xCF, 0x3E, 0x07, 0x8F, 0xFF, 0xFF],
    [0xFF, 0xFE, 0x3E, 0x3E, 0x7C, 0xF8, 0xF8, 0xFF, 0xFF],
    [0xFF, 0xFF, 0xF3, 0xEF, 0x3E, 0x07, 0xCF, 0xFF, 0xFF],
    [0xFF, 0xFF, 0xF8, 0xE7, 0x3F, 0xFF, 0x3F, 0xFF, 0xFF],
    [0xFF, 0xFF, 0xF3, 0xCF, 0x3F, 0x83, 0x9F, 0xFF, 0xFF]
]



# ============== BUTTON POLLING ==============

def check_buttons():
    """Poll buttons for mode changes"""
    global display_data, current_mode, last_button_states, last_button_time
    
    current_time = time.time()
    
    buttons = [
        (BUTTON_CIRCLE, "circle", lambda: generate_circle_data(radius_leds=28, color_rgb=(0, 255, 255)), "CIRCLE"),
        (BUTTON_SQUARE, "square", lambda: generate_square_data(side_length_leds=24, color_rgb=(255, 0, 255)), "SQUARE"),
        (BUTTON_IMAGE, "image", lambda: load_binary_image_data(Image_1, color_rgb=(0, 255, 255)), "IMAGE")
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
    Poll hall sensor with noise filtering and debouncing.
    Key improvements:
    1. Hardware debounce - ignore triggers too close together
    2. RPM validation - reject readings outside expected range
    3. Outlier rejection - reject sudden RPM jumps (noise)
    4. Aggressive smoothing - average over 15 rotations
    """
    global last_hall_state, last_rotation_micros, rotation_time_micros
    global time_per_line_micros, current_line, rotation_count, rotation_active
    global current_rpm, stable_rpm, rpm_history, missed_lines_count
    global last_hall_trigger_time, valid_rotation_count, noise_rejected_count
    global rpm_locked, rpm_stable_count
    
    current_state = GPIO.input(HALL_SENSOR_PIN)
    
    # Detect rising edge = magnet detected = 0° position
    if current_state == GPIO.HIGH and last_hall_state == GPIO.LOW:
        current_time = get_time_micros()
        
        # DEBOUNCE: Ignore triggers too close to last one (noise/bounce)
        time_since_last = current_time - last_hall_trigger_time
        if time_since_last < HALL_DEBOUNCE_US:
            last_hall_state = current_state
            noise_rejected_count += 1
            return
        
        last_hall_trigger_time = current_time
        
        # Calculate rotation time
        if last_rotation_micros > 0:
            measured_rotation_time = current_time - last_rotation_micros
            
            # VALIDATION 1: Check if rotation time is in valid RPM range
            min_rotation_time = int(60_000_000 / MAX_RPM)  # ~42ms at 1400 RPM
            max_rotation_time = int(60_000_000 / MIN_RPM)  # ~240ms at 250 RPM
            
            if not (min_rotation_time <= measured_rotation_time <= max_rotation_time):
                # Outside valid range - likely noise
                noise_rejected_count += 1
                last_hall_state = current_state
                # Still reset position but don't update timing
                current_line = 0
                rotation_count += 1
                last_rotation_micros = current_time
                return
            
            # Calculate instant RPM
            instant_rpm = 60_000_000 / measured_rotation_time
            
            # VALIDATION 2: Reject sudden RPM jumps (outliers)
            if len(rpm_history) >= 3:
                avg_rpm = sum(rpm_history) / len(rpm_history)
                rpm_change_percent = abs(instant_rpm - avg_rpm) / avg_rpm * 100
                
                if rpm_change_percent > MAX_RPM_CHANGE_PERCENT:
                    # Too big a jump - likely noise, reject it
                    noise_rejected_count += 1
                    last_hall_state = current_state
                    current_line = 0
                    rotation_count += 1
                    last_rotation_micros = current_time
                    return
            
            # Valid reading! Add to history
            rpm_history.append(instant_rpm)
            if len(rpm_history) > RPM_HISTORY_SIZE:
                rpm_history.pop(0)
            
            valid_rotation_count += 1
            
            # Calculate smoothed RPM (median is more robust than mean)
            if len(rpm_history) >= 5:
                sorted_rpm = sorted(rpm_history)
                # Use trimmed mean (remove highest and lowest, average rest)
                trimmed = sorted_rpm[2:-2] if len(sorted_rpm) > 6 else sorted_rpm[1:-1]
                stable_rpm = sum(trimmed) / len(trimmed) if trimmed else sum(sorted_rpm) / len(sorted_rpm)
            else:
                stable_rpm = sum(rpm_history) / len(rpm_history)
            
            current_rpm = stable_rpm
            
            # Calculate timing from stable RPM
            rotation_time_micros = int(60_000_000 / stable_rpm)
            time_per_line_micros = rotation_time_micros // NUM_DIVISIONS
            
            # Sanity check - ensure minimum time for LED update
            if time_per_line_micros < LED_UPDATE_TIME_US:
                time_per_line_micros = LED_UPDATE_TIME_US
            
            # Display status periodically (less spam)
            if valid_rotation_count % 50 == 0:
                max_safe = rotation_time_micros // LED_UPDATE_TIME_US
                status = "✓" if NUM_DIVISIONS <= max_safe else "⚠"
                print(f"{status} RPM: {stable_rpm:.0f} | "
                      f"Line time: {time_per_line_micros}µs | "
                      f"Noise rejected: {noise_rejected_count}")
        
        # Reset to position 0° (line 0)
        current_line = 0
        rotation_active = True
        rotation_count += 1
        last_rotation_micros = current_time
        
        if rotation_count == 1:
            print("\n✓ ROTATION DETECTED!")
            print(f"  Divisions: {NUM_DIVISIONS} ({360/NUM_DIVISIONS:.1f}° each)")
            print(f"  LED update: ~{LED_UPDATE_TIME_US}µs")
            print(f"  Default RPM: {DEFAULT_RPM}")
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
    
    # Calculate timing info
    rotation_time_at_default = int(60_000_000 / DEFAULT_RPM)
    time_per_line_at_default = rotation_time_at_default // NUM_DIVISIONS
    max_safe_divisions = rotation_time_at_default // LED_UPDATE_TIME_US
    degrees_per_division = 360.0 / NUM_DIVISIONS
    
    # Calculate for RPM range
    rotation_time_at_max = int(60_000_000 / MAX_RPM)
    max_safe_at_max_rpm = rotation_time_at_max // LED_UPDATE_TIME_US
    
    print("\n" + "="*65)
    print("  POV FAN - OPTIMIZED FOR HIGH-SPEED DISPLAY")
    print("="*65)
    
    print("\n▸ HARDWARE:")
    print(f"  • LED strip: {NUM_LEDS} WS2815 LEDs")
    print(f"  • LED update time: ~{LED_UPDATE_TIME_US}µs ({LED_UPDATE_TIME_US/1000:.1f}ms)")
    print(f"  • Brightness: {int(BRIGHTNESS_RATIO * 100)}%")
    
    print("\n▸ DIVISIONS:")
    print(f"  • {NUM_DIVISIONS} divisions ({degrees_per_division:.1f}° each)")
    print(f"  • Time per line at {DEFAULT_RPM} RPM: {time_per_line_at_default}µs")
    
    print("\n▸ RPM RANGE: {}-{} RPM".format(MIN_RPM, MAX_RPM))
    print(f"  • At {DEFAULT_RPM} RPM: max safe = {max_safe_divisions} divisions ✓" if NUM_DIVISIONS <= max_safe_divisions else f"  • At {DEFAULT_RPM} RPM: max safe = {max_safe_divisions} divisions")
    print(f"  • At {MAX_RPM} RPM: max safe = {max_safe_at_max_rpm} divisions" + (" ✓" if NUM_DIVISIONS <= max_safe_at_max_rpm else " ⚠"))
    
    if NUM_DIVISIONS <= max_safe_at_max_rpm:
        print(f"\n  ✓ {NUM_DIVISIONS} divisions is SAFE for your RPM range!")
    else:
        print(f"\n  ⚠ May have issues above ~{int(60_000_000 / (NUM_DIVISIONS * LED_UPDATE_TIME_US))} RPM")
    
    print("\n▸ NOISE FILTERING:")
    print(f"  • Hall debounce: {HALL_DEBOUNCE_US}µs")
    print(f"  • Max RPM change: {MAX_RPM_CHANGE_PERCENT}%")
    print(f"  • Smoothing: {RPM_HISTORY_SIZE} samples")
    
    print("\n▸ CONTROLS:")
    print("  • GPIO 17 → Circle (cyan)")
    print("  • GPIO 27 → Square (magenta)")
    print("  • GPIO 22 → Image")
    
    print("\n" + "="*65)
    print("  Spin the fan to start!")
    print("="*65 + "\n")
    
    # Generate initial shape
    display_data = generate_circle_data(radius_leds=26, color_rgb=(0, 255, 255))
    
    # Startup indicator
    for i in range(NUM_LEDS):
        strip.setPixelColor(i, Color(0, 30, 0) if i < 3 else Color(0, 0, 0))
    strip.show()
    
    try:
        while True:
            check_buttons()
            check_hall_sensor()
            display_current_line()
                
    except KeyboardInterrupt:
        print("\n\n" + "-"*50)
        print("SHUTDOWN STATS:")
        print(f"  • Total rotations: {rotation_count}")
        print(f"  • Valid rotations: {valid_rotation_count}")
        print(f"  • Final RPM: {stable_rpm:.1f}")
        print(f"  • Noise rejected: {noise_rejected_count}")
        if missed_lines_count > 0:
            print(f"  • Missed lines: {missed_lines_count}")
        clear_strip()
        print("-"*50)
        
    finally:
        GPIO.cleanup()
        print("Done!\n")


if __name__ == "__main__":
    main()
