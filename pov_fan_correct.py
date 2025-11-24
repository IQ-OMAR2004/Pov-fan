#!/usr/bin/env python3
"""
POV Holographic Fan Display - CORRECT POV LOGIC
Works directly from hall sensor readings
No averaging, no prediction - pure real-time response

For WS2815 LED Strip (72 LEDs) and A3144 Hall Sensor
Optimized for 400-600 RPM

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
LED_BRIGHTNESS = 100
LED_INVERT = False
LED_CHANNEL = 0

HALL_SENSOR_PIN = 4
BUTTON_CIRCLE = 17
BUTTON_SQUARE = 27
BUTTON_IMAGE = 22

# ============== DISPLAY CONFIGURATION ==============
NUM_DIVISIONS = 150  # Number of lines per rotation
BRIGHTNESS_RATIO = 0.5
LINES_TO_SHIFT = -18

# ============== GLOBAL VARIABLES ==============
current_mode = "circle"
display_data = []

# Timing variables - THE SIMPLE WAY
last_rotation_micros = 0
rotation_time_micros = 0  # Time for ONE full rotation
time_per_line_micros = 0  # Time to display each line
current_line = 0
rotation_active = False

# Button state tracking
last_button_states = {BUTTON_CIRCLE: GPIO.HIGH, BUTTON_SQUARE: GPIO.HIGH, BUTTON_IMAGE: GPIO.HIGH}
last_button_time = {BUTTON_CIRCLE: 0, BUTTON_SQUARE: 0, BUTTON_IMAGE: 0}
DEBOUNCE_TIME = 0.3

# Hall sensor tracking
last_hall_state = GPIO.LOW
rotation_count = 0

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
    """Generate circle data"""
    data = []
    center_led = NUM_LEDS // 2
    r, g, b = color_rgb
    
    for angle_idx in range(NUM_DIVISIONS):
        line = [Color(0, 0, 0)] * NUM_LEDS
        
        if radius_leds < NUM_LEDS // 2:
            led_pos_1 = center_led - radius_leds
            led_pos_2 = center_led + radius_leds
            
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
    """Generate CLEAR square data - very obvious square shape"""
    data = []
    center_led = NUM_LEDS // 2
    r, g, b = color_rgb
    
    # Make square edges thicker for visibility
    edge_thickness = 3  # LEDs thick for each edge
    
    for angle_idx in range(NUM_DIVISIONS):
        line = [Color(0, 0, 0)] * NUM_LEDS
        
        # Calculate angle in degrees (0-360)
        angle_deg = (angle_idx * 360.0 / NUM_DIVISIONS) % 360
        
        # Determine which edge of the square we're on
        # Rotate square 45° so corners are at 45°, 135°, 225°, 315°
        # Edges are at 0°, 90°, 180°, 270°
        
        # Normalize angle to 0-90 degrees (one quadrant)
        normalized_angle = angle_deg % 90
        
        # Determine if we're showing an edge (flat side) or nothing (corner area)
        # Show square ONLY on the 4 cardinal directions
        show_edge = False
        distance = side_length_leds // 2
        
        # Right edge (around 0°)
        if (angle_deg >= 337.5 or angle_deg < 22.5):
            show_edge = True
            
        # Top edge (around 90°)
        elif (67.5 <= angle_deg < 112.5):
            show_edge = True
            
        # Left edge (around 180°)
        elif (157.5 <= angle_deg < 202.5):
            show_edge = True
            
        # Bottom edge (around 270°)
        elif (247.5 <= angle_deg < 292.5):
            show_edge = True
        
        # Light up LEDs at the calculated distance if we're on an edge
        if show_edge:
            # Create thicker edges for visibility
            for offset in range(-edge_thickness//2, edge_thickness//2 + 1):
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
    Calculate timing from LAST rotation
    Use that timing for CURRENT rotation
    """
    global last_hall_state, last_rotation_micros, rotation_time_micros
    global time_per_line_micros, current_line, rotation_count, rotation_active
    
    current_state = GPIO.input(HALL_SENSOR_PIN)
    
    # Detect rising edge = magnet detected = 0° position
    if current_state == GPIO.HIGH and last_hall_state == GPIO.LOW:
        current_time = get_time_micros()
        
        # Calculate how long the LAST rotation took
        if last_rotation_micros > 0:
            rotation_time_micros = current_time - last_rotation_micros
            # This is how much time we have for each line
            time_per_line_micros = rotation_time_micros / NUM_DIVISIONS
            
            # Calculate RPM for display
            if rotation_time_micros > 0:
                rpm = 60_000_000 / rotation_time_micros
                if rotation_count % 20 == 0:
                    print(f"RPM: {rpm:.1f}")
        
        # Reset to position 0° (line 0)
        current_line = 0
        rotation_active = True
        rotation_count += 1
        last_rotation_micros = current_time
        
        if rotation_count == 1:
            print("\n✓ ROTATION DETECTED!")
            print("Display active. Press buttons to change modes.\n")
    
    last_hall_state = current_state


# ============== DISPLAY FUNCTION - THE CORRECT WAY ==============

def display_current_line():
    """
    Display the current line, then wait precise time before next line
    THIS is how POV should work - simple and direct!
    """
    global current_line
    
    if not rotation_active or time_per_line_micros <= 0:
        return
    
    # Which line to show (with rotation adjustment)
    line_to_show = (current_line + LINES_TO_SHIFT + NUM_DIVISIONS) % NUM_DIVISIONS
    
    # Start timing
    start_time = get_time_micros()
    
    # Set LEDs for this line
    if display_data and line_to_show < len(display_data):
        line_data = display_data[line_to_show]
        for i in range(NUM_LEDS):
            strip.setPixelColor(i, line_data[i])
        strip.show()
    
    # Calculate how long LED update took
    elapsed = get_time_micros() - start_time
    
    # Wait the remaining time for this angular position
    remaining = time_per_line_micros - elapsed
    
    if remaining > 0:
        # Precise busy-wait for accurate timing
        target_time = get_time_micros() + remaining
        while get_time_micros() < target_time:
            pass
    
    # Move to next line
    current_line += 1
    if current_line >= NUM_DIVISIONS:
        current_line = 0


# ============== MAIN LOOP ==============

def main():
    global display_data
    
    print("\n" + "="*60)
    print("POV FAN - CORRECT REAL-TIME LOGIC")
    print("="*60)
    print("\nHow it works:")
    print("  1. Hall sensor triggers = 0° position")
    print("  2. Measure time since last trigger = rotation time")
    print("  3. Divide by lines = time per line")
    print("  4. Display lines with precise timing")
    print("  5. Sensor triggers again = back to 0°")
    print("\nConfiguration:")
    print(f"  Lines per rotation: {NUM_DIVISIONS}")
    print(f"  LEDs: {NUM_LEDS}")
    print(f"  Target RPM: 400-600")
    print("\nButtons:")
    print("  GPIO 17 - Circle")
    print("  GPIO 27 - Square")
    print("  GPIO 22 - Custom Image")
    print("\n" + "="*60)
    print("Spin the fan to start!")
    print("="*60 + "\n")
    
    # Start with circle
    display_data = generate_circle_data()
    
    # Startup indicator
    for i in range(5):
        strip.setPixelColor(i, Color(30, 30, 150))
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
        print("\n\nShutting down...")
        if rotation_count > 0:
            print(f"Total rotations: {rotation_count}")
        clear_strip()
        
    finally:
        GPIO.cleanup()
        print("Done!\n")


if __name__ == "__main__":
    main()
