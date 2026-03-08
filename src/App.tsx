import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Camera, Mic, MicOff, Loader2, Image as ImageIcon, Download, Upload, X, Play, Pause, Music } from 'lucide-react';
import { GoogleGenAI, Type, LiveServerMessage, Modality } from '@google/genai';

const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY });

const generateClothingImageDeclaration = {
  name: "generateClothingImage",
  description: "Generate an image of the user wearing the requested clothing style and/or in a specific background. Call this when the user asks to see themselves in a specific outfit, style, or location.",
  parameters: {
    type: Type.OBJECT,
    properties: {
      styleDescription: {
        type: Type.STRING,
        description: "The description of the clothing style the user wants to wear. E.g., 'a red leather jacket', 'a vintage 1920s dress'. Leave empty if they only want to change the background.",
      },
      backgroundDescription: {
        type: Type.STRING,
        description: "The description of the background or location. E.g., 'a cyberpunk city', 'a sunny beach'. Leave empty if they only want to change clothes.",
      },
      characterName: {
        type: Type.STRING,
        description: "A creative, fitting name for the character in this outfit/setting.",
      },
      biography: {
        type: Type.STRING,
        description: "A short, fun biography (1-2 sentences) for this character based on their look.",
      },
      circa: {
        type: Type.STRING,
        description: "The year or era this image represents (e.g., 'Circa 1920', 'Circa 2077', 'Circa 18th Century').",
      }
    },
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
  const [generatedAudio, setGeneratedAudio] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isGeneratingAudio, setIsGeneratingAudio] = useState(false);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const [statusText, setStatusText] = useState("Ready to style");
  const [characterInfo, setCharacterInfo] = useState<{name: string, bio: string, circa: string} | null>(null);
  
  const [inspirationImage, setInspirationImage] = useState<string | null>(null);
  const [inspirationMode, setInspirationMode] = useState<'clothing' | 'background'>('clothing');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    if (generatedAudio && audioRef.current) {
      audioRef.current.play().catch(e => console.error("Autoplay prevented:", e));
    }
  }, [generatedAudio]);

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      setInspirationImage(event.target?.result as string);
      
      if (sessionRef.current) {
        try {
          sessionRef.current.sendClientContent({
            turns: [{
              role: "user",
              parts: [{ text: "System Notification: The user just uploaded an inspiration image. Acknowledge it briefly and ask if they want to use it for their clothing style or their background." }]
            }],
            turnComplete: true
          });
        } catch (err) {
          console.error("Failed to send notification to Live API", err);
        }
      }
    };
    reader.readAsDataURL(file);
  };

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

  const generateLyriaAudio = async (styleDescription?: string, backgroundDescription?: string) => {
    const apiKey = import.meta.env.VITE_LYRIA_API_KEY;
    if (!apiKey) {
      console.warn("Lyria API key not found. Please set VITE_LYRIA_API_KEY in your environment variables.");
      return;
    }
    
    setIsGeneratingAudio(true);
    try {
      const audioPrompt = `A thematic background soundtrack for a character wearing ${styleDescription || 'casual clothes'} in a ${backgroundDescription || 'neutral environment'}.`;
      
      // Using the API structure provided, targeting the lyria model
      // Note: We use generateContent instead of streamGenerateContent to get the complete audio file
      const modelName = "lyria-2"; // Adjust this if the exact model name differs
      const url = `https://aiplatform.googleapis.com/v1/publishers/google/models/${modelName}:generateContent?key=${apiKey}`;
      
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          contents: [
            {
              role: "user",
              parts: [
                { text: audioPrompt }
              ]
            }
          ]
        })
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`API Error ${response.status}: ${errorText}`);
      }
      
      const data = await response.json();
      
      // Extract the audio from the response (assuming standard Gemini API response format with inlineData)
      let audioBase64 = null;
      let mimeType = "audio/mpeg";
      
      const parts = data.candidates?.[0]?.content?.parts || [];
      for (const part of parts) {
        if (part.inlineData && part.inlineData.mimeType?.startsWith('audio/')) {
          audioBase64 = part.inlineData.data;
          mimeType = part.inlineData.mimeType;
          break;
        }
      }
      
      if (audioBase64) {
        setGeneratedAudio(`data:${mimeType};base64,${audioBase64}`);
      } else {
        console.error("No audio data found in the response:", data);
      }
    } catch (err) {
      console.error("Error generating audio:", err);
    } finally {
      setIsGeneratingAudio(false);
    }
  };

  const generateImage = async (styleDescription?: string, backgroundDescription?: string) => {
    setIsGenerating(true);
    setGeneratedAudio(null); // Reset audio for new image
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
      
      const parts: any[] = [
        {
          inlineData: {
            data: base64ImageData,
            mimeType: 'image/jpeg',
          },
        },
      ];

      let promptText = "";
      if (inspirationImage) {
        const inspirationBase64 = inspirationImage.split(',')[1];
        const mimeType = inspirationImage.split(';')[0].split(':')[1];
        parts.push({
          inlineData: {
            data: inspirationBase64,
            mimeType: mimeType,
          }
        });
        
        if (inspirationMode === 'clothing') {
          promptText = "You are provided with two images. The first image is the base image of a person. The second image is a style reference. Edit the first image so that the person is wearing the exact same clothing and style as shown in the second image. ";
          if (styleDescription) promptText += `Additional clothing instructions: ${styleDescription}. `;
          if (backgroundDescription) promptText += `Also change the background to: ${backgroundDescription}. `;
        } else {
          promptText = "You are provided with two images. The first image is the base image of a person. The second image is a background reference. Edit the first image so that the person is placed in the exact same environment and background as shown in the second image. ";
          if (styleDescription) promptText += `Also change their clothing to: ${styleDescription}. `;
          if (backgroundDescription) promptText += `Additional background instructions: ${backgroundDescription}. `;
        }
      } else {
        if (styleDescription && backgroundDescription) {
          promptText = `Change the clothing of the person in the image to: ${styleDescription}, and change the background to: ${backgroundDescription}. `;
        } else if (styleDescription) {
          promptText = `Change the clothing of the person in the image to: ${styleDescription}. `;
        } else if (backgroundDescription) {
          promptText = `Keep the person's clothing exactly the same, but change the background to: ${backgroundDescription}. `;
        } else {
          promptText = "Enhance the image. ";
        }
      }
      
      promptText += "Keep the person's face, identity, and pose exactly the same. Only change what was requested.";
      parts.push({ text: promptText });
      
      const response = await ai.models.generateContent({
        model: 'gemini-2.5-flash-image',
        contents: {
          parts: parts,
        },
      });
      
      let imageFound = false;
      for (const part of response.candidates?.[0]?.content?.parts || []) {
        if (part.inlineData) {
          setGeneratedImage(`data:image/jpeg;base64,${part.inlineData.data}`);
          setStatusText(`Image generated successfully!`);
          imageFound = true;
          break;
        }
      }
      
      if (imageFound) {
        generateLyriaAudio(styleDescription, backgroundDescription);
      } else {
        console.error("No image returned by the model. Response:", response);
        setStatusText("Failed to generate image. Try a different prompt.");
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
                    const backgroundDescription = args.backgroundDescription;
                    const characterName = args.characterName || "Unknown Traveler";
                    const biography = args.biography || "A mysterious figure from an unknown time.";
                    const circa = args.circa || "Circa Unknown";
                    
                    let status = "Generating image...";
                    if (styleDescription && backgroundDescription) status = `Generating style & background...`;
                    else if (styleDescription) status = `Generating style: ${styleDescription}...`;
                    else if (backgroundDescription) status = `Generating background: ${backgroundDescription}...`;
                    
                    setStatusText(status);
                    setCharacterInfo({ name: characterName, bio: biography, circa: circa });
                    generateImage(styleDescription, backgroundDescription);
                    
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
          systemInstruction: "You are a helpful virtual stylist. The user is looking at a camera. When they ask to try on a specific clothing style, outfit, or change their background/location, use the generateClothingImage tool to apply that style and background to them. The user has an interface where they can upload an inspiration image. If they mention an uploaded image, picture, or inspiration, assume it is uploaded and call the generateClothingImage tool. When the user uploads or removes an image, you will receive a System Notification. Acknowledge it naturally. Be conversational, friendly, and brief.",
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

  const downloadImage = () => {
    if (!generatedImage) return;
    const a = document.createElement('a');
    a.href = generatedImage;
    a.download = `style-me-${Date.now()}.jpg`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
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
        {/* Left Column */}
        <div className="flex flex-col gap-4">
          {/* Camera View */}
          <div className="relative rounded-2xl overflow-hidden bg-neutral-900 border border-white/5 flex flex-col min-h-[400px] flex-1">
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

          {/* Inspiration Upload */}
          <div className="bg-neutral-900 border border-white/5 rounded-2xl p-4 flex flex-col gap-3">
            <div className="flex items-center gap-4">
              <div className="flex-1">
                <h3 className="text-sm font-medium text-white mb-1">Inspiration Image</h3>
                <p className="text-xs text-neutral-400">Upload a photo of an outfit or location you like to use as a reference.</p>
              </div>
              {inspirationImage ? (
                <div className="relative w-16 h-16 rounded-lg overflow-hidden border border-white/10 shrink-0">
                  <img src={inspirationImage} alt="Inspiration" className="w-full h-full object-cover" />
                  <button 
                    onClick={() => {
                      setInspirationImage(null);
                      if (fileInputRef.current) fileInputRef.current.value = '';
                      if (sessionRef.current) {
                        try {
                          sessionRef.current.sendClientContent({
                            turns: [{
                              role: "user",
                              parts: [{ text: "System Notification: The user just removed their inspiration image. They no longer have an image uploaded." }]
                            }],
                            turnComplete: true
                          });
                        } catch (err) {
                          console.error("Failed to send notification to Live API", err);
                        }
                      }
                    }}
                    className="absolute top-1 right-1 bg-black/50 rounded-full p-0.5 hover:bg-black/80 text-white"
                  >
                    <X size={12} />
                  </button>
                </div>
              ) : (
                <button 
                  onClick={() => fileInputRef.current?.click()}
                  className="flex items-center gap-2 px-3 py-2 bg-white/10 hover:bg-white/20 rounded-lg text-sm font-medium transition-colors shrink-0"
                >
                  <Upload size={16} />
                  Upload
                </button>
              )}
              <input 
                type="file" 
                ref={fileInputRef} 
                onChange={handleFileUpload} 
                accept="image/*" 
                className="hidden" 
              />
            </div>
            
            {inspirationImage && (
              <div className="flex bg-black/50 rounded-lg p-1 border border-white/5">
                <button 
                  onClick={() => setInspirationMode('clothing')}
                  className={`flex-1 text-xs py-1.5 rounded-md transition-colors font-medium ${inspirationMode === 'clothing' ? 'bg-white/20 text-white shadow-sm' : 'text-neutral-400 hover:text-white'}`}
                >
                  Use for Clothing
                </button>
                <button 
                  onClick={() => setInspirationMode('background')}
                  className={`flex-1 text-xs py-1.5 rounded-md transition-colors font-medium ${inspirationMode === 'background' ? 'bg-white/20 text-white shadow-sm' : 'text-neutral-400 hover:text-white'}`}
                >
                  Use for Background
                </button>
              </div>
            )}
          </div>
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
            <>
              <img 
                src={generatedImage} 
                alt="Generated Style" 
                className="w-full h-full object-cover absolute inset-0"
                referrerPolicy="no-referrer"
              />
              <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/90 via-black/60 to-transparent p-6 pt-20 z-10">
                {characterInfo && (
                  <div className="text-white">
                    <div className="flex items-baseline gap-3 mb-1">
                      <h2 className="text-2xl font-serif font-medium">{characterInfo.name}</h2>
                      <span className="text-sm font-mono text-neutral-300">{characterInfo.circa}</span>
                    </div>
                    <p className="text-sm text-neutral-200 leading-relaxed mb-4">{characterInfo.bio}</p>
                    
                    {isGeneratingAudio ? (
                      <div className="flex items-center gap-2 text-xs text-neutral-400">
                        <div className="w-3 h-3 border-2 border-white/20 border-t-white/80 rounded-full animate-spin" />
                        Generating thematic soundtrack with Lyria...
                      </div>
                    ) : generatedAudio ? (
                      <div className="flex items-center gap-3">
                        <button
                          onClick={() => {
                            if (audioRef.current) {
                              if (isPlayingAudio) {
                                audioRef.current.pause();
                              } else {
                                audioRef.current.play();
                              }
                            }
                          }}
                          className="flex items-center gap-2 bg-white/10 hover:bg-white/20 text-white px-4 py-2 rounded-full text-sm font-medium transition-colors border border-white/10 backdrop-blur-md"
                        >
                          {isPlayingAudio ? <Pause size={16} /> : <Play size={16} />}
                          {isPlayingAudio ? "Pause Soundtrack" : "Play Soundtrack"}
                        </button>
                        <audio 
                          ref={audioRef} 
                          src={generatedAudio} 
                          autoPlay 
                          onPlay={() => setIsPlayingAudio(true)}
                          onPause={() => setIsPlayingAudio(false)}
                          onEnded={() => setIsPlayingAudio(false)}
                          className="hidden"
                        >
                          Your browser does not support the audio element.
                        </audio>
                      </div>
                    ) : null}
                  </div>
                )}
              </div>
              <button
                onClick={downloadImage}
                className="absolute top-4 right-4 z-10 bg-black/50 hover:bg-black/70 backdrop-blur-md p-3 rounded-full text-white transition-colors border border-white/10"
                title="Download Image"
              >
                <Download size={20} />
              </button>
            </>
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
