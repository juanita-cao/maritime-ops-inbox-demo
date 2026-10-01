// The chosen colour mode and its setter, shared by the App and the Mode picker (U13, U14).
import { createContext } from 'react'
import { DEFAULT_MODE, type ModeId } from '../theme'

export const ModeContext = createContext<{ mode: ModeId; setMode: (m: ModeId) => void }>({
  mode: DEFAULT_MODE,
  setMode: () => {},
})
