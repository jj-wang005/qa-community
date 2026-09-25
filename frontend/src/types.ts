export interface Question {
  id: number
  author_name: string
  title: string
  content: string
  answer_count: number
  view_count: number
  created_at: string
  updated_at: string
}

export interface Answer {
  id: number
  question_id: number
  author_name: string
  content: string
  like_count: number
  is_accepted: boolean
  is_liked: boolean
  created_at: string
}

export interface ApprovalAction {
  name: 'like_answer'
  args: { answer_id: number }
  allowed_decisions: Array<'approve' | 'reject'>
}

export interface PendingApproval {
  session_id: string
  approval_id: string
  expires_in: number
  actions: ApprovalAction[]
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
}
