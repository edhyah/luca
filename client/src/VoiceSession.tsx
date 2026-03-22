import { useRTVIClient, useRTVIClientEvent } from '@pipecat-ai/client-react'
import { RTVIEvent, TransportState } from '@pipecat-ai/client-js'
import { useState, useCallback, useEffect, useRef } from 'react'

function VoiceSession() {
  const client = useRTVIClient()
  const [connectionState, setConnectionState] = useState<TransportState>('disconnected')
  const [isMicMuted, setIsMicMuted] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isBotSpeaking, setIsBotSpeaking] = useState(false)
  const audioRef = useRef<HTMLAudioElement>(null)

  useRTVIClientEvent(
    RTVIEvent.TransportStateChanged,
    useCallback((state: TransportState) => {
      setConnectionState(state)
    }, [])
  )

  useRTVIClientEvent(
    RTVIEvent.Error,
    useCallback((err: Error) => {
      setError(err.message)
    }, [])
  )

  useRTVIClientEvent(
    RTVIEvent.BotStartedSpeaking,
    useCallback(() => {
      console.log('[VoiceSession] Bot started speaking')
      setIsBotSpeaking(true)
    }, [])
  )

  useRTVIClientEvent(
    RTVIEvent.BotStoppedSpeaking,
    useCallback(() => {
      console.log('[VoiceSession] Bot stopped speaking')
      setIsBotSpeaking(false)
    }, [])
  )

  useRTVIClientEvent(
    RTVIEvent.TrackStarted,
    useCallback((track: MediaStreamTrack, participant: any) => {
      console.log('[VoiceSession] Track started:', track.kind, participant?.id)
      if (track.kind === 'audio' && participant?.local === false) {
        // This is the bot's audio track - attach it to an audio element
        console.log('[VoiceSession] Attaching bot audio track')
        if (audioRef.current) {
          const stream = new MediaStream([track])
          audioRef.current.srcObject = stream
          audioRef.current.play().catch(e => console.error('Audio play error:', e))
        }
      }
    }, [])
  )

  const handleConnect = useCallback(async () => {
    if (!client) return

    try {
      setError(null)
      await client.connect()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to connect')
    }
  }, [client])

  const handleDisconnect = useCallback(async () => {
    if (!client) return
    await client.disconnect()
  }, [client])

  const toggleMic = useCallback(() => {
    if (!client) return

    if (isMicMuted) {
      client.enableMic(true)
    } else {
      client.enableMic(false)
    }
    setIsMicMuted(!isMicMuted)
  }, [client, isMicMuted])

  useEffect(() => {
    // Auto-connect when component mounts
    if (client && connectionState === 'disconnected') {
      handleConnect()
    }
  }, [client, connectionState, handleConnect])

  const isConnected = connectionState === 'connected' || connectionState === 'ready'
  const isConnecting = connectionState === 'connecting' || connectionState === 'authenticating'

  return (
    <div className="voice-session">
      <div className="status">
        <span className={`status-indicator ${connectionState}`} />
        <span className="status-text">
          {connectionState === 'disconnected' && 'Disconnected'}
          {connectionState === 'connecting' && 'Connecting...'}
          {connectionState === 'authenticating' && 'Authenticating...'}
          {connectionState === 'connected' && 'Connected'}
          {connectionState === 'ready' && 'Ready'}
          {connectionState === 'disconnecting' && 'Disconnecting...'}
        </span>
      </div>

      {error && (
        <div className="error">
          {error}
        </div>
      )}

      <div className="controls">
        {!isConnected && !isConnecting && (
          <button onClick={handleConnect} className="connect-button">
            Connect
          </button>
        )}

        {isConnected && (
          <>
            <button
              onClick={toggleMic}
              className={`mic-button ${isMicMuted ? 'muted' : ''}`}
            >
              {isMicMuted ? 'Unmute' : 'Mute'}
            </button>

            <button onClick={handleDisconnect} className="disconnect-button">
              End Session
            </button>
          </>
        )}

        {isConnecting && (
          <button disabled className="connect-button">
            Connecting...
          </button>
        )}
      </div>

      {isConnected && (
        <div className="session-info">
          <p>Speak to start your lesson with Luca.</p>
          {isBotSpeaking && <p className="bot-speaking">🔊 Luca is speaking...</p>}
        </div>
      )}

      {/* Hidden audio element for bot audio playback */}
      <audio ref={audioRef} autoPlay playsInline />
    </div>
  )
}

export default VoiceSession
