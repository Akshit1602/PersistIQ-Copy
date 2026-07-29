import { MatchViewProvider, useMatchView } from './context/MatchViewContext'
import { ConversationalLoopProvider } from './context/ConversationalLoopContext'
import { LoginScreen } from './components/auth/LoginScreen'
import { AppShell } from './components/layout/AppShell'

function AuthenticatedApp() {
  const { isAuthenticated } = useMatchView()

  if (!isAuthenticated) {
    return <LoginScreen />
  }

  return (
    <ConversationalLoopProvider>
      <AppShell />
    </ConversationalLoopProvider>
  )
}

function App() {
  return (
    <MatchViewProvider>
      <AuthenticatedApp />
    </MatchViewProvider>
  )
}

export default App
