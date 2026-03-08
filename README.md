# Team: The Bananoids
Devin J. Dawson - devin@waterpistol.co
Veena Vijay - vijayveen@gmail.com
Sri Bhuvana Vaishnavi Dasika - sd3971@columbia.edu | dasikavaishnavi@gmail.com
Prisma Lopez - zznailmail@gmail.com

# AI Virtual Stylist

A real-time, voice-activated virtual stylist application that uses your webcam and Google's Gemini AI to generate personalized outfits and backgrounds. Talk to the stylist, upload inspiration images, and see yourself transformed into new characters and eras.

## Features

- 🎙️ **Real-time Voice Interaction**: Converse naturally with the AI stylist using the Gemini Live API. Just click "Talk to Stylist" and start speaking!
- 📸 **Webcam Integration**: Captures your current look from your webcam to use as a base for transformations, keeping your face and pose intact.
- 👗 **Outfit & Background Generation**: Ask the stylist to try on new clothes (e.g., "Put me in a 1920s suit") or place you in different environments (e.g., "Put me on Mars").
- 🖼️ **Inspiration Uploads**: Upload an image to use as a reference. Toggle between using the uploaded image for **Clothing** inspiration or **Background** inspiration.
- 🎭 **Character Creation**: Automatically generates a unique character name, a short biography, and an era (circa) for each new look, displayed beautifully on the generated image.
- 💾 **Download**: Save your generated styles directly to your device with a single click.

## Tech Stack

- **Frontend**: React 18, Vite, Tailwind CSS
- **Icons**: Lucide React
- **AI Integration**: `@google/genai` SDK
  - Live Voice Conversation: `gemini-2.5-flash-native-audio-preview-09-2025`
  - Image Generation: `gemini-2.5-flash-image`

## Getting Started

### Prerequisites

- Node.js (v18 or higher)
- A Gemini API Key

### Installation

1. Clone the repository and navigate to the project directory.
2. Install dependencies:
   ```bash
   npm install
   ```
3. Create a `.env` file in the root directory and add your Gemini API key:
   ```env
   GEMINI_API_KEY=your_api_key_here
   ```
4. Start the development server:
   ```bash
   npm run dev
   ```

## How to Use

1. **Allow Camera/Microphone Access**: The app requires access to your webcam and microphone to function.
2. **Start a Session**: Click the "Talk to Stylist" button to connect to the Gemini Live API.
3. **Speak your Request**: Ask the stylist for a new look. For example: "I want to see what I look like in a cyberpunk outfit."
4. **Use Inspiration (Optional)**: Click "Upload" under the Inspiration Image section to provide a reference photo. Use the toggle to specify if the AI should use it for your clothing or your background.
5. **View & Download**: The AI will generate an image of you in your new style, complete with a character bio. Click the download icon in the top right of the generated image to save it.

