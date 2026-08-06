import loginHeroArt from '../../assets/login_img.svg'

/**
 * Login left-hero illustration with layered motion.
 * Base art is a flat SVG export (no semantic groups), so gears / flame / charts
 * are animated via an aligned overlay with the same 500×500 viewBox.
 */
export function LoginHeroIllustration() {
  return (
    <div
      className="login-hero-scene relative aspect-square size-[min(100%,68vh)] max-h-full max-w-full shrink select-none"
      aria-hidden="true"
    >
      <img
        src={loginHeroArt}
        alt=""
        className="pointer-events-none relative z-0 h-full w-full object-contain"
        draggable={false}
      />

      <svg
        className="pointer-events-none absolute inset-0 z-10 h-full w-full overflow-hidden"
        viewBox="0 0 500 500"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        {/* Soft rotating highlights over the drawn gears */}
        <g className="login-gear-a" style={{ transformOrigin: '65px 102px' }}>
          <circle
            cx="65"
            cy="102"
            r="40"
            stroke="rgba(152,199,237,0.45)"
            strokeWidth="3"
            strokeDasharray="12 10"
          />
        </g>
        <g className="login-gear-b" style={{ transformOrigin: '133px 59px' }}>
          <circle
            cx="133"
            cy="59"
            r="30"
            stroke="rgba(82,189,240,0.4)"
            strokeWidth="2.5"
            strokeDasharray="8 8"
          />
        </g>
        <g className="login-gear-c" style={{ transformOrigin: '95px 48px' }}>
          <circle
            cx="95"
            cy="48"
            r="18"
            stroke="rgba(9,98,143,0.4)"
            strokeWidth="2"
            strokeDasharray="5 6"
          />
        </g>

        {/* Rocket ignition plume at the nozzle */}
        <g className="login-rocket-flame" style={{ transformOrigin: '169px 348px' }}>
          <ellipse
            className="login-flame-glow"
            cx="169"
            cy="378"
            rx="26"
            ry="34"
            fill="url(#loginFlameGlow)"
          />
          <path
            className="login-flame-core"
            d="M155 348 C160 366 164 386 169 412 C174 386 178 366 183 348 C176 354 162 354 155 348Z"
            fill="url(#loginFlameCore)"
          />
          <path
            className="login-flame-inner"
            d="M162 352 C165 368 167 384 169 404 C171 384 173 368 176 352 C171 355 167 355 162 352Z"
            fill="#FFF8E7"
            opacity="0.92"
          />
          {/* Ember sparks */}
          <circle className="login-ember-a" cx="160" cy="390" r="2.2" fill="#FFB347" />
          <circle className="login-ember-b" cx="178" cy="396" r="1.8" fill="#FFD27A" />
          <circle className="login-ember-c" cx="169" cy="404" r="1.6" fill="#FF8A3D" />
        </g>

        {/* Chart motion accents on the floating panels */}
        <g className="login-chart-a" style={{ transformOrigin: '254px 140px' }}>
          <rect x="238" y="112" width="7" height="30" rx="1.5" fill="rgba(82,189,240,0.55)" />
          <rect x="249" y="100" width="7" height="42" rx="1.5" fill="rgba(82,189,240,0.75)" />
          <rect x="260" y="118" width="7" height="24" rx="1.5" fill="rgba(9,98,143,0.7)" />
          <rect x="271" y="106" width="7" height="36" rx="1.5" fill="rgba(82,189,240,0.65)" />
        </g>
        <g className="login-chart-b" style={{ transformOrigin: '84px 250px' }}>
          <path
            d="M66 270 C74 258 80 262 88 248 C94 238 100 244 108 234"
            stroke="rgba(82,189,240,0.8)"
            strokeWidth="2.5"
            strokeLinecap="round"
            fill="none"
          />
          <circle cx="88" cy="248" r="3.2" fill="rgba(82,189,240,0.95)" />
          <circle cx="108" cy="234" r="3.2" fill="rgba(82,189,240,0.95)" />
        </g>

        {/* Working-activity cues near characters */}
        <ellipse
          className="login-work-glow-a"
          cx="298"
          cy="362"
          rx="30"
          ry="11"
          fill="rgba(82,189,240,0.28)"
        />
        <ellipse
          className="login-work-glow-b"
          cx="419"
          cy="320"
          rx="24"
          ry="9"
          fill="rgba(82,189,240,0.22)"
        />
        <circle className="login-idea-pulse" cx="432" cy="248" r="11" fill="rgba(82,189,240,0.4)" />

        <defs>
          <radialGradient id="loginFlameGlow" cx="0.5" cy="0.3" r="0.75">
            <stop offset="0%" stopColor="rgba(255,190,70,0.9)" />
            <stop offset="50%" stopColor="rgba(255,90,30,0.45)" />
            <stop offset="100%" stopColor="rgba(255,40,10,0)" />
          </radialGradient>
          <linearGradient id="loginFlameCore" x1="169" y1="348" x2="169" y2="412">
            <stop offset="0%" stopColor="#FFE29A" />
            <stop offset="45%" stopColor="#FF7A2E" />
            <stop offset="100%" stopColor="#FF2E14" stopOpacity="0.1" />
          </linearGradient>
        </defs>
      </svg>
    </div>
  )
}
