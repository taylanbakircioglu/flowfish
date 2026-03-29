import React from 'react';

interface FlowfishLogoProps {
  size?: number;
  showText?: boolean;
  textSize?: number;
  style?: React.CSSProperties;
}

const FlowfishLogo: React.FC<FlowfishLogoProps> = ({ 
  size = 40, 
  showText = false, 
  textSize,
  style 
}) => {
  const uniqueId = React.useId().replace(/:/g, '');

  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: size * 0.3, ...style }}>
      <svg
        viewBox="0 0 64 64"
        width={size}
        height={size}
        style={{ display: 'block', flexShrink: 0 }}
      >
        <defs>
          <linearGradient id={`bodyGrad-${uniqueId}`} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#22d3ee" />
            <stop offset="50%" stopColor="#06b6d4" />
            <stop offset="100%" stopColor="#0891b2" />
          </linearGradient>
          <linearGradient id={`finGrad-${uniqueId}`} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#0891b2" />
            <stop offset="100%" stopColor="#0e7490" />
          </linearGradient>
        </defs>

        {/* Fish body */}
        <path
          d="M 54 32 C 54 23 45 16 33 16 C 24 16 17 20 14 26 L 6 18 Q 9 25 10 32 Q 9 39 6 46 L 14 38 C 17 44 24 48 33 48 C 45 48 54 41 54 32 Z"
          fill={`url(#bodyGrad-${uniqueId})`}
        />

        {/* Dorsal fin */}
        <path d="M 30 16 C 28 10 32 8 36 14 C 34 15 32 16 30 16 Z" fill={`url(#finGrad-${uniqueId})`} />

        {/* Ventral fin */}
        <path d="M 30 48 C 28 52 32 54 34 49 C 32 48 30 48 30 48 Z" fill={`url(#finGrad-${uniqueId})`} opacity={0.8} />

        {/* Pectoral fin */}
        <path d="M 26 34 C 22 38 20 42 24 40 C 26 38 27 36 26 34 Z" fill={`url(#finGrad-${uniqueId})`} opacity={0.7} />

        {/* Flow lines (network data paths) */}
        <path d="M 16 30 Q 24 27 32 29 Q 40 31 48 30" stroke="rgba(255,255,255,0.3)" strokeWidth={0.8} fill="none" strokeLinecap="round" />
        <path d="M 18 35 Q 26 33 34 35 Q 40 36 46 34" stroke="rgba(255,255,255,0.2)" strokeWidth={0.6} fill="none" strokeLinecap="round" />

        {/* Network nodes (eBPF observation points) */}
        <circle cx={24} cy={29} r={2} fill="rgba(255,255,255,0.45)" />
        <circle cx={32} cy={30} r={2} fill="rgba(255,255,255,0.45)" />
        <circle cx={40} cy={31} r={1.6} fill="rgba(255,255,255,0.35)" />
        <circle cx={28} cy={35} r={1.4} fill="rgba(255,255,255,0.3)" />

        {/* Node connections (dependency mapping) */}
        <line x1={24} y1={29} x2={32} y2={30} stroke="rgba(255,255,255,0.25)" strokeWidth={0.5} />
        <line x1={32} y1={30} x2={40} y2={31} stroke="rgba(255,255,255,0.25)" strokeWidth={0.5} />
        <line x1={24} y1={29} x2={28} y2={35} stroke="rgba(255,255,255,0.15)" strokeWidth={0.5} />
        <line x1={32} y1={30} x2={28} y2={35} stroke="rgba(255,255,255,0.15)" strokeWidth={0.5} />

        {/* Eye */}
        <circle cx={46} cy={28} r={4} fill="white" opacity={0.95} />
        <circle cx={46.5} cy={28} r={2.5} fill="#164e63" />
        <circle cx={47.5} cy={27} r={1} fill="rgba(255,255,255,0.8)" />
      </svg>

      {showText && (
        <span
          style={{
            fontSize: textSize || size * 0.45,
            fontWeight: 700,
            background: 'linear-gradient(135deg, #06b6d4 0%, #0891b2 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
            whiteSpace: 'nowrap',
          }}
        >
          Flowfish
        </span>
      )}
    </div>
  );
};

export default FlowfishLogo;
