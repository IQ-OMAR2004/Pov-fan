# POV Display Image Converter

A web application to convert images to optimized byte arrays for POV (Persistence of Vision) LED displays.

## Features

- **8x Compression**: Stores 8 pixels per byte (binary format)
- **POV Polar Mode**: Converts images to polar coordinates for spinning LED displays
- **Grid Mode**: Standard conversion for LED matrix displays
- **Multiple Image Support**: Convert multiple images at once
- **Dual Output**: Generates both C++/Arduino and Python code
- **Customizable Settings**:
  - Resolution (32, 64, 72, 128 pixels)
  - Number of divisions (for POV mode)
  - Black/white threshold
  - Color inversion

## Usage

### Quick Start

1. Open `index.html` in a web browser
2. Drag and drop images or click to browse
3. Adjust settings as needed
4. Click "Convert to Code"
5. Copy or download the generated code

### Settings

| Setting | Description |
|---------|-------------|
| **Resolution** | Number of LEDs in your strip (72 for your POV fan) |
| **Divisions** | Number of angular slices per rotation (16 for your setup) |
| **Threshold** | Brightness cutoff for black/white (0-255) |
| **Invert Colors** | Flip black and white pixels |
| **POV Polar Mode** | Enable for spinning LED fans (recommended) |

### For Your POV Fan

Use these settings:
- Resolution: **72 LEDs (Custom)**
- Divisions: **16**
- POV Polar Mode: **Enabled**

## Output Format

### Arduino/C++ (pov_images.h)

```cpp
const uint8_t PROGMEM Image_1[NUM_DIVISIONS][BYTES_PER_LINE] = {
  {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF},
  // ... more lines
};
```

### Python (pov_images.py)

```python
Image_1 = [
    [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF],
    # ... more lines
]
```

## Image Preparation Tips

1. **Use square images** - The converter will center non-square images
2. **High contrast works best** - Clear black and white images convert better
3. **Keep it simple** - Complex images may not display well on low-resolution POV displays
4. **Test the threshold** - Adjust the threshold slider to get the best conversion

## File Structure

```
pov-image-converter/
├── index.html     # Main HTML file
├── styles.css     # Styling
├── app.js         # Conversion logic
└── README.md      # This file
```

## Browser Support

Works in all modern browsers (Chrome, Firefox, Safari, Edge).

No server required - runs entirely in the browser!

## Integration with POV Fan

To use the generated code with your POV fan:

1. Convert your image using this tool
2. Copy the Python code
3. Add the image data to your `pov_fan_correct.py` file
4. Load the image data in your display function

Example integration:

```python
# In pov_fan_correct.py

from pov_images import Image_1, NUM_DIVISIONS, BYTES_PER_LINE

def load_binary_image(image_data):
    """Load image from binary format"""
    data = []
    for slice_idx in range(len(image_data)):
        line = [Color(0, 0, 0)] * NUM_LEDS
        for byte_idx, byte_val in enumerate(image_data[slice_idx]):
            for bit in range(8):
                led_pos = byte_idx * 8 + bit
                if led_pos < NUM_LEDS:
                    if byte_val & (1 << (7 - bit)):
                        line[led_pos] = Color(255, 255, 255)
        data.append(line)
    return data
```

## License

Open source - use freely for your projects!

