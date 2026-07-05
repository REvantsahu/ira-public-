# Sarvam AI TTS Setup for IRA

To enable Sarvam AI TTS with automatic key rotation in your IRA agent, follow these steps:

## 1. Get Sarvam AI API Keys

Visit https://sarvam.ai to obtain API keys. You can get multiple keys for rotation (recommended: 3-5 keys).

## 2. Configure the Keys

Edit the `web/app.js` file and locate this section near the top:

```javascript
// Sarvam AI TTS Integration with Key Rotation
let sarvamApiKeys = [
  // Add your Sarvam API keys here - will be rotated automatically
  // Example: "your_sarvam_api_key_1", "your_sarvam_api_key_2", etc.
];
let currentKeyIndex = 0;
```

Replace it with your actual keys:

```javascript
// Sarvam AI TTS Integration with Key Rotation
let sarvamApiKeys = [
  "your_first_sarvam_api_key_here",
  "your_second_sarvam_api_key_here", 
  "your_third_sarvam_api_key_here",
  "your_fourth_sarvam_api_key_here",
  "your_fifth_sarvam_api_key_here"
];
let currentKeyIndex = 0;
```

## 3. Key Rotation System

The system automatically rotates through your keys:
- Uses Key 1 for first TTS request
- Uses Key 2 for second TTS request  
- Continues rotating through all keys
- After the last key, goes back to Key 1
- If a key fails (quota exceeded, invalid, etc.), it automatically falls back to the next key
- If all keys fail, falls back to browser's native TTS

## 4. Customization Options

You can adjust these parameters in the `speakWithSarvam` function:

- `target_language_code`: Change to 'en-IN' for English or other language codes
- `speaker': Choose different voices like 'meera', 'arya', etc. (check Sarvam docs)
- `pitch`, `pace`, `loudness`: Adjust voice characteristics
- `model`: Different Sarvam models if available

## 5. Testing

After adding your keys:
1. Save the `web/app.js` file
2. Restart the IRA server (`python web_gui.py`)
3. Enable voice mode and test with any message
4. Check browser console for any errors or fallback messages

## 6. Monitoring Key Usage

The system will show in the console:
- Successful Sarvam TTS usage
- Fallback events when keys fail
- Automatic switching between keys

## Benefits of This Setup:

✅ **Automatic Load Distribution**: Requests spread evenly across all keys
✅ **Quota Protection**: If one key hits limit, others continue working
✅ **Failover Protection**: Automatic fallback to next key or browser TTS
✅ **Zero Downtime**: Service continues even if individual keys have issues
✅ **Optimal Performance**: Uses fastest available key at any moment

This implementation follows the multi-oscillator/rotation pattern you requested, treating the 5 API keys as oscillators that rotate in sequence to distribute load and provide redundancy.