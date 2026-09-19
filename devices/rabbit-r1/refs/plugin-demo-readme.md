# R1 Creations Static Website - Implementation Plan

## Project Overview
A static website designed for a 240x282 browser window with interactive features for testing R1 Creations plugin capabilities using the Creations SDK. This test app demonstrates major SDK features including hardware events, LLM integration, and sensor data.

## Technical Specifications
- **Browser Size**: 240x282 pixels (fixed)
- **Type**: Static HTML/CSS/JavaScript
- **API**: R1 Creations SDK only (no direct WebSocket usage)
- **Features**: Hardware controls, LLM integration, sensor data

## Architecture

### File Structure
```
/
├── index.html          # Main SPA with menu navigation
├── css/
│   └── styles.css      # Shared styles (240x282 optimized)
├── js/
│   ├── app.js          # Main application logic & navigation
│   ├── hardware.js     # Hardware page - button events & accelerometer
│   ├── data.js         # Data page - LLM interactions & dynamic theming
│   └── speak.js        # Speak page - TTS
└── reference/
    └── creation-triggers.md  # SDK documentation
```

## Implementation Plan

## Current Implementation Status

### ✅ Completed Features

1. **Navigation System**
   - Hamburger menu (top-right) with slide-in drawer
   - Three pages: Hardware, Data, Speak 
   - Dynamic page loading without refresh
   - Active page highlighting

2. **Hardware Page**
   - UP/DOWN/PTT buttons with LED blink animations
   - Real-time accelerometer display (X, Y, Z axes)
   - Start/Stop accelerometer toggle
   - Hardware event listeners for scroll wheel and side button

3. **Data Page**
   - Compact horizontal button layout
   - Chat window with scrollable history
   - Cat Facts: Requests and parses JSON array of facts
   - Dinos: Simple text responses
   - Paint toggle: Changes app border color dynamically
   - Clear chat functionality

4. **Speak Page**
   - Text area for message input
   - R1 speaker output option
   - Status indicator


### Phase 1: Foundation Setup
1. **Base HTML Structure**
   - Create index.html with responsive layout for 240x282px
   - Implement menu button (top-right hamburger icon)
   - Set up navigation drawer with 3 menu items
   - Configure viewport meta tags for fixed sizing

2. **Navigation System**
   - Single-page application with dynamic content loading
   - Menu slides in from right side
   - Smooth transitions between pages
   - Active page highlighting

3. **Core Styling**
   - CSS Grid/Flexbox for 240x282 constraint
   - Dark theme with high contrast for small screen
   - Touch-friendly button sizes (min 44x44px)
   - Consistent 5px border for dynamic coloring

## Usage Examples

### Running the App
1. Deploy as an R1 Creation plugin
2. Open the app on your R1 device
3. Use the hamburger menu to navigate between pages

### Hardware Page Testing
```javascript
// Scroll wheel events trigger LED blinks
// UP scroll → UP LED blinks green
// DOWN scroll → DOWN LED blinks green
// PTT click → PTT LED blinks green

// Accelerometer shows real-time values
// X: -1.00 to 1.00 (left/right tilt)
// Y: -1.00 to 1.00 (forward/back tilt)
// Z: -1.00 to 1.00 (face up/down)
```

### Data Page Examples

```javascript
// Cat Facts Button
PluginMessageHandler.postMessage(JSON.stringify({
  message: 'Tell me 5 facts about cats. Respond ONLY with valid JSON in this exact format: {"facts":["fact1","fact2","fact3","fact4","fact5"]}',
  useLLM: true
}));

// Expected Response (in data.data or data.message):
{
  "facts": [
    "Cats have 32 muscles in each ear",
    "A group of cats is called a clowder",
    "Cats sleep for 13-14 hours a day",
    "A cat's nose print is unique",
    "Cats can rotate their ears 180 degrees"
  ]
}

// Display in chat:
// Fact 1: Cats have 32 muscles in each ear
// Fact 2: A group of cats is called a clowder
// ...

// Paint Color Button
PluginMessageHandler.postMessage(JSON.stringify({
  message: 'Give me the hex color code for red. Return ONLY valid JSON in this exact format: {"paint":"#hexcode"}',
  useLLM: true
}));

// Expected Response:
{"paint": "#ff0000"}
// Result: App border changes to red
```

### Speak Page Examples

```javascript
// Speak with R1 voice output
PluginMessageHandler.postMessage(JSON.stringify({
  message: "Hello, this is a test message",
  useLLM: true,
  wantsR1Response: true    // Speaks through R1 speaker
}));

// Silent processing (no voice)
PluginMessageHandler.postMessage(JSON.stringify({
  message: "Process this silently",
  useLLM: true,
  wantsR1Response: false
}));
```

## Technical Details

### Message Handling Flow

```javascript
// Plugin sends message
PluginMessageHandler.postMessage(JSON.stringify(payload));

// App receives response
window.onPluginMessage = function(data) {
  // Response can be in data.data (JSON string) or data.message (text)
  if (data.data) {
    const parsed = JSON.parse(data.data);
    // Handle structured data
  }
  if (data.message) {
    // Handle text message
  }
};
```

### Storage API Usage

```javascript
// Save to persistent storage
await window.creationStorage.plain.setItem(
  'app_settings',
  btoa(JSON.stringify(settings))
);

// Load from storage
const stored = await window.creationStorage.plain.getItem('app_settings');
const settings = JSON.parse(atob(stored));
```

### Hardware Event Registration

```javascript
// Scroll wheel
window.addEventListener('scrollUp', handleScrollUp);
window.addEventListener('scrollDown', handleScrollDown);

// Side button (PTT)
window.addEventListener('sideClick', handleClick);
window.addEventListener('longPressStart', handleLongPressStart);
window.addEventListener('longPressEnd', handleLongPressEnd);

// Accelerometer
window.creationSensors.accelerometer.start((data) => {
  // data = { x: 0.1, y: -0.2, z: 0.98 }
}, { frequency: 60 });
```

## Testing Guide

### Quick Test Checklist

1. **Menu Navigation**
   - [ ] Hamburger button opens menu
   - [ ] All 3 pages load correctly
   - [ ] Menu closes after selection

2. **Hardware Page**
   - [ ] Scroll up → UP LED blinks
   - [ ] Scroll down → DOWN LED blinks
   - [ ] PTT click → PTT LED blinks
   - [ ] Accelerometer shows live data

3. **Data Page**
   - [ ] Cat Facts returns 5 facts
   - [ ] Dino button returns text
   - [ ] Paint button changes border color
   - [ ] Chat window scrolls properly

4. **Speak Page**
   - [ ] R1 speaks the text
   - [ ] Status updates show

## Troubleshooting

### Common Issues

**Accelerometer not working:**
- Check if `window.creationSensors` is available
- Verify device has accelerometer support
- Check console for permission errors

**LLM responses not parsing:**
- Check console for response format
- Verify JSON is valid (double quotes, not single)
- Check both `data.data` and `data.message` fields

**Border color not changing:**
- Ensure hex code is valid format (#RRGGBB)
- Check if `updateAppBorderColor()` is called
- Verify CSS border property on #app element

## Important Notes

- **No WebSocket Usage**: All communication happens through the R1 Creations SDK JavaScript channels (PluginMessageHandler, CreationStorageHandler, etc.)
- The 240x282px constraint requires careful UI design
- Prioritize essential features for small screen
- Use progressive enhancement for advanced features
- Consider battery impact of continuous sensor polling
- All plugin messages are handled via `window.onPluginMessage` callback
- Hardware events use native window event listeners provided by the SDK