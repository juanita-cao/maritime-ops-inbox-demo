import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ConfigProvider } from 'antd'
import enGB from 'antd/locale/en_GB'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider locale={enGB}>
      <App />
    </ConfigProvider>
  </StrictMode>,
)
