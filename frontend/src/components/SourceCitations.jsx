import { useState } from 'react'

/**
 * SourceCitations — collapsible list of source citations shown beneath
 * each assistant message.
 *
 * Props:
 *   citations (array): List of objects with { document_name, page_number, chunk_text }
 */
export default function SourceCitations({ citations }) {
  const [expanded, setExpanded] = useState(false)

  if (!citations || citations.length === 0) return null

  return (
    <div style={styles.container}>
      {/* Toggle button */}
      <button
        style={styles.toggle}
        onClick={() => setExpanded((prev) => !prev)}
        aria-expanded={expanded}
      >
        <span style={styles.toggleIcon}>{expanded ? '▾' : '▸'}</span>
        {citations.length} source{citations.length !== 1 ? 's' : ''}
      </button>

      {/* Citation cards */}
      {expanded && (
        <ul style={styles.list}>
          {citations.map((c, i) => (
            <li key={i} style={styles.card}>
              <div style={styles.cardHeader}>
                <span style={styles.docIcon}>📄</span>
                <span style={styles.docName}>{c.document_name}</span>
                {c.page_number != null && (
                  <span style={styles.pageLabel}>p.{c.page_number}</span>
                )}
              </div>
              {c.source_type === 'table' || c.source_type === 'figure' ? (
                <p style={styles.referenceNote}>
                  {c.source_type === 'table' ? '📊' : '🖼️'}
                  {' '}Refer to the {c.source_type} on page {c.page_number ?? '?'} for more information.
                </p>
              ) : (
                <pre style={styles.chunkText}>{c.chunk_text}</pre>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

const styles = {
  container: {
    marginTop: 6,
    maxWidth: '80%',
  },
  toggle: {
    display: 'flex',
    alignItems: 'center',
    gap: 4,
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    fontSize: 12,
    color: 'var(--color-primary)',
    padding: '2px 0',
    fontWeight: 500,
  },
  toggleIcon: {
    fontSize: 10,
  },
  list: {
    listStyle: 'none',
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
    marginTop: 6,
  },
  card: {
    background: '#f7faff',
    border: '1px solid #bee3f8',
    borderRadius: 'var(--radius-sm)',
    padding: '8px 10px',
  },
  cardHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    marginBottom: 4,
  },
  docIcon: {
    fontSize: 12,
  },
  docName: {
    fontSize: 12,
    fontWeight: 600,
    color: 'var(--color-text-secondary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    flex: 1,
  },
  pageLabel: {
    fontSize: 11,
    color: 'var(--color-text-muted)',
    flexShrink: 0,
    background: '#ebf4ff',
    padding: '1px 5px',
    borderRadius: 4,
  },
  chunkText: {
    fontSize: 12,
    color: 'var(--color-text-secondary)',
    lineHeight: 1.5,
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
    fontFamily: 'inherit',
    margin: 0,
    maxHeight: 160,
    overflowY: 'auto',
  },
  referenceNote: {
    fontSize: 12,
    color: 'var(--color-text-muted)',
    fontStyle: 'italic',
  },
}
