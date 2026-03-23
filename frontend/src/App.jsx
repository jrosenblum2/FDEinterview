import React, { useState, useEffect, useCallback } from 'react'
import { v4 as uuidv4 } from 'uuid'
import ChatWindow from './components/ChatWindow.jsx'
import MessageInput from './components/MessageInput.jsx'
import DocumentList from './components/DocumentList.jsx'
import LoadingIndicator from './components/LoadingIndicator.jsx'
import reductoLogo from './assets/reducto_logo.png'

const API_BASE = import.meta.env.VITE_API_URL || ''

/**
 * App — root component.
 *
 * Responsibilities:
 *  - Session management via localStorage (UUID v4, persists across refreshes)
 *  - On mount: restore chat history and document list from the API
 *  - Coordinate upload → query flow: upload first, then fire the query automatically
 *  - Pass state and callbacks down to child components
 */
export default function App() {
  // -------------------------------------------------------------------------
  // Session management
  // -------------------------------------------------------------------------
  const [sessionId] = useState(() => {
    const existing = localStorage.getItem('rag_session_id')
    if (existing) return existing
    const fresh = uuidv4()
    localStorage.setItem('rag_session_id', fresh)
    return fresh
  })

  // -------------------------------------------------------------------------
  // State
  // -------------------------------------------------------------------------
  const [messages, setMessages] = useState([])        // Chat history
  const [documents, setDocuments] = useState([])      // Uploaded document list
  const [uploadingFilename, setUploadingFilename] = useState(null)
  const [isQuerying, setIsQuerying] = useState(false)
  const [error, setError] = useState(null)

  // -------------------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------------------

  /** Adds a message object to the local chat state. */
  const appendMessage = useCallback((role, content, citations = []) => {
    setMessages(prev => [...prev, { role, content, citations, id: uuidv4() }])
  }, [])

  /** Fetches the full document list and updates state. */
  const refreshDocuments = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/documents`)
      if (!res.ok) throw new Error('Failed to load documents')
      const data = await res.json()
      setDocuments(data.documents || [])
    } catch (err) {
      console.error('refreshDocuments error:', err)
    }
  }, [])

  // -------------------------------------------------------------------------
  // On mount: restore history and documents
  // -------------------------------------------------------------------------
  useEffect(() => {
    const init = async () => {
      try {
        // Restore conversation history for this session
        const histRes = await fetch(`${API_BASE}/api/history/${sessionId}`)
        if (histRes.ok) {
          const histData = await histRes.json()
          if (histData.messages?.length) {
            setMessages(
              histData.messages.map(m => ({
                role: m.role,
                content: m.content,
                citations: [],
                id: uuidv4(),
              }))
            )
          }
        }
      } catch (err) {
        console.error('Failed to restore chat history:', err)
      }

      await refreshDocuments()
    }

    init()
  }, [sessionId, refreshDocuments])

  // -------------------------------------------------------------------------
  // Upload handler
  // -------------------------------------------------------------------------

  /**
   * Uploads a PDF file. Returns the result dict on success, or null on failure.
   * Updates the document list after a successful upload.
   */
  const uploadFile = useCallback(async (file) => {
    setUploadingFilename(file.name)
    setError(null)

    const formData = new FormData()
    formData.append('file', file)
    formData.append('session_id', sessionId)

    try {
      const res = await fetch(`${API_BASE}/api/upload`, {
        method: 'POST',
        body: formData,
      })
      const data = await res.json()

      if (!res.ok) {
        throw new Error(data.detail || 'Upload failed')
      }

      await refreshDocuments()
      return data
    } catch (err) {
      setError(err.message || 'Upload failed. Please try again.')
      return null
    } finally {
      setUploadingFilename(null)
    }
  }, [sessionId, refreshDocuments])

  // -------------------------------------------------------------------------
  // Query handler
  // -------------------------------------------------------------------------

  /**
   * Sends a message to the RAG pipeline and appends both the user message
   * and the assistant response (with citations) to the chat state.
   */
  const sendQuery = useCallback(async (message) => {
    appendMessage('user', message)
    setIsQuerying(true)
    setError(null)

    try {
      const res = await fetch(`${API_BASE}/api/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, session_id: sessionId }),
      })
      const data = await res.json()

      if (!res.ok) {
        throw new Error(data.detail || 'Query failed')
      }

      appendMessage('assistant', data.answer, data.citations || [])
    } catch (err) {
      setError(err.message || 'Something went wrong. Please try again.')
      appendMessage('assistant', 'Sorry, something went wrong. Please try again.')
    } finally {
      setIsQuerying(false)
    }
  }, [sessionId, appendMessage])

  // -------------------------------------------------------------------------
  // Combined submit handler (called by MessageInput)
  // -------------------------------------------------------------------------

  /**
   * If the user submits both a message and a file simultaneously:
   *  1. Upload the file first and wait for success
   *  2. Then automatically fire the query
   *
   * If only a message is submitted (no file), go straight to the query.
   */
  const handleSubmit = useCallback(async (message, files) => {
    if (files && files.length > 0) {
      // Upload all files sequentially, then fire the query
      for (const file of files) {
        const uploadResult = await uploadFile(file)
        if (!uploadResult) continue  // Upload failed — error already set

        if (uploadResult.status === 'already_exists') {
          appendMessage('assistant', `"${uploadResult.filename}" is already in the document library.`)
        } else {
          appendMessage('assistant', `The file "${uploadResult.filename}" has finished processing! I'm ready to answer your questions about it.`)
        }
      }

      if (message.trim()) {
        await sendQuery(message)
      }
    } else if (message.trim()) {
      await sendQuery(message)
    }
  }, [uploadFile, sendQuery, appendMessage])

  // -------------------------------------------------------------------------
  // Document deletion handler
  // -------------------------------------------------------------------------
  const handleDeleteDocument = useCallback(async (documentId) => {
    try {
      const res = await fetch(`${API_BASE}/api/documents/${documentId}`, {
        method: 'DELETE',
      })
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.detail || 'Delete failed')
      }
      await refreshDocuments()
    } catch (err) {
      setError(err.message || 'Failed to delete document.')
    }
  }, [refreshDocuments])

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  const isLoading = !!uploadingFilename || isQuerying

  return (
    <div style={styles.appShell}>
      {/* Sidebar */}
      <aside style={styles.sidebar}>
        <div style={styles.sidebarHeader}>
          <img src={reductoLogo} alt="Reducto" style={styles.logo} />
          <p style={styles.appSubtitle}>Financial Document Assistant</p>
        </div>
        <DocumentList
          documents={documents}
          onDelete={handleDeleteDocument}
          isUploading={!!uploadingFilename}
        />
      </aside>

      {/* Main chat area */}
      <main style={styles.main}>
        {error && (
          <div style={styles.errorBanner}>
            <span>{error}</span>
            <button style={styles.errorClose} onClick={() => setError(null)}>✕</button>
          </div>
        )}

        <ChatWindow messages={messages} />

        {isLoading && (
          <LoadingIndicator
            message={uploadingFilename ? `Processing ${uploadingFilename}…` : 'Thinking…'}
          />
        )}

        <MessageInput
          onSubmit={handleSubmit}
          disabled={isLoading}
        />
      </main>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Inline styles (avoids external CSS dependencies for portability)
// ---------------------------------------------------------------------------
const styles = {
  appShell: {
    display: 'flex',
    height: '100vh',
    overflow: 'hidden',
    background: 'var(--color-bg)',
  },
  sidebar: {
    width: 280,
    minWidth: 220,
    background: 'var(--color-surface)',
    borderRight: '1px solid var(--color-border)',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  sidebarHeader: {
    padding: '20px 16px 14px',
    borderBottom: '1px solid var(--color-border)',
  },
  logo: {
    width: '100%',
    maxWidth: 140,
    display: 'block',
    marginBottom: -18,
  },
  appSubtitle: {
    fontSize: 12,
    color: 'var(--color-text-muted)',
    marginTop: 2,
  },
  main: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    position: 'relative',
  },
  errorBanner: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '10px 16px',
    background: '#fff5f5',
    borderBottom: '1px solid #fed7d7',
    color: 'var(--color-error)',
    fontSize: 13,
  },
  errorClose: {
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    color: 'var(--color-error)',
    fontSize: 14,
    padding: '0 4px',
  },
}
