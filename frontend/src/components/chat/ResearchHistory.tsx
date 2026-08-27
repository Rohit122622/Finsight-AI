





import { useState } from "react";
import type { ResearchConversation } from "../../types/research";

interface ResearchHistoryProps {
  conversations: ResearchConversation[];
  activeConversationId: string | null;
  isLoading: boolean;
  onSelectConversation: (conversationId: string) => void;
  onNewConversation: () => void;
  onDeleteConversation: (conversationId: string) => void;
}

export function ResearchHistory({
  conversations,
  activeConversationId,
  isLoading,
  onSelectConversation,
  onNewConversation,
  onDeleteConversation,
}: ResearchHistoryProps) {
  const [filterText, setFilterText] = useState("");

  const filteredConversations = conversations.filter((c) =>
    (c.title || "Research Conversation")
      .toLowerCase()
      .includes(filterText.toLowerCase()),
  );

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        backgroundColor: "var(--color-bg-surface)",
        borderRight: "1px solid var(--color-border-subtle)",
        overflow: "hidden",
      }}
    >
      {}
      <div
        style={{
          padding: "1rem",
          borderBottom: "1px solid var(--color-border-subtle)",
          display: "flex",
          flexDirection: "column",
          gap: "0.75rem",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span
            style={{
              fontSize: "0.75rem",
              fontWeight: 700,
              color: "var(--color-text-secondary)",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
            }}
          >
            Research Threads
          </span>
          <button
            className="btn btn-primary"
            onClick={onNewConversation}
            style={{
              padding: "0.3rem 0.625rem",
              fontSize: "0.6875rem",
              borderRadius: "6px",
            }}
            title="Start new research conversation"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            New Chat
          </button>
        </div>

        {}
        {conversations.length > 2 && (
          <input
            type="text"
            placeholder="Search past threads..."
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            style={{
              width: "100%",
              backgroundColor: "var(--color-bg-surface-alt)",
              border: "1px solid var(--color-border-subtle)",
              borderRadius: "4px",
              padding: "0.35rem 0.6rem",
              color: "var(--color-text-primary)",
              fontSize: "0.75rem",
              outline: "none",
            }}
          />
        )}
      </div>

      {}
      <div style={{ flex: 1, overflowY: "auto", padding: "0.5rem" }}>
        {isLoading && conversations.length === 0 ? (
          <div style={{ display: "flex", justifyContent: "center", padding: "2rem 0" }}>
            <span
              className="animate-spin"
              style={{
                width: "1.25rem",
                height: "1.25rem",
                border: "2px solid var(--color-border-subtle)",
                borderTopColor: "var(--color-emerald-500)",
                borderRadius: "50%",
              }}
            />
          </div>
        ) : filteredConversations.length === 0 ? (
          <div
            style={{
              textAlign: "center",
              padding: "2rem 1rem",
              color: "var(--color-text-secondary)",
              fontSize: "0.75rem",
            }}
          >
            {conversations.length === 0
              ? "No previous research conversations in this session."
              : "No threads matching your search."}
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
            {filteredConversations.map((conv) => {
              const isActive = conv.conversation_id === activeConversationId;
              const dateStr = new Date(conv.updated_at || conv.created_at).toLocaleDateString([], {
                month: "short",
                day: "numeric",
              });

              return (
                <div
                  key={conv.conversation_id}
                  onClick={() => onSelectConversation(conv.conversation_id)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "0.5rem 0.625rem",
                    borderRadius: "0.375rem",
                    backgroundColor: isActive
                      ? "rgba(16, 185, 129, 0.12)"
                      : "transparent",
                    border: `1px solid ${isActive ? "rgba(16, 185, 129, 0.4)" : "transparent"}`,
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                  }}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") onSelectConversation(conv.conversation_id);
                  }}
                  aria-selected={isActive}
                >
                  <div style={{ flex: 1, minWidth: 0, paddingRight: "0.5rem" }}>
                    <div
                      style={{
                        fontSize: "0.8125rem",
                        fontWeight: isActive ? 600 : 400,
                        color: isActive ? "var(--color-text-primary)" : "var(--color-text-secondary)",
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                    >
                      {conv.title || "Research Conversation"}
                    </div>
                    <div
                      className="font-tabular"
                      style={{
                        fontSize: "0.6875rem",
                        color: "var(--color-text-secondary)",
                        marginTop: "0.125rem",
                      }}
                    >
                      {dateStr} • {conv.message_count} turn{conv.message_count !== 1 ? "s" : ""}
                    </div>
                  </div>

                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (window.confirm("Delete this research conversation?")) {
                        onDeleteConversation(conv.conversation_id);
                      }
                    }}
                    style={{
                      background: "transparent",
                      border: "none",
                      color: "var(--color-text-secondary)",
                      cursor: "pointer",
                      padding: "0.25rem",
                      borderRadius: "4px",
                      opacity: isActive ? 1 : 0.4,
                      display: "flex",
                      alignItems: "center",
                    }}
                    title="Delete thread"
                    aria-label={`Delete conversation ${conv.title || conv.conversation_id}`}
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    </svg>
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
