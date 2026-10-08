import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MotionConfig } from 'motion/react'
import { BrowserRouter } from 'react-router-dom'
import '@fontsource-variable/mona-sans/standard.css'
import 'leaflet/dist/leaflet.css'
import './index.css'
import App from './App'
import { PresentationProvider } from './presentation'
import { ThemeProvider } from './theme'

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } })

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <PresentationProvider>
          <MotionConfig reducedMotion="user">
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </MotionConfig>
        </PresentationProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
)
