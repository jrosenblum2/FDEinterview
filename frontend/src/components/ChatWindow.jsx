import React, { useEffect, useRef } from 'react'
import Markdown from 'react-markdown'
import SourceCitations from './SourceCitations.jsx'

/**
 * ChatWindow — displays the full conversation history.
 *
 * Props:
 *   messages (array): List of message objects { id, role, content, citations }
 */
export default function ChatWindow({ messages }) {
  const bottomRef = useRef(null)

  // Auto-scroll to the latest message whenever messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (messages.length === 0) {
    return (
      <div style={styles.empty}>
        <div style={styles.emptyIcon}>📄</div>
        <p style={styles.emptyTitle}>No conversation yet</p>
        <p style={styles.emptyHint}>
          Upload a financial document from the left sidebar, then ask a question below.
        </p>
      </div>
    )
  }

  return (
    <div style={styles.container}>
      <div style={styles.messageList}>
        {messages.map((msg) => (
          <div key={msg.id} style={styles.messageWrapper(msg.role)}>
            <div style={styles.bubble(msg.role)}>
              {msg.role === 'assistant' ? (
                <div style={styles.messageText} className="assistant-markdown">
                  <Markdown>{msg.content}</Markdown>
                </div>
              ) : (
                <p style={styles.messageText}>{msg.content}</p>
              )}
            </div>
            {msg.role === 'assistant' && msg.citations?.length > 0 && (
              <SourceCitations citations={msg.citations} />
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

const styles = {
  container: {
    flex: 1,
    overflowY: 'auto',
    padding: '16px 0',
  },
  messageList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
    padding: '0 20px',
    maxWidth: 800,
    margin: '0 auto',
    width: '100%',
  },
  messageWrapper: (role) => ({
    display: 'flex',
    flexDirection: 'column',
    alignItems: role === 'user' ? 'flex-end' : 'flex-start',
  }),
  bubble: (role) => ({
    maxWidth: '80%',
    padding: '10px 14px',
    borderRadius: role === 'user'
      ? '16px 16px 4px 16px'
      : '16px 16px 16px 4px',
    background: role === 'user'
      ? 'var(--color-user-bubble)'
      : 'var(--color-assistant-bubble)',
    color: role === 'user'
      ? 'var(--color-user-bubble-text)'
      : 'var(--color-assistant-bubble-text)',
    boxShadow: 'var(--shadow-sm)',
  }),
  messageText: {
    fontSize: 14,
    lineHeight: 1.6,
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
  },
  empty: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 40,
    color: 'var(--color-text-muted)',
    textAlign: 'center',
  },
  emptyIcon: {
    fontSize: 48,
    marginBottom: 12,
  },
  emptyTitle: {
    fontSize: 16,
    fontWeight: 600,
    color: 'var(--color-text-secondary)',
    marginBottom: 8,
  },
  emptyHint: {
    fontSize: 13,
    maxWidth: 320,
    lineHeight: 1.6,
  },
}
