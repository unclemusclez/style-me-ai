import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Camera, Mic, MicOff, Loader2, Image as ImageIcon } from 'lucide-react';
import { GoogleGenAI, Type, LiveServerMessage, Modality } from '@google/genai';

const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

const generateClothingImageDeclaration = {
  name: "generateClothingImage",
  description: "Generate an image of the user wearing the requested clothing style. Call this when the user asks to see themselves in a specific outfit or style.",
  parameters: {
    type: Type.OBJECT,
    properties: {
      styleDescription: {
        type: Type.STRING,
        description: "The description of the clothing style the user wants to wear. E.g., 'a red leather jacket', 'a vintage 1920s dress', 'cyberpunk streetwear'.",
      },
    },
    required: ["styleDescription"],
  },
};

export default function App() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [cameraActive, setCameraActive] = useState(false);

  const [isListening, setIsListening] = useState(false);
  const sessionRef = useRef<any>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const nextPlayTimeRef = useRef<number>(0);
  
  const micAudioContextRef = useRef<AudioContext | null>(null);
  const scriptProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const videoIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const [generatedImage, setGeneratedImage] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [statusText, setStatusText] = useState("Ready to style");

  useEffect(() => {
    const startCamera = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ 
          video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } } 
        });
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
        setCameraActive(true);
      } catch (err) {
        console.error("Error accessing camera:", err);
        setStatusText("Camera access denied.");
      }
    };
    
    startCamera();
    
    return () => {
      if (videoRef.current && videoRef.current.srcObject) {
        const stream = videoRef.current.srcObject as MediaStream;
        stream.getTracks().forEach(track => track.stop());
      }
      cleanupAudio();
    };
  }, []);

  const cleanupAudio = useCallback(() => {
    if (scriptProcessorRef.current) {
      scriptProcessorRef.current.disconnect();
      scriptProcessorRef.current = null;
    }
    if (micAudioContextRef.current) {
      micAudioContextRef.current.close();
      micAudioContextRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => track.stop());
      mediaStreamRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    if (sessionRef.current) {
      try {
        sessionRef.current.close();
      } catch (e) {
        console.error("Error closing session", e);
      }
      sessionRef.current = null;
    }
    if (videoIntervalRef.current) {
      clearInterval(videoIntervalRef.current);
      videoIntervalRef.current = null;
    }
  }, []);

  const playAudioChunk = useCallback((base64Audio: string) => {
    if (!audioContextRef.current) return;
    
    try {
      const binaryString = atob(base64Audio);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      
      const int16Array = new Int16Array(bytes.buffer);
      const float32Array = new Float32Array(int16Array.length);
      for (let i = 0; i < int16Array.length; i++) {
        float32Array[i] = int16Array[i] / 32768.0;
      }
      
      const audioBuffer = audioContextRef.current.createBuffer(1, float32Array.length, 24000);
      audioBuffer.getChannelData(0).set(float32Array);
      
      const source = audioContextRef.current.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(audioContextRef.current.destination);
      
      const currentTime = audioContextRef.current.currentTime;
      if (nextPlayTimeRef.current < currentTime) {
        nextPlayTimeRef.current = currentTime;
      }
      
      source.start(nextPlayTimeRef.current);
      nextPlayTimeRef.current += audioBuffer.duration;
    } catch (err) {
      console.error("Error playing audio chunk:", err);
    }
  }, []);

  const generateImage = async (styleDescription: string) => {
    setIsGenerating(true);
    try {
      if (!videoRef.current || !canvasRef.current) {
        throw new Error("Video or canvas not ready");
      }
      
      const video = videoRef.current;
      const canvas = canvasRef.current;
      
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext('2d');
      if (!ctx) throw new Error("Could not get canvas context");
      
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const base64ImageData = canvas.toDataURL('image/jpeg').split(',')[1];
      
      const prompt = `Change the clothing of the person in the image to: ${styleDescription}. Keep the person's face, identity, and pose exactly the same. Only change the clothing.`;
      
      const response = await ai.models.generateContent({
        model: 'gemini-2.5-flash-image',
        contents: {
          parts: [
            {
              inlineData: {
                data: base64ImageData,
                mimeType: 'image/jpeg',
              },
            },
            {
              text: prompt,
            },
          ],
        },
      });
      
      for (const part of response.candidates?.[0]?.content?.parts || []) {
        if (part.inlineData) {
          setGeneratedImage(`data:image/jpeg;base64,${part.inlineData.data}`);
          setStatusText(`Style applied: ${styleDescription}`);
          break;
        }
      }
    } catch (err) {
      console.error("Error generating image:", err);
      setStatusText("Failed to generate image.");
    } finally {
      setIsGenerating(false);
    }
  };

  const connectLiveAPI = async () => {
    try {
      setIsListening(true);
      setStatusText("Connecting...");
      
      audioContextRef.current = new AudioContext({ sampleRate: 24000 });
      nextPlayTimeRef.current = 0;
      
      const sessionPromise = ai.live.connect({
        model: "gemini-2.5-flash-native-audio-preview-09-2025",
        callbacks: {
          onopen: async () => {
            setStatusText("Listening...");
            try {
              const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
              mediaStreamRef.current = stream;
              
              const micAudioContext = new AudioContext({ sampleRate: 16000 });
              micAudioContextRef.current = micAudioContext;
              
              const source = micAudioContext.createMediaStreamSource(stream);
              const processor = micAudioContext.createScriptProcessor(4096, 1, 1);
              scriptProcessorRef.current = processor;
              
              processor.onaudioprocess = (e) => {
                const inputData = e.inputBuffer.getChannelData(0);
                const pcmData = new Int16Array(inputData.length);
                for (let i = 0; i < inputData.length; i++) {
                  let s = Math.max(-1, Math.min(1, inputData[i]));
                  pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
                }
                const buffer = new ArrayBuffer(pcmData.length * 2);
                const view = new DataView(buffer);
                for (let i = 0; i < pcmData.length; i++) {
                  view.setInt16(i * 2, pcmData[i], true);
                }
                const base64 = btoa(String.fromCharCode(...new Uint8Array(buffer)));
                
                sessionPromise.then((session) => {
                  session.sendRealtimeInput({
                    media: {
                      mimeType: 'audio/pcm;rate=16000',
                      data: base64
                    }
                  });
                });
              };
              
              source.connect(processor);
              processor.connect(micAudioContext.destination);

              // Start sending video frames
              videoIntervalRef.current = setInterval(() => {
                if (videoRef.current && canvasRef.current) {
                  const video = videoRef.current;
                  const canvas = canvasRef.current;
                  if (video.videoWidth > 0 && video.videoHeight > 0) {
                    const scale = 0.5;
                    canvas.width = video.videoWidth * scale;
                    canvas.height = video.videoHeight * scale;
                    const ctx = canvas.getContext('2d');
                    if (ctx) {
                      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                      const base64ImageData = canvas.toDataURL('image/jpeg', 0.5).split(',')[1];
                      sessionPromise.then(session => {
                        session.sendRealtimeInput({
                          media: {
                            mimeType: 'image/jpeg',
                            data: base64ImageData
                          }
                        });
                      });
                    }
                  }
                }
              }, 1000);

            } catch (err) {
              console.error("Mic error:", err);
              setStatusText("Microphone access denied.");
            }
          },
          onmessage: async (message: LiveServerMessage) => {
            const base64Audio = message.serverContent?.modelTurn?.parts[0]?.inlineData?.data;
            if (base64Audio) {
              playAudioChunk(base64Audio);
            }
            
            if (message.serverContent?.interrupted) {
              nextPlayTimeRef.current = 0;
              if (audioContextRef.current) {
                 audioContextRef.current.close();
                 audioContextRef.current = new AudioContext({ sampleRate: 24000 });
              }
            }
            
            if (message.toolCall) {
              const functionCalls = message.toolCall.functionCalls;
              if (functionCalls) {
                for (const call of functionCalls) {
                  if (call.name === "generateClothingImage") {
                    const args = call.args as any;
                    const styleDescription = args.styleDescription;
                    
                    setStatusText(`Generating style: ${styleDescription}...`);
                    generateImage(styleDescription);
                    
                    sessionPromise.then(session => {
                      session.sendToolResponse({
                        functionResponses: [{
                          id: call.id,
                          name: call.name,
                          response: { result: "Image generation started. Tell the user it will take a few seconds." }
                        }]
                      });
                    });
                  }
                }
              }
            }
          },
          onclose: () => {
            setIsListening(false);
            setStatusText("Disconnected.");
            cleanupAudio();
          },
          onerror: (err) => {
            console.error("Live API Error:", err);
            setIsListening(false);
            setStatusText("Error occurred.");
            cleanupAudio();
          }
        },
        config: {
          responseModalities: [Modality.AUDIO],
          speechConfig: {
            voiceConfig: { prebuiltVoiceConfig: { voiceName: "Zephyr" } },
          },
          systemInstruction: "You are a helpful virtual stylist. The user is looking at a camera. When they ask to try on a specific clothing style or outfit, use the generateClothingImage tool to apply that style to them. Be conversational, friendly, and brief.",
          tools: [{ functionDeclarations: [generateClothingImageDeclaration] }],
        },
      });
      
      sessionRef.current = await sessionPromise;
      
    } catch (err) {
      console.error("Live API error:", err);
      setIsListening(false);
      setStatusText("Error connecting.");
      cleanupAudio();
    }
  };

  const stopLiveAPI = () => {
    setIsListening(false);
    setStatusText("Ready to style");
    cleanupAudio();
  };

  return (
    <div className="min-h-screen bg-neutral-950 text-white flex flex-col font-sans">
      <header className="p-6 border-b border-white/10 flex items-center justify-between">
        <h1 className="text-2xl font-serif font-medium tracking-tight">Style Me AI</h1>
        <div className="flex items-center gap-4">
          <span className="text-sm text-neutral-400 font-mono hidden sm:inline-block">{statusText}</span>
          <button 
            onClick={isListening ? stopLiveAPI : connectLiveAPI}
            className={`flex items-center gap-2 px-4 py-2 rounded-full font-medium transition-colors ${
              isListening ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30' : 'bg-white text-black hover:bg-neutral-200'
            }`}
          >
            {isListening ? <MicOff size={18} /> : <Mic size={18} />}
            {isListening ? 'Stop Listening' : 'Start Styling'}
          </button>
        </div>
      </header>
      
      <main className="flex-1 p-6 grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Camera View */}
        <div className="relative rounded-2xl overflow-hidden bg-neutral-900 border border-white/5 flex flex-col min-h-[400px]">
          <div className="absolute top-4 left-4 z-10 bg-black/50 backdrop-blur-md px-3 py-1 rounded-full text-xs font-mono text-white/80 border border-white/10">
            LIVE CAMERA
          </div>
          <video 
            ref={videoRef} 
            autoPlay 
            playsInline 
            muted 
            className="w-full h-full object-cover absolute inset-0"
          />
          <canvas ref={canvasRef} className="hidden" />
          {!cameraActive && (
            <div className="absolute inset-0 flex items-center justify-center bg-neutral-900">
              <Loader2 size={32} className="animate-spin text-neutral-500" />
            </div>
          )}
        </div>
        
        {/* Generated Image View */}
        <div className="relative rounded-2xl overflow-hidden bg-neutral-900 border border-white/5 flex items-center justify-center min-h-[400px]">
          <div className="absolute top-4 left-4 z-10 bg-black/50 backdrop-blur-md px-3 py-1 rounded-full text-xs font-mono text-white/80 border border-white/10">
            GENERATED STYLE
          </div>
          
          {isGenerating ? (
            <div className="flex flex-col items-center gap-4 text-neutral-400 z-10">
              <Loader2 size={32} className="animate-spin text-white" />
              <p className="font-mono text-sm">Designing your outfit...</p>
            </div>
          ) : generatedImage ? (
            <img 
              src={generatedImage} 
              alt="Generated Style" 
              className="w-full h-full object-cover absolute inset-0"
              referrerPolicy="no-referrer"
            />
          ) : (
            <div className="flex flex-col items-center gap-4 text-neutral-500 z-10 p-6 text-center">
              <ImageIcon size={48} className="opacity-50" />
              <p className="font-mono text-sm max-w-xs">
                Click "Start Styling" and ask the stylist to try on different clothes to see them here.
              </p>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
