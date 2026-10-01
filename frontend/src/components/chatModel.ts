// The chat model the officer picked last (v5.1 model picker), kept per browser.
// v2: the options changed (Hybrid is the default); an older saved choice must not carry over
export const CHAT_MODEL_KEY = 'mm-chat-model-v2'

export function savedChatModel(): string | null {
  try {
    return localStorage.getItem(CHAT_MODEL_KEY)
  } catch {
    return null
  }
}
