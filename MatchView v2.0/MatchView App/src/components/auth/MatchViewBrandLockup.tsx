import matchViewLogo from '../../assets/matchview_logo.svg'

/** Match View brand lockup — logo + title + tagline for login. */
export function MatchViewBrandLockup({ className = '' }: { className?: string }) {
  return (
    <div className={`flex flex-col items-center text-center ${className}`}>
      <img
        src={matchViewLogo}
        alt=""
        className="h-10 w-auto lg:h-12"
        aria-hidden="true"
      />
      <h1
        className="type-display mt-3 lg:mt-4 lg:text-display-lg"
        style={{ color: '#0a2a5c' }}
      >
        Match View
      </h1>
      <p className="mt-1 max-w-[20rem] text-sm leading-snug text-slate-500 lg:mt-1.5">
        Your AI copilot for end-to-end experimentation
      </p>
    </div>
  )
}
