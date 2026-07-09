#!/usr/bin/env python
"""
Everlay Desktop Chat App - Local GUI for AI agents.
"""
import asyncio
import sys
import threading
import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import get_settings
from core.logging_config import setup_logging
from core.openrouter_client import OpenRouterClient
from agents.presets import AgentFactory
from agents.base import AgentContext
import uuid
from datetime import datetime


class EverlayApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Everlay AI Chat")
        self.root.geometry("900x700")
        self.root.minsize(700, 500)

        # State
        self.current_agent_type = "default"
        self.agent = None
        self.context = None
        self.message_count = 0
        self.is_processing = False

        # Setup
        self.setup_logging()
        self.create_widgets()
        self.initialize_agent()

    def setup_logging(self):
        settings = get_settings()
        setup_logging(settings)

    def create_widgets(self):
        # Free OpenRouter models
        self.FREE_MODELS = [
            "nvidia/nemotron-3-ultra-550b-a55b:free",
            "poolside/laguna-m.1:free",
            "nvidia/nemotron-3-super-120b-a12b:free",
            "cohere/north-mini-code:free",
            "poolside/laguna-xs-2.1:free",
            "openai/gpt-oss-120b:free",
            "nvidia/nemotron-3-nano-30b-a3b:free",
            "google/gemma-4-31b-it:free",
            "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
            "nvidia/nemotron-nano-9b-v2:free",
            "openai/gpt-oss-20b:free",
            "openai/gpt-4o-mini",  # Default paid model
        ]

        # Top bar - Agent selection
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(fill=tk.X)

        ttk.Label(top_frame, text="Agent:").pack(side=tk.LEFT, padx=(0, 5))

        self.agent_var = tk.StringVar(value="default")
        agent_combo = ttk.Combobox(
            top_frame,
            textvariable=self.agent_var,
            values=["default", "code", "chat"],
            state="readonly",
            width=12
        )
        agent_combo.pack(side=tk.LEFT, padx=(0, 10))
        agent_combo.bind("<<ComboboxSelected>>", self.on_agent_change)

        # Model selection
        ttk.Label(top_frame, text="Model:").pack(side=tk.LEFT, padx=(10, 5))
        self.model_var = tk.StringVar(value="nvidia/nemotron-3-ultra-550b-a55b:free")
        model_combo = ttk.Combobox(
            top_frame,
            textvariable=self.model_var,
            values=self.FREE_MODELS,
            state="normal",  # Allow typing custom models
            width=45
        )
        model_combo.pack(side=tk.LEFT, padx=(0, 10))
        model_combo.bind("<<ComboboxSelected>>", lambda e: self.update_model())
        model_combo.bind("<Return>", lambda e: self.update_model())

        ttk.Button(top_frame, text="Apply Model", command=self.update_model).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="Clear Chat", command=self.clear_chat).pack(side=tk.LEFT, padx=5)

        # Status label
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(top_frame, textvariable=self.status_var, foreground="gray").pack(side=tk.RIGHT)

        # Chat area
        chat_frame = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        chat_frame.pack(fill=tk.BOTH, expand=True)

        self.chat_display = scrolledtext.ScrolledText(
            chat_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Consolas", 10),
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white",
            selectbackground="#264f78",
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True)

        # Right-click context menu for copy
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Copy", command=self.copy_selection, accelerator="Ctrl+C")
        self.context_menu.add_command(label="Select All", command=self.select_all, accelerator="Ctrl+A")
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Clear Chat", command=self.clear_chat)

        self.chat_display.bind("<Button-3>", self.show_context_menu)  # Right-click
        self.chat_display.bind("<Control-c>", lambda e: self.copy_selection())
        self.chat_display.bind("<Control-a>", lambda e: self.select_all())

        # Configure tags for styling
        self.chat_display.tag_config("user", foreground="#4ec9b0", font=("Consolas", 10, "bold"))
        self.chat_display.tag_config("assistant", foreground="#dcdcaa")
        self.chat_display.tag_config("system", foreground="#6a9955", font=("Consolas", 9, "italic"))
        self.chat_display.tag_config("error", foreground="#f44747", font=("Consolas", 10, "bold"))
        self.chat_display.tag_config("tool", foreground="#ce9178", font=("Consolas", 9))

        # Input area
        input_frame = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        input_frame.pack(fill=tk.X)

        self.input_text = tk.Text(
            input_frame,
            height=4,
            wrap=tk.WORD,
            font=("Consolas", 10),
            bg="#2d2d2d",
            fg="#d4d4d4",
            insertbackground="white",
        )
        self.input_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        self.input_text.bind("<Control-Return>", lambda e: self.send_message())
        self.input_text.bind("<Return>", self.on_enter)

        # Buttons
        btn_frame = ttk.Frame(input_frame)
        btn_frame.pack(side=tk.RIGHT, fill=tk.Y)

        self.send_btn = ttk.Button(btn_frame, text="Send (Ctrl+Enter)", command=self.send_message)
        self.send_btn.pack(fill=tk.X, pady=(0, 5))

        ttk.Button(btn_frame, text="Stop", command=self.stop_generation).pack(fill=tk.X)

        # Focus input
        self.input_text.focus()

    def show_context_menu(self, event):
        """Show right-click context menu."""
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def copy_selection(self):
        """Copy selected text to clipboard."""
        try:
            selected = self.chat_display.get(tk.SEL_FIRST, tk.SEL_LAST)
            if selected:
                self.root.clipboard_clear()
                self.root.clipboard_append(selected)
        except tk.TclError:
            pass  # No selection

    def select_all(self):
        """Select all text in chat display."""
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.tag_add(tk.SEL, "1.0", tk.END)
        self.chat_display.mark_set(tk.INSERT, "1.0")
        self.chat_display.see(tk.INSERT)
        self.chat_display.config(state=tk.DISABLED)
        return "break"

    def initialize_agent(self):
        """Create the initial agent."""
        self.agent = AgentFactory.create(self.current_agent_type)
        self.context = AgentContext(
            agent_id=str(uuid.uuid4()),
            conversation_id=str(uuid.uuid4()),
        )
        self.add_message("system", f"✅ Connected to {self.current_agent_type} agent\nModel: {self.agent.model}\nTools: {', '.join(self.agent.tools.keys()) if self.agent.tools else 'none'}\n\nType your message and press Ctrl+Enter to send.")

    def on_agent_change(self, event=None):
        """Switch agent type."""
        new_type = self.agent_var.get()
        if new_type != self.current_agent_type:
            self.current_agent_type = new_type
            self.agent = AgentFactory.create(new_type)
            self.context = AgentContext(
                agent_id=str(uuid.uuid4()),
                conversation_id=str(uuid.uuid4()),
            )
            self.message_count = 0
            self.clear_chat(silent=True)
            self.add_message("system", f"🔄 Switched to {new_type} agent\nModel: {self.agent.model}\nTools: {', '.join(self.agent.tools.keys()) if self.agent.tools else 'none'}")

    def update_model(self):
        """Update the model for current agent."""
        model = self.model_var.get().strip()
        if model:
            self.agent.model = model
            self.add_message("system", f"🔧 Model changed to: {model}")

    def on_enter(self, event):
        """Handle Enter key - Shift+Enter for newline, Enter to send."""
        if not event.state & 0x1:  # No Shift
            self.send_message()
            return "break"
        return None  # Allow newline

    def send_message(self):
        """Send message to agent."""
        text = self.input_text.get("1.0", tk.END).strip()
        if not text or self.is_processing:
            return

        self.input_text.delete("1.0", tk.END)
        self.add_message("user", text)
        self.message_count += 1
        self.status_var.set("Thinking...")
        self.is_processing = True
        self.send_btn.config(state=tk.DISABLED)

        # Run agent in background thread
        threading.Thread(target=self.run_agent, args=(text,), daemon=True).start()

    def stop_generation(self):
        """Stop current generation."""
        self.is_processing = False
        self.status_var.set("Stopped")
        self.send_btn.config(state=tk.NORMAL)

    def run_agent(self, message):
        """Run agent in background thread using asyncio.run() with fresh client per request."""
        try:
            # Create a fresh client for this request to avoid event loop conflicts
            fresh_client = OpenRouterClient()

            # Create a new agent with the fresh client (preserves tools, history, etc.)
            fresh_agent = AgentFactory.create(self.current_agent_type, client=fresh_client)
            fresh_agent.model = self.agent.model
            fresh_agent.temperature = self.agent.temperature
            fresh_agent.max_tokens = self.agent.max_tokens
            # Copy conversation history
            fresh_agent._conversation_history = self.agent._conversation_history.copy()

            # Use asyncio.run() which creates and closes its own event loop properly
            # Do everything in one asyncio.run() call to avoid loop conflicts
            async def run_with_cleanup():
                try:
                    return await fresh_agent.run(message, self.context)
                finally:
                    await fresh_client.close()

            result = asyncio.run(run_with_cleanup())

            # Sync back the updated conversation history
            self.agent._conversation_history = fresh_agent._conversation_history

            # Update UI on main thread
            self.root.after(0, self.on_agent_result, result)

        except Exception as e:
            self.root.after(0, self.on_agent_error, str(e))

    def on_agent_result(self, result):
        """Handle agent result on main thread."""
        self.is_processing = False
        self.send_btn.config(state=tk.NORMAL)
        self.status_var.set("Ready")

        if result.success:
            self.add_message("assistant", result.content)
            if result.tool_calls:
                for tc in result.tool_calls:
                    tool_name = tc.get("function", {}).get("name", "unknown")
                    self.add_message("tool", f"🔧 Tool used: {tool_name}")
        else:
            self.add_message("error", f"❌ Error: {result.error}")

    def on_agent_error(self, error):
        """Handle agent error on main thread."""
        self.is_processing = False
        self.send_btn.config(state=tk.NORMAL)
        self.status_var.set("Error")

        # Better error messages for common issues
        error_lower = str(error).lower()
        if "rate limit" in error_lower or "429" in error_lower:
            self.add_message("error",
                "❌ Rate limited! Free models have strict limits.\n"
                "• Wait 30-60 seconds before next request\n"
                "• Try a different free model from dropdown\n"
                "• Or use a paid model (e.g., openai/gpt-4o-mini)")
        elif "event loop" in error_lower:
            self.add_message("error", f"❌ Event loop error (should be fixed): {error}")
        else:
            self.add_message("error", f"❌ Error: {error}")

    def add_message(self, role, content):
        """Add message to chat display."""
        self.chat_display.config(state=tk.NORMAL)

        # Add timestamp
        timestamp = datetime.now().strftime("%H:%M:%S")

        if role == "user":
            self.chat_display.insert(tk.END, f"[{timestamp}] You: ", "user")
            self.chat_display.insert(tk.END, f"{content}\n\n")
        elif role == "assistant":
            self.chat_display.insert(tk.END, f"[{timestamp}] AI: ", "assistant")
            self.chat_display.insert(tk.END, f"{content}\n\n")
        elif role == "system":
            self.chat_display.insert(tk.END, f"{content}\n\n", "system")
        elif role == "tool":
            self.chat_display.insert(tk.END, f"{content}\n", "tool")
        elif role == "error":
            self.chat_display.insert(tk.END, f"{content}\n\n", "error")

        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)

    def clear_chat(self, silent=False):
        """Clear chat display."""
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.delete("1.0", tk.END)
        self.chat_display.config(state=tk.DISABLED)
        if not silent:
            self.add_message("system", "🧹 Chat cleared")


def main():
    root = tk.Tk()

    # Try to set a nice theme
    try:
        style = ttk.Style()
        style.theme_use("clam")  # Works on all platforms

        # Dark theme colors
        style.configure(".", background="#1e1e1e", foreground="#d4d4d4")
        style.configure("TFrame", background="#1e1e1e")
        style.configure("TLabel", background="#1e1e1e", foreground="#d4d4d4")
        style.configure("TButton", background="#3c3c3c", foreground="#d4d4d4")
        style.map("TButton", background=[("active", "#4c4c4c")])
        style.configure("TCombobox", fieldbackground="#2d2d2d", background="#3c3c3c")
        style.configure("TEntry", fieldbackground="#2d2d2d", foreground="#d4d4d4")
    except:
        pass

    app = EverlayApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()