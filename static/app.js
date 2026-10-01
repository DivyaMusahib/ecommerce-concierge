document.addEventListener('DOMContentLoaded', () => {
    const chatInput = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    const chatContainer = document.getElementById('chat-container');

    // Handle send button click
    sendBtn.addEventListener('click', sendMessage);

    // Handle enter key
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });

    async function sendMessage() {
        const text = chatInput.value.trim();
        if (!text) return;

        // Add user message
        appendMessage('user', text);
        chatInput.value = '';

        // Add loading state
        const loadingId = appendLoading();

        try {
            // Call the FastAPI backend
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ message: text })
            });

            const data = await response.json();
            
            // Remove loading state
            document.getElementById(loadingId).remove();

            // Simulate "Agents Working" visualization before showing final answer
            await simulateAgentsWorking(data.intent, data.agent_used);

            // Add final assistant message
            appendMessage('assistant', data.response);

        } catch (error) {
            console.error('Error:', error);
            document.getElementById(loadingId).remove();
            appendMessage('assistant', 'Sorry, I encountered an error connecting to the servers.');
        }
    }

    function appendMessage(role, text) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${role}`;
        
        let avatarHTML = '';
        if (role === 'assistant') {
            avatarHTML = `<div class="logo-icon"><i class="fa-solid fa-robot"></i></div>`;
        } else {
            avatarHTML = `<div class="avatar small">DM</div>`;
        }

        msgDiv.innerHTML = `
            ${avatarHTML}
            <div class="message-content">
                <p>${text}</p>
            </div>
        `;
        
        chatContainer.appendChild(msgDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }

    function appendLoading() {
        const id = 'loading-' + Date.now();
        const msgDiv = document.createElement('div');
        msgDiv.className = `message assistant`;
        msgDiv.id = id;
        
        msgDiv.innerHTML = `
            <div class="logo-icon"><i class="fa-solid fa-robot"></i></div>
            <div class="message-content">
                <div class="typing-indicator">
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                </div>
            </div>
        `;
        
        chatContainer.appendChild(msgDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;
        return id;
    }

    async function simulateAgentsWorking(intent, agentUsed) {
        // Create the agents working visual block
        const msgDiv = document.createElement('div');
        msgDiv.className = `message assistant`;
        
        msgDiv.innerHTML = `
            <div class="logo-icon" style="background: transparent; color: var(--text-muted);"><i class="fa-solid fa-microchip"></i></div>
            <div class="message-content" style="background: transparent; box-shadow: none; border: 1px solid var(--border-color); padding: 1.5rem;">
                <h4 style="margin-bottom: 1rem; color: var(--text-main);">Agents Working...</h4>
                <div id="agents-steps-${Date.now()}"></div>
            </div>
        `;
        
        chatContainer.appendChild(msgDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;

        const stepsContainer = msgDiv.querySelector('div[id^="agents-steps"]');

        const steps = [
            { name: "Intent Classifier", desc: `Detected intent: ${intent}`, color: "blue", icon: "fa-brain" },
            { name: agentUsed, desc: "Fetching data from respective APIs...", color: "purple", icon: "fa-bolt" },
            { name: "Aggregator", desc: "Combining and formatting response...", color: "green", icon: "fa-layer-group" }
        ];

        for (let i = 0; i < steps.length; i++) {
            await new Promise(r => setTimeout(r, 600)); // Simulate delay
            
            const stepDiv = document.createElement('div');
            stepDiv.className = 'agent-step done';
            stepDiv.innerHTML = `
                <div class="step-icon ${steps[i].color}"><i class="fa-solid ${steps[i].icon}"></i></div>
                <div>
                    <strong>${steps[i].name}</strong>
                    <div style="font-size: 0.8rem; color: var(--text-muted);">${steps[i].desc}</div>
                </div>
            `;
            stepsContainer.appendChild(stepDiv);
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }

        await new Promise(r => setTimeout(r, 500)); // Final pause before response
    }
});
