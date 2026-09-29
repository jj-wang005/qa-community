import { reactive } from 'vue'

// Memory only: preserve drafts across login/navigation without persisting content to disk.
export const drafts = reactive({ title: '', content: '', answers: {} as Record<string, string> })
