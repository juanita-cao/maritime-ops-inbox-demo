// The dolphin's mood from the number of to-dos (emails to review plus open tasks), U11.
export type Mood = 'tired' | 'calm' | 'eating'

export function moodOf(todo: number): Mood {
  if (todo > 20) return 'tired'
  if (todo >= 8) return 'calm'
  return 'eating'
}
