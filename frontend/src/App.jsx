import React, { useState, useEffect, useRef } from 'react';
import {
  LogOut, Plus, MessageSquare, Trash2, Globe, Menu, X,
  Send, Copy, Check, Baby, AlertTriangle, HeartPulse,
  ClipboardList, Stethoscope, User, HelpCircle, Activity,
  Paperclip, BarChart2
} from 'lucide-react';
import Analytics from './Analytics';

const API_BASE = window.location.port === "5173" ? "http://localhost:8000/api" : "/api";

export default function App() {
  // ── Auth States ────────────────────────────────────────────────
  const [token, setToken] = useState(localStorage.getItem('hb_token') || '');
  const [user, setUser] = useState(null);
  const [authMode, setAuthMode] = useState('login'); // 'login' or 'signup'
  const [authError, setAuthError] = useState('');

  // Auth Form Inputs
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [role, setRole] = useState('ASHA Worker');

  // ── Chat States ────────────────────────────────────────────────
  const [chats, setChats] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [language, setLanguage] = useState('English');
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeView, setActiveView] = useState('chat'); // 'chat' or 'analytics'

  // ── Layout & Status States ─────────────────────────────────────
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [copiedMessageId, setCopiedMessageId] = useState(null);
  const [isBackendHealthy, setIsBackendHealthy] = useState(true);

  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  const [selectedFile, setSelectedFile] = useState(null);
  const fileInputRef = useRef(null);

  // ── Effects ────────────────────────────────────────────────────

  // Fetch user profile on load or token change
  useEffect(() => {
    if (token) {
      localStorage.setItem('hb_token', token);
      fetchUserProfile();
    } else {
      localStorage.removeItem('hb_token');
      setUser(null);
      setChats([]);
      setActiveChatId(null);
      setMessages([]);
      setActiveView('chat');
    }
  }, [token]);

  // Fetch messages when active chat changes
  useEffect(() => {
    if (activeChatId) {
      fetchMessages(activeChatId);
    }
  }, [activeChatId]);

  // Scroll to bottom when messages list changes
  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  // Auto-expand textarea on typing
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`;
    }
  }, [input]);

  // Health check on load
  useEffect(() => {
    checkBackendHealth();
    // Set a periodic health check
    const interval = setInterval(checkBackendHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  const checkBackendHealth = async () => {
    try {
      const res = await fetch(`${API_BASE}/health`);
      if (res.ok) {
        setIsBackendHealthy(true);
      } else {
        setIsBackendHealthy(false);
      }
    } catch {
      setIsBackendHealthy(false);
    }
  };

  const getAuthHeaders = () => ({
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  });

  const fetchUserProfile = async () => {
    try {
      const res = await fetch(`${API_BASE}/auth/me`, {
        headers: getAuthHeaders()
      });
      if (res.ok) {
        const data = await res.json();
        setUser(data.user);
        fetchChats();
      } else {
        // Token is invalid/expired
        setToken('');
      }
    } catch (err) {
      console.error("Profile fetch error:", err);
      // Don't log out on simple network failure, check backend health
      setIsBackendHealthy(false);
    }
  };

  const fetchChats = async () => {
    try {
      const res = await fetch(`${API_BASE}/chats`, {
        headers: getAuthHeaders()
      });
      if (res.ok) {
        const data = await res.json();
        setChats(data.chats);
        // Set the active chat to the first chat if there's any and we don't have one selected
        if (data.chats.length > 0 && !activeChatId) {
          setActiveChatId(data.chats[0].id);
          setLanguage(data.chats[0].language);
        }
      }
    } catch (err) {
      console.error("Chats fetch error:", err);
    }
  };

  const fetchMessages = async (chatId) => {
    try {
      const res = await fetch(`${API_BASE}/chats/${chatId}`, {
        headers: getAuthHeaders()
      });
      if (res.ok) {
        const data = await res.json();
        setMessages(data.messages);
      }
    } catch (err) {
      console.error("Messages fetch error:", err);
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // ── Auth Handlers ──────────────────────────────────────────────
  const handleLogin = async (e) => {
    e.preventDefault();
    setAuthError('');
    if (!email || !password) {
      setAuthError('Please fill in all fields');
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });

      const data = await res.json();
      if (res.ok) {
        setToken(data.token);
        // Clear fields
        setEmail('');
        setPassword('');
      } else {
        setAuthError(data.detail || 'Login failed. Please verify credentials.');
      }
    } catch (err) {
      setAuthError('Unable to connect to server. Check your connection.');
    }
  };

  const handleSignup = async (e) => {
    e.preventDefault();
    setAuthError('');
    if (!name || !email || !password) {
      setAuthError('Please fill in all fields');
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/auth/signup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, password, role })
      });

      const data = await res.json();
      if (res.ok) {
        setToken(data.token);
        // Clear fields
        setName('');
        setEmail('');
        setPassword('');
      } else {
        setAuthError(data.detail || 'Signup failed. Email may already be in use.');
      }
    } catch (err) {
      setAuthError('Unable to connect to server. Check your connection.');
    }
  };

  const handleLogout = async () => {
    try {
      await fetch(`${API_BASE}/auth/logout`, {
        method: 'POST',
        headers: getAuthHeaders()
      });
    } catch (err) {
      console.error("Logout request error:", err);
    } finally {
      setToken('');
    }
  };

  // ── Chat Handlers ──────────────────────────────────────────────
  const handleStartNewChat = async () => {
    try {
      const res = await fetch(`${API_BASE}/chats`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ title: "New Conversation", language })
      });
      if (res.ok) {
        const data = await res.json();
        setChats([data.chat, ...chats]);
        setActiveChatId(data.chat.id);
        setMessages([]);
        setActiveView('chat');
        setIsSidebarOpen(false);
      }
    } catch (err) {
      console.error("Create chat error:", err);
    }
  };

  const handleDeleteChat = async (chatId, e) => {
    e.stopPropagation();
    try {
      const res = await fetch(`${API_BASE}/chats/${chatId}`, {
        method: 'DELETE',
        headers: getAuthHeaders()
      });
      if (res.ok) {
        const updatedChats = chats.filter(c => c.id !== chatId);
        setChats(updatedChats);
        if (activeChatId === chatId) {
          if (updatedChats.length > 0) {
            setActiveChatId(updatedChats[0].id);
            setLanguage(updatedChats[0].language);
          } else {
            setActiveChatId(null);
            setMessages([]);
          }
        }
      }
    } catch (err) {
      console.error("Delete chat error:", err);
    }
  };

  const handleLanguageChange = (e) => {
    const newLang = e.target.value;
    setLanguage(newLang);
    // Note: In a production app, you might sync the language configuration back to the active chat on the database.
  };

  const handleSendMessage = async (e) => {
    e?.preventDefault();
    if ((!input.trim() && !selectedFile) || loading) return;

    let targetChatId = activeChatId;

    // 1. If no active chat, create one first
    if (!targetChatId) {
      const defaultTitle = input.trim() || (selectedFile ? "Medical Document Analysis" : "New Conversation");
      try {
        const res = await fetch(`${API_BASE}/chats`, {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({ title: defaultTitle.substring(0, 30), language })
        });
        if (res.ok) {
          const data = await res.json();
          targetChatId = data.chat.id;
          setActiveChatId(targetChatId);
          setChats([data.chat, ...chats]);
        } else {
          console.error("Auto-create chat failed");
          return;
        }
      } catch (err) {
        console.error("Auto-create chat network error", err);
        return;
      }
    }

    const currentInput = input.trim();
    const currentFile = selectedFile;
    
    setInput('');
    setSelectedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }

    // Add temporary messages to UI immediately
    const tempUserMsg = {
      id: 'temp-user-' + Date.now(),
      role: 'user',
      content: currentInput || "Uploaded a medical document/prescription.",
      language: language,
      image_path: currentFile ? URL.createObjectURL(currentFile) : null,
      created_at: new Date().toISOString()
    };
    setMessages(prev => [...prev, tempUserMsg]);
    setLoading(true);

    try {
      const formData = new FormData();
      if (currentInput) {
        formData.append('query', currentInput);
      }
      formData.append('language', language);
      if (currentFile) {
        formData.append('image', currentFile);
      }

      const res = await fetch(`${API_BASE}/chats/${targetChatId}/messages`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData
      });

      if (res.ok) {
        const data = await res.json();

        // Append bot message to state
        const tempBotMsg = {
          id: 'temp-bot-' + Date.now(),
          role: 'assistant',
          content: data.response,
          query_type: data.query_type,
          language: data.language,
          created_at: new Date().toISOString()
        };

        setMessages(prev => [...prev, tempBotMsg]);

        // Refresh sidebar so that if this was the first message, the auto-updated title is loaded.
        fetchChats();

        // Synchronize messages with database
        fetchMessages(targetChatId);
      } else {
        const errorData = await res.json();
        alert(`Failed to send message: ${errorData.detail || "Server Error"}`);
      }
    } catch (err) {
      console.error("Message send network error:", err);
      alert("Unable to reach server. Please check your internet connection.");
    } finally {
      setLoading(false);
    }
  };

  const handleQuickAction = async (queryText) => {
    setInput(queryText);
    // We let the useEffect expand the textarea, and then trigger sending.
    // To send immediately, we can pass it to the handler:
    setTimeout(() => {
      if (textareaRef.current) {
        textareaRef.current.focus();
      }
    }, 100);
  };

  const copyToClipboard = (text, id) => {
    navigator.clipboard.writeText(text);
    setCopiedMessageId(id);
    setTimeout(() => {
      setCopiedMessageId(null);
    }, 2000);
  };

  // ── Badge Helpers ──────────────────────────────────────────────
  const badgeMap = {
    maternal_health: { icon: <HeartPulse className="w-3.5 h-3.5" />, label: "Maternal", className: "maternal" },
    child_health: { icon: <Baby className="w-3.5 h-3.5" />, label: "Child", className: "child" },
    scheme_eligibility: { icon: <ClipboardList className="w-3.5 h-3.5" />, label: "Scheme", className: "scheme" },
    referral_decision: { icon: <AlertTriangle className="w-3.5 h-3.5" />, label: "Referral", className: "referral" },
    drug_protocol: { icon: <Stethoscope className="w-3.5 h-3.5" />, label: "Drug", className: "drug" },
    general_health: { icon: <Activity className="w-3.5 h-3.5" />, label: "General", className: "general" },
    medical_document: { icon: <ClipboardList className="w-3.5 h-3.5" />, label: "Document", className: "document" },
    error: { icon: <AlertTriangle className="w-3.5 h-3.5" />, label: "Error", className: "general" },
  };

  // ── Render Auth Page ───────────────────────────────────────────
  if (!token || !user) {
    return (
      <div className="auth-wrapper">
        <div className="auth-card">
          <div className="auth-header">
            <span className="auth-logo">🏥</span>
            <h2>HealthBridge AI</h2>
            <p>Clinical Support & NHM Guidelines for ASHA Workers</p>
          </div>

          {authError && <div className="auth-error">{authError}</div>}

          {authMode === 'login' ? (
            <form onSubmit={handleLogin}>
              <div className="auth-form-group">
                <label>Email Address</label>
                <input
                  type="email"
                  className="auth-input"
                  placeholder="name@gmail.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
              <div className="auth-form-group">
                <label>Password</label>
                <input
                  type="password"
                  className="auth-input"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
              <button type="submit" className="auth-button">Login →</button>
              <div className="auth-footer">
                Don't have an account?{' '}
                <span className="auth-link" onClick={() => { setAuthMode('signup'); setAuthError(''); }}>
                  Sign Up
                </span>
              </div>
            </form>
          ) : (
            <form onSubmit={handleSignup}>
              <div className="auth-form-group">
                <label>Full Name</label>
                <input
                  type="text"
                  className="auth-input"
                  placeholder="Sunita Devi"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </div>
              <div className="auth-form-group">
                <label>Email Address</label>
                <input
                  type="email"
                  className="auth-input"
                  placeholder="name@gmail.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
              <div className="auth-form-group">
                <label>Password</label>
                <input
                  type="password"
                  className="auth-input"
                  placeholder="Min 6 characters"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
              <div className="auth-form-group">
                <label>Role</label>
                <select
                  className="auth-select"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                >
                  <option value="ASHA Worker">ASHA Worker</option>
                  <option value="ANM">ANM (Auxiliary Nurse Midwife)</option>
                  <option value="PHC Staff">PHC Staff / Doctor</option>
                </select>
              </div>
              <button type="submit" className="auth-button">Register & Sign Up</button>
              <div className="auth-footer">
                Already have an account?{' '}
                <span className="auth-link" onClick={() => { setAuthMode('login'); setAuthError(''); }}>
                  Log In
                </span>
              </div>
            </form>
          )}
        </div>
      </div>
    );
  }

  // Helper to get user initial
  const getUserInitial = () => {
    if (!user.name) return 'A';
    return user.name.charAt(0).toUpperCase();
  };

  // ── Render Application Page ─────────────────────────────────────
  return (
    <div className="app-container">

      {/* Mobile Sidebar overlay */}
      <div
        className={`sidebar-overlay ${isSidebarOpen ? 'active' : ''}`}
        onClick={() => setIsSidebarOpen(false)}
      />

      {/* Sidebar Panel */}
      <aside className={`sidebar ${isSidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-profile">
          <div className="profile-avatar">
            {getUserInitial()}
          </div>
          <div className="profile-info">
            <div className="profile-name" title={user.name}>{user.name}</div>
            <div className="profile-role">{user.role}</div>
          </div>
          <button
            className="profile-logout"
            onClick={handleLogout}
            title="Log Out"
          >
            <LogOut className="w-5 h-5" />
          </button>
        </div>

        <div className="sidebar-action">
          <button className="new-chat-btn" onClick={handleStartNewChat}>
            <Plus className="w-4 h-4" />
            New Chat Session
          </button>
        </div>

        <div className="sidebar-history">
          <div className="history-title">Chat Threads</div>
          <div className="history-list">
            {chats.length === 0 ? (
              <div style={{ textAlign: 'center', color: '#9ca3af', padding: '16px 0', fontSize: '13px' }}>
                No past sessions
              </div>
            ) : (
              chats.map((c) => (
                <div
                  key={c.id}
                  className={`history-item ${activeChatId === c.id ? 'active' : ''}`}
                  onClick={() => {
                    setActiveChatId(c.id);
                    setLanguage(c.language);
                    setActiveView('chat');
                    setIsSidebarOpen(false);
                  }}
                >
                  <div className="history-meta">
                    <MessageSquare className="w-4 h-4 flex-shrink-0" style={{ opacity: 0.7 }} />
                    <span className="history-text" title={c.title}>{c.title}</span>
                  </div>
                  <button
                    className="history-delete-btn"
                    onClick={(e) => handleDeleteChat(c.id, e)}
                    title="Delete Chat"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="sidebar-analytics-link" style={{ padding: '0 12px 16px 12px', borderBottom: '1.5px solid var(--primary-border)' }}>
          <div
            className={`history-item ${activeView === 'analytics' ? 'active' : ''}`}
            onClick={() => {
              setActiveView('analytics');
              setIsSidebarOpen(false);
            }}
          >
            <div className="history-meta">
              <BarChart2 className="w-4 h-4 flex-shrink-0" style={{ opacity: 0.7 }} />
              <span className="history-text">Analytics Dashboard</span>
            </div>
          </div>
        </div>

        <div className="sidebar-settings">
          <label className="settings-label">
            <Globe className="w-3.5 h-3.5 inline mr-1.5 align-text-bottom" />
            Response Language
          </label>
          <select
            className="settings-select"
            value={language}
            onChange={handleLanguageChange}
          >
            <option value="English">English</option>
            <option value="Tamil">தமிழ் (Tamil)</option>
            <option value="Telugu">తెలుగు (Telugu)</option>
            <option value="Hindi">हिन्दी (Hindi)</option>
          </select>
        </div>
      </aside>

      {/* Main Chat Workspace */}
      <main className="main-content">
        {activeView === 'analytics' ? (
          <Analytics token={token} onClose={() => setActiveView('chat')} />
        ) : (
          <>
            {/* App Bar */}
        <header className="header-bar">
          <div className="header-left">
            <button
              className="sidebar-toggle-btn"
              onClick={() => setIsSidebarOpen(true)}
            >
              <Menu className="w-5 h-5" />
            </button>
            <div className="header-title">
              <span className="header-logo">🏥</span>
              <h1>HealthBridge AI</h1>
              <span className="header-subtitle">NHM Decision Support</span>
            </div>
          </div>

          <div className="header-right">
            <div className="status-badge" style={{ color: isBackendHealthy ? '#047857' : '#ef4444', backgroundColor: isBackendHealthy ? '#f0fdf4' : '#fee2e2' }}>
              <span className="status-dot" style={{ backgroundColor: isBackendHealthy ? '#10b981' : '#ef4444' }} />
              {isBackendHealthy ? 'Cloud Connected' : 'Local Offline'}
            </div>
          </div>
        </header>

        {/* Conversation Area */}
        <section className="messages-container">
          {messages.length === 0 ? (
            /* Welcome Dashboard (Empty state) */
            <div className="welcome-container">
              <div className="welcome-hero">
                <span className="welcome-logo">🌿</span>
                <h2>Namaste, {user.name.split(' ')[0]} Didi</h2>
                <p>Verify National Health Mission clinical guidelines, referral criteria, or eligibility protocols instantly.</p>
              </div>

              <div className="quick-actions-section">
                <div className="quick-actions-title">Suggested Inquiries</div>
                <div className="quick-actions-grid">
                  <div
                    className="quick-action-card"
                    onClick={() => handleQuickAction("What are danger signs in a child under 5 that need immediate referral?")}
                  >
                    <span className="quick-action-icon">👶</span>
                    <h3>Child Danger Signs</h3>
                    <p>Referral criteria for infants and kids under 5 years old.</p>
                  </div>
                  <div
                    className="quick-action-card"
                    onClick={() => handleQuickAction("What should I check during a home visit for a pregnant woman in third trimester?")}
                  >
                    <span className="quick-action-icon">🤰</span>
                    <h3>Maternal Care Visit</h3>
                    <p>Antenatal & postnatal protocols for third-trimester checks.</p>
                  </div>
                  <div
                    className="quick-action-card"
                    onClick={() => handleQuickAction("Who is eligible for Janani Suraksha Yojana and what documents are needed?")}
                  >
                    <span className="quick-action-icon">📋</span>
                    <h3>JSY Eligibility Rules</h3>
                    <p>Janani Suraksha Yojana benefits and required paperwork.</p>
                  </div>
                  <div
                    className="quick-action-card"
                    onClick={() => handleQuickAction("What is the protocol for treating anaemia in pregnant women?")}
                  >
                    <span className="quick-action-icon">💊</span>
                    <h3>Anaemia Treatment Protocol</h3>
                    <p>Standard medicine dosages and monitoring rules.</p>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            /* Chat Feed */
            <div className="messages-list">
              {messages.map((m) => {
                const isUser = m.role === 'user';
                const badgeInfo = isUser ? null : (badgeMap[m.query_type] || badgeMap.general_health);

                return (
                  <div
                    key={m.id}
                    className={`message-wrapper ${isUser ? 'user' : 'assistant'}`}
                  >
                    <div className={`message-bubble ${isUser ? 'user' : `assistant ${badgeInfo?.className || 'general'}`}`}>

                      {!isUser && (
                        <div className="message-header">
                          <span className={`category-badge ${badgeInfo?.className || 'general'}`}>
                            {badgeInfo?.icon}
                            {badgeInfo?.label}
                          </span>
                          <span className="message-lang">{m.language || 'English'}</span>
                          <button
                            className="message-copy-btn"
                            onClick={() => copyToClipboard(m.content, m.id)}
                            title="Copy Response"
                          >
                            {copiedMessageId === m.id ? (
                              <Check className="w-3.5 h-3.5 text-green-600" />
                            ) : (
                              <Copy className="w-3.5 h-3.5" />
                            )}
                          </button>
                        </div>
                      )}

                      <div className="message-body">
                        {m.image_path && (
                          <div className="message-image-container">
                            <img
                              src={m.image_path.startsWith('blob:') ? m.image_path : `${API_BASE.replace('/api', '')}/${m.image_path}`}
                              alt="Uploaded medical doc"
                              className="message-image"
                              onClick={() => window.open(m.image_path.startsWith('blob:') ? m.image_path : `${API_BASE.replace('/api', '')}/${m.image_path}`, '_blank')}
                            />
                          </div>
                        )}
                        {m.content.split('\n').map((line, i) => (
                          <span key={i}>
                            {line}
                            <br />
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                );
              })}

              {/* Bot typing state loader */}
              {loading && (
                <div className="message-wrapper assistant">
                  <div className="message-bubble assistant general" style={{ padding: '14px 20px' }}>
                    <div className="message-header" style={{ marginBottom: 4, border: 'none', padding: 0 }}>
                      <span className="category-badge general">
                        <Activity className="w-3.5 h-3.5 animate-spin" />
                        Analyzing...
                      </span>
                    </div>
                    <div className="typing-indicator">
                      <div className="typing-dot" />
                      <div className="typing-dot" />
                      <div className="typing-dot" />
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </section>

        {/* Input Panel */}
        <footer className="input-panel">
          <div className="input-container-inner">
            {selectedFile && (
              <div className="file-preview-container">
                <div className="file-preview-bubble">
                  <img src={URL.createObjectURL(selectedFile)} alt="Preview" className="file-preview-image" />
                  <span className="file-preview-name">{selectedFile.name}</span>
                  <button type="button" className="file-preview-remove" onClick={() => setSelectedFile(null)} title="Remove Image">
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            )}
            <form onSubmit={handleSendMessage} className="input-form">
              <input
                type="file"
                accept="image/*"
                ref={fileInputRef}
                style={{ display: 'none' }}
                onChange={(e) => {
                  if (e.target.files && e.target.files[0]) {
                    setSelectedFile(e.target.files[0]);
                  }
                }}
              />
              <button
                type="button"
                className="chat-attach-btn"
                onClick={() => fileInputRef.current?.click()}
                title="Attach Medical Document Image"
                disabled={loading}
              >
                <Paperclip className="w-4 h-4" />
              </button>
              <textarea
                ref={textareaRef}
                className="chat-textarea"
                rows="1"
                placeholder="Ask about patient guidelines or upload medical docs/prescriptions..."
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSendMessage();
                  }
                }}
              />
              <button
                type="submit"
                className="chat-send-btn"
                disabled={(!input.trim() && !selectedFile) || loading}
                title="Send Message"
              >
                <Send className="w-4 h-4" />
              </button>
            </form>

            <div className="app-disclaimer">
              <span className="text-amber-500 flex-shrink-0" style={{ fontSize: 16 }}>⚠️</span>
              <div>
                <strong>ASHA Worker decision support.</strong> All data is based on official National Health Mission (NHM) documents. It does not replace clinical assessment by an ANM or Doctor. In case of medical emergencies, immediately call <strong>104</strong> or transfer to the nearest health facility.
              </div>
            </div>
          </div>
        </footer>
          </>
        )}
      </main>
    </div>
  );
}
