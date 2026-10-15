import React, { useRef, useEffect, useState } from 'react';
import { useAgentChatStore } from '../../stores/agentChatStore';

interface Props {
  open: boolean;
  onClose: () => void;
  stockCode?: string;
}

export const AskAIDrawer: React.FC<Props> = ({ open, onClose, stockCode }) => {
  const { messages, loading, startStream, startNewChat } = useAgentChatStore();
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const send = () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput('');
    startStream({ message: text, context: stockCode ? { symbol: stockCode } : undefined });
  };

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  };

  if (!open) return null;

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 50, display: 'flex', justifyContent: 'flex-end' }}>
      {/* Backdrop */}
      <div onClick={onClose} style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.4)' }} />

      {/* Drawer */}
      <div style={{ position: 'relative', width: 420, maxWidth: '90vw', background: '#1a1a2e', display: 'flex', flexDirection: 'column', height: '100%', borderLeft: '1px solid #2a2a3e' }}>

        {/* Header */}
        <div style={{ padding: '14px 16px', borderBottom: '1px solid #2a2a3e', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: 14, color: '#e2e8f0' }}>Ask AI {stockCode && <span style={{ color: '#60a5fa' }}>· {stockCode}</span>}</div>
            <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>Powered by Gemini</div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => startNewChat()} style={{ fontSize: 11, color: '#6b7280', background: 'none', border: '1px solid #374151', borderRadius: 6, padding: '3px 8px', cursor: 'pointer' }}>New</button>
            <button onClick={onClose} style={{ color: '#6b7280', background: 'none', border: 'none', cursor: 'pointer', fontSize: 18, lineHeight: 1 }}>×</button>
          </div>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
          {messages.length === 0 && (
            <div style={{ textAlign: 'center', color: '#4b5563', fontSize: 13, marginTop: 40 }}>
              Ask anything about {stockCode || 'stocks'}
            </div>
          )}
          {messages.map((m) => (
            <div key={m.id} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
              <div style={{
                maxWidth: '85%', padding: '8px 12px', borderRadius: 12, fontSize: 13, lineHeight: 1.6,
                background: m.role === 'user' ? '#2563eb' : '#1e293b',
                color: m.role === 'user' ? '#fff' : '#cbd5e1',
                borderBottomRightRadius: m.role === 'user' ? 4 : 12,
                borderBottomLeftRadius: m.role === 'assistant' ? 4 : 12,
                whiteSpace: 'pre-wrap',
              }}>
                {m.content}
              </div>
            </div>
          ))}
          {loading && (
            <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
              <div style={{ background: '#1e293b', borderRadius: 12, borderBottomLeftRadius: 4, padding: '8px 14px', color: '#60a5fa', fontSize: 13 }}>
                Thinking...
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div style={{ padding: '12px 16px', borderTop: '1px solid #2a2a3e', display: 'flex', gap: 8 }}>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask about this stock..."
            rows={1}
            style={{ flex: 1, background: '#0f172a', border: '1px solid #374151', borderRadius: 8, padding: '8px 12px', color: '#e2e8f0', fontSize: 13, resize: 'none', outline: 'none', fontFamily: 'inherit' }}
          />
          <button
            onClick={send}
            disabled={!input.trim() || loading}
            style={{ background: '#2563eb', border: 'none', borderRadius: 8, padding: '0 16px', color: '#fff', fontSize: 13, cursor: 'pointer', opacity: (!input.trim() || loading) ? 0.5 : 1 }}
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
};
