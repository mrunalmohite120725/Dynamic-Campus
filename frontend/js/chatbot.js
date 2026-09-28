/**
 * chatbot.js — Campus Genie Frontend Logic
 */

const chatbotHTML = `
  <div class="chatbot-widget">
    <div class="chat-window" id="chat-window">
      <div class="chat-header">
        <h3>Campus Genie ✨</h3>
        <p>AI Assistant • Online</p>
      </div>
      <div class="chat-messages" id="chat-messages">
        <div class="message bot">
          Hi! I'm your Campus Genie. Ask me anything about the schedule, teachers, or room availability! 🎓
        </div>
      </div>
      <div class="chat-input-area">
        <input type="text" class="chat-input" id="chat-input" placeholder="Ask me something..." autocomplete="off">
        <button class="chat-send-btn" id="chat-send-btn">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20">
            <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
          </svg>
        </button>
      </div>
    </div>
    <div class="chat-bubble" id="chat-bubble">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
      </svg>
    </div>
  </div>
`;

// Inject Chatbot into body
document.body.insertAdjacentHTML('beforeend', chatbotHTML);

const bubble = document.getElementById('chat-bubble');
const windowEl = document.getElementById('chat-window');
const input = document.getElementById('chat-input');
const sendBtn = document.getElementById('chat-send-btn');
const messagesContainer = document.getElementById('chat-messages');

// Toggle Window
bubble.onclick = () => windowEl.classList.toggle('active');

// Send Logic
async function sendMessage() {
  const text = input.value.trim();
  if (!text) return;

  // Add User Message
  appendMessage('user', text);
  input.value = '';

  // Show Typing
  const typingId = appendMessage('bot', '...', true);

  try {
    const res = await fetch('/api/ai/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text })
    });
    const data = await res.json();
    
    // Remove Typing and add response
    removeMessage(typingId);
    appendMessage('bot', data.response);
  } catch (err) {
    removeMessage(typingId);
    appendMessage('bot', "Oops, my brain is a bit foggy right now. Please check if the server is running!");
  }
}

function appendMessage(type, text, isTyping = false) {
  const id = 'msg-' + Date.now();
  const div = document.createElement('div');
  div.className = `message ${type}`;
  div.id = id;
  div.textContent = text;
  messagesContainer.appendChild(div);
  messagesContainer.scrollTop = messagesContainer.scrollHeight;
  return id;
}

function removeMessage(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

// Event Listeners
sendBtn.onclick = sendMessage;
input.onkeypress = (e) => { if (e.key === 'Enter') sendMessage(); };
