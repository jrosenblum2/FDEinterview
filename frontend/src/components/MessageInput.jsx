import React, { useState, useRef } from 'react'

/**
 * MessageInput — text input bar with optional PDF file attachment.
 *
 * Props:
 *   onSubmit (fn): Called with (message: string, file: File | null)
 *   disabled (bool): Disables input and button during loading
 */
export default function MessageInput({ onSubmit, disabled }) {
  const [text, setText] = useState('')
  const [pendingFile, setPendingFile] = useState(null)
  const fileInputRef = useRef(null)

  const handleFileChange = (e) => {
    const file = e.target.files?.[0]
    if (file) setPendingFile(file)
    // Reset the input so the same file can be re-selected if needed
    e.target.value = ''
  }

  const handleRemoveFile = () => {
    setPendingFile(null)
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (disabled) return
    if (!text.trim() && !pendingFile) return

    onSubmit(text.trim(), pendingFile)
    setText('')
    setPendingFile(null)
  }

  const handleKeyDown = (e) => {
    // Submit on Enter (but not Shift+Enter, which inserts a newline)
    if (e.key === 'Enter' && !e.shiftKey) {
      handleSubmit(e)
    }
  }

  return (
    <div style={styles.wrapper}>
      {/* Pending file badge */}
      {pendingFile && (
        <div style={styles.fileBadge}>
          <span style={styles.fileIcon}>📎</span>
          <span style={styles.fileName}>{pendingFile.name}</span>
          <button
            style={styles.removeFile}
            onClick={handleRemoveFile}
            type="button"
            aria-label="Remove file"
          >
            ✕
          </button>
        </div>
      )}

      <form style={styles.form} onSubmit={handleSubmit}>
        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
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
          title="Attach a PDF document"
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
            pendingFile
              ? 'Ask a question about this document…'
              : 'Ask a question about your documents…'
          }
          disabled={disabled}
          rows={1}
        />

        {/* Send button */}
        <button
          type="submit"
          style={styles.sendButton(disabled || (!text.trim() && !pendingFile))}
          disabled={disabled || (!text.trim() && !pendingFile)}
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
  fileBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    background: '#ebf4ff',
    border: '1px solid #bee3f8',
    borderRadius: 'var(--radius-sm)',
    padding: '4px 10px',
    marginBottom: 8,
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
