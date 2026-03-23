import React, { useState, useRef } from 'react'

/**
 * MessageInput — text input bar with optional PDF file attachment.
 *
 * Props:
 *   onSubmit (fn): Called with (message: string, files: File[])
 *   disabled (bool): Disables input and button during loading
 */
export default function MessageInput({ onSubmit, disabled }) {
  const [text, setText] = useState('')
  const [pendingFiles, setPendingFiles] = useState([])
  const fileInputRef = useRef(null)

  const handleFileChange = (e) => {
    const selected = Array.from(e.target.files || [])
    if (selected.length) {
      setPendingFiles(prev => {
        const existingNames = new Set(prev.map(f => f.name))
        return [...prev, ...selected.filter(f => !existingNames.has(f.name))]
      })
    }
    e.target.value = ''
  }

  const handleRemoveFile = (name) => {
    setPendingFiles(prev => prev.filter(f => f.name !== name))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (disabled) return
    if (!text.trim() && pendingFiles.length === 0) return

    onSubmit(text.trim(), pendingFiles)
    setText('')
    setPendingFiles([])
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      handleSubmit(e)
    }
  }

  return (
    <div style={styles.wrapper}>
      {/* Pending file badges */}
      {pendingFiles.length > 0 && (
        <div style={styles.fileBadgeRow}>
          {pendingFiles.map(file => (
            <div key={file.name} style={styles.fileBadge}>
              <span style={styles.fileIcon}>📎</span>
              <span style={styles.fileName}>{file.name}</span>
              <button
                style={styles.removeFile}
                onClick={() => handleRemoveFile(file.name)}
                type="button"
                aria-label={`Remove ${file.name}`}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      <form style={styles.form} onSubmit={handleSubmit}>
        {/* Hidden file input — multiple enabled */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          multiple
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />

        {/* Attach PDF button */}
        <button
          type="button"
          style={styles.attachButton}
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
          aria-label="Attach PDF"
          title="Attach PDF documents"
        >
          📎
        </button>

        {/* Text input */}
        <textarea
          style={styles.textarea}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            pendingFiles.length > 0
              ? 'Ask a question about these documents…'
              : 'Ask a question about your documents…'
          }
          disabled={disabled}
          rows={1}
        />

        {/* Send button */}
        <button
          type="submit"
          style={styles.sendButton(disabled || (!text.trim() && pendingFiles.length === 0))}
          disabled={disabled || (!text.trim() && pendingFiles.length === 0)}
          aria-label="Send"
        >
          ➤
        </button>
      </form>
    </div>
  )
}

const styles = {
  wrapper: {
    borderTop: '1px solid var(--color-border)',
    background: 'var(--color-surface)',
    padding: '10px 20px 14px',
  },
  fileBadgeRow: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 6,
    marginBottom: 8,
  },
  fileBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    background: '#f3e8fd',
    border: '1px solid #d8b4fe',
    borderRadius: 'var(--radius-sm)',
    padding: '4px 10px',
    fontSize: 12,
    color: 'var(--color-primary)',
    maxWidth: '100%',
  },
  fileIcon: {
    fontSize: 13,
  },
  fileName: {
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    maxWidth: 260,
  },
  removeFile: {
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    color: 'var(--color-text-muted)',
    fontSize: 11,
    padding: '0 2px',
    lineHeight: 1,
  },
  form: {
    display: 'flex',
    alignItems: 'flex-end',
    gap: 8,
    maxWidth: 800,
    margin: '0 auto',
  },
  attachButton: {
    flexShrink: 0,
    width: 38,
    height: 38,
    border: '1px solid var(--color-border)',
    borderRadius: 'var(--radius-sm)',
    background: 'var(--color-surface)',
    cursor: 'pointer',
    fontSize: 17,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'background 0.15s',
  },
  textarea: {
    flex: 1,
    border: '1px solid var(--color-border)',
    borderRadius: 'var(--radius-sm)',
    padding: '9px 12px',
    fontSize: 14,
    lineHeight: 1.5,
    resize: 'none',
    outline: 'none',
    fontFamily: 'inherit',
    background: 'var(--color-surface)',
    color: 'var(--color-text-primary)',
    minHeight: 38,
    maxHeight: 120,
    overflowY: 'auto',
  },
  sendButton: (isDisabled) => ({
    flexShrink: 0,
    width: 38,
    height: 38,
    borderRadius: 'var(--radius-sm)',
    border: 'none',
    background: isDisabled ? '#a0aec0' : 'var(--color-primary)',
    color: '#fff',
    cursor: isDisabled ? 'not-allowed' : 'pointer',
    fontSize: 15,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'background 0.15s',
  }),
}
