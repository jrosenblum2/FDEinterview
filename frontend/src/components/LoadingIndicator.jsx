import React from 'react'

/**
 * LoadingIndicator — animated indicator shown during document processing
 * and query answering.
 *
 * Props:
 *   message (string): Short description of what is happening
 */
export default function LoadingIndicator({ message }) {
  return (
    <div style={styles.wrapper}>
      <div style={styles.container}>
        <div style={styles.dots}>
          <span style={{ ...styles.dot, animationDelay: '0ms' }} />
          <span style={{ ...styles.dot, animationDelay: '160ms' }} />
          <span style={{ ...styles.dot, animationDelay: '320ms' }} />
        </div>
        <span style={styles.label}>{message}</span>
      </div>

      {/* Keyframe animation injected via a style tag */}
      <style>{`
        @keyframes dotBounce {
          0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
          40% { transform: translateY(-6px); opacity: 1; }
        }
      `}</style>
    </div>
  )
}

const styles = {
  wrapper: {
    padding: '6px 20px 10px',
    display: 'flex',
    justifyContent: 'flex-start',
    maxWidth: 800,
    margin: '0 auto',
    width: '100%',
  },
  container: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    background: 'var(--color-assistant-bubble)',
    borderRadius: '16px 16px 16px 4px',
    padding: '10px 14px',
    boxShadow: 'var(--shadow-sm)',
  },
  dots: {
    display: 'flex',
    gap: 4,
    alignItems: 'center',
  },
  dot: {
    display: 'inline-block',
    width: 7,
    height: 7,
    borderRadius: '50%',
    background: 'var(--color-primary)',
    animation: 'dotBounce 1.2s ease-in-out infinite',
  },
  label: {
    fontSize: 13,
    color: 'var(--color-text-secondary)',
  },
}
