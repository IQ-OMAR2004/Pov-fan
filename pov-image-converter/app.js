/**
 * POV Display Image Converter
 * Converts images to optimized byte arrays for LED displays
 * Supports both standard grid and polar (POV) formats
 */

// State
let uploadedImages = [];
let convertedData = [];

// DOM Elements
const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('fileInput');
const previewSection = document.getElementById('previewSection');
const previewGrid = document.getElementById('previewGrid');
const convertBtn = document.getElementById('convertBtn');
const clearBtn = document.getElementById('clearBtn');
const outputSection = document.getElementById('outputSection');
const codeOutput = document.getElementById('codeOutput');
const pythonOutput = document.getElementById('pythonOutput');
const outputStats = document.getElementById('outputStats');
const toast = document.getElementById('toast');

// Settings
const resolutionSelect = document.getElementById('resolution');
const divisionsInput = document.getElementById('divisions');
const thresholdInput = document.getElementById('threshold');
const thresholdValue = document.getElementById('thresholdValue');
const invertCheckbox = document.getElementById('invertColors');
const polarCheckbox = document.getElementById('polarMode');

// ============================================
// Event Listeners
// ============================================

// Dropzone events
dropzone.addEventListener('click', () => fileInput.click());
dropzone.addEventListener('dragover', handleDragOver);
dropzone.addEventListener('dragleave', handleDragLeave);
dropzone.addEventListener('drop', handleDrop);
fileInput.addEventListener('change', handleFileSelect);

// Button events
convertBtn.addEventListener('click', convertImages);
clearBtn.addEventListener('click', clearAll);

// Copy buttons
document.getElementById('copyAllBtn').addEventListener('click', () => copyToClipboard(codeOutput.textContent + '\n\n' + pythonOutput.textContent));
document.getElementById('copyCodeBtn').addEventListener('click', () => copyToClipboard(codeOutput.textContent));
document.getElementById('copyPythonBtn').addEventListener('click', () => copyToClipboard(pythonOutput.textContent));
document.getElementById('downloadBtn').addEventListener('click', downloadCode);

// Settings
thresholdInput.addEventListener('input', (e) => {
    thresholdValue.textContent = e.target.value;
});

// ============================================
// Drag & Drop Handlers
// ============================================

function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    dropzone.classList.add('dragover');
}

function handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    dropzone.classList.remove('dragover');
}

function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    dropzone.classList.remove('dragover');

    const files = Array.from(e.dataTransfer.files).filter(file => file.type.startsWith('image/'));
    if (files.length > 0) {
        processFiles(files);
    }
}

function handleFileSelect(e) {
    const files = Array.from(e.target.files);
    if (files.length > 0) {
        processFiles(files);
    }
}

// ============================================
// File Processing
// ============================================

function processFiles(files) {
    files.forEach((file, index) => {
        const reader = new FileReader();
        reader.onload = (e) => {
            const img = new Image();
            img.onload = () => {
                const imageData = {
                    id: Date.now() + index,
                    name: file.name.replace(/\.[^/.]+$/, ''),
                    originalImage: img,
                    file: file
                };
                uploadedImages.push(imageData);
                updatePreview();
                updateConvertButton();
            };
            img.src = e.target.result;
        };
        reader.readAsDataURL(file);
    });
}

function updatePreview() {
    previewSection.classList.add('visible');
    previewGrid.innerHTML = '';

    uploadedImages.forEach((imageData, index) => {
        const item = document.createElement('div');
        item.className = 'preview-item';
        item.innerHTML = `
            <img src="${imageData.originalImage.src}" alt="${imageData.name}">
            <span class="preview-name">Image_${index + 1}</span>
            <button class="remove-btn" data-id="${imageData.id}">×</button>
        `;

        item.querySelector('.remove-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            removeImage(imageData.id);
        });

        previewGrid.appendChild(item);
    });
}

function removeImage(id) {
    uploadedImages = uploadedImages.filter(img => img.id !== id);
    updatePreview();
    updateConvertButton();

    if (uploadedImages.length === 0) {
        previewSection.classList.remove('visible');
    }
}

function clearAll() {
    uploadedImages = [];
    convertedData = [];
    previewGrid.innerHTML = '';
    previewSection.classList.remove('visible');
    outputSection.classList.remove('visible');
    updateConvertButton();
}

function updateConvertButton() {
    convertBtn.disabled = uploadedImages.length === 0;
}

// ============================================
// Image Conversion
// ============================================

function convertImages() {
    const resolution = parseInt(resolutionSelect.value);
    const divisions = parseInt(divisionsInput.value);
    const threshold = parseInt(thresholdInput.value);
    const invert = invertCheckbox.checked;
    const polarMode = polarCheckbox.checked;

    convertedData = [];

    uploadedImages.forEach((imageData, index) => {
        let result;

        if (polarMode) {
            // POV mode - convert to polar coordinates for spinning LED display
            result = convertToPolar(imageData.originalImage, resolution, divisions, threshold, invert);
        } else {
            // Standard grid mode - for matrix displays
            result = convertToGrid(imageData.originalImage, resolution, threshold, invert);
        }

        convertedData.push({
            name: `Image_${index + 1}`,
            data: result.data,
            binaryData: result.binaryData,  // For polar mode packed bytes
            width: result.width,
            height: result.height,
            bytes: result.bytes,
            mode: polarMode ? 'polar' : 'grid'
        });
    });

    generateOutput();
}

function convertToGrid(img, size, threshold, invert) {
    // Create canvas for processing
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    canvas.width = size;
    canvas.height = size;

    // Draw and resize image
    ctx.fillStyle = 'white';
    ctx.fillRect(0, 0, size, size);

    // Calculate aspect ratio fit
    const scale = Math.min(size / img.width, size / img.height);
    const x = (size - img.width * scale) / 2;
    const y = (size - img.height * scale) / 2;
    ctx.drawImage(img, x, y, img.width * scale, img.height * scale);

    // Get pixel data
    const imageData = ctx.getImageData(0, 0, size, size);
    const pixels = imageData.data;

    // Convert to binary array (8 pixels per byte)
    const bytesPerRow = Math.ceil(size / 8);
    const data = [];

    for (let row = 0; row < size; row++) {
        const rowBytes = [];
        for (let byteIndex = 0; byteIndex < bytesPerRow; byteIndex++) {
            let byte = 0;
            for (let bit = 0; bit < 8; bit++) {
                const col = byteIndex * 8 + bit;
                if (col < size) {
                    const pixelIndex = (row * size + col) * 4;
                    // Convert to grayscale
                    const gray = pixels[pixelIndex] * 0.299 +
                        pixels[pixelIndex + 1] * 0.587 +
                        pixels[pixelIndex + 2] * 0.114;

                    let isWhite = gray > threshold;
                    if (invert) isWhite = !isWhite;

                    if (isWhite) {
                        byte |= (1 << (7 - bit));
                    }
                }
            }
            rowBytes.push(byte);
        }
        data.push(rowBytes);
    }

    return {
        data: data,
        width: size,
        height: size,
        bytes: size * bytesPerRow
    };
}

function convertToPolar(img, numLeds, divisions, threshold, invert) {
    // Create canvas for processing
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    const size = 600; // Internal processing size
    canvas.width = size;
    canvas.height = size;

    // Draw image centered
    ctx.fillStyle = 'white';
    ctx.fillRect(0, 0, size, size);

    const scale = Math.min(size / img.width, size / img.height);
    const x = (size - img.width * scale) / 2;
    const y = (size - img.height * scale) / 2;
    ctx.drawImage(img, x, y, img.width * scale, img.height * scale);

    const imageData = ctx.getImageData(0, 0, size, size);
    const pixels = imageData.data;

    const centerX = size / 2;
    const centerY = size / 2;
    const radius = size / 2 - 1;
    const ledsPerSide = numLeds / 2;

    const data = [];

    // For each angular division
    for (let slice = 0; slice < divisions; slice++) {
        const angleDeg = (slice * 360.0) / divisions;
        const angleRad = (angleDeg * Math.PI) / 180;

        const lineData = [];

        // First half of LEDs (0 to center)
        for (let led = 0; led < ledsPerSide; led++) {
            const radialDist = ((led + 1) * radius) / ledsPerSide;
            const px = Math.floor(centerX + radialDist * Math.cos(angleRad));
            const py = Math.floor(centerY + radialDist * Math.sin(angleRad));

            if (px >= 0 && px < size && py >= 0 && py < size) {
                const pixelIndex = (py * size + px) * 4;
                const gray = pixels[pixelIndex] * 0.299 +
                    pixels[pixelIndex + 1] * 0.587 +
                    pixels[pixelIndex + 2] * 0.114;

                let isLit = gray < threshold; // Dark = lit for POV
                if (invert) isLit = !isLit;

                // Store as RGB values (for color support)
                if (isLit) {
                    lineData.push({
                        r: pixels[pixelIndex],
                        g: pixels[pixelIndex + 1],
                        b: pixels[pixelIndex + 2],
                        pos: ledsPerSide - led - 1
                    });
                }
            }
        }

        // Second half of LEDs (center to end) - opposite direction
        const oppositeAngle = angleRad + Math.PI;
        for (let led = 0; led < ledsPerSide; led++) {
            const radialDist = ((led + 1) * radius) / ledsPerSide;
            const px = Math.floor(centerX + radialDist * Math.cos(oppositeAngle));
            const py = Math.floor(centerY + radialDist * Math.sin(oppositeAngle));

            if (px >= 0 && px < size && py >= 0 && py < size) {
                const pixelIndex = (py * size + px) * 4;
                const gray = pixels[pixelIndex] * 0.299 +
                    pixels[pixelIndex + 1] * 0.587 +
                    pixels[pixelIndex + 2] * 0.114;

                let isLit = gray < threshold;
                if (invert) isLit = !isLit;

                if (isLit) {
                    lineData.push({
                        r: pixels[pixelIndex],
                        g: pixels[pixelIndex + 1],
                        b: pixels[pixelIndex + 2],
                        pos: ledsPerSide + led
                    });
                }
            }
        }

        data.push(lineData);
    }

    // Also create binary packed version
    const binaryData = [];
    const bytesPerLine = Math.ceil(numLeds / 8);

    for (let slice = 0; slice < divisions; slice++) {
        const lineBytes = new Array(bytesPerLine).fill(0);
        const angleDeg = (slice * 360.0) / divisions;
        const angleRad = (angleDeg * Math.PI) / 180;

        // Process all LEDs for this slice
        for (let led = 0; led < numLeds; led++) {
            let px, py;

            if (led < ledsPerSide) {
                // First half
                const radialDist = ((ledsPerSide - led) * radius) / ledsPerSide;
                px = Math.floor(centerX + radialDist * Math.cos(angleRad));
                py = Math.floor(centerY + radialDist * Math.sin(angleRad));
            } else {
                // Second half (opposite direction)
                const radialDist = ((led - ledsPerSide + 1) * radius) / ledsPerSide;
                const oppositeAngle = angleRad + Math.PI;
                px = Math.floor(centerX + radialDist * Math.cos(oppositeAngle));
                py = Math.floor(centerY + radialDist * Math.sin(oppositeAngle));
            }

            if (px >= 0 && px < size && py >= 0 && py < size) {
                const pixelIndex = (py * size + px) * 4;
                const gray = pixels[pixelIndex] * 0.299 +
                    pixels[pixelIndex + 1] * 0.587 +
                    pixels[pixelIndex + 2] * 0.114;

                let isLit = gray < threshold;
                if (invert) isLit = !isLit;

                if (isLit) {
                    const byteIndex = Math.floor(led / 8);
                    const bitIndex = 7 - (led % 8);
                    lineBytes[byteIndex] |= (1 << bitIndex);
                }
            }
        }
        binaryData.push(lineBytes);
    }

    return {
        data: data,
        binaryData: binaryData,
        width: numLeds,
        height: divisions,
        bytes: divisions * bytesPerLine
    };
}

// ============================================
// Output Generation
// ============================================

function generateOutput() {
    outputSection.classList.add('visible');

    const resolution = parseInt(resolutionSelect.value);
    const divisions = parseInt(divisionsInput.value);
    const polarMode = polarCheckbox.checked;

    // Generate stats
    let totalBytes = 0;
    convertedData.forEach(img => totalBytes += img.bytes);

    outputStats.innerHTML = `
        <div class="stat-item">
            <span class="stat-label">Images</span>
            <span class="stat-value">${convertedData.length}</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">Mode</span>
            <span class="stat-value">${polarMode ? 'POV Polar' : 'Grid'}</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">${polarMode ? 'LEDs × Divisions' : 'Resolution'}</span>
            <span class="stat-value">${polarMode ? `${resolution} × ${divisions}` : `${resolution}×${resolution}`}</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">Total Size</span>
            <span class="stat-value">${formatBytes(totalBytes)}</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">Compression</span>
            <span class="stat-value">8:1</span>
        </div>
    `;

    // Generate Arduino/C++ code
    codeOutput.innerHTML = generateArduinoCode();

    // Generate Python code
    pythonOutput.innerHTML = generatePythonCode();
}

function generateArduinoCode() {
    const polarMode = polarCheckbox.checked;
    const resolution = parseInt(resolutionSelect.value);
    const divisions = parseInt(divisionsInput.value);

    let code = '';

    // Header comment
    code += `<span class="comment">/*
 * POV Display Image Data
 * Generated by POV Image Converter
 * Mode: ${polarMode ? 'POV Polar' : 'Standard Grid'}
 * ${polarMode ? `LEDs: ${resolution}, Divisions: ${divisions}` : `Resolution: ${resolution}x${resolution}`}
 */</span>\n\n`;

    // Include guard
    code += `<span class="keyword">#ifndef</span> POV_IMAGES_H\n`;
    code += `<span class="keyword">#define</span> POV_IMAGES_H\n\n`;

    // Constants
    if (polarMode) {
        code += `<span class="keyword">#define</span> NUM_LEDS ${resolution}\n`;
        code += `<span class="keyword">#define</span> NUM_DIVISIONS ${divisions}\n`;
        code += `<span class="keyword">#define</span> BYTES_PER_LINE ${Math.ceil(resolution / 8)}\n\n`;
    } else {
        code += `<span class="keyword">#define</span> IMAGE_WIDTH ${resolution}\n`;
        code += `<span class="keyword">#define</span> IMAGE_HEIGHT ${resolution}\n`;
        code += `<span class="keyword">#define</span> BYTES_PER_ROW ${Math.ceil(resolution / 8)}\n\n`;
    }

    // Generate arrays for each image
    convertedData.forEach((img, index) => {
        // Determine which data to use based on mode
        const isPolar = img.mode === 'polar';
        const dataToUse = isPolar ? img.binaryData : img.data;

        if (!dataToUse || dataToUse.length === 0) {
            code += `<span class="comment">// ${img.name} - ERROR: No data available</span>\n\n`;
            return;
        }

        code += `<span class="comment">// ${img.name} - ${img.bytes} bytes</span>\n`;

        if (isPolar) {
            code += `<span class="keyword">const</span> <span class="type">uint8_t</span> PROGMEM ${img.name}[NUM_DIVISIONS][BYTES_PER_LINE] = {\n`;
        } else {
            code += `<span class="keyword">const</span> <span class="type">uint8_t</span> PROGMEM ${img.name}[IMAGE_HEIGHT][BYTES_PER_ROW] = {\n`;
        }

        dataToUse.forEach((row, rowIndex) => {
            // Ensure we're working with numbers, not objects
            const bytes = row.map(b => {
                const byteVal = typeof b === 'number' ? b : 0;
                return `<span class="number">0x${byteVal.toString(16).padStart(2, '0').toUpperCase()}</span>`;
            }).join(', ');
            const comma = rowIndex < dataToUse.length - 1 ? ',' : '';
            code += `  {${bytes}}${comma}\n`;
        });

        code += `};\n\n`;
    });

    // Image count
    code += `<span class="keyword">#define</span> NUM_IMAGES ${convertedData.length}\n\n`;

    // Array of pointers
    code += `<span class="comment">// Array of image pointers</span>\n`;
    code += `<span class="keyword">const</span> <span class="type">uint8_t</span>* <span class="keyword">const</span> images[NUM_IMAGES] = {\n`;
    convertedData.forEach((img, index) => {
        const comma = index < convertedData.length - 1 ? ',' : '';
        code += `  (<span class="keyword">const</span> <span class="type">uint8_t</span>*)${img.name}${comma}\n`;
    });
    code += `};\n\n`;

    code += `<span class="keyword">#endif</span> <span class="comment">// POV_IMAGES_H</span>`;

    return code;
}

function generatePythonCode() {
    const polarMode = polarCheckbox.checked;
    const resolution = parseInt(resolutionSelect.value);
    const divisions = parseInt(divisionsInput.value);

    let code = '';

    // Header comment
    code += `<span class="comment"># POV Display Image Data
# Generated by POV Image Converter
# Mode: ${polarMode ? 'POV Polar' : 'Standard Grid'}
# ${polarMode ? `LEDs: ${resolution}, Divisions: ${divisions}` : `Resolution: ${resolution}x${resolution}`}</span>\n\n`;

    // Constants
    if (polarMode) {
        code += `NUM_LEDS = <span class="number">${resolution}</span>\n`;
        code += `NUM_DIVISIONS = <span class="number">${divisions}</span>\n`;
        code += `BYTES_PER_LINE = <span class="number">${Math.ceil(resolution / 8)}</span>\n\n`;
    } else {
        code += `IMAGE_WIDTH = <span class="number">${resolution}</span>\n`;
        code += `IMAGE_HEIGHT = <span class="number">${resolution}</span>\n`;
        code += `BYTES_PER_ROW = <span class="number">${Math.ceil(resolution / 8)}</span>\n\n`;
    }

    // Generate arrays
    convertedData.forEach((img, index) => {
        // Determine which data to use based on mode
        const isPolar = img.mode === 'polar';
        const dataToUse = isPolar ? img.binaryData : img.data;

        if (!dataToUse || dataToUse.length === 0) {
            code += `<span class="comment"># ${img.name} - ERROR: No data available</span>\n\n`;
            return;
        }

        code += `<span class="comment"># ${img.name} - ${img.bytes} bytes</span>\n`;
        code += `${img.name} = [\n`;

        dataToUse.forEach((row, rowIndex) => {
            // Ensure we're working with numbers, not objects
            const bytes = row.map(b => {
                const byteVal = typeof b === 'number' ? b : 0;
                return `<span class="number">0x${byteVal.toString(16).padStart(2, '0').toUpperCase()}</span>`;
            }).join(', ');
            const comma = rowIndex < dataToUse.length - 1 ? ',' : '';
            code += `    [${bytes}]${comma}\n`;
        });

        code += `]\n\n`;
    });

    // List of images
    code += `<span class="comment"># All images</span>\n`;
    code += `images = [\n`;
    convertedData.forEach((img, index) => {
        const comma = index < convertedData.length - 1 ? ',' : '';
        code += `    ${img.name}${comma}\n`;
    });
    code += `]\n`;

    return code;
}

// ============================================
// Utility Functions
// ============================================

function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
}

function copyToClipboard(text) {
    // Remove HTML tags for clipboard
    const plainText = text.replace(/<[^>]*>/g, '');

    navigator.clipboard.writeText(plainText).then(() => {
        showToast('Copied to clipboard!');
    }).catch(err => {
        console.error('Failed to copy:', err);
        showToast('Failed to copy');
    });
}

function showToast(message) {
    toast.querySelector('.toast-text').textContent = message;
    toast.classList.add('visible');

    setTimeout(() => {
        toast.classList.remove('visible');
    }, 2000);
}

function downloadCode() {
    const arduinoCode = codeOutput.textContent.replace(/<[^>]*>/g, '');
    const pythonCode = pythonOutput.textContent.replace(/<[^>]*>/g, '');

    // Create Arduino header file
    const arduinoBlob = new Blob([arduinoCode], { type: 'text/plain' });
    const arduinoUrl = URL.createObjectURL(arduinoBlob);
    const arduinoLink = document.createElement('a');
    arduinoLink.href = arduinoUrl;
    arduinoLink.download = 'pov_images.h';
    arduinoLink.click();

    // Create Python file
    setTimeout(() => {
        const pythonBlob = new Blob([pythonCode], { type: 'text/plain' });
        const pythonUrl = URL.createObjectURL(pythonBlob);
        const pythonLink = document.createElement('a');
        pythonLink.href = pythonUrl;
        pythonLink.download = 'pov_images.py';
        pythonLink.click();

        URL.revokeObjectURL(arduinoUrl);
        URL.revokeObjectURL(pythonUrl);
    }, 100);

    showToast('Files downloaded!');
}

// Initialize
console.log('POV Image Converter loaded');

