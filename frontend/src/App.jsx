import { useMemo, useState } from "react";

const sampleAlerts = [
  { id: "INC-1001", severity: "high", location: "Dock A", summary: "Possible fall detected" },
  { id: "INC-1002", severity: "medium", location: "Line 3", summary: "PPE compliance warning" }
];

export default function App() {
  const [messages, setMessages] = useState([
    { role: "assistant", text: "I am your AI Safety Coach. Ask me about incident prevention or response playbooks." }
  ]);
  const [draft, setDraft] = useState("");

  const activeCount = useMemo(() => sampleAlerts.length, []);

  const sendMessage = (event) => {
    event.preventDefault();
    if (!draft.trim()) return;

    setMessages((prev) => [
      ...prev,
      { role: "user", text: draft.trim() },
      { role: "assistant", text: "Thanks. Safety guidance suggestions can be connected to your backend assistant service." }
    ]);
    setDraft("");
  };

  return (
    <main className="dashboard">
      <section className="panel">
        <h1>Call-Help Safety Dashboard</h1>
        <p>Active incidents: <strong>{activeCount}</strong></p>
        <ul>
          {sampleAlerts.map((alert) => (
            <li key={alert.id}>
              <strong>{alert.id}</strong> ({alert.severity}) - {alert.summary} @ {alert.location}
            </li>
          ))}
        </ul>
      </section>

      <section className="panel">
        <h2>AI Safety Coach</h2>
        <div className="chat-log">
          {messages.map((message, index) => (
            <p key={`${message.role}-${index}`} className={`msg ${message.role}`}>
              <strong>{message.role === "assistant" ? "Coach" : "You"}:</strong> {message.text}
            </p>
          ))}
        </div>
        <form onSubmit={sendMessage}>
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Ask about safety protocols..."
          />
          <button type="submit">Send</button>
        </form>
      </section>
    </main>
  );
}
