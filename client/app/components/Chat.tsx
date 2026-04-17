'use client'

import { useState, useEffect, useRef, useCallback } from 'react'

type Role = 'user' | 'assistant'

interface Source {
  title: string
  url: string
}

interface Message {
  id: number
  role: Role
  content: string
  sources: Source[]
  isStreaming: boolean
}

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000/chat'

function parseSources(content: string): { text: string; sources: Source[] } {
  const match = content.match(/([\s\S]*?)\n\*{0,2}Fonti:?\*{0,2}\s*\n([\s\S]*)$/i)
  if (!match) return { text: content.trim(), sources: [] }

  const text = match[1].trim()
  const sources: Source[] = []

  for (const line of match[2].split('\n')) {
    const urlMatch = line.match(/https?:\/\/\S+/)
    if (!urlMatch) continue
    const url = urlMatch[0].replace(/[.,)]+$/, '')
    const title = line
      .replace(url, '')
      .replace(/^[-*\d.\s"']+/, '')
      .replace(/["'—:\s]+$/, '')
      .trim() || url
    sources.push({ title, url })
  }

  return { text, sources }
}

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [connected, setConnected] = useState(false)
  const [loading, setLoading] = useState(false)
  const ws = useRef<WebSocket | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const idCounter = useRef(0)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    const socket = new WebSocket(WS_URL)
    ws.current = socket

    socket.onopen = () => setConnected(true)
    socket.onclose = () => setConnected(false)
    socket.onerror = () => setConnected(false)

    socket.onmessage = (event) => {
      const data = event.data as string

      if (data === '[END]') {
        setMessages(prev =>
          prev.map((m, i) => (i === prev.length - 1 ? { ...m, isStreaming: false } : m))
        )
        setLoading(false)
        return
      }

      setMessages(prev => {
        const last = prev[prev.length - 1]
        if (last?.role === 'assistant' && last.isStreaming) {
          return prev.map((m, i) =>
            i === prev.length - 1 ? { ...m, content: m.content + data } : m
          )
        }
        idCounter.current += 1
        return [
          ...prev,
          { id: idCounter.current, role: 'assistant', content: data, sources: [], isStreaming: true },
        ]
      })
    }

    return () => socket.close()
  }, [])

  const sendMessage = useCallback(() => {
    if (!input.trim() || !connected || loading) return
    idCounter.current += 1
    setMessages(prev => [
      ...prev,
      { id: idCounter.current, role: 'user', content: input.trim(), sources: [], isStreaming: false },
    ])
    ws.current?.send(input.trim())
    setInput('')
    setLoading(true)
  }, [input, connected, loading])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        sendMessage()
      }
    },
    [sendMessage]
  )

  return (
    <div className="flex flex-col h-screen bg-gray-50">

      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center gap-3 shadow-sm">
        <div className="w-8 h-8 bg-[#c60000] rounded flex items-center justify-center shrink-0">
          <span className="text-white font-bold text-sm">P</span>
        </div>
        <div>
          <h1 className="font-bold text-gray-900 text-base leading-none">Il Post</h1>
          <p className="text-xs text-gray-400 mt-0.5">Assistente editoriale</p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-400' : 'bg-red-400'}`} />
          <span className="text-xs text-gray-400">{connected ? 'Connesso' : 'Disconnesso'}</span>
        </div>
      </header>

      {/* Messages */}
      <main className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-3xl mx-auto space-y-6">

          {messages.length === 0 && (
            <div className="text-center text-gray-400 mt-24">
              <p className="text-lg font-medium text-gray-600">Ciao! Cosa vuoi sapere?</p>
              <p className="text-sm mt-1">Fai una domanda su politica, economia o attualità italiana.</p>
            </div>
          )}

          {messages.map((message) => {
            if (message.role === 'user') {
              return (
                <div key={message.id} className="flex justify-end">
                  <div className="bg-[#c60000] text-white rounded-2xl rounded-tr-sm px-4 py-3 max-w-[75%] text-sm leading-relaxed">
                    {message.content}
                  </div>
                </div>
              )
            }

            const { text, sources } = message.isStreaming
              ? { text: message.content, sources: [] }
              : parseSources(message.content)

            return (
              <div key={message.id} className="flex justify-start">
                <div className="max-w-[80%] space-y-2">
                  <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-4 py-3 text-sm leading-relaxed text-gray-800 shadow-sm">
                    <p className="whitespace-pre-wrap">{text}</p>
                    {message.isStreaming && (
                      <span className="inline-block w-1.5 h-4 bg-gray-400 ml-0.5 animate-pulse align-middle" />
                    )}
                  </div>

                  {sources.length > 0 && (
                    <div className="bg-white border border-gray-100 rounded-xl px-4 py-3 space-y-2 shadow-sm">
                      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Fonti</p>
                      {sources.map((source, i) => (
                        <a
                          key={i}
                          href={source.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-start gap-2 group"
                        >
                          <span className="text-[#c60000] text-xs mt-0.5 shrink-0">↗</span>
                          <span className="text-xs text-gray-600 group-hover:text-[#c60000] transition-colors leading-snug">
                            {source.title}
                          </span>
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )
          })}

          <div ref={messagesEndRef} />
        </div>
      </main>

      {/* Input */}
      <footer className="bg-white border-t border-gray-200 px-4 py-4 shadow-sm">
        <div className="flex gap-3 max-w-3xl mx-auto">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Fai una domanda su politica o economia italiana..."
            disabled={!connected || loading}
            rows={1}
            className="flex-1 resize-none rounded-xl border border-gray-300 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#c60000] focus:border-transparent disabled:opacity-50 disabled:bg-gray-50"
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || !connected || loading}
            className="bg-[#c60000] text-white rounded-xl px-5 py-3 text-sm font-medium hover:bg-[#a50000] transition-colors disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
          >
            {loading ? '...' : 'Invia'}
          </button>
        </div>
      </footer>

    </div>
  )
}
