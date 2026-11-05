function emptyOffer() {
  return {
    resource_id: "",
    resource_qty: "",
    discounted_currency_qty: "",
    discount_pct: "",
    min_vip_level: "",
    limit_qty: "",
  };
}

function offerForm(initial) {
  return {
    rows: Array.isArray(initial) && initial.length ? initial : [emptyOffer()],
    addRow() {
      this.rows.push(emptyOffer());
    },
  };
}

function emptyBoxItem() {
  return {
    resource_id: "",
    qty: "",
  };
}

function boxForm(initial) {
  return {
    rows: Array.isArray(initial) && initial.length ? initial : [emptyBoxItem()],
    addRow() {
      this.rows.push(emptyBoxItem());
    },
  };
}

function chatApp(initialSessions, initialSessionId) {
  return {
    sessions: Array.isArray(initialSessions) ? initialSessions : [],
    sessionId: initialSessionId || null,
    messages: [],
    input: "",
    streaming: false,
    streamText: "",
    streamTools: [],
    finalHtml: "",
    error: "",

    async init() {
      if (this.sessionId) {
        await this.loadSession(this.sessionId);
      }
    },

    scroll() {
      this.$nextTick(() => {
        const el = this.$refs.scroller;
        if (el) el.scrollTop = el.scrollHeight;
      });
    },

    escapeText(text) {
      return String(text || "").replace(
        /[&<>"']/g,
        (char) =>
          ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;",
          })[char]
      );
    },

    upsertSession(session) {
      const index = this.sessions.findIndex((item) => item.id === session.id);
      if (index >= 0) {
        this.sessions[index] = { ...this.sessions[index], ...session };
      } else {
        this.sessions.unshift(session);
      }
    },

    async refreshSessions() {
      try {
        const response = await fetch("/api/chat/sessions");
        if (response.ok) this.sessions = await response.json();
      } catch (error) {
        /* 会话列表刷新失败不影响当前对话 */
      }
    },

    async loadSession(id) {
      this.sessionId = id;
      this.error = "";
      try {
        const response = await fetch(`/api/chat/sessions/${id}`);
        if (!response.ok) throw new Error("加载会话失败");
        const data = await response.json();
        this.messages = data.messages || [];
        this.scroll();
      } catch (error) {
        this.error = error.message || String(error);
      }
    },

    newSession() {
      this.sessionId = null;
      this.messages = [];
      this.input = "";
      this.error = "";
      this.streaming = false;
      this.streamText = "";
      this.streamTools = [];
      this.finalHtml = "";
    },

    async removeSession(id) {
      if (!window.confirm("删除这个对话？")) return;
      try {
        const response = await fetch(`/api/chat/sessions/${id}`, {
          method: "DELETE",
        });
        if (!response.ok) throw new Error("删除失败");
        this.sessions = this.sessions.filter((item) => item.id !== id);
        if (this.sessionId === id) {
          if (this.sessions.length) {
            await this.loadSession(this.sessions[0].id);
          } else {
            this.newSession();
          }
        }
      } catch (error) {
        this.error = error.message || String(error);
      }
    },

    ask(text) {
      this.input = text;
      this.send();
    },

    async send() {
      const text = this.input.trim();
      if (!text || this.streaming) return;

      this.input = "";
      this.error = "";
      this.messages.push({ role: "user", content: text, tools: [] });
      this.streaming = true;
      this.streamText = "";
      this.streamTools = [];
      this.finalHtml = "";
      this.scroll();

      try {
        const response = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: this.sessionId, message: text }),
        });
        if (!response.ok) {
          let detail = "请求失败";
          try {
            const payload = await response.json();
            detail = payload.detail || detail;
          } catch (error) {
            /* 非 JSON 错误响应 */
          }
          if (response.status === 404 && this.sessionId) {
            this.sessionId = null;
            detail = "会话已不存在，已重置，请重新发送。";
          }
          throw new Error(detail);
        }
        await this.consume(response);
      } catch (error) {
        this.error = error.message || String(error);
      } finally {
        this.streaming = false;
        this.scroll();
      }
    },

    async consume(response) {
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let boundary = buffer.indexOf("\n\n");
        while (boundary >= 0) {
          const chunk = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          this.handleEvent(chunk);
          boundary = buffer.indexOf("\n\n");
        }
      }
    },

    handleEvent(chunk) {
      let event = "message";
      let data = "";
      for (const line of chunk.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) return;

      let payload;
      try {
        payload = JSON.parse(data);
      } catch (error) {
        return;
      }

      if (event === "session") {
        this.sessionId = payload.id;
        this.upsertSession({ id: payload.id, title: payload.title });
      } else if (event === "tool") {
        this.streamTools.push(payload.label || payload.name);
        this.scroll();
      } else if (event === "token") {
        this.streamText += payload.text || "";
        this.scroll();
      } else if (event === "html") {
        this.finalHtml = payload.html || "";
      } else if (event === "done") {
        this.messages.push({
          role: "assistant",
          content: this.streamText,
          html: this.finalHtml,
          tools: this.streamTools.slice(),
        });
        this.streaming = false;
        this.streamText = "";
        this.streamTools = [];
        this.finalHtml = "";
        this.refreshSessions();
        this.scroll();
      } else if (event === "error") {
        this.error = payload.detail || "模型调用失败";
        this.streaming = false;
      }
    },
  };
}
