export default function WarehouseScene({ fallen }: { fallen: boolean }) {
  return <svg className="warehouse-scene" viewBox="0 0 1000 520" role="img" aria-label={fallen ? "Simulated warehouse camera showing a fallen worker" : "Simulated warehouse camera showing a worker in a forklift corridor"} preserveAspectRatio="xMidYMid slice">
    <defs>
      <linearGradient id="floor" x2="0" y2="1"><stop stopColor="#3c4748"/><stop offset="1" stopColor="#69706b"/></linearGradient>
      <linearGradient id="ceiling" x2="0" y2="1"><stop stopColor="#121c20"/><stop offset="1" stopColor="#566260"/></linearGradient>
      <linearGradient id="shelf" x2="1" y2="0"><stop stopColor="#233035"/><stop offset="1" stopColor="#4e5b58"/></linearGradient>
      <filter id="grain"><feTurbulence type="fractalNoise" baseFrequency=".7" numOctaves="3" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/><feComponentTransfer><feFuncA type="linear" slope=".085"/></feComponentTransfer><feBlend in="SourceGraphic" mode="soft-light"/></filter>
    </defs>
    <g filter="url(#grain)">
      <rect width="1000" height="520" fill="#354341"/>
      <path d="M0 0H1000L660 230H395Z" fill="url(#ceiling)"/>
      <path d="M0 520V210L400 230H650L1000 200V520Z" fill="url(#floor)"/>
      <path d="M420 95H631V255H420Z" fill="#596461"/><path d="M480 130H573V258H480Z" fill="#243234"/>
      {[0,1,2,3,4,5].map(i=><g key={i}><path d={`M${i*195-80} 0L${445+i*24} 230`} stroke="#73817b" strokeWidth="5"/><path d={`M0 ${20+i*32}H1000`} stroke="#263536" strokeWidth="7"/></g>)}
      <path d="M274 35L464 204M777 30L588 204" stroke="#d2dfcf" strokeWidth="7" opacity=".7"/>
      <path d="M0 76L405 212V298L0 441Z" fill="url(#shelf)"/><path d="M1000 57L637 209V286L1000 403Z" fill="url(#shelf)"/>
      {[0,1,2,3].map(i=><g key={i}><path d={`M${i*100} ${76+i*34}V${441-i*35}`} stroke="#a67b39" strokeWidth={11-i*2}/><path d={`M${1000-i*92} ${57+i*38}V${403-i*31}`} stroke="#a67b39" strokeWidth={11-i*2}/></g>)}
      {[0,1,2].map(i=><g key={i}><path d={`M0 ${160+i*107}L405 ${236+i*28}`} stroke="#b37b35" strokeWidth="8"/><path d={`M1000 ${141+i*105}L637 ${231+i*24}`} stroke="#b37b35" strokeWidth="8"/></g>)}
      {[0,1,2,3,4].map(i=><g key={i}><path d={`M${12+i*77} ${98+i*25}l58 20v55l-58 -13z`} fill={i%2?'#62665a':'#81806b'}/><path d={`M${8+i*77} ${228+i*3}l58 0v62l-58 14z`} fill="#60675a"/><path d={`M${986-i*72} ${88+i*29}l-52 22v51l52 -17z`} fill={i%2?'#797a64':'#626856'}/><path d={`M${990-i*73} ${210+i*7}l-54 5v60l54 15z`} fill="#6d7360"/></g>)}
      <path d="M175 520L441 268M865 520L611 268" stroke="#c7ac56" strokeWidth="5" opacity=".85"/><path d="M230 520L462 268M803 520L592 268" stroke="#b5ac72" strokeWidth="2" opacity=".7"/>
      <path d="M485 520L517 275" stroke="#adb3a2" strokeWidth="3" strokeDasharray="30 20" opacity=".35"/>
      <g transform="translate(695 278)"><ellipse cx="38" cy="84" rx="64" ry="13" fill="#243332" opacity=".6"/><path d="M0 10H74V61H0Z" fill="#a48a38"/><path d="M14 -49H58V10H14Z" fill="#243538"/><path d="M18 -44H54V-8H18Z" fill="#6a7d7a"/><path d="M72 -42V73H80V-42Z" fill="#182526"/><path d="M76 72H125" stroke="#273435" strokeWidth="6"/><circle cx="13" cy="66" r="16" fill="#182323"/><circle cx="62" cy="66" r="16" fill="#182323"/><path d="M7 23H48" stroke="#e0b956" strokeWidth="4"/></g>
      <ellipse cx="496" cy="376" rx="39" ry="10" fill="#162525" opacity=".65"/>
      <g transform={fallen ? "translate(464 354) rotate(80 30 0)" : "translate(465 232)"}>
        <circle cx="28" cy="19" r="14" fill="#c0ae8a"/><path d="M12 13Q12 -3 28 -3Q45 -3 45 13Z" fill="#d3b654"/>
        <path d="M14 36L41 36L47 86H7Z" fill="#b8c16b"/><path d="M18 37L18 79M36 37L36 79" stroke="#d6ddc0" strokeWidth="4"/><path d="M11 44L0 79M43 44L55 80" stroke="#344349" strokeWidth="12" strokeLinecap="round"/>
        <path d="M17 84L12 131M36 84L42 131" stroke="#233238" strokeWidth="13"/><path d="M4 134H18M37 134H53" stroke="#172224" strokeWidth="9" strokeLinecap="round"/>
      </g>
    </g>
    <rect width="1000" height="520" fill="#051014" opacity=".2"/>
  </svg>;
}
