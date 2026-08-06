import { useState } from 'react'
import { ArrowRight, Eye, EyeOff, Lock, Mail } from 'lucide-react'
import { useMatchView } from '../../context/MatchViewContext'
import { AppIcon } from '../shared/AppIcon'
import latentViewLockup from '../../assets/LV__White Horizontal Lock up-With Tagline 1.png'
import twentyYearsLockup from '../../assets/20years.png'
import { LoginHeroIllustration } from './LoginHeroIllustration'
import { MatchViewBrandLockup } from './MatchViewBrandLockup'

function GoogleGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615Z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18Z"
      />
      <path
        fill="#FBBC05"
        d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332Z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58Z"
      />
    </svg>
  )
}

export function LoginScreen() {
  const { login } = useMatchView()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!login(email, password)) {
      setError('Enter your work email to continue.')
      return
    }
    setError('')
  }

  const handleGoogleSignIn = () => {
    if (!login(email || 'demo@latentview.com', password || 'demo')) {
      setError('Unable to sign in with Google right now.')
    }
  }

  return (
    <div className="flex h-dvh max-h-dvh w-full overflow-hidden bg-white">
      {/* Left hero — LatentView brand plane */}
      <section
        className="relative hidden h-full w-[60%] flex-col overflow-hidden px-8 py-5 lg:flex xl:px-10 xl:py-6"
        aria-label="LatentView brand"
      >
        <div
          className="absolute inset-0"
          style={{
            background:
              'radial-gradient(120% 90% at 70% 100%, #5b8fd4 0%, #1c3f78 28%, #0c1c38 58%, #060e1c 100%)',
          }}
        />
        <div
          className="absolute inset-0 opacity-70"
          style={{
            background:
              'radial-gradient(ellipse 80% 55% at 45% 110%, rgba(152,199,237,0.45) 0%, transparent 55%), radial-gradient(ellipse 50% 40% at 85% 20%, rgba(28,87,171,0.35) 0%, transparent 50%)',
          }}
        />
        <div
          className="pointer-events-none absolute -bottom-24 left-1/2 h-[55%] w-[90%] -translate-x-1/2 rounded-full opacity-40 blur-3xl"
          style={{
            background:
              'radial-gradient(circle, rgba(152,199,237,0.55) 0%, rgba(28,87,171,0.2) 45%, transparent 70%)',
          }}
        />
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.1]"
          style={{
            backgroundImage:
              'url("data:image/svg+xml,%3Csvg viewBox=%270 0 200 200%27 xmlns=%27http://www.w3.org/2000/svg%27%3E%3Cfilter id=%27n%27%3E%3CfeTurbulence type=%27fractalNoise%27 baseFrequency=%270.85%27 numOctaves=%274%27 stitchTiles=%27stitch%27/%3E%3C/filter%3E%3Crect width=%27100%25%27 height=%27100%25%27 filter=%27url(%23n)%27/%3E%3C/svg%3E")',
          }}
        />

        <header className="relative z-10 flex shrink-0 items-start justify-between gap-6 animate-[loginFade_700ms_ease-out]">
          <img
            src={latentViewLockup}
            alt="LatentView"
            className="h-8 w-auto object-contain object-left mix-blend-screen sm:h-9"
          />
          <img
            src={twentyYearsLockup}
            alt="20 years — Building What's Next"
            className="h-10 w-auto shrink-0 object-contain object-right mix-blend-screen sm:h-12"
          />
        </header>

        <div className="relative z-10 flex min-h-0 flex-1 items-center justify-center px-6 pb-5 pt-2 animate-[loginFade_900ms_ease-out] xl:px-10">
          <LoginHeroIllustration />
        </div>
      </section>

      {/* Right auth panel */}
      <section className="relative flex h-full w-full flex-col overflow-hidden bg-white lg:w-[40%]">
        <div className="flex min-h-0 flex-1 flex-col justify-center px-8 py-6 sm:px-12 lg:px-14 lg:py-8 xl:px-16">
          <div className="mx-auto w-full max-w-[360px] animate-[loginRise_650ms_ease-out]">
            <div className="mb-5 lg:mb-6">
              <MatchViewBrandLockup />
            </div>

            <form onSubmit={handleSubmit} className="space-y-3.5 lg:space-y-5">
              <div>
                <label
                  htmlFor="login-email"
                  className="mb-1.5 block text-sm font-semibold text-slate-800"
                >
                  Work Email
                </label>
                <div className="relative">
                  <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-slate-400">
                    <AppIcon icon={Mail} size="sm" />
                  </span>
                  <input
                    id="login-email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="name@latentview.com"
                    autoComplete="username"
                    className="w-full rounded-lg border border-slate-200 bg-white py-2.5 pl-10 pr-3 text-sm text-slate-900 outline-none transition-[border-color,box-shadow] placeholder:text-slate-400 focus:border-[#1c57ab] focus:shadow-[0_0_0_3px_rgba(28,87,171,0.12)]"
                  />
                </div>
              </div>

              <div>
                <div className="mb-1.5 flex items-center justify-between gap-3">
                  <label
                    htmlFor="login-password"
                    className="block text-sm font-semibold text-slate-800"
                  >
                    Password
                  </label>
                  <button
                    type="button"
                    className="text-sm font-medium text-[#1c57ab] transition-opacity hover:opacity-80"
                  >
                    Forgot password?
                  </button>
                </div>
                <div className="relative">
                  <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-slate-400">
                    <AppIcon icon={Lock} size="sm" />
                  </span>
                  <input
                    id="login-password"
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    autoComplete="current-password"
                    className="w-full rounded-lg border border-slate-200 bg-white py-2.5 pl-10 pr-10 text-sm text-slate-900 outline-none transition-[border-color,box-shadow] placeholder:text-slate-400 focus:border-[#1c57ab] focus:shadow-[0_0_0_3px_rgba(28,87,171,0.12)]"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    className="absolute inset-y-0 right-2.5 flex items-center rounded-md px-1.5 text-slate-400 transition-colors hover:text-slate-600"
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                  >
                    <AppIcon icon={showPassword ? EyeOff : Eye} size="sm" />
                  </button>
                </div>
              </div>

              {error ? <p className="text-sm text-red-600">{error}</p> : null}

              <button
                type="submit"
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-[#1c57ab] py-2.5 text-sm font-semibold text-white transition-[opacity,transform] hover:opacity-95 active:scale-[0.99]"
              >
                Sign In
                <AppIcon icon={ArrowRight} size="sm" />
              </button>
            </form>

            <div className="my-4 flex items-center gap-3 lg:my-6">
              <div className="h-px flex-1 bg-slate-200" />
              <span className="text-xs font-medium tracking-wide text-slate-400">OR</span>
              <div className="h-px flex-1 bg-slate-200" />
            </div>

            <button
              type="button"
              onClick={handleGoogleSignIn}
              className="flex w-full items-center justify-center gap-2.5 rounded-lg border border-slate-200 bg-white py-2.5 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
            >
              <GoogleGlyph />
              Sign in with Google
            </button>

            <p className="mt-5 text-center text-sm text-slate-500 lg:mt-7">
              Don&apos;t have an account?{' '}
              <button
                type="button"
                className="font-semibold text-[#1c57ab] transition-opacity hover:opacity-80"
              >
                Request Access
              </button>
            </p>
          </div>
        </div>

        <footer className="flex shrink-0 items-center justify-center gap-6 px-8 pb-5 pt-1 text-xs text-slate-400 lg:pb-6">
          <button type="button" className="transition-colors hover:text-slate-600">
            Privacy
          </button>
          <button type="button" className="transition-colors hover:text-slate-600">
            Legal
          </button>
          <button type="button" className="transition-colors hover:text-slate-600">
            Security
          </button>
        </footer>
      </section>
    </div>
  )
}
