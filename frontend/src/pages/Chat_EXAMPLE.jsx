/**
 * pages/Chat.jsx - Enhanced with conversation history and proper formatting
 * 
 * Features:
 * - Session-based conversations (remembers context)
 * - Displays conversational summaries
 * - Renders results as tables, metrics, or formatted text
 * - Shows previous conversations
 * - Proper error handling
 */

import { useState, useEffect, useRef } from 'react';
import { apiCall } from '../lib/api';
import MessageBubble from '../components/chat/MessageBubble';
import ResultTable from '../components/chat/ResultTable';
import '../styles/Chat.css';

export default function Chat() {
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [previousSessions, setPreviousSessions] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [showSessions, setShowSessions] = useState(false);
  const messagesEndRef = useRef(null);

  // Load user's previous sessions on mount
  useEffect(() => {
    loadPreviousSessions();
  }, []);

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const loadPreviousSessions = async () => {
    try {
      const response = await apiCall('/api/chat/sessions', {
        method: 'GET',
      });
      setPreviousSessions(response);
    } catch (error) {
      console.error('Failed to load sessions:', error);
    }
  };

  const loadSession = async (selectedSessionId) => {
    try {
      setSessionId(selectedSessionId);
      setShowSessions(false);
      
      const response = await apiCall(`/api/chat/history/${selectedSessionId}`, {
        method: 'GET',
      });
      
      // Convert stored messages to display format
      const displayMessages = response.messages.map(msg => ({
        id: msg.id,
        type: 'exchange',
        userQuestion: msg.question,
        assistant: {
          summary: msg.response,
          display_type: 'text',
          sql: msg.sql,
          results_json: msg.results_json,
          row_count: msg.result_count,
          model_used: msg.model_used,
          confidence: msg.confidence,
          execution_ms: msg.execution_ms,
          error: msg.error,
        }
      }));
      
      setMessages(displayMessages);
    } catch (error) {
      console.error('Failed to load session:', error);
      alert('Could not load conversation');
    }
  };

  const startNewChat = () => {
    setSessionId(null);
    setMessages([]);
    setInput('');
  };

  const sendMessage = async (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const question = input;
    setInput('');
    setLoading(true);

    try {
      const response = await apiCall('/api/chat', {
        method: 'POST',
        body: {
          question,
          session_id: sessionId,
        },
      });

      // Initialize session on first message
      if (!sessionId) {
        setSessionId(response.session_id);
      }

      // Parse results if available
      let rows = [];
      try {
        if (response.data?.results_json) {
          rows = JSON.parse(response.data.results_json);
        } else if (response.data?.rows) {
          rows = response.data.rows;
        }
      } catch {
        // JSON parsing failed, use empty array
      }

      // Add message pair
      setMessages(prev => [...prev, {
        id: response.message_id,
        type: 'exchange',
        userQuestion: question,
        assistant: {
          summary: response.summary,
          display_type: response.display_type || 'text',
          data: response.data || {},
          rows,
          columns: response.columns || [],
          row_count: response.row_count,
          sql: response.sql,
          model_used: response.model_used,
          confidence: response.confidence,
          execution_ms: response.execution_ms,
          error: response.error,
        },
      }]);

      // Refresh sessions list
      loadPreviousSessions();
    } catch (error) {
      console.error('Chat error:', error);
      setMessages(prev => [...prev, {
        type: 'error',
        message: error.message || 'Failed to process your question',
      }]);
    } finally {
      setLoading(false);
    }
  };

  const renderAssistantContent = (assistant) => {
    return (
      <div className="assistant-content">
        {/* Main summary */}
        <div className="summary" dangerously SetInnerHTML={{ __html: assistant.summary }} />

        {/* Display based on type */}
        {assistant.display_type === 'table' && assistant.rows?.length > 0 && (
          <div className="result-table-container">
            <ResultTable 
              rows={assistant.rows}
              columns={assistant.columns}
              maxRows={20}
            />
            {assistant.row_count > 20 && (
              <p className="truncation-notice">
                Showing 20 of {assistant.row_count} results. Full data available on desktop.
              </p>
            )}
          </div>
        )}

        {assistant.display_type === 'metric' && assistant.data?.value !== undefined && (
          <div className="metric-display">
            <div className="metric-value">
              {typeof assistant.data.value === 'number' 
                ? assistant.data.value.toLocaleString()
                : assistant.data.value}
            </div>
            {assistant.data.label && (
              <div className="metric-label">{assistant.data.label}</div>
            )}
          </div>
        )}

        {assistant.display_type === 'summary' && assistant.data?.row && (
          <div className="summary-display">
            {Object.entries(assistant.data.row).slice(0, 5).map(([key, value]) => (
              <div key={key} className="summary-item">
                <span className="key">{key}:</span>
                <span className="value">{value}</span>
              </div>
            ))}
          </div>
        )}

        {assistant.display_type === 'empty' && (
          <p className="no-results">No data found. Try refining your search.</p>
        )}

        {assistant.display_type === 'error' && (
          <div className="error-box">
            <p>⚠️ {assistant.data?.error || assistant.error}</p>
          </div>
        )}

        {/* Debug info */}
        <div className="assistant-meta">
          <small>
            Model: <code>{assistant.model_used}</code> | 
            Confidence: <code>{assistant.confidence}</code> | 
            Time: <code>{assistant.execution_ms.toFixed(1)}ms</code>
          </small>
          
          {assistant.sql && (
            <details className="sql-viewer">
              <summary>SQL Query</summary>
              <pre><code>{assistant.sql}</code></pre>
            </details>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="chat-page">
      <div className="chat-main">
        <div className="chat-header">
          <h1>💬 College Assistant</h1>
          <div className="header-actions">
            <button 
              className="btn-secondary"
              onClick={() => setShowSessions(!showSessions)}
            >
              📋 History {previousSessions.length > 0 && `(${previousSessions.length})`}
            </button>
            {sessionId && (
              <button 
                className="btn-outline"
                onClick={startNewChat}
              >
                ➕ New Chat
              </button>
            )}
          </div>
        </div>

        {/* Previous Sessions Sidebar */}
        {showSessions && previousSessions.length > 0 && (
          <div className="sessions-sidebar">
            <h3>Recent Conversations</h3>
            <div className="sessions-list">
              {previousSessions.map(session => (
                <div 
                  key={session.session_id}
                  className={`session-item ${sessionId === session.session_id ? 'active' : ''}`}
                  onClick={() => loadSession(session.session_id)}
                >
                  <div className="session-preview">{session.preview}</div>
                  <div className="session-meta">
                    {session.message_count} messages
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Messages Container */}
        <div className="chat-messages">
          {messages.length === 0 ? (
            <div className="welcome-message">
              <h2>👋 Welcome to College Assistant</h2>
              <p>Ask me anything about:</p>
              <ul>
                <li>📚 Students (by department, GPA, arrears, etc.)</li>
                <li>👨‍🏫 Faculty (timetable, contact, department)</li>
                <li>🏢 Departments and subjects</li>
                <li>📊 Statistics and analytics</li>
              </ul>
              <h3>Example Questions:</h3>
              <div className="example-questions">
                <button 
                  className="example-btn"
                  onClick={() => setInput('Show me all students from DCS department')}
                >
                  "Show all students in DCS"
                </button>
                <button 
                  className="example-btn"
                  onClick={() => setInput('What is the average GPA of hosteller students?')}
                >
                  "Average GPA of hostellers?"
                </button>
                <button 
                  className="example-btn"
                  onClick={() => setInput('List faculty members in the CSE department')}
                >
                  "CSE faculty members"
                </button>
              </div>
            </div>
          ) : (
            messages.map(msg => (
              <div key={msg.id} className="message-pair">
                {/* User message */}
                <MessageBubble 
                  type="user"
                  content={msg.userQuestion}
                />

                {/* Assistant message */}
                {msg.type === 'exchange' ? (
                  <MessageBubble 
                    type="assistant"
                    content={renderAssistantContent(msg.assistant)}
                  />
                ) : (
                  /* Error message */
                  <MessageBubble 
                    type="error"
                    content={msg.message}
                  />
                )}
              </div>
            ))
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <form className="chat-input-area" onSubmit={sendMessage}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question about students, faculty, departments..."
            disabled={loading}
            autoFocus
          />
          <button 
            type="submit" 
            disabled={loading || !input.trim()}
            className="btn-primary"
          >
            {loading ? '⏳ Processing...' : '✉️ Send'}
          </button>
        </form>

        {loading && (
          <div className="loading-indicator">
            <span className="spinner"></span> Thinking...
          </div>
        )}
      </div>
    </div>
  );
}
