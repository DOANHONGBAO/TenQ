/** Flat clay-style treasure chest. The lid swings open and coins pop out when `open` is set. */
export function TreasureChest({ open }: { open: boolean }) {
  return (
    <div className={`chest ${open ? 'chest-open' : 'chest-closed'}`} aria-hidden="true">
      <div className="chest-glow" />
      <svg className="chest-svg" viewBox="0 0 200 170" focusable="false">
        <g className="chest-coins">
          <circle className="coin coin-1" cx="70" cy="78" r="13" />
          <circle className="coin coin-2" cx="100" cy="70" r="15" />
          <circle className="coin coin-3" cx="130" cy="78" r="13" />
          <path className="sparkle sparkle-1" d="M52 40l4 10 10 4-10 4-4 10-4-10-10-4 10-4z" />
          <path className="sparkle sparkle-2" d="M150 34l3 8 8 3-8 3-3 8-3-8-8-3 8-3z" />
        </g>
        <g className="chest-body">
          <rect x="22" y="82" width="156" height="78" rx="22" className="chest-wood" />
          <rect x="22" y="82" width="156" height="18" rx="9" className="chest-rim" />
          <rect x="44" y="82" width="14" height="78" className="chest-band" />
          <rect x="142" y="82" width="14" height="78" className="chest-band" />
          <rect x="84" y="94" width="32" height="34" rx="10" className="chest-lock" />
          <circle cx="100" cy="109" r="5" className="chest-keyhole" />
        </g>
        <g className="chest-lid">
          <path d="M22 86 V70 a44 44 0 0 1 44 -44 h68 a44 44 0 0 1 44 44 V86 z" className="chest-wood" />
          <rect x="44" y="27" width="14" height="59" className="chest-band" />
          <rect x="142" y="27" width="14" height="59" className="chest-band" />
          <path d="M34 60 q66 -40 132 0" className="chest-shine" />
        </g>
      </svg>
    </div>
  )
}
