import React from 'react'

/**
 * DocumentList — sidebar list of all uploaded documents.
 *
 * Props:
 *   documents (array): List of document objects from GET /api/documents
 *   onDelete (fn): Called with document_id when the delete button is clicked
 *   isUploading (bool): Disables delete buttons during an active upload
 */
export default function DocumentList({ documents, onDelete, isUploading }) {
  const formatDate = (isoString) => {
    if (!isoString) return ''
    try {
      return new Date(isoString).toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    } catch {
      return ''
    }
  }

  const statusColor = (status) => {
    switch (status) {
      case 'complete':   return '#38a169'
      case 'failed':     return '#e53e3e'
      case 'processing': return '#d69e2e'
      default:           return '#718096'
    }
  }

  return (
    <div style={styles.container}>
      <div style={styles.sectionLabel}>
        Documents
        {documents.length > 0 && (
          <span style={styles.count}>{documents.length}</span>
        )}
      </div>

      {documents.length === 0 ? (
        <p style={styles.empty}>No documents uploaded yet.</p>
      ) : (
        <ul style={styles.list}>
          {documents.map((doc) => (
            <li key={doc.document_id} style={styles.item}>
              <div style={styles.itemContent}>
                <span style={styles.fileIcon}>📄</span>
                <div style={styles.itemInfo}>
                  <span style={styles.fileName} title={doc.filename}>
                    {doc.filename}
                  </span>
                  <span style={styles.meta}>
                    {formatDate(doc.uploaded_at)}
                    {' · '}
                    <span style={{ color: statusColor(doc.status) }}>
                      {doc.status}
                    </span>
                  </span>
                </div>
              </div>
              <button
                style={styles.deleteButton}
                onClick={() => onDelete(doc.document_id)}
                disabled={isUploading}
                aria-label={`Delete ${doc.filename}`}
                title="Delete document"
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

const styles = {
  container: {
    flex: 1,
    overflowY: 'auto',
    padding: '12px 0',
  },
  sectionLabel: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '0 16px 8px',
    fontSize: 11,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    color: 'var(--color-text-muted)',
  },
  count: {
    background: '#ebf4ff',
    color: 'var(--color-primary)',
    borderRadius: 10,
    padding: '1px 6px',
    fontSize: 10,
    fontWeight: 700,
  },
  empty: {
    padding: '8px 16px',
    fontSize: 13,
    color: 'var(--color-text-muted)',
    fontStyle: 'italic',
  },
  list: {
    listStyle: 'none',
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
    padding: '0 8px',
  },
  item: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '8px 8px',
    borderRadius: 'var(--radius-sm)',
    gap: 6,
    transition: 'background 0.1s',
  },
  itemContent: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: 8,
    flex: 1,
    minWidth: 0,
  },
  fileIcon: {
    fontSize: 16,
    flexShrink: 0,
    marginTop: 1,
  },
  itemInfo: {
    display: 'flex',
    flexDirection: 'column',
    minWidth: 0,
  },
  fileName: {
    fontSize: 13,
    fontWeight: 500,
    color: 'var(--color-text-primary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  meta: {
    fontSize: 11,
    color: 'var(--color-text-muted)',
    marginTop: 1,
  },
  deleteButton: {
    flexShrink: 0,
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    color: 'var(--color-text-muted)',
    fontSize: 11,
    padding: '2px 4px',
    borderRadius: 4,
    lineHeight: 1,
    transition: 'color 0.1s',
  },
}
