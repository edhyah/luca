import { RTVIClientProvider } from '@pipecat-ai/client-react'
import { DailyTransport } from '@pipecat-ai/daily-transport'
import { RTVIClient } from '@pipecat-ai/client-js'
import { useState, useCallback } from 'react'
import VoiceSession from './VoiceSession'

function App() {
  const [client, setClient] = useState<RTVIClient | null>(null)

  const initClient = useCallback(async () => {
    const transport = new DailyTransport()

    const newClient = new RTVIClient({
      transport,
      params: {
        baseUrl: '/connect',
        endpoints: {
          connect: '/connect',
        },
      },
      enableMic: true,
      enableCam: false,
    })

    setClient(newClient)
    return newClient
  }, [])

  return (
    <div className="app">
      <header>
        <h1>Luca</h1>
        <p>Language Transfer AI Tutor</p>
      </header>

      <main>
        {client ? (
          <RTVIClientProvider client={client}>
            <VoiceSession />
          </RTVIClientProvider>
        ) : (
          <button onClick={initClient} className="connect-button">
            Start Session
          </button>
        )}
      </main>
    </div>
  )
}

export default App
